import logging
from io import BytesIO
from datetime import timedelta
import os
import hashlib
import json


import re
import textwrap


from django.core.files.base import ContentFile
from django.core.mail import send_mail
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

from django.conf import settings


logger = logging.getLogger(__name__)


def _safe_template_filename(name: str) -> str | None:
   base = os.path.basename(str(name or '').strip())
   base = base.replace('\\', '').replace('/', '')
   if not base:
       return None
   if not base.lower().endswith('.txt'):
       base = f'{base}.txt'
   return base


def _read_template_file_signature_config(*, template_filename: str) -> dict | None:
   """Read signature_fields_config from filesystem template meta json."""
   safe = _safe_template_filename(template_filename)
   if not safe:
       return None

   try:
       template_path = os.path.join(settings.BASE_DIR, 'templates', safe)
       meta_path = f'{template_path}.meta.json'
       if not os.path.exists(meta_path):
           return None
       with open(meta_path, 'r', encoding='utf-8') as f:
           meta = json.load(f) or {}
       if not isinstance(meta, dict):
           return None
       cfg = meta.get('signature_fields_config')
       if isinstance(cfg, dict) and isinstance(cfg.get('fields'), list):
           return cfg
   except Exception:
       return None
   return None




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




def _get_contract_pdf_bytes_from_r2(*, contract: Contract, force_refresh: bool = False) -> tuple[bytes, str | None]:
   """Return (pdf_bytes, r2_key).

   If Cloudflare R2 is not configured, falls back to generating the PDF in-memory
   and returns (pdf_bytes, None).

   When force_refresh=True and R2 is configured, regenerates the PDF from the latest
   stored editor content and uploads it to R2, updating contract.document_r2_key.
   """

   r2: R2StorageService | None = None
   try:
       r2 = R2StorageService()
   except Exception:
       r2 = None

   if r2 is not None and not force_refresh:
       r2_key = _resolve_contract_pdf_r2_key(contract)
       if r2_key:
           pdf_bytes = r2.get_file_bytes(r2_key)
           if pdf_bytes:
               return pdf_bytes, r2_key

   pdf_bytes = _generate_contract_pdf_bytes(contract)

   if r2 is None:
       return pdf_bytes, None

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




def _get_signature_field_config(contract: Contract) -> dict:
   """Get signature field configuration for a contract.
  
   Returns a dict with field templates that define where signatures should be placed.
   Priority order:
   1. Contract-specific metadata (contract.metadata.signature_fields_config)
   2. Template defaults (if contract has a template)
   3. Smart defaults based on document type
  
   Returns:
       {
           "fields": [
               {
                   "label": "Signature 1",
                   "type": "signature",
                   "page_number": 1,
                   "position": {"x": 10, "y": 80, "width": 30, "height": 8},
                   "required": true,
                   "recipient_index": 0  # Maps to signer at index 0
               },
               ...
           ],
           "auto_stack": true  # If true, auto-generate fields for additional signers
       }
   """
   metadata = contract.metadata or {}

   # Prefer template-level config for file-based templates (template editor use-case).
   # If the contract was generated from a filesystem template, persist the placement on that template
   # so future contracts reuse it.
   template_filename = metadata.get('template_filename') or metadata.get('template')
   if isinstance(template_filename, str) and template_filename.strip():
       cfg = _read_template_file_signature_config(template_filename=template_filename)
       if cfg:
           return cfg

   # Contract-specific override (legacy / optional)
   if isinstance(metadata.get('signature_fields_config'), dict):
       config = metadata['signature_fields_config']
       if isinstance(config.get('fields'), list):
           return config
  
   # Check DB template for default config (if template relationship exists)
   try:
       if hasattr(contract, 'template') and contract.template:
           br = getattr(contract.template, 'business_rules', None) or {}
           if isinstance(br, dict) and isinstance(br.get('signature_fields_config'), dict):
               config = br['signature_fields_config']
               if isinstance(config.get('fields'), list):
                   return config
   except Exception:
       pass
  
   # Return smart defaults
   return {
       "fields": [
           {
               "label": "Primary Signature",
               "type": "signature",
               "page_number": 1,
               "position": {"x": 10, "y": 80, "width": 30, "height": 8},
               "required": True,
               "recipient_index": 0
           }
       ],
       "auto_stack": True,  # Auto-generate fields for additional signers
       "stack_spacing": 12  # Percentage spacing between auto-stacked fields
   }




def _generate_signature_fields(contract: Contract, signers: list, signing_order: str) -> tuple[list, list]:
   """Generate Firma recipients and signature fields for a contract.
  
   Args:
       contract: The Contract instance
       signers: List of cleaned signers [{"email": str, "name": str}, ...]
       signing_order: "sequential" or "parallel"
  
   Returns:
       Tuple of (recipients, fields) ready for Firma API
   """
   if not signers:
       return [], []
  
   config = _get_signature_field_config(contract)
   field_templates = config.get('fields', [])
   auto_stack = config.get('auto_stack', True)
   stack_spacing = config.get('stack_spacing', 12)
  
   recipients = []
   fields = []
  
   for idx, signer in enumerate(signers):
       name_parts = signer.get('name', '').strip().split(maxsplit=1)
       first_name = name_parts[0] if name_parts else 'Signer'
       last_name = name_parts[1] if len(name_parts) > 1 else f'{idx + 1}'
      
       # Firma expects deterministic temporary recipient IDs (temp_*) during request creation.
       # These will be converted by Firma into real UUIDs internally.
       temp_id = f"temp_{idx + 1}"
      
       # Create recipient
       # Firma is strict: recipients must include first_name, email, designation, and order.
       recipient = {
           'id': temp_id,
           'first_name': first_name,
           'last_name': last_name,
           'email': signer.get('email', ''),
           'designation': 'Signer',
       }
       if signing_order == 'sequential':
           recipient['order'] = idx + 1
       else:
           # Parallel signing: same order for all signers.
           recipient['order'] = 1
       recipients.append(recipient)
      
       # Determine signature field position for this signer
       field_position = None
       field_label = f"Signature {idx + 1}"
       page_number = 1
      
       # Try to find a matching field template
       for template in field_templates:
           if not isinstance(template, dict):
               continue
          
           # Match by recipient_index
           if template.get('recipient_index') == idx:
               field_position = template.get('position')
               field_label = template.get('label', field_label)
               page_number = template.get('page_number', 1)
               break
          
           # Match by recipient_role if signer has a role
           if 'recipient_role' in template and signer.get('role') == template['recipient_role']:
               field_position = template.get('position')
               field_label = template.get('label', field_label)
               page_number = template.get('page_number', 1)
               break
      
       # If no template matched and this is beyond configured fields, auto-stack if enabled
       if not field_position and auto_stack:
           if idx < len(field_templates):
               # Use the template position even if index doesn't match explicitly
               template = field_templates[idx]
               if isinstance(template, dict) and isinstance(template.get('position'), dict):
                   field_position = template['position'].copy()
                   field_label = template.get('label', field_label)
                   page_number = template.get('page_number', 1)
           else:
               # Auto-generate position based on last template or default
               base_template = field_templates[-1] if field_templates else None
               if base_template and isinstance(base_template.get('position'), dict):
                   base_pos = base_template['position']
                   # Stack below the last defined field
                   y_offset = stack_spacing * (idx - len(field_templates) + 1)
                   field_position = {
                       'x': base_pos.get('x', 10),
                       'y': max(10, base_pos.get('y', 80) - y_offset),
                       'width': base_pos.get('width', 30),
                       'height': base_pos.get('height', 8)
                   }
               else:
                   # Ultimate fallback: default stacking from top
                   y_position = 80 - (idx * stack_spacing)
                   field_position = {
                       'x': 10,
                       'y': max(10, y_position),
                       'width': 30,
                       'height': 8
                   }
      
       # If still no position (auto_stack=False and no template), skip field creation
       if not field_position or not isinstance(field_position, dict):
           logger.warning(
               f"No signature field position found for signer {idx} ({signer.get('email')}). "
               f"Auto-stacking disabled and no template match."
           )
           continue
      
       # Validate position values
       try:
           x = float(field_position.get('x', 10))
           y = float(field_position.get('y', 80))
           width = float(field_position.get('width', 30))
           height = float(field_position.get('height', 8))
          
           # Clamp to valid percentage ranges
           x = max(0, min(100, x))
           y = max(0, min(100, y))
           width = max(1, min(100 - x, width))
           height = max(1, min(100 - y, height))
          
       except (ValueError, TypeError) as e:
           logger.error(f"Invalid position values for signer {idx}: {field_position}, error: {e}")
           # Use safe defaults
           x, y, width, height = 10, 80 - (idx * stack_spacing), 30, 8
      
       # Create signature field
       field = {
           'type': 'signature',
           'required': True,
           'recipient_id': temp_id,
           'page_number': int(page_number) if page_number else 1,
           'position': {
               'x': x,
               'y': y,
               'width': width,
               'height': height
           }
       }
      
       # Add optional label if supported by Firma API
       # (Note: Check Firma docs to see if 'label' or 'name' is supported)
       # field['label'] = field_label
      
       fields.append(field)
  
   logger.info(
       f"Generated {len(fields)} signature fields for {len(signers)} signers using "
       f"{len(field_templates)} template(s), auto_stack={auto_stack}"
   )
  
   return recipients, fields




def _ensure_uploaded(*, contract: Contract, document_name: str, signers=None, signing_order: str = 'sequential') -> FirmaSignatureContract:
   """Upload contract to Firma with customizable signature field placement.
  
   Note: Firma requires recipients at creation time, so signers should be provided upfront.
   If signers are not provided, document is uploaded with empty recipients array.
  
   Signature fields are generated based on:
   1. Contract-specific field configuration (contract.metadata.signature_fields_config)
   2. Template defaults (if contract has a template)
   3. Smart defaults with auto-stacking
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


   # Generate recipients and signature fields using custom configuration
   recipients = []
   fields = []
   if signers:
       cleaned = _clean_signers(signers)
       recipients, fields = _generate_signature_fields(contract, cleaned, signing_order)


   service = _get_firma_service()
   logger.info(
       f"Uploading contract {contract.id} to Firma: {len(recipients)} recipients, "
       f"{len(fields)} signature fields (custom config: {bool(contract.metadata.get('signature_fields_config'))})"
   )
   upload_res = service.upload_document(
       pdf_bytes,
       str(document_name),
       recipients=recipients if recipients else None,
       fields=fields if fields else None,
   )
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
           'fields_count': len(fields),
           'pdf_sha256': pdf_sha256,
           'pdf_bytes_len': len(pdf_bytes),
       },
   )


   FirmaSigningAuditLog.objects.create(
       firma_signature_contract=record,
       event='upload',
       message=f'Document uploaded to Firma with {len(recipients)} recipients and {len(fields)} fields: {firma_document_id}',
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
   # Preserve upload-time metadata (recipients_count/fields_count/pdf_sha256/etc.)
   # so reset heuristics can make correct decisions later.
   data = record.signing_request_data if isinstance(record.signing_request_data, dict) else {}
   data.update(
       {
           'signers': cleaned,
           'signing_order': signing_order,
           'expires_in_days': expires_in_days,
       }
   )
   record.signing_request_data = data
   record.save()


def _send_firma_invite_emails(*, contract: Contract, signers: list[dict], signing_links: dict[str, str]) -> dict:
   """Send invite emails to all signers via our SMTP (independent of vendor email delivery)."""
   subject = f"Signature requested: {(contract.title or 'Contract').strip() or 'Contract'}"
   sent = 0
   failures: list[dict] = []

   for s in signers:
       email = str(s.get('email') or '').strip()
       name = str(s.get('name') or '').strip() or email
       if not email:
           continue
       link = str(signing_links.get(email.lower()) or '').strip()
       if not link:
           failures.append({'email': email, 'error': 'missing signing link'})
           continue

       text_body = (
           f"Hello {name},\n\n"
           f"You have been invited to sign the contract: {(contract.title or 'Contract').strip() or 'Contract'}.\n\n"
           f"Signing link: {link}\n\n"
           "If you were not expecting this email, you can ignore it.\n"
       )
       html_body = (
           f"<p>Hello {name},</p>"
           f"<p>You have been invited to sign the contract: <b>{(contract.title or 'Contract').strip() or 'Contract'}</b>.</p>"
           f"<p><a href=\"{link}\" target=\"_blank\" rel=\"noopener noreferrer\">Click here to sign</a></p>"
           f"<p style=\"color:#6b7280;font-size:12px\">If you were not expecting this email, you can ignore it.</p>"
       )

       try:
           send_mail(
               subject,
               text_body,
               settings.DEFAULT_FROM_EMAIL,
               [email],
               fail_silently=False,
               html_message=html_body,
           )
           sent += 1
       except Exception as e:
           failures.append({'email': email, 'error': str(e)})

   return {'sent': sent, 'failures': failures}


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
               fields_count = None
               previous_pdf_sha = None
               existing_signer_emails = []
               try:
                   if isinstance(existing.signing_request_data, dict):
                       recipients_count = existing.signing_request_data.get('recipients_count')
                       fields_count = existing.signing_request_data.get('fields_count')
                       previous_pdf_sha = existing.signing_request_data.get('pdf_sha256')
               except Exception:
                   recipients_count = None
                   fields_count = None
                   previous_pdf_sha = None

               try:
                   existing_signer_emails = list(existing.signers.values_list('email', flat=True))
               except Exception:
                   existing_signer_emails = []

               new_emails = {str(s.get('email') or '').strip().lower() for s in cleaned if s.get('email')}
               old_emails = {str(e or '').strip().lower() for e in existing_signer_emails if e}


               # Heuristics for an auto-reset:
               # - previous upload had 0 recipients recorded, OR
               # - record is in a terminal/bad state, OR
               # - legacy upload without signature fields (would result in no signing controls), OR
               # - contract content changed since last upload (prevents blank/stale vendor PDFs)
               if recipients_count == 0 or existing.status in ('declined', 'failed'):
                   should_reset = True
               elif recipients_count is None and not old_emails and new_emails:
                   # Legacy/buggy state: signing_request_data lost recipients_count and we have no local signer rows,
                   # meaning the vendor request likely has no recipients. Reset so all signers get invited.
                   should_reset = True
               elif recipients_count is not None and recipients_count != len(cleaned):
                   # User changed number of signers; recipients are immutable on vendor request.
                   should_reset = True
               elif old_emails and new_emails and old_emails != new_emails:
                   # User changed signer emails; must reset vendor request to match.
                   should_reset = True
               elif (existing.signing_order or 'sequential') != (signing_order or 'sequential'):
                   # Signing order affects recipient ordering; reset to ensure correctness.
                   should_reset = True
               elif fields_count in (None, 0):
                   # Legacy uploads without signature fields = no signing controls in UI
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

           # If the request was already sent and at least one signer has signed, do NOT reset.
           # Changing recipients mid-process would invalidate the audit trail.
           if should_reset and existing.status == 'sent':
               try:
                   if existing.signers.filter(has_signed=True).exists():
                       return Response(
                           {
                               'error': 'Cannot change signers or signing order after signing has started.',
                               'details': 'At least one signer has already signed. Create a new signing request/contract to change recipients.',
                           },
                           status=status.HTTP_400_BAD_REQUEST,
                       )
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


           # Generate recipients and signature fields using custom configuration
           recipients, fields = _generate_signature_fields(contract, cleaned, signing_order)


           if not recipients:
               return Response(
                   {
                       'error': 'signers are required to reset/re-upload an existing Firma signing request',
                   },
                   status=status.HTTP_400_BAD_REQUEST,
               )


           service = _get_firma_service()
           old_document_id = existing.firma_document_id
           upload_res = service.upload_document(
               pdf_bytes,
               str(document_name),
               recipients=recipients,
               fields=fields,
           )
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
               'fields_count': len(fields),
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def firma_invite_all(request):
   """Single, reliable invite flow: upload/reset with ALL recipients then email ALL signers.

   This intentionally avoids sequential/parallel complexity: all signers are invited at the same time.

   POST /api/v1/firma/esign/invite-all/
   Body: {"contract_id": "uuid", "signers": [{"name":...,"email":...}], "expires_in_days": 30}

   Returns the first signer's signing URL for convenience.
   """
   contract_id = request.data.get('contract_id')
   signers = request.data.get('signers') or []
   expires_in_days = int(request.data.get('expires_in_days') or 30)

   if not contract_id:
       return Response({'error': 'contract_id is required'}, status=status.HTTP_400_BAD_REQUEST)

   cleaned = _clean_signers(signers)
   if not cleaned:
       return Response({'error': 'At least one signer with name+email is required'}, status=status.HTTP_400_BAD_REQUEST)

   contract = get_object_or_404(Contract, id=contract_id, tenant_id=request.user.tenant_id)
   document_name = request.data.get('document_name') or getattr(contract, 'title', 'Contract')

   # If an existing request is already in progress, don't allow rewriting recipients.
   if hasattr(contract, 'firma_signature_contract'):
       existing = contract.firma_signature_contract
       if existing.status == 'sent':
           try:
               if existing.signers.filter(has_signed=True).exists():
                   return Response(
                       {
                           'error': 'Cannot re-invite after signing has started.',
                           'details': 'At least one signer has already signed. Create a new contract/signing request to change recipients.',
                       },
                       status=status.HTTP_400_BAD_REQUEST,
                   )
           except Exception:
               pass

   try:
       # Always regenerate/upload latest PDF and ALWAYS include all recipients/fields.
       pdf_bytes, source_r2_key = _get_contract_pdf_bytes_from_r2(contract=contract, force_refresh=True)
       pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

       signing_order = 'parallel'
       recipients, fields = _generate_signature_fields(contract, cleaned, signing_order)
       if not recipients:
           return Response({'error': 'signers are required'}, status=status.HTTP_400_BAD_REQUEST)

       service = _get_firma_service()
       upload_res = service.upload_document(
           pdf_bytes,
           str(document_name),
           recipients=recipients,
           fields=fields,
       )
       new_document_id = str(upload_res.get('id') or '').strip()
       if not new_document_id:
           raise FirmaApiError('Firma did not return a document id')

       # Build signing links mapping (prefer upload response recipients if present).
       signing_links: dict[str, str] = {}
       try:
           resp_recipients = upload_res.get('recipients') or []
           if isinstance(resp_recipients, list):
               for r in resp_recipients:
                   email = str((r or {}).get('email') or '').strip().lower()
                   rid = str((r or {}).get('id') or '').strip()
                   if email and rid:
                       signing_links[email] = f"https://app.firma.dev/signing/{rid}"
       except Exception:
           signing_links = {}

       if not signing_links:
           for s in cleaned:
               email = str(s.get('email') or '').strip()
               if not email:
                   continue
               link_res = service.get_signing_link(new_document_id, email)
               link = str(link_res.get('signing_link') or '').strip()
               if link:
                   signing_links[email.lower()] = link

       # Persist/update local record
       if hasattr(contract, 'firma_signature_contract'):
           record = contract.firma_signature_contract
           old_document_id = record.firma_document_id
           record.signers.all().delete()
           record.firma_document_id = new_document_id
           record.status = 'draft'
           record.signing_order = signing_order
           record.sent_at = None
           record.completed_at = None
           record.expires_at = None
           record.last_status_check_at = None
           record.executed_r2_key = None
           if source_r2_key:
               record.original_r2_key = source_r2_key
           record.signing_request_data = {
               'document_name': str(document_name),
               'recipients_count': len(recipients),
               'fields_count': len(fields),
               'reset_from_firma_document_id': old_document_id,
               'source_r2_key': source_r2_key,
               'pdf_sha256': pdf_sha256,
               'pdf_bytes_len': len(pdf_bytes),
           }
           record.save()

           FirmaSigningAuditLog.objects.create(
               firma_signature_contract=record,
               event='upload',
               message=f'Document uploaded to Firma for invite-all. Old: {old_document_id} -> New: {new_document_id}',
               old_status='draft',
               new_status='draft',
               firma_response=upload_res,
           )
       else:
           record = FirmaSignatureContract.objects.create(
               contract=contract,
               firma_document_id=new_document_id,
               status='draft',
               signing_order=signing_order,
               original_r2_key=source_r2_key or None,
               signing_request_data={
                   'document_name': str(document_name),
                   'recipients_count': len(recipients),
                   'fields_count': len(fields),
                   'source_r2_key': source_r2_key,
                   'pdf_sha256': pdf_sha256,
                   'pdf_bytes_len': len(pdf_bytes),
               },
           )
           FirmaSigningAuditLog.objects.create(
               firma_signature_contract=record,
               event='upload',
               message=f'Document uploaded to Firma for invite-all: {new_document_id}',
               new_status='draft',
               firma_response=upload_res,
           )

       # Trigger vendor invite (best-effort) and update our signer rows.
       _ensure_sent(record=record, signers=cleaned, signing_order=signing_order, expires_in_days=expires_in_days)

       # Send our own emails to all signers with their links (the thing you care about).
       email_result = _send_firma_invite_emails(contract=contract, signers=cleaned, signing_links=signing_links)

       first_email = str(cleaned[0].get('email') or '').strip().lower()
       first_link = signing_links.get(first_email)
       if not first_link:
           # Fall back to DB signer (if stored) or vendor lookup.
           try:
               signer = record.signers.filter(email__iexact=cleaned[0]['email']).first()
               if signer and signer.signing_url:
                   first_link = signer.signing_url
           except Exception:
               pass

       return Response(
           {
               'success': True,
               'contract_id': str(contract_id),
               'firma_document_id': record.firma_document_id,
               'status': record.status,
               'signers_invited': len(cleaned),
               'emails_sent': email_result.get('sent', 0),
               'email_failures': email_result.get('failures', []),
               'signing_url': first_link,
               'signer_email': cleaned[0]['email'],
           },
           status=status.HTTP_200_OK,
       )

   except FirmaApiError as e:
       return Response({'error': str(e), 'details': e.response_text}, status=status.HTTP_502_BAD_GATEWAY)
   except Exception as e:
       logger.error('Firma invite-all failed: %s', e, exc_info=True)
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


       record = _ensure_uploaded(
           contract=contract,
           document_name=str(document_name),
           signers=cleaned,
           signing_order=signing_order,
       )
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




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_dragged_signature_positions(request, contract_id: str):
   """Save signature field positions from drag-and-drop UI.
  
   POST /api/v1/firma/contracts/<uuid>/drag-signature-positions/
   Body: {
     "positions": [
       {
         "recipient_index": 0,
         "page_number": 1,
         "position": {"x": 15.5, "y": 72.3, "width": 25, "height": 6}
       }
     ]
   }
  
   This endpoint is optimized for drag-and-drop UIs where users visually place
   signature boxes on the PDF. Positions are saved to contract metadata.
   """
   try:
       contract = Contract.objects.get(id=contract_id, tenant_id=request.user.tenant_id)
   except Contract.DoesNotExist:
       return Response({"error": "Contract not found or access denied."}, status=404)


   positions = request.data.get('positions', [])
   if not isinstance(positions, list):
       return Response({"error": "positions must be an array."}, status=400)


   # Validate position structure
   for idx, pos_data in enumerate(positions):
       if 'recipient_index' not in pos_data:
           return Response({"error": f"Position {idx}: recipient_index is required."}, status=400)
       if 'page_number' not in pos_data or not isinstance(pos_data['page_number'], int):
           return Response({"error": f"Position {idx}: page_number must be an integer."}, status=400)
       if 'position' not in pos_data or not isinstance(pos_data['position'], dict):
           return Response({"error": f"Position {idx}: position must be an object."}, status=400)
      
       position = pos_data['position']
       for key in ['x', 'y', 'width', 'height']:
           if key not in position:
               return Response({"error": f"Position {idx}: position.{key} is required."}, status=400)
           if not isinstance(position[key], (int, float)):
               return Response({"error": f"Position {idx}: position.{key} must be a number."}, status=400)


   # Convert to signature fields config format
   fields = []
   for pos_data in positions:
       fields.append({
           "label": f"Signature {pos_data['recipient_index'] + 1}",
           "type": "signature",
           "page_number": pos_data['page_number'],
           "position": pos_data['position'],
           "required": True,
           "recipient_index": pos_data['recipient_index']
       })


   # Store in contract metadata
   if contract.metadata is None:
       contract.metadata = {}
   contract.metadata['signature_fields_config'] = {
       "fields": fields,
       "auto_stack": False,  # User manually positioned, don't auto-stack
       "source": "drag_drop_ui"
   }


   # Best-effort: also persist a deterministic snapshot to R2 for durability/debugging.
   # (DB metadata remains the source of truth; R2 snapshot is an additional backup.)
   try:
       tenant_id = str(getattr(request.user, 'tenant_id', '') or '')
       if tenant_id:
           r2_key = f"{tenant_id}/contracts/{contract_id}/signature_fields/latest.json"
           payload = {
               'contract_id': str(contract_id),
               'tenant_id': tenant_id,
               'saved_at': timezone.now().isoformat(),
               'signature_fields_config': contract.metadata.get('signature_fields_config') or {},
           }
           r2_service = R2StorageService()
           r2_service.put_text(
               r2_key,
               json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
               content_type='application/json; charset=utf-8',
               metadata={
                   'tenant_id': tenant_id,
                   'contract_id': str(contract_id),
                   'purpose': 'firma_signature_fields_config',
               },
           )
           contract.metadata['signature_fields_r2_key'] = r2_key
   except Exception as e:
       logger.warning(f"[save_dragged_signature_positions] R2 snapshot write failed: {e}")


   contract.save(update_fields=['metadata'])


   logger.info(f"[save_dragged_signature_positions] Saved {len(fields)} dragged positions for contract {contract_id}")
   return Response({
       "message": "Signature field positions saved successfully.",
       "fields_count": len(fields),
       "contract_id": str(contract_id)
   })




@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def firma_signature_fields_config(request, contract_id: str):
    """Get or update signature field configuration for a contract.

    GET returns the current signature field configuration (contract-specific, template, or defaults).
    PUT updates the contract's signature field configuration.
    """

    contract = get_object_or_404(Contract, id=contract_id, tenant_id=request.user.tenant_id)

    if request.method == 'GET':
        config = _get_signature_field_config(contract)

        metadata = contract.metadata or {}
        if isinstance(metadata.get('signature_fields_config'), dict):
            source = 'contract'
        else:
            try:
                if hasattr(contract, 'template') and contract.template:
                    template_metadata = contract.template.metadata or {}
                    source = 'template' if isinstance(template_metadata.get('signature_fields_config'), dict) else 'default'
                else:
                    source = 'default'
            except Exception:
                source = 'default'

        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'config': config,
                'source': source,
                'message': f'Configuration from {source}',
            },
            status=status.HTTP_200_OK,
        )

    if request.method == 'PUT':
        new_config = request.data

        if not isinstance(new_config, dict):
            return Response({'error': 'Configuration must be a JSON object'}, status=status.HTTP_400_BAD_REQUEST)

        fields = new_config.get('fields', [])
        if not isinstance(fields, list):
            return Response({'error': 'fields must be an array'}, status=status.HTTP_400_BAD_REQUEST)

        validation_errors = []
        for idx, field in enumerate(fields):
            if not isinstance(field, dict):
                validation_errors.append(f"Field {idx}: must be an object")
                continue

            if 'type' not in field:
                validation_errors.append(f"Field {idx}: 'type' is required")
            elif field['type'] not in ('signature', 'text', 'date', 'checkbox'):
                validation_errors.append(f"Field {idx}: invalid type '{field['type']}'")

            if 'page_number' in field:
                try:
                    page_num = int(field['page_number'])
                    if page_num < 1:
                        validation_errors.append(f"Field {idx}: page_number must be >= 1")
                except (ValueError, TypeError):
                    validation_errors.append(f"Field {idx}: page_number must be an integer")

            position = field.get('position')
            if not isinstance(position, dict):
                validation_errors.append(f"Field {idx}: 'position' is required and must be an object")
                continue

            for coord in ['x', 'y', 'width', 'height']:
                if coord not in position:
                    validation_errors.append(f"Field {idx}: position.{coord} is required")
                    continue
                try:
                    val = float(position[coord])
                    if not (0 <= val <= 100):
                        validation_errors.append(
                            f"Field {idx}: position.{coord} must be between 0 and 100 (percentage)"
                        )
                except (ValueError, TypeError):
                    validation_errors.append(f"Field {idx}: position.{coord} must be a number")

        if validation_errors:
            return Response(
                {'error': 'Invalid configuration', 'validation_errors': validation_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        metadata = contract.metadata or {}
        metadata['signature_fields_config'] = {
            'fields': fields,
            'auto_stack': bool(new_config.get('auto_stack', True)),
            'stack_spacing': int(new_config.get('stack_spacing', 12)),
        }
        contract.metadata = metadata
        contract.save(update_fields=['metadata', 'updated_at'])

        logger.info(
            f"Updated signature field configuration for contract {contract_id}: "
            f"{len(fields)} fields, auto_stack={metadata['signature_fields_config']['auto_stack']}"
        )

        return Response(
            {
                'success': True,
                'contract_id': str(contract_id),
                'config': metadata['signature_fields_config'],
                'message': f'Configuration updated with {len(fields)} field(s)',
            },
            status=status.HTTP_200_OK,
        )

    return Response({'error': 'Method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
