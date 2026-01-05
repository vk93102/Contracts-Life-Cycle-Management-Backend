from background_task import background
from django.core.mail import send_mail
from django.conf import settings
import logging
import time

logger = logging.getLogger(__name__)


@background(schedule=0)
def generate_contract_async(contract_id: str, template_type: str, variables: dict, special_instructions: str = ""):
    """
    Async contract generation using Gemini AI
    
    Process:
    1. Generate contract with Chain-of-Thought
    2. Validate output
    3. Store with provenance metadata
    4. Generate embedding
    5. Send notification
    
    Args:
        contract_id: Contract UUID
        template_type: Type of contract
        variables: Contract variables
        special_instructions: Custom requirements
    """
    from .models import Contract
    from .ai_services import GeminiService, PIIRedactionService
    
    try:
        contract = Contract.objects.get(id=contract_id)
        
        # Update status to processing
        contract.metadata = contract.metadata or {}
        contract.metadata['generation_status'] = 'processing'
        contract.metadata['generation_started_at'] = time.time()
        contract.save(update_fields=['metadata'])
        
        logger.info(f"Starting async generation for contract {contract_id}")
        
        # Initialize services
        gemini_service = GeminiService()
        
        # Step 1: PII Redaction
        redacted_vars = {}
        redaction_map_combined = {}
        
        for key, value in variables.items():
            if isinstance(value, str):
                redacted_value, redaction_map = PIIRedactionService.redact_pii(value)
                redacted_vars[key] = redacted_value
                redaction_map_combined.update(redaction_map)
            else:
                redacted_vars[key] = value
        
        # Step 2: Generate contract with Chain-of-Thought
        result = gemini_service.generate_contract_with_cot(
            contract_type=template_type,
            variables=redacted_vars,
            special_instructions=special_instructions
        )
        
        if 'error' in result:
            raise Exception(f"Generation failed: {result['error']}")
        
        contract_text = result['content']
        generation_metadata = result['generation_metadata']
        
        # Step 3: Restore PII
        contract_text = PIIRedactionService.restore_pii(contract_text, redaction_map_combined)
        
        # Step 4: Rule-based validation
        validation_result = validate_generated_contract(contract_text, template_type)
        
        if not validation_result['is_valid']:
            logger.warning(f"Validation failed for contract {contract_id}: {validation_result['errors']}")
        
        # Step 5: Generate embedding for search
        embedding = gemini_service.generate_embedding(contract_text[:50000])
        
        # Step 6: Store results
        contract.metadata.update({
            'generation_status': 'completed',
            'generation_completed_at': time.time(),
            'generated_text': contract_text,
            'generation_metadata': generation_metadata,
            'validation_result': validation_result,
            'embedding': embedding,
            'redaction_applied': len(redaction_map_combined) > 0,
            'confidence_score': result.get('confidence_score', 0.75),
            'warnings': result.get('warnings', [])
        })
        contract.status = 'generated'
        contract.save(update_fields=['metadata', 'status'])
        
        logger.info(f"Contract {contract_id} generated successfully")
        
        # Step 7: Send notification
        send_contract_ready_notification(str(contract.id), schedule=5)
        
        return {
            'status': 'success',
            'contract_id': str(contract_id),
            'confidence_score': result.get('confidence_score', 0)
        }
        
    except Exception as e:
        logger.error(f"Contract generation failed: {e}", exc_info=True)
        
        # Update contract status
        try:
            contract.metadata['generation_status'] = 'failed'
            contract.metadata['generation_error'] = str(e)
            contract.save(update_fields=['metadata'])
        except:
            pass
        
        raise


@background(schedule=0)
def generate_embeddings_for_contract(contract_id: str):
    """
    Generate and store vector embeddings for a contract
    
    Used for:
    - Semantic search
    - Similar contract finding
    - AI analysis
    """
    from .models import Contract
    from .ai_services import GeminiService
    
    try:
        contract = Contract.objects.get(id=contract_id)
        
        # Build text to embed
        text_parts = [
            contract.title,
            contract.description or '',
            contract.contract_type,
        ]
        
        # Include generated text if available
        if contract.metadata and 'generated_text' in contract.metadata:
            text_parts.append(contract.metadata['generated_text'][:50000])
        
        full_text = ' '.join(filter(None, text_parts))
        
        # Generate embedding
        gemini_service = GeminiService()
        embedding = gemini_service.generate_embedding(full_text)
        
        if embedding:
            contract.metadata = contract.metadata or {}
            contract.metadata['embedding'] = embedding
            contract.metadata['embedding_generated_at'] = time.time()
            contract.save(update_fields=['metadata'])
            
            logger.info(f"Generated embedding for contract {contract_id}")
            return {'status': 'success', 'dimensions': len(embedding)}
        else:
            logger.warning(f"Failed to generate embedding for contract {contract_id}")
            return {'status': 'failed', 'reason': 'Gemini API error'}
            
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}

@background(schedule=0)
def send_contract_ready_notification(contract_id: str):
    """
    Send email notification when contract is ready
    
    Uses Django's email backend (configure in settings.py)
    """
    from .models import Contract
    from authentication.models import User
    
    try:
        contract = Contract.objects.get(id=contract_id)
        user = User.objects.get(user_id=contract.created_by)
        
        subject = f"Contract Ready: {contract.title}"
        message = f"""
Hello {user.first_name or user.email},

Your contract "{contract.title}" has been generated and is ready for review.

Contract Details:
- Type: {contract.contract_type}
- Status: {contract.status}
- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

Confidence Score: {contract.metadata.get('confidence_score', 'N/A')}

Please review the contract in your dashboard.

Best regards,
CLM System
"""
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f"Sent notification to {user.email} for contract {contract_id}")
        return {'status': 'sent', 'recipient': user.email}
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}


@background(schedule=0)
def process_ocr_document(document_id: str):
    """
    OCR processing for uploaded documents
    
    Process:
    1. Download from R2
    2. Run OCR (Tesseract)
    3. Extract text
    4. Generate embedding
    5. Update status
    """
    from PIL import Image
    import pytesseract
    import io
    from .models import Contract
    from .ai_services import GeminiService
    from authentication.r2_service import r2_service
    
    try:
        logger.info(f"OCR processing started for document {document_id}")
        
        contract = Contract.objects.get(id=document_id)
        
        # Download file from R2
        if not contract.file_url:
            raise Exception("No file URL found")
        
        # Get file from R2
        file_content = r2_service.download_file(contract.file_url)
        
        if not file_content:
            raise Exception("Failed to download file from R2")
        
        # Process based on file type
        file_extension = contract.file_url.split('.')[-1].lower()
        
        extracted_text = ""
        
        if file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
            # Image OCR using Tesseract
            image = Image.open(io.BytesIO(file_content))
            extracted_text = pytesseract.image_to_string(image)
            
        elif file_extension == 'pdf':
            # PDF OCR (requires pdf2image)
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(file_content)
                
                text_parts = []
                for image in images:
                    page_text = pytesseract.image_to_string(image)
                    text_parts.append(page_text)
                
                extracted_text = '\n\n'.join(text_parts)
            except ImportError:
                logger.warning("pdf2image not installed, skipping PDF OCR")
                extracted_text = "PDF OCR requires pdf2image package"
        
        # Generate embedding
        gemini_service = GeminiService()
        embedding = gemini_service.generate_embedding(extracted_text)
        
        # Update contract
        contract.metadata = contract.metadata or {}
        contract.metadata['ocr_text'] = extracted_text
        contract.metadata['ocr_processed_at'] = time.time()
        contract.metadata['ocr_length'] = len(extracted_text)
        contract.metadata['embedding'] = embedding
        contract.save(update_fields=['metadata'])
        
        logger.info(f"OCR completed for document {document_id}, extracted {len(extracted_text)} characters")
        
        return {
            'status': 'success',
            'text_length': len(extracted_text),
            'has_embedding': embedding is not None
        }
        
    except Exception as e:
        logger.error(f"OCR processing failed: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}



def validate_generated_contract(contract_text: str, template_type: str) -> dict:
    """
    Rule-based validation of AI-generated contracts
    
    Validates:
    1. Required sections present
    2. Payment terms have valid numbers
    3. Dates are properly formatted
    4. Signature blocks included
    
    Args:
        contract_text: Generated contract
        template_type: Type of contract
        
    Returns:
        Validation result dict
    """
    import re
    
    errors = []
    warnings = []
    
    # Required sections for different contract types
    required_sections = {
        'NDA': ['Confidential Information', 'Non-Disclosure', 'Term', 'Signature'],
        'MSA': ['Services', 'Payment', 'Term', 'Termination', 'Liability', 'Signature'],
        'SOW': ['Scope', 'Deliverables', 'Timeline', 'Payment', 'Signature'],
    }
    
    sections_to_check = required_sections.get(template_type, ['Signature'])
    
    # Check for required sections
    for section in sections_to_check:
        if section.lower() not in contract_text.lower():
            errors.append(f"Missing required section: {section}")
    
    # Validate payment terms (if present)
    if 'payment' in contract_text.lower():
        # Look for currency amounts
        currency_pattern = r'\$[\d,]+\.?\d*|USD\s*[\d,]+\.?\d*|EUR\s*[\d,]+\.?\d*'
        if not re.search(currency_pattern, contract_text):
            warnings.append("Payment section lacks specific monetary amount")
    
    # Validate dates
    date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}'
    if not re.search(date_pattern, contract_text):
        warnings.append("No dates found in contract")
    
    # Check for signature blocks
    signature_keywords = ['signature', 'signed', 'executed', 'authorized representative']
    has_signature = any(kw in contract_text.lower() for kw in signature_keywords)
    if not has_signature:
        errors.append("No signature block found")
    
    is_valid = len(errors) == 0
    
    return {
        'is_valid': is_valid,
        'errors': errors,
        'warnings': warnings,
        'sections_found': sum(1 for s in sections_to_check if s.lower() in contract_text.lower()),
        'sections_required': len(sections_to_check)
    }
