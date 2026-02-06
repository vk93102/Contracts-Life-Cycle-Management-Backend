import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class FirmaApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


@dataclass(frozen=True)
class FirmaConfig:
    api_key: str
    base_url: str

    # Endpoint templates (override via env if needed)
    upload_path: str
    invite_path: str
    signing_link_path: str
    status_path: str
    users_path: str
    download_path: str
    reminders_path: str

    webhooks_path: str
    webhook_detail_path: str
    webhook_secret_status_path: str

    generate_template_token_path: str
    revoke_template_token_path: str
    jwt_generate_signing_request_path: str
    jwt_revoke_signing_request_path: str

    # Auth header customization
    auth_header_name: str
    auth_header_value_prefix: str

    timeout_seconds: int
    mock_mode: bool
    mock_auto_complete: bool


def load_firma_config() -> FirmaConfig:
    mock_mode = (os.getenv('FIRMA_MOCK') or '').strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    api_key = (os.getenv('FIRMA_API') or '').strip()
    if not api_key and not mock_mode:
        raise FirmaApiError('FIRMA_API is not configured')

    base_url = (os.getenv('FIRMA_BASE_URL') or '').strip().rstrip('/')
    if not base_url:
        # We avoid guessing the vendor URL. Require explicit config for real API usage.
        base_url = 'https://example.invalid'

    return FirmaConfig(
        api_key=api_key,
        base_url=base_url,
        # Firma API paths per https://docs.firma.dev
        upload_path=(os.getenv('FIRMA_UPLOAD_PATH') or '/functions/v1/signing-request-api/signing-requests').strip(),
        invite_path=(os.getenv('FIRMA_INVITE_PATH') or '/functions/v1/signing-request-api/signing-requests/{document_id}/send').strip(),
        signing_link_path=(os.getenv('FIRMA_SIGNING_LINK_PATH') or '/functions/v1/signing-request-api/signing-requests/{document_id}/signing-link').strip(),
        status_path=(os.getenv('FIRMA_STATUS_PATH') or '/functions/v1/signing-request-api/signing-requests/{document_id}').strip(),
        users_path=(os.getenv('FIRMA_USERS_PATH') or '/functions/v1/signing-request-api/signing-requests/{document_id}/users').strip(),
        download_path=(os.getenv('FIRMA_DOWNLOAD_PATH') or '/functions/v1/signing-request-api/signing-requests/{document_id}/download').strip(),
        reminders_path=(os.getenv('FIRMA_REMINDERS_PATH') or '/functions/v1/signing-request-api/signing-requests/{document_id}/reminders').strip(),

        webhooks_path=(os.getenv('FIRMA_WEBHOOKS_PATH') or '/functions/v1/signing-request-api/webhooks').strip(),
        webhook_detail_path=(os.getenv('FIRMA_WEBHOOK_DETAIL_PATH') or '/functions/v1/signing-request-api/webhooks/{webhook_id}').strip(),
        webhook_secret_status_path=(os.getenv('FIRMA_WEBHOOK_SECRET_STATUS_PATH') or '/functions/v1/signing-request-api/webhooks/secret-status').strip(),

        generate_template_token_path=(os.getenv('FIRMA_GENERATE_TEMPLATE_TOKEN_PATH') or '/functions/v1/signing-request-api/generate-template-token').strip(),
        revoke_template_token_path=(os.getenv('FIRMA_REVOKE_TEMPLATE_TOKEN_PATH') or '/functions/v1/signing-request-api/revoke-template-token').strip(),
        jwt_generate_signing_request_path=(os.getenv('FIRMA_JWT_GENERATE_SIGNING_REQUEST_PATH') or '/functions/v1/signing-request-api/jwt/generate-signing-request').strip(),
        jwt_revoke_signing_request_path=(os.getenv('FIRMA_JWT_REVOKE_SIGNING_REQUEST_PATH') or '/functions/v1/signing-request-api/jwt/revoke-signing-request').strip(),
        auth_header_name=(os.getenv('FIRMA_AUTH_HEADER') or 'Authorization').strip(),
        auth_header_value_prefix=(os.getenv('FIRMA_AUTH_PREFIX') or 'Bearer ').strip(),
        timeout_seconds=int(os.getenv('FIRMA_TIMEOUT_SECONDS') or '30'),
        mock_mode=mock_mode,
        mock_auto_complete=(os.getenv('FIRMA_MOCK_AUTO_COMPLETE') or '').strip().lower() in ('1', 'true', 'yes', 'y', 'on'),
    )


class FirmaAPIService:
    """Production-grade HTTP wrapper for the Firma e-sign API.

    This implementation is intentionally configurable via env vars because vendor
    API paths/auth schemes vary. For real signing, set FIRMA_BASE_URL and (if
    necessary) the *_PATH and auth header env vars.

    For local testing without a vendor account, set FIRMA_MOCK=true.
    """

    def __init__(self, config: Optional[FirmaConfig] = None):
        self.config = config or load_firma_config()

    def _headers(self) -> Dict[str, str]:
        """Build request headers with Authorization token.
        
        Firma docs state: Bearer prefix is optional but not required.
        We use the raw API key directly as recommended.
        """
        return {
            'Authorization': self.config.api_key,
            'Content-Type': 'application/json',
        }

    def _url(self, path: str) -> str:
        return f"{self.config.base_url}{path if path.startswith('/') else '/' + path}"

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = dict(kwargs.pop('headers', {}) or {})
        headers.update(self._headers())
        
        # Debug logging: log sanitized headers and payload
        debug_headers = dict(headers)
        if self.config.auth_header_name in debug_headers:
            key = debug_headers[self.config.auth_header_name]
            debug_headers[self.config.auth_header_name] = f"{key[:20]}...{key[-8:]}" if len(key) > 30 else "***"
        
        debug_body = None
        if 'json' in kwargs:
            debug_body = kwargs['json']
        elif 'data' in kwargs:
            debug_body = kwargs['data']
        elif 'files' in kwargs:
            debug_body = f"<files: {list(kwargs['files'].keys())}>"
        
        logger.info(f"Firma API request: {method} {url} | Headers: {debug_headers} | Body: {debug_body}")
        
        try:
            resp = requests.request(method, url, headers=headers, timeout=self.config.timeout_seconds, **kwargs)
        except requests.RequestException as e:
            logger.error(f"Firma API request failed: {method} {url} | Error: {e}", exc_info=True)
            raise FirmaApiError(f'Firma API request failed: {e}') from e

        logger.info(f"Firma API response: {method} {url} | Status: {resp.status_code} | Response: {resp.text[:500]}")
        
        if resp.status_code < 200 or resp.status_code >= 300:
            logger.error(f"Firma API error response: {method} {url} | Status: {resp.status_code} | Body: {resp.text[:1000]}")
            raise FirmaApiError(
                f'Firma API error ({resp.status_code})',
                status_code=resp.status_code,
                response_text=(resp.text or '')[:2000],
            )
        return resp

    def upload_document(
        self,
        pdf_bytes: bytes,
        document_name: str,
        recipients: List[Dict[str, Any]] = None,
        fields: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create signing request with document, recipients, and signature fields.
        
        Args:
            pdf_bytes: PDF file content
            document_name: Name for the document
            recipients: List of recipient dicts with first_name, last_name, email, designation
            fields: List of field dicts with type, page_number, position (percentage-based), recipient_id
        """
        if self.config.mock_mode:
            return {
                'id': f'mock_doc_{uuid.uuid4().hex}',
                'name': document_name,
                'status': 'draft',
                'recipients': recipients or [],
            }

        if self.config.base_url.endswith('example.invalid'):
            raise FirmaApiError('FIRMA_BASE_URL is not configured for real API usage')

        # Firma API expects base64-encoded PDF in JSON payload
        import base64
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        
        url = self._url(self.config.upload_path)
        
        # Create signing request with embedded document and recipients
        # IMPORTANT: Recipients must be included at creation time for Firma to process them
        payload = {
            'name': document_name,
            'document': base64_pdf,
            'recipients': recipients or []  # Add recipients upfront
        }
        
        # Add signature fields if provided (percentage-based positioning required)
        if fields:
            payload['fields'] = fields
        
        logger.info(
            f"Creating signing request for: {document_name} "
            f"(PDF size: {len(pdf_bytes)} bytes, recipients: {len(recipients or [])}, fields: {len(fields or [])})"
        )
        resp = self._request('POST', url, json=payload)
        result = resp.json()
        logger.info(
            f"Signing request created: {result.get('id')} "
            f"with {len(result.get('recipients', []))} recipients and {len(result.get('fields', []))} fields"
        )
        return result

    def create_invite(self, document_id: str, signers: List[Dict[str, str]], signing_order: str = 'sequential') -> Dict[str, Any]:
        """
        Send signing invites for existing signing request.
        
        Firma's workflow:
        1. Create signing request with recipients via upload_document()
        2. Send invites via /send endpoint to trigger email notifications
        3. Recipients receive emails with signing links
        
        Note: Recipients should be added during creation (upload_document),
        not here. This method only sends the invites.
        """
        if self.config.mock_mode:
            return {
                'document_id': document_id,
                'signers': signers,
                'signing_order': signing_order,
                'status': 'sent',
            }

        logger.info(f"Sending invites for signing request {document_id} with {len(signers)} signers")
        
        # Send the signing request to trigger emails
        # No payload needed - Firma sends to all recipients in the signing request
        url = self._url(self.config.invite_path.format(document_id=document_id))
        
        try:
            resp = self._request('POST', url, json={})
            result = resp.json()
            logger.info(f"Invites sent successfully for signing request {document_id}")
            return result
        except FirmaApiError as e:
            # Idempotency: vendor may return 400 when the request was already sent.
            # Treat that case as success so the client can proceed.
            body = (e.response_text or '').lower()
            if e.status_code == 400 and 'already been sent' in body:
                logger.info("Signing request %s already sent; treating as success", document_id)
                return {
                    'document_id': document_id,
                    'status': 'sent',
                    'already_sent': True,
                }
            raise

    def get_signing_link(self, document_id: str, signer_email: str) -> Dict[str, Any]:
        """
        Generate signing link for a signer.
        
        For Firma, the signing URL format is:
        https://app.firma.dev/signing/{signing_request_user_id}
        
        We fetch the signing request details to find the matching recipient.
        """
        if self.config.mock_mode:
            return {
                'signing_link': f"http://localhost:3000/firma/mock-sign?doc={document_id}&email={signer_email}",
            }

        # Firma does not include recipients on GET /signing-requests/{id}.
        # Use the documented users endpoint to find the signing-request user id.
        users_url = self._url(self.config.users_path.format(document_id=document_id))
        users_resp = self._request('GET', users_url)
        users_data = users_resp.json()

        users = []
        if isinstance(users_data, list):
            users = users_data
        elif isinstance(users_data, dict):
            users = users_data.get('results') or []

        signing_request_user_id = None
        for user in users:
            if str(user.get('email') or '').lower() == signer_email.lower():
                signing_request_user_id = user.get('id')
                break
        
        if not signing_request_user_id:
            logger.warning(
                "Could not find signing_request_user_id for %s in request %s; recipients are missing or email mismatch",
                signer_email,
                document_id,
            )
            raise FirmaApiError(
                'Signer not found in Firma signing request recipients. Re-upload the document with signers and re-send invites.'
            )
        
        return {
            'signing_link': f"https://app.firma.dev/signing/{signing_request_user_id}",
        }

    def get_document_status(self, document_id: str) -> Dict[str, Any]:
        """
        Get signing request status from Firma.
        
        Returns recipient status, completion status, etc.
        """
        if self.config.mock_mode:
            return {
                'id': document_id,
                'status': 'completed' if self.config.mock_auto_complete else 'sent',
                'is_completed': self.config.mock_auto_complete,
                'signers': [],
            }

        url = self._url(self.config.status_path.format(document_id=document_id))
        resp = self._request('GET', url)
        status_data = resp.json()
        
        # Normalize Firma response to match our expected format
        # Firma returns: {id, status, recipients: [{email, status, signed_at, ...}, ...]}

        status_value = status_data.get('status')
        
        recipients = status_data.get('recipients') or []

        # Determine completion.
        # Vendor may not return recipients here; prefer status flags when available.
        is_completed = False
        if isinstance(status_value, dict) and bool(status_value.get('finished')):
            is_completed = True
        elif recipients:
            signed_count = sum(1 for r in recipients if str(r.get('status') or '').lower() == 'completed')
            total_count = len(recipients)
            is_completed = signed_count == total_count and total_count > 0

        # Firma may return status as a string OR as an object of boolean flags.
        # Keep a raw string for debugging, but normalize using structure when available.
        if isinstance(status_value, (dict, list)):
            raw_status = str(status_value)
        else:
            raw_status = str(status_value or '').strip()
        raw_status_lc = raw_status.lower()

        # Map vendor status -> our internal status choices.
        # This prevents DB truncation errors and keeps UI consistent.
        if isinstance(status_value, dict):
            finished = bool(status_value.get('finished'))
            declined = bool(status_value.get('declined'))
            cancelled = bool(status_value.get('cancelled'))
            expired = bool(status_value.get('expired'))
            sent = bool(status_value.get('sent'))

            if is_completed or finished:
                normalized_status = 'completed'
            elif declined or any('declin' in str(r.get('status') or '').lower() for r in recipients):
                normalized_status = 'declined'
            elif cancelled or expired:
                normalized_status = 'failed'
            elif sent:
                normalized_status = 'sent'
            else:
                # If there are recipients but it's not sent/finished yet, treat as in progress.
                normalized_status = 'in_progress' if recipients else 'draft'
        else:
            if is_completed or raw_status_lc in {'completed', 'complete', 'signed'}:
                normalized_status = 'completed'
            elif raw_status_lc in {'draft', 'created'}:
                normalized_status = 'draft'
            elif raw_status_lc in {'sent', 'emailed'}:
                normalized_status = 'sent'
            elif 'declin' in raw_status_lc or 'reject' in raw_status_lc or any('declin' in str(r.get('status') or '').lower() for r in recipients):
                normalized_status = 'declined'
            elif 'fail' in raw_status_lc or 'error' in raw_status_lc:
                normalized_status = 'failed'
            else:
                normalized_status = 'in_progress'
        
        return {
            'id': status_data.get('id'),
            'status': normalized_status,
            'raw_status': raw_status,
            'is_completed': is_completed,
            'recipients': recipients,
            'created_at': status_data.get('created_at'),
            'completed_at': status_data.get('completed_at'),
        }

    def get_signing_request_details(self, document_id: str) -> Dict[str, Any]:
        """Fetch the raw signing-request object (includes vendor certificate/status fields)."""
        if self.config.mock_mode:
            return {
                'id': document_id,
                'status': 'sent',
                'certificate': {'generated': False, 'generated_on': None, 'has_error': False},
            }

        url = self._url(self.config.status_path.format(document_id=document_id))
        resp = self._request('GET', url)
        return resp.json()

    def get_reminders(self, document_id: str) -> Any:
        """Fetch reminders for a signing request."""
        if self.config.mock_mode:
            return []

        url = self._url(self.config.reminders_path.format(document_id=document_id))
        resp = self._request('GET', url)
        return resp.json()

    # ===== Webhooks =====
    def list_webhooks(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = 'created_on',
        sort_order: str = 'desc',
    ) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {
                'results': [],
                'pagination': {'current_page': 1, 'page_size': page_size, 'total_count': 0, 'total_pages': 0},
            }

        qs = f"?page={int(page)}&page_size={int(page_size)}&sort_by={sort_by}&sort_order={sort_order}"
        url = self._url(self.config.webhooks_path + qs)
        resp = self._request('GET', url)
        return resp.json()

    def create_webhook(self, *, url: str, events: List[str]) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'id': f'mock_webhook_{uuid.uuid4().hex}', 'url': url, 'events': events, 'enabled': True}

        api_url = self._url(self.config.webhooks_path)
        resp = self._request('POST', api_url, json={'url': url, 'events': events})
        return resp.json()

    def get_webhook(self, webhook_id: str) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'id': webhook_id, 'url': 'http://localhost/mock', 'events': [], 'enabled': True}

        api_url = self._url(self.config.webhook_detail_path.format(webhook_id=webhook_id))
        resp = self._request('GET', api_url)
        return resp.json()

    def update_webhook(self, webhook_id: str, *, url: str, events: List[str]) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'id': webhook_id, 'url': url, 'events': events, 'enabled': True}

        api_url = self._url(self.config.webhook_detail_path.format(webhook_id=webhook_id))
        resp = self._request('PUT', api_url, json={'url': url, 'events': events})
        return resp.json()

    def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'message': 'Webhook deleted successfully', 'webhook_id': webhook_id}

        api_url = self._url(self.config.webhook_detail_path.format(webhook_id=webhook_id))
        resp = self._request('DELETE', api_url)
        try:
            return resp.json()
        except Exception:
            return {'message': (resp.text or '').strip() or 'deleted', 'webhook_id': webhook_id}

    def webhook_secret_status(self) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'has_secret': False}

        api_url = self._url(self.config.webhook_secret_status_path)
        resp = self._request('GET', api_url)
        return resp.json()

    # ===== JWT helpers =====
    def generate_template_token(self, *, companies_workspaces_templates_id: str) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {
                'token': f'mock_token_{uuid.uuid4().hex}',
                'expires_at': None,
                'jwt_record_id': f'mock_jwt_{uuid.uuid4().hex}',
            }

        api_url = self._url(self.config.generate_template_token_path)
        resp = self._request('POST', api_url, json={'companies_workspaces_templates_id': companies_workspaces_templates_id})
        return resp.json()

    def revoke_template_token(self, *, jwt_id: str) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'message': 'JWT revoked successfully', 'jwt_id': jwt_id}

        api_url = self._url(self.config.revoke_template_token_path)
        resp = self._request('POST', api_url, json={'jwt_id': jwt_id})
        return resp.json()

    def jwt_generate_signing_request(self, *, companies_workspaces_signing_requests_id: str) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {
                'jwt': f'mock_jwt_{uuid.uuid4().hex}',
                'jwt_id': f'mock_jwt_id_{uuid.uuid4().hex}',
                'expires_at': None,
                'signing_request_id': companies_workspaces_signing_requests_id,
            }

        api_url = self._url(self.config.jwt_generate_signing_request_path)
        resp = self._request('POST', api_url, json={'companies_workspaces_signing_requests_id': companies_workspaces_signing_requests_id})
        return resp.json()

    def jwt_revoke_signing_request(self, *, jwt_id: str) -> Dict[str, Any]:
        if self.config.mock_mode:
            return {'message': 'JWT revoked successfully', 'jwt_id': jwt_id}

        api_url = self._url(self.config.jwt_revoke_signing_request_path)
        resp = self._request('POST', api_url, json={'jwt_id': jwt_id})
        return resp.json()

    def download_document(self, document_id: str) -> bytes:
        if self.config.mock_mode:
            # In mock mode, we don't have a vendor PDF. Callers should fall back to stored original.
            return b''

        url = self._url(self.config.download_path.format(document_id=document_id))
        resp = self._request('GET', url)
        return resp.content
