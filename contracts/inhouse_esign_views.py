"""Inhouse e-sign endpoints (no third-party provider).

This module implements invite + magic-link signing + audit logging.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import Any
from uuid import UUID

from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

from PIL import Image
from pypdf import PdfReader, PdfWriter

from authentication.r2_service import R2StorageService

from .models import Contract, TemplateFile
from .models import InhouseSignatureContract, InhouseSigner, InhouseSigningAuditLog


def _client_ip(request) -> str | None:
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        parts = [p.strip() for p in str(xff).split(',') if p.strip()]
        if parts:
            return parts[0]
    ip = request.META.get('REMOTE_ADDR')
    return str(ip).strip() if ip else None


def _user_agent(request) -> str | None:
    ua = request.META.get('HTTP_USER_AGENT')
    return str(ua).strip() if ua else None


def _device_id(request) -> str | None:
    # Frontend can send a stable device id header (stored in localStorage).
    val = request.META.get('HTTP_X_DEVICE_ID')
    return str(val).strip() if val else None


def _log_event(
    *,
    signing_contract: InhouseSignatureContract,
    event: str,
    message: str,
    request,
    signer: InhouseSigner | None = None,
    extra: dict | None = None,
):
    InhouseSigningAuditLog.objects.create(
        inhouse_signature_contract=signing_contract,
        signer=signer,
        event=event,
        message=message,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        device_id=_device_id(request),
        extra=extra or {},
    )


def _strip_html(html: str) -> str:
    if not html:
        return ''
    text = re.sub(r'(?i)<\s*br\s*/?>', '\n', html)
    text = re.sub(r'(?i)</\s*(p|div|h\d|li)\s*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _get_editor_snapshot_from_r2(r2_key: str) -> dict | None:
    try:
        if not r2_key:
            return None
        r2 = R2StorageService()
        raw = r2.get_file_bytes(r2_key)
        if not raw:
            return None
        obj = json.loads(raw.decode('utf-8', errors='replace'))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _contract_export_text(contract: Contract) -> str:
    md = contract.metadata or {}

    try:
        r2_key = md.get('editor_r2_key')
        if isinstance(r2_key, str) and r2_key.strip():
            snap = _get_editor_snapshot_from_r2(r2_key.strip())
            if isinstance(snap, dict):
                txt = snap.get('rendered_text')
                if isinstance(txt, str) and txt.strip():
                    return txt
                html = snap.get('rendered_html')
                if isinstance(html, str) and html.strip():
                    return _strip_html(html)
    except Exception:
        pass

    txt = md.get('rendered_text')
    if isinstance(txt, str) and txt.strip():
        return txt
    html = md.get('rendered_html')
    if isinstance(html, str) and html.strip():
        return _strip_html(html)
    return ''


def _generate_contract_pdf_bytes(contract: Contract) -> bytes:
    text = _contract_export_text(contract)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER
    left = 0.75 * inch
    top = height - 0.75 * inch
    bottom = 0.75 * inch

    text_obj = c.beginText(left, top)
    text_obj.setFont('Times-Roman', 11)

    import textwrap

    max_chars = 110
    for line in (text or '').splitlines():
        wrapped_lines = (
            textwrap.wrap(
                line,
                width=max_chars,
                replace_whitespace=False,
                drop_whitespace=False,
            )
            or ['']
        )
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


@dataclass
class Placement:
    page_number: int
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float


def _resolve_signature_placement(contract: Contract, recipient_index: int, *, pdf_bytes: bytes | None = None) -> Placement:
    md = contract.metadata or {}
    template_filename = str(md.get('template_filename') or md.get('template') or '').strip()

    if template_filename:
        tf = TemplateFile.objects.filter(filename=template_filename).first()
        cfg = (tf.signature_fields_config or {}) if tf else {}
        fields = cfg.get('fields') if isinstance(cfg, dict) else None
        if isinstance(fields, list):
            for f in fields:
                if not isinstance(f, dict):
                    continue
                if str(f.get('type') or '').lower() != 'signature':
                    continue
                if int(f.get('recipient_index') or 0) != int(recipient_index):
                    continue
                pos = f.get('position') or {}
                if isinstance(pos, dict):
                    return Placement(
                        page_number=max(1, int(f.get('page_number') or 1)),
                        x_pct=float(pos.get('x') or 10),
                        y_pct=float(pos.get('y') or 80),
                        w_pct=float(pos.get('width') or 30),
                        h_pct=float(pos.get('height') or 8),
                    )

    # Default placement:
    # - Prefer the last page (most contracts place signature blocks at the end)
    # - Place in upper/mid area so it's visible (y_pct measured from top)
    page_number = 1
    try:
        if pdf_bytes:
            reader = PdfReader(BytesIO(pdf_bytes))
            if reader.pages:
                page_number = max(1, len(reader.pages))
    except Exception:
        page_number = 1

    y = 30 + int(recipient_index) * 12
    if y > 85:
        y = 85
    return Placement(page_number=page_number, x_pct=12, y_pct=float(y), w_pct=35, h_pct=10)


def _parse_data_url_png(data_url: str) -> bytes:
    raw = str(data_url or '').strip()
    if not raw.startswith('data:'):
        raise ValueError('Expected a data URL')
    header, _, b64 = raw.partition(',')
    if 'base64' not in header.lower():
        raise ValueError('Expected base64 data URL')
    payload = base64.b64decode(b64)
    # Normalize to PNG bytes
    img = Image.open(BytesIO(payload))
    out = BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()


def _stamp_signature_on_pdf(base_pdf: bytes, *, signature_png: bytes, placement: Placement) -> bytes:
    reader = PdfReader(BytesIO(base_pdf))
    writer = PdfWriter()

    page_index = max(0, int(placement.page_number) - 1)
    if page_index >= len(reader.pages):
        page_index = 0

    for idx, page in enumerate(reader.pages):
        if idx == page_index:
            page_w = float(page.mediabox.width)
            page_h = float(page.mediabox.height)

            box_x = page_w * (float(placement.x_pct) / 100.0)
            box_w = page_w * (float(placement.w_pct) / 100.0)

            box_h = page_h * (float(placement.h_pct) / 100.0)
            # y_pct is measured from top in the UI
            box_y_from_top = page_h * (float(placement.y_pct) / 100.0)
            box_y = page_h - box_y_from_top - box_h

            img = Image.open(BytesIO(signature_png))
            iw, ih = img.size
            if iw <= 0 or ih <= 0:
                raise ValueError('Invalid signature image')

            scale = min(box_w / float(iw), box_h / float(ih))
            draw_w = float(iw) * scale
            draw_h = float(ih) * scale
            draw_x = box_x + (box_w - draw_w) / 2.0
            draw_y = box_y + (box_h - draw_h) / 2.0

            overlay_buf = BytesIO()
            c = canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))
            c.drawImage(ImageReader(img), draw_x, draw_y, width=draw_w, height=draw_h, mask='auto')
            c.save()
            overlay_buf.seek(0)

            overlay_pdf = PdfReader(overlay_buf)
            page.merge_page(overlay_pdf.pages[0])

        writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _frontend_base_url(request) -> str:
    # Prefer explicit config; otherwise infer from request.
    base = getattr(settings, 'FRONTEND_BASE_URL', None)
    if isinstance(base, str) and base.strip():
        return base.strip().rstrip('/')

    inferred = request.build_absolute_uri('/')
    return inferred.strip().rstrip('/')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def inhouse_start(request):
    contract_id = request.data.get('contract_id')
    signers_data = request.data.get('signers', [])
    signing_order = str(request.data.get('signing_order') or 'sequential').strip() or 'sequential'
    expires_in_days = int(request.data.get('expires_in_days') or 30)

    if signing_order not in ('sequential', 'parallel'):
        return Response({'error': 'Invalid signing_order'}, status=status.HTTP_400_BAD_REQUEST)

    if not contract_id or not isinstance(signers_data, list) or len(signers_data) == 0:
        return Response({'error': 'contract_id and signers are required'}, status=status.HTTP_400_BAD_REQUEST)

    cleaned = []
    for s in signers_data:
        if not isinstance(s, dict):
            continue
        email = str(s.get('email') or '').strip()
        name = str(s.get('name') or '').strip()
        if not email or not name:
            continue
        cleaned.append({'email': email, 'name': name})

    if not cleaned:
        return Response({'error': 'At least one valid signer is required'}, status=status.HTTP_400_BAD_REQUEST)

    contract = get_object_or_404(Contract, id=contract_id, tenant_id=request.user.tenant_id)

    sc, _ = InhouseSignatureContract.objects.get_or_create(contract=contract)

    # Reset if already in a non-draft state.
    if sc.status in ('sent', 'in_progress', 'completed', 'declined', 'failed'):
        sc.status = 'draft'
        sc.executed_pdf = None
        sc.signing_request_data = {}
        sc.sent_at = None
        sc.completed_at = None
        sc.last_activity_at = None
        sc.save(update_fields=['status', 'executed_pdf', 'signing_request_data', 'sent_at', 'completed_at', 'last_activity_at', 'updated_at'])
        sc.signers.all().delete()

    sc.status = 'sent'
    sc.signing_order = signing_order
    sc.sent_at = timezone.now()
    sc.expires_at = timezone.now() + timedelta(days=max(1, expires_in_days))
    sc.last_activity_at = timezone.now()
    sc.signing_request_data = {
        'signers': cleaned,
        'signing_order': signing_order,
        'expires_in_days': expires_in_days,
        'provider': 'inhouse',
    }
    sc.save()
    invite_urls = []

    for idx, signer_info in enumerate(cleaned):
        signer = InhouseSigner.objects.create(
            inhouse_signature_contract=sc,
            email=signer_info['email'],
            name=signer_info['name'],
            recipient_index=idx,
            signing_order=(idx + 1) if signing_order == 'sequential' else 0,
            token_expires_at=sc.expires_at,
        )

        url = f"/sign/inhouse?token={signer.access_token}"
        invite_urls.append({'email': signer.email, 'name': signer.name, 'signing_url': url})
        _log_event(
            signing_contract=sc,
            event='invite_sent',
            message=f"Invitation created for {signer.email}",
            request=request,
            signer=signer,
        )

    first_url = invite_urls[0]['signing_url'] if invite_urls else None

    return Response(
        {
            'success': True,
            'contract_id': str(contract.id),
            'status': sc.status,
            'signing_order': sc.signing_order,
            'expires_at': sc.expires_at.isoformat() if sc.expires_at else None,
            'signing_url': first_url,
            'invite_urls': invite_urls,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inhouse_status(request, contract_id: str):
    contract = get_object_or_404(Contract, id=contract_id, tenant_id=request.user.tenant_id)
    sc = get_object_or_404(InhouseSignatureContract, contract=contract)

    signers_response = []
    for signer in sc.signers.all().order_by('recipient_index', 'email'):
        signers_response.append(
            {
                'email': signer.email,
                'name': signer.name,
                'status': signer.status,
                'signed_at': signer.signed_at.isoformat() if signer.signed_at else None,
                'has_signed': signer.has_signed,
                'recipient_index': signer.recipient_index,
            }
        )

    all_signed = bool(signers_response) and all(s.get('has_signed') for s in signers_response)

    _log_event(
        signing_contract=sc,
        event='status_checked',
        message='Status checked',
        request=request,
        extra={'all_signed': all_signed},
    )

    return Response(
        {
            'success': True,
            'contract_id': str(contract.id),
            'status': sc.status,
            'signers': signers_response,
            'all_signed': all_signed,
            'expires_at': sc.expires_at.isoformat() if sc.expires_at else None,
            'last_checked': timezone.now().isoformat(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inhouse_download_executed(request, contract_id: str):
    contract = get_object_or_404(Contract, id=contract_id, tenant_id=request.user.tenant_id)
    sc = get_object_or_404(InhouseSignatureContract, contract=contract)

    if sc.status != 'completed' or not sc.executed_pdf:
        return Response({'error': 'Contract not yet completed'}, status=status.HTTP_400_BAD_REQUEST)

    _log_event(
        signing_contract=sc,
        event='document_downloaded',
        message='Executed document downloaded',
        request=request,
    )

    filename = f"{(contract.title or 'contract').strip().replace(' ', '_')}_signed.pdf"
    return FileResponse(
        BytesIO(sc.executed_pdf),
        as_attachment=True,
        filename=filename,
        content_type='application/pdf',
    )


@api_view(['GET'])
@permission_classes([AllowAny])
def inhouse_session(request, token: UUID):
    signer = get_object_or_404(InhouseSigner, access_token=token)
    sc = signer.inhouse_signature_contract

    if signer.token_expires_at and signer.token_expires_at <= timezone.now():
        return Response({'error': 'Signing link expired'}, status=status.HTTP_410_GONE)

    if signer.status == 'invited':
        signer.status = 'viewed'
        signer.last_viewed_at = timezone.now()
        signer.save(update_fields=['status', 'last_viewed_at', 'updated_at'])

    if sc.status == 'sent':
        sc.status = 'in_progress'
        sc.last_activity_at = timezone.now()
        sc.save(update_fields=['status', 'last_activity_at', 'updated_at'])

    _log_event(
        signing_contract=sc,
        event='link_viewed',
        message=f"Signing link viewed by {signer.email}",
        request=request,
        signer=signer,
    )

    contract = sc.contract
    pdf_bytes = sc.executed_pdf or _generate_contract_pdf_bytes(contract)
    placement = _resolve_signature_placement(contract, signer.recipient_index, pdf_bytes=pdf_bytes)

    return Response(
        {
            'success': True,
            'contract_id': str(contract.id),
            'contract_title': contract.title,
            'status': sc.status,
            'signer': {
                'email': signer.email,
                'name': signer.name,
                'recipient_index': signer.recipient_index,
                'status': signer.status,
            },
            'pdf_url': f"/api/v1/inhouse/esign/pdf/{signer.access_token}/",
            'placement': {
                'recipient_index': signer.recipient_index,
                'page_number': placement.page_number,
                'position': {
                    'x': placement.x_pct,
                    'y': placement.y_pct,
                    'width': placement.w_pct,
                    'height': placement.h_pct,
                },
            },
        },
        status=status.HTTP_200_OK,
    )


@xframe_options_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def inhouse_pdf(request, token: UUID):
    signer = get_object_or_404(InhouseSigner, access_token=token)
    sc = signer.inhouse_signature_contract

    if signer.token_expires_at and signer.token_expires_at <= timezone.now():
        return Response({'error': 'Signing link expired'}, status=status.HTTP_410_GONE)

    contract = sc.contract
    pdf_bytes = sc.executed_pdf or _generate_contract_pdf_bytes(contract)

    resp = FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=False,
        filename=f"{(contract.title or 'contract').strip().replace(' ', '_')}.pdf",
        content_type='application/pdf',
    )

    # Avoid stale iframe renders (especially after signing) by disabling caching.
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'

    # Allow the signer frontend (often on a different origin in dev/prod)
    # to embed the PDF in an iframe.
    resp.xframe_options_exempt = True
    return resp


@api_view(['POST'])
@permission_classes([AllowAny])
def inhouse_sign(request, token: UUID):
    signer = get_object_or_404(InhouseSigner, access_token=token)
    sc = signer.inhouse_signature_contract

    if signer.token_expires_at and signer.token_expires_at <= timezone.now():
        return Response({'error': 'Signing link expired'}, status=status.HTTP_410_GONE)

    if signer.has_signed:
        return Response({'error': 'Already signed'}, status=status.HTTP_400_BAD_REQUEST)

    if sc.signing_order == 'sequential':
        next_signer = (
            sc.signers.filter(has_signed=False)
            .exclude(status='declined')
            .order_by('signing_order', 'recipient_index')
            .first()
        )
        if next_signer and next_signer.id != signer.id:
            _log_event(
                signing_contract=sc,
                event='error',
                message='Signer attempted to sign out of order',
                request=request,
                signer=signer,
                extra={'expected_signer_email': next_signer.email},
            )
            return Response({'error': 'Not your turn to sign'}, status=status.HTTP_403_FORBIDDEN)

    signature_data_url = request.data.get('signature_data_url')
    if not signature_data_url:
        return Response({'error': 'signature_data_url is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        png = _parse_data_url_png(signature_data_url)
    except Exception as e:
        return Response({'error': f'Invalid signature image: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    contract = sc.contract

    base_pdf = sc.executed_pdf or _generate_contract_pdf_bytes(contract)
    placement = _resolve_signature_placement(contract, signer.recipient_index, pdf_bytes=base_pdf)

    try:
        next_pdf = _stamp_signature_on_pdf(base_pdf, signature_png=png, placement=placement)
    except Exception as e:
        _log_event(
            signing_contract=sc,
            event='error',
            message=f"Failed to stamp signature: {str(e)}",
            request=request,
            signer=signer,
        )
        return Response({'error': 'Failed to apply signature'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    signer.signature_png = png
    signer.signature_mime = 'image/png'
    signer.status = 'signed'
    signer.has_signed = True
    signer.signed_at = timezone.now()
    signer.signed_ip_address = _client_ip(request)
    signer.signed_user_agent = _user_agent(request)
    signer.signed_device_id = _device_id(request)
    signer.save()

    sc.executed_pdf = next_pdf
    sc.last_activity_at = timezone.now()

    # Check completion
    remaining = sc.signers.filter(has_signed=False).count()
    if remaining == 0:
        sc.status = 'completed'
        sc.completed_at = timezone.now()
        try:
            contract.status = 'executed'
            contract.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass

    sc.save()

    _log_event(
        signing_contract=sc,
        event='signing_completed',
        message=f"Signer completed: {signer.email}",
        request=request,
        signer=signer,
        extra={
            'recipient_index': signer.recipient_index,
            'page_number': placement.page_number,
            'position': {
                'x': placement.x_pct,
                'y': placement.y_pct,
                'width': placement.w_pct,
                'height': placement.h_pct,
            },
        },
    )

    return Response(
        {
            'success': True,
            'contract_id': str(contract.id),
            'status': sc.status,
            'all_signed': remaining == 0,
        },
        status=status.HTTP_200_OK,
    )
