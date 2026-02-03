import logging
from io import BytesIO
from datetime import timedelta
import os
import hashlib

import re
import textwrap

from django.core.files.base import ContentFile
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contracts.firma_service import FirmaAPIService, FirmaApiError
from contracts.models import Contract, ContractVersion, FirmaSignatureContract, FirmaSigner, FirmaSigningAuditLog
from authentication.r2_service import R2StorageService

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    if not html:
        return ''
    text = re.sub(r'(?i)<\s*br\s*/?>', '\n', html)
    text = re.sub(r'(?i)</\s*(p|div|h\d|li)\s*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _contract_export_text(contract: Contract) -> str:
    md = contract.metadata or {}
    txt = md.get('rendered_text')
    if isinstance(txt, str) and txt.strip():
        return txt
    html = md.get('rendered_html')
    if isinstance(html, str) and html.strip():
        return _strip_html(html)
    return ''


def _generate_contract_pdf_bytes(contract: Contract) -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch

    text = _contract_export_text(contract)
    if not text:
        text = (contract.title or 'Contract').strip() or 'Contract'

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER
    left = 0.75 * inch
    top = height - 0.75 * inch
    bottom = 0.75 * inch

    text_obj = c.beginText(left, top)
    text_obj.setFont('Times-Roman', 11)

    max_chars = 110
    for line in (text or '').splitlines():
        wrapped_lines = textwrap.wrap(
            line,
            width=max_chars,
            replace_whitespace=False,
            drop_whitespace=False,
        ) or ['']
        for wl in wrapped_lines:
            if text_obj.getY() <= bottom:
                c.drawText(text_obj)
                c.showPage()
                text_obj = c.beginText(left, top)
                text_obj.setFont('Times-Roman', 11)
            text_obj.textLine(wl)

    c.drawText(text_obj)
    c.save()
    buffer.seek(0)
    return buffer.read()


def _resolve_contract_pdf_r2_key(contract: Contract) -> str | None:
    """Best-effort resolve of the latest stored PDF in R2."""
    try:
        latest = contract.versions.latest('version_number')
        if latest and latest.r2_key:
            return latest.r2_key
    except ContractVersion.DoesNotExist:
        pass
    except Exception:
        pass

    key = getattr(contract, 'document_r2_key', None)
    if key:
        return str(key).strip()
    return None


def _get_contract_pdf_bytes_from_r2(*, contract: Contract, force_refresh: bool = False) -> tuple[bytes, str]:
    """Return (pdf_bytes, r2_key).

    When force_refresh=True, always regenerates the PDF from the latest stored
    editor content and uploads it to R2, updating contract.document_r2_key.
    """
    r2 = R2StorageService()

    if not force_refresh:
        r2_key = _resolve_contract_pdf_r2_key(contract)
        if r2_key:
            pdf_bytes = r2.get_file_bytes(r2_key)
            if pdf_bytes:
                return pdf_bytes, r2_key

    pdf_bytes = _generate_contract_pdf_bytes(contract)
    safe_title = (contract.title or 'Contract').strip().replace(' ', '_') or 'Contract'
    ts = int(timezone.now().timestamp())
    filename = f"{safe_title}_{contract.id}_{ts}.pdf"
    uploaded_key = r2.upload_file(ContentFile(pdf_bytes, name=filename), contract.tenant_id, filename)

    # Persist the latest PDF location so subsequent operations use the real document.
    contract.document_r2_key = uploaded_key
    contract.save(update_fields=['document_r2_key', 'updated_at'])
    return pdf_bytes, uploaded_key


def _get_firma_service() -> FirmaAPIService:
    return FirmaAPIService()


def _clean_signers(signers):
    cleaned = []
    if not isinstance(signers, list):
        return cleaned
    for s in signers:
        email = str((s or {}).get('email') or '').strip()
        name = str((s or {}).get('name') or '').strip()
        if not email or not name:
            continue
        cleaned.append({'email': email, 'name': name})
    return cleaned


def _ensure_uploaded(*, contract: Contract, document_name: str, signers=None, signing_order: str = 'sequential') -> FirmaSignatureContract:
    """Upload contract to Firma.
    
    Note: Firma requires recipients at creation time, so signers should be provided upfront.
    If signers are not provided, document is uploaded with empty recipients array.
    """
    if hasattr(contract, 'firma_signature_contract'):
        return contract.firma_signature_contract

    try:
        # Always regenerate+upload the latest PDF when starting a signing flow.
        # This prevents sending stale/blank documents if an older PDF was previously cached in R2.
        pdf_bytes, source_r2_key = _get_contract_pdf_bytes_from_r2(contract=contract, force_refresh=True)
    except Exception as e:
        logger.error('Failed to read contract PDF: %s', e, exc_info=True)
        raise RuntimeError('Failed to read contract file') from e

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    # Convert signers to Firma format for upload
    recipients = []
    if signers:
        cleaned = _clean_signers(signers)
        for idx, signer in enumerate(cleaned):
            name_parts = signer.get('name', '').strip().split(maxsplit=1)
            first_name = name_parts[0] if name_parts else 'Signer'
            last_name = name_parts[1] if len(name_parts) > 1 else 'Signer'
            
            recipient = {
                'first_name': first_name,
                'last_name': last_name,
                'email': signer.get('email', ''),
                'designation': 'Signer',
                'order': idx + 1 if signing_order == 'sequential' else 0,
            }
            recipients.append(recipient)

    service = _get_firma_service()
    logger.info(f"Uploading contract to Firma with {len(recipients)} recipients")
    upload_res = service.upload_document(pdf_bytes, str(document_name), recipients=recipients if recipients else None)
    firma_document_id = str(upload_res.get('id') or '').strip()
    if not firma_document_id:
        raise FirmaApiError('Firma did not return a document id')

    record = FirmaSignatureContract.objects.create(
        contract=contract,
        firma_document_id=firma_document_id,
        status='draft',
        signing_order=signing_order,
        original_r2_key=source_r2_key,
        signing_request_data={
            'document_name': str(document_name),
            'recipients_count': len(recipients),
            'pdf_sha256': pdf_sha256,
            'pdf_bytes_len': len(pdf_bytes),
        },
    )

    FirmaSigningAuditLog.objects.create(
        firma_signature_contract=record,
        event='upload',
        message=f'Document uploaded to Firma with {len(recipients)} recipients: {firma_document_id}',
        new_status='draft',
        firma_response=upload_res,
    )

    return record


def _ensure_sent(*, record: FirmaSignatureContract, signers, signing_order: str, expires_in_days: int) -> None:
    if record.status == 'completed':
        raise ValueError('Contract is already completed')

    cleaned = _clean_signers(signers)
    if not cleaned:
        raise ValueError('At least one signer with name+email is required')

    service = _get_firma_service()
    invite_res = service.create_invite(record.firma_document_id, cleaned, signing_order=signing_order)

    for idx, signer in enumerate(cleaned):
        FirmaSigner.objects.update_or_create(
            firma_signature_contract=record,
            email=signer['email'],
            defaults={
                'name': signer['name'],
                'signing_order': (idx + 1) if signing_order == 'sequential' else 0,
                'status': 'invited',
                'has_signed': False,
                'signed_at': None,
                'signing_url': None,
                'signing_url_expires_at': None,
            },
        )

    record.status = 'sent'
    record.signing_order = signing_order
    record.sent_at = timezone.now()
    record.expires_at = timezone.now() + timedelta(days=expires_in_days)
    record.signing_request_data = {
        'signers': cleaned,
        'signing_order': signing_order,
        'expires_in_days': expires_in_days,
    }
    record.save()

    FirmaSigningAuditLog.objects.create(
        firma_signature_contract=record,
        event='invite_sent',
        message=f'Invitations sent to {len(cleaned)} signer(s)',
        old_status='draft',
        new_status='sent',
        firma_response=invite_res,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def firma_upload_contract(request):
    """Upload contract PDF to Firma.

    Request:
    {
      "contract_id": "uuid",
      "document_name": "Optional name",
      "signers": [{"name": "John Doe", "email": "john@example.com"}, ...],
      "signing_order": "sequential" or "parallel"
    }
    """
    contract_id = request.data.get('contract_id')
    if not contract_id:
        return Response({'error': 'contract_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    contract = get_object_or_404(Contract, id=contract_id)

    document_name = request.data.get('document_name') or getattr(contract, 'title', 'Contract')
    signers = request.data.get('signers') or []
    signing_order = request.data.get('signing_order') or 'sequential'
    force = bool(request.data.get('force') or request.data.get('reset'))
    
    logger.info(
        "Firma upload starting: contract_id=%s, document_name=%s, signers=%s, signing_order=%s, force=%s",
        contract_id,
        document_name,
        len(signers) if isinstance(signers, list) else 'invalid',
        signing_order,
        force,
    )

    try:
        # If a record already exists, don't immediately fail. Old records may have been
        # created without recipients (Firma requires recipients at creation time).
        if hasattr(contract, 'firma_signature_contract'):
            existing = contract.firma_signature_contract

            should_reset = force
            cleaned = _clean_signers(signers)

            # Always refresh the latest PDF into R2 when the user presses the signing button.
            # Then decide whether the vendor signing request must be reset (re-upload) to match.
            latest_pdf_bytes = None
            latest_pdf_sha = None
            latest_source_r2_key = None
            if cleaned:
                try:
                    latest_pdf_bytes, latest_source_r2_key = _get_contract_pdf_bytes_from_r2(contract=contract, force_refresh=True)
                    latest_pdf_sha = hashlib.sha256(latest_pdf_bytes).hexdigest()
                except Exception:
                    # If we can't regenerate the PDF, don't reset; let downstream errors surface.
                    pass

            if not should_reset and cleaned:
                recipients_count = None
                previous_pdf_sha = None
                try:
                    if isinstance(existing.signing_request_data, dict):
                        recipients_count = existing.signing_request_data.get('recipients_count')
                        previous_pdf_sha = existing.signing_request_data.get('pdf_sha256')
                except Exception:
                    recipients_count = None
                    previous_pdf_sha = None

                # Heuristics for an auto-reset:
                # - previous upload had 0 recipients recorded, OR
                # - record is in a terminal/bad state, OR
                # - contract content changed since last upload (prevents blank/stale vendor PDFs)
                if recipients_count == 0 or existing.status in ('declined', 'failed'):
                    should_reset = True
                elif previous_pdf_sha is None and latest_pdf_sha is not None:
                    # Legacy signing requests (created before pdf_sha256 tracking) are risky:
                    # they may point to a stale/blank vendor document. Reset once to guarantee
                    # the vendor is using the latest PDF.
                    should_reset = True
                elif previous_pdf_sha and latest_pdf_sha and previous_pdf_sha != latest_pdf_sha:
                    should_reset = True
                else:
                    # Optional vendor check: avoid resetting finished requests.
                    try:
                        service = _get_firma_service()
                        status_info = service.get_document_status(existing.firma_document_id)
                        if bool(status_info.get('is_completed')):
                            should_reset = False
                    except Exception:
                        pass

            if not should_reset:
                return Response(
                    {
                        'success': True,
                        'already_uploaded': True,
                        'contract_id': str(contract_id),
                        'firma_document_id': existing.firma_document_id,
                        'status': existing.status,
                        'message': 'Contract already uploaded for Firma signing',
                    },
                    status=status.HTTP_200_OK,
                )

            # Reset/re-upload in-place (keeps OneToOne relationship stable)
            if latest_pdf_bytes is not None and latest_source_r2_key:
                pdf_bytes, source_r2_key = latest_pdf_bytes, latest_source_r2_key
            else:
                pdf_bytes, source_r2_key = _get_contract_pdf_bytes_from_r2(contract=contract, force_refresh=True)

            # Convert signers to Firma recipients
            recipients = []
            for idx, signer in enumerate(cleaned):
                name_parts = signer.get('name', '').strip().split(maxsplit=1)
                first_name = name_parts[0] if name_parts else 'Signer'
                last_name = name_parts[1] if len(name_parts) > 1 else 'Signer'

                recipients.append(
                    {
                        'first_name': first_name,
                        'last_name': last_name,
                        'email': signer.get('email', ''),
                        'designation': 'Signer',
                        'order': idx + 1 if signing_order == 'sequential' else 0,
                    }
                )

            if not recipients:
                return Response(
                    {
                        'error': 'signers are required to reset/re-upload an existing Firma signing request',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            service = _get_firma_service()
            old_document_id = existing.firma_document_id
            upload_res = service.upload_document(pdf_bytes, str(document_name), recipients=recipients)
            new_document_id = str(upload_res.get('id') or '').strip()
            if not new_document_id:
                raise FirmaApiError('Firma did not return a document id')

            pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

            # Clear local signer records and reset status
            existing.signers.all().delete()
            existing.firma_document_id = new_document_id
            existing.status = 'draft'
            existing.signing_order = signing_order
            existing.sent_at = None
            existing.completed_at = None
            existing.expires_at = None
            existing.last_status_check_at = None
            existing.executed_r2_key = None
            existing.original_r2_key = source_r2_key
            existing.signing_request_data = {
                'document_name': str(document_name),
                'recipients_count': len(recipients),
                'reset_from_firma_document_id': old_document_id,
                'pdf_sha256': pdf_sha256,
                'pdf_bytes_len': len(pdf_bytes),
            }
            existing.save()

            FirmaSigningAuditLog.objects.create(
                firma_signature_contract=existing,
                event='upload',
                message=(
                    f'Document re-uploaded to Firma (reset). Old: {old_document_id} -> New: {new_document_id} '
                    f'with {len(recipients)} recipients'
                ),
                old_status='draft',
                new_status='draft',
                firma_response=upload_res,
            )

            record = existing
        else:
            record = _ensure_uploaded(contract=contract, document_name=str(document_name), signers=signers, signing_order=signing_order)
        
        logger.info(f"Firma upload succeeded: contract_id={contract_id}, firma_document_id={record.firma_document_id}")

        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'firma_document_id': record.firma_document_id,
                'status': record.status,
                'signers_added': len(signers),
                'message': 'Contract uploaded successfully' + (f' with {len(signers)} signers' if signers else ''),
            },
            status=status.HTTP_201_CREATED,
        )

    except FirmaApiError as e:
        logger.error(f"Firma API error during upload: {str(e)} | Status: {e.status_code} | Response: {e.response_text}")
        return Response(
            {
                'error': str(e),
                'details': e.response_text,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as e:
        logger.error('Firma upload failed: %s', e, exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def firma_send_for_signature(request):
    """Send a Firma document for signature."""

    contract_id = request.data.get('contract_id')
    signers = request.data.get('signers') or []
    signing_order = request.data.get('signing_order') or 'sequential'
    expires_in_days = int(request.data.get('expires_in_days') or 30)

    if not contract_id or not isinstance(signers, list) or len(signers) == 0:
        return Response({'error': 'contract_id and signers are required'}, status=status.HTTP_400_BAD_REQUEST)

    record = get_object_or_404(FirmaSignatureContract, contract_id=contract_id)
    if record.status == 'completed':
        return Response({'error': 'Contract already completed'}, status=status.HTTP_400_BAD_REQUEST)

    cleaned = _clean_signers(signers)
    if not cleaned:
        return Response({'error': 'At least one signer with name+email is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        _ensure_sent(record=record, signers=cleaned, signing_order=signing_order, expires_in_days=expires_in_days)

        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'status': record.status,
                'signers_invited': len(cleaned),
                'expires_at': record.expires_at.isoformat() if record.expires_at else None,
                'message': 'Invitations sent successfully',
            },
            status=status.HTTP_200_OK,
        )

    except FirmaApiError as e:
        FirmaSigningAuditLog.objects.create(
            firma_signature_contract=record,
            event='error',
            message=f'Firma invite failed: {e}',
            old_status=record.status,
            new_status='failed',
            firma_response={'details': e.response_text},
        )
        record.status = 'failed'
        record.save(update_fields=['status'])
        return Response({'error': str(e), 'details': e.response_text}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Firma send failed: %s', e, exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def firma_get_signing_url(request, contract_id: str):
    signer_email = request.query_params.get('signer_email')
    if not signer_email:
        return Response({'error': 'signer_email query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

    record = get_object_or_404(FirmaSignatureContract, contract_id=contract_id)
    signer = get_object_or_404(FirmaSigner, firma_signature_contract=record, email=signer_email)

    try:
        if not signer.signing_url or (signer.signing_url_expires_at and signer.signing_url_expires_at <= timezone.now()):
            service = _get_firma_service()
            link_res = service.get_signing_link(record.firma_document_id, signer_email)
            signer.signing_url = str(link_res.get('signing_link') or '').strip() or None
            signer.signing_url_expires_at = timezone.now() + timedelta(hours=24)
            signer.save(update_fields=['signing_url', 'signing_url_expires_at', 'updated_at'])

        if not signer.signing_url:
            return Response(
                {
                    'error': 'Failed to generate a signing URL. Re-upload with signers and re-send invites.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'success': True,
                'signing_url': signer.signing_url,
                'signer_email': signer_email,
                'expires_at': signer.signing_url_expires_at.isoformat() if signer.signing_url_expires_at else None,
            },
            status=status.HTTP_200_OK,
        )

    except FirmaApiError as e:
        # Most common: old signing request created without recipients.
        # Return 400 so the client can trigger a reset/re-upload flow.
        return Response(
            {
                'error': str(e),
                'details': e.response_text,
                'needs_reupload': True,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.error('Firma signing url failed: %s', e, exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def firma_check_status(request, contract_id: str):
    record = get_object_or_404(FirmaSignatureContract, contract_id=contract_id)

    try:
        service = _get_firma_service()
        status_info = service.get_document_status(record.firma_document_id)

        old = record.status
        new_status = str(status_info.get('status') or record.status)
        raw_status = status_info.get('raw_status')
        is_completed = bool(status_info.get('is_completed') or new_status == 'completed')

        # Persist the raw vendor status in JSON (safe for long strings)
        try:
            data = record.signing_request_data if isinstance(record.signing_request_data, dict) else {}
            if raw_status:
                data['firma_raw_status'] = raw_status
            record.signing_request_data = data
        except Exception:
            # Best-effort only; don't fail status polling due to JSON issues
            pass

        if is_completed:
            record.status = 'completed'
            if not record.completed_at:
                record.completed_at = timezone.now()

            # Best-effort signer state sync. In mock mode, the API doesn't return signer details,
            # so we mark all invited signers as signed when the document completes.
            now = timezone.now()
            for signer in record.signers.all():
                if not signer.has_signed:
                    signer.has_signed = True
                    signer.status = 'signed'
                    signer.signed_at = signer.signed_at or now
                    signer.save(update_fields=['has_signed', 'status', 'signed_at', 'updated_at'])
        else:
            record.status = new_status

        record.last_status_check_at = timezone.now()
        record.save(update_fields=['status', 'completed_at', 'last_status_check_at', 'updated_at', 'signing_request_data'])

        if old != record.status:
            FirmaSigningAuditLog.objects.create(
                firma_signature_contract=record,
                event='status_checked',
                message=f'Status changed from {old} to {record.status}',
                old_status=old,
                new_status=record.status,
                firma_response=status_info,
            )

        signers_resp = []
        for s in record.signers.all():
            signers_resp.append(
                {
                    'email': s.email,
                    'name': s.name,
                    'status': s.status,
                    'signed_at': s.signed_at.isoformat() if s.signed_at else None,
                    'has_signed': s.has_signed,
                }
            )

        all_signed = all(x['has_signed'] for x in signers_resp) if signers_resp else False

        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'status': record.status,
                'signers': signers_resp,
                'all_signed': all_signed,
                'last_checked': record.last_status_check_at.isoformat() if record.last_status_check_at else None,
            },
            status=status.HTTP_200_OK,
        )

    except FirmaApiError as e:
        # Return cached status if vendor is down
        logger.warning('Firma status poll failed, returning cached: %s', e)
        signers_resp = []
        for s in record.signers.all():
            signers_resp.append(
                {
                    'email': s.email,
                    'name': s.name,
                    'status': s.status,
                    'signed_at': s.signed_at.isoformat() if s.signed_at else None,
                    'has_signed': s.has_signed,
                }
            )
        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'status': record.status,
                'signers': signers_resp,
                'all_signed': all(x['has_signed'] for x in signers_resp) if signers_resp else False,
                'last_checked': record.last_status_check_at.isoformat() if record.last_status_check_at else None,
                'warning': str(e),
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.error('Firma status check failed: %s', e, exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def firma_get_executed_document(request, contract_id: str):
    record = get_object_or_404(FirmaSignatureContract, contract_id=contract_id)

    # If not completed, ask client to poll.
    if record.status != 'completed':
        return Response(
            {
                'error': 'Contract not yet completed by all signers',
                'current_status': record.status,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    r2 = R2StorageService()

    # Try vendor download; if unavailable (mock mode), fall back to original.
    try:
        service = _get_firma_service()
        pdf_bytes = service.download_document(record.firma_document_id)
    except Exception:
        pdf_bytes = b''

    if not pdf_bytes:
        try:
            pdf_bytes = r2.get_file_bytes(record.original_r2_key)
        except Exception as e:
            logger.error('Failed to read stored PDF from R2: %s', e, exc_info=True)
            return Response({'error': 'Failed to retrieve executed document'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not record.executed_r2_key and pdf_bytes:
        filename = f"firma_executed_{contract_id}.pdf"
        r2_key = r2.upload_file(ContentFile(pdf_bytes, name=filename), record.contract.tenant_id, filename)
        record.executed_r2_key = r2_key
        record.save(update_fields=['executed_r2_key', 'updated_at'])

    FirmaSigningAuditLog.objects.create(
        firma_signature_contract=record,
        event='document_downloaded',
        message='Executed document downloaded',
        new_status='completed',
        firma_response={},
    )

    pdf_file = BytesIO(pdf_bytes)
    pdf_file.seek(0)
    filename = f"signed_contract_{contract_id}.pdf"
    return FileResponse(pdf_file, as_attachment=True, filename=filename, content_type='application/pdf')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def firma_sign(request):
    """Convenience endpoint: upload (if needed) + send invites (if needed) + return signing URL for the first signer."""

    contract_id = request.data.get('contract_id')
    signers = request.data.get('signers') or []
    signing_order = request.data.get('signing_order') or 'sequential'
    expires_in_days = int(request.data.get('expires_in_days') or 30)

    if not contract_id:
        return Response({'error': 'contract_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    cleaned = _clean_signers(signers)
    if not cleaned:
        return Response({'error': 'At least one signer with name+email is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        contract = get_object_or_404(Contract, id=contract_id)
        document_name = request.data.get('document_name') or getattr(contract, 'title', 'Contract')

        record = _ensure_uploaded(contract=contract, document_name=str(document_name))
        _ensure_sent(record=record, signers=cleaned, signing_order=signing_order, expires_in_days=expires_in_days)

        signer_email = cleaned[0]['email']
        signer = FirmaSigner.objects.get(firma_signature_contract=record, email=signer_email)
        if not signer.signing_url or (signer.signing_url_expires_at and signer.signing_url_expires_at <= timezone.now()):
            service = _get_firma_service()
            link_res = service.get_signing_link(record.firma_document_id, signer_email)
            signer.signing_url = str(link_res.get('signing_link') or '').strip() or None
            signer.signing_url_expires_at = timezone.now() + timedelta(hours=24)
            signer.save(update_fields=['signing_url', 'signing_url_expires_at', 'updated_at'])

        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'firma_document_id': record.firma_document_id,
                'status': record.status,
                'signing_url': signer.signing_url,
                'signer_email': signer_email,
                'expires_at': signer.signing_url_expires_at.isoformat() if signer.signing_url_expires_at else None,
            },
            status=status.HTTP_200_OK,
        )
    except FirmaApiError as e:
        return Response({'error': str(e), 'details': e.response_text}, status=status.HTTP_502_BAD_GATEWAY)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Firma sign failed: %s', e, exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def firma_debug_config(request):
    """Debug endpoint: Show Firma configuration (sanitized)."""
    api_key = (os.getenv('FIRMA_API') or '').strip()
    base_url = (os.getenv('FIRMA_BASE_URL') or '').strip()
    mock_mode = (os.getenv('FIRMA_MOCK') or '').strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    
    return Response({
        'FIRMA_API': f"{api_key[:20]}...{api_key[-8:]}" if len(api_key) > 30 else "***",
        'FIRMA_API_LENGTH': len(api_key),
        'FIRMA_BASE_URL': base_url,
        'FIRMA_MOCK': mock_mode,
        'FIRMA_MOCK_ENV': os.getenv('FIRMA_MOCK'),
        'all_firma_env_keys': [k for k in os.environ.keys() if 'FIRMA' in k],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def firma_debug_connectivity(request):
    """Debug endpoint: Test Firma API connectivity."""
    try:
        service = _get_firma_service()
        
        # Test configuration
        if service.config.base_url.endswith('example.invalid'):
            return Response({
                'status': 'not_configured',
                'message': 'FIRMA_BASE_URL is not set to a real endpoint',
                'config': {
                    'base_url': service.config.base_url,
                    'api_key_set': bool(service.config.api_key),
                    'mock_mode': service.config.mock_mode,
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Try a simple GET to status endpoint (if available)
        logger.info(f"Testing Firma connectivity to {service.config.base_url}")
        status_path = service.config.status_path.format(document_id='test-connectivity')
        url = service._url(status_path)
        
        logger.info(f"Attempting GET {url}")
        headers = service._headers()
        
        import requests
        resp = requests.get(url, headers=headers, timeout=10)
        
        return Response({
            'status': 'success' if resp.status_code < 500 else 'error',
            'http_status': resp.status_code,
            'url_tested': url,
            'response_preview': resp.text[:500],
            'config': {
                'base_url': service.config.base_url,
                'api_key_set': bool(service.config.api_key),
                'mock_mode': service.config.mock_mode,
            }
        })
        
    except Exception as e:
        logger.error(f"Firma connectivity test failed: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
        }, status=status.HTTP_502_BAD_GATEWAY)

