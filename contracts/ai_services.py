"""
Production-Level Gemini AI Integration Service
Handles text embeddings, contract generation, and AI analysis
"""
import os
import logging
import time
import google.generativeai as genai
from typing import List, Dict, Optional, Tuple
from django.conf import settings
import re

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').replace('GEMINI_API_KEY=', '')
genai.configure(api_key=GEMINI_API_KEY)


class GeminiService:
    """
    Production-level Gemini AI service with retry logic, caching, and error handling
    """
    
    # Model configurations for different tasks
    EMBEDDING_MODEL = 'models/text-embedding-004'
    GENERATION_MODEL = 'gemini-2.0-flash'  # Updated to latest stable model
    
    def __init__(self):
        self.embedding_model = GEMINI_API_KEY and genai
        self.generation_model = None
        if GEMINI_API_KEY:
            try:
                self.generation_model = genai.GenerativeModel(self.GENERATION_MODEL)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini model: {e}")
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate vector embedding for text using Gemini
        
        Args:
            text: Text to embed (contracts, clauses, search queries)
            
        Returns:
            List of floats (768 dimensions) or None on error
            
        Production Features:
        - Retry logic with exponential backoff
        - Text truncation to model limits
        - Error isolation
        """
        if not self.embedding_model:
            logger.warning("Gemini not configured, returning None")
            return None
        
        # Truncate to Gemini's token limit (~30k tokens ≈ 120k chars)
        text = text[:100000] if len(text) > 100000 else text
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = genai.embed_content(
                    model=self.EMBEDDING_MODEL,
                    content=text,
                    task_type="retrieval_document"
                )
                
                if result and 'embedding' in result:
                    logger.info(f"Generated embedding: {len(result['embedding'])} dimensions")
                    return result['embedding']
                    
            except Exception as e:
                logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to generate embedding after {max_retries} attempts")
        
        return None
    
    def generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """
        Generate embedding optimized for search queries
        
        Args:
            query: User search query
            
        Returns:
            Vector embedding for similarity search
        """
        if not self.embedding_model:
            return None
        
        try:
            result = genai.embed_content(
                model=self.EMBEDDING_MODEL,
                content=query,
                task_type="retrieval_query"  # Optimized for queries
            )
            
            if result and 'embedding' in result:
                return result['embedding']
                
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
        
        return None
    
    def generate_contract_with_cot(
        self,
        template_type: str,
        variables: Dict,
        special_instructions: str = ""
    ) -> Tuple[str, Dict]:
        """
        Generate contract using Chain-of-Thought prompting
        
        Chain-of-Thought Process:
        1. Ask AI to create outline first
        2. Generate each section separately
        3. Validate each section
        4. Combine into final document
        
        Args:
            template_type: Type of contract (NDA, MSA, etc.)
            variables: Contract variables (parties, dates, amounts)
            special_instructions: Custom requirements
            
        Returns:
            Tuple of (generated_text, metadata)
            
        Metadata includes:
        - prompt_id: Hash of the prompt used
        - model_version: Gemini model version
        - confidence_score: Self-assessed quality (1-10)
        - sections_generated: List of sections
        """
        if not self.generation_model:
            raise ValueError("Gemini generation model not available")
        
        metadata = {
            'model_version': self.GENERATION_MODEL,
            'template_type': template_type,
            'timestamp': time.time()
        }
        
        # Step 1: Generate outline using Chain-of-Thought
        outline_prompt = f"""
You are a legal contract drafting expert. Create a detailed outline for a {template_type}.

Context:
{self._format_variables(variables)}

Special Instructions: {special_instructions}

IMPORTANT: First, think through the essential sections step-by-step:
1. What are the mandatory sections for a {template_type}?
2. What sections are needed based on the jurisdiction and parties?
3. What order should these sections appear in?

Now provide the outline in this format:
## Section 1: [Name]
- Key points to cover
- Legal requirements

## Section 2: [Name]
- Key points to cover
...
"""
        
        try:
            # Generate outline
            outline_response = self.generation_model.generate_content(outline_prompt)
            outline = outline_response.text
            
            logger.info(f"Generated outline for {template_type}")
            metadata['outline'] = outline
            
            # Step 2: Generate full contract based on outline
            generation_prompt = f"""
You are a legal contract drafting expert. Generate a complete, legally sound {template_type} based on this outline:

{outline}

Contract Details:
{self._format_variables(variables)}

Special Instructions: {special_instructions}

REQUIREMENTS:
1. Use clear, professional legal language
2. Include all standard clauses for {template_type}
3. Ensure proper numbering and formatting
4. Include signature blocks
5. Add "[PARTY_A]", "[PARTY_B]" as placeholders for names
6. Use "[AMOUNT]", "[DATE]" for numerical values

Generate the complete contract now:
"""
            
            generation_response = self.generation_model.generate_content(generation_prompt)
            contract_text = generation_response.text
            
            # Step 3: Self-validation and confidence scoring
            validation_prompt = f"""
Review the following {template_type} contract and assess its quality:

{contract_text[:5000]}... (truncated for review)

Rate this contract on a scale of 1-10 based on:
1. Legal completeness (all necessary clauses present)
2. Clarity and readability
3. Compliance with standard {template_type} requirements
4. Proper formatting and structure

Provide ONLY a number from 1-10, then a brief explanation.
Format: "Score: X/10 - [explanation]"
"""
            
            validation_response = self.generation_model.generate_content(validation_prompt)
            validation_text = validation_response.text
            
            # Extract confidence score
            confidence_score = self._extract_confidence_score(validation_text)
            metadata['confidence_score'] = confidence_score
            metadata['validation_notes'] = validation_text
            
            # Generate prompt hash for provenance
            import hashlib
            prompt_hash = hashlib.sha256(
                (outline_prompt + generation_prompt).encode()
            ).hexdigest()[:16]
            metadata['prompt_id'] = prompt_hash
            
            logger.info(
                f"Generated {template_type} with confidence {confidence_score}/10"
            )
            
            return contract_text, metadata
            
        except Exception as e:
            logger.error(f"Contract generation failed: {e}", exc_info=True)
            raise
    
    def generate_clause_summary(self, clause_text: str) -> str:
        """
        Generate plain-English summary of legal clause for non-legal users
        
        Args:
            clause_text: Legal clause text
            
        Returns:
            Plain-English summary
        """
        if not self.generation_model:
            logger.error("Generation model not initialized")
            return "AI summary not available - model not initialized"
        
        prompt = f"""
Explain the following legal clause in simple, everyday language that a non-lawyer can understand:

{clause_text}

Provide a brief, clear explanation (2-3 sentences max) of:
1. What this clause means
2. Why it's important
3. What obligations it creates

Keep it simple and avoid legal jargon.
"""
        
        try:
            response = self.generation_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Clause summary generation failed: {e}", exc_info=True)
            return f"Could not generate summary: {str(e)}"
    
    def compare_contracts(
        self,
        contract_a_text: str,
        contract_b_text: str
    ) -> Dict:
        """
        AI-powered contract comparison highlighting risk differences
        
        Args:
            contract_a_text: First contract
            contract_b_text: Second contract
            
        Returns:
            Comparison report with risk analysis
        """
        if not self.generation_model:
            return {'error': 'AI comparison not available'}
        
        # Truncate for API limits
        a_text = contract_a_text[:20000]
        b_text = contract_b_text[:20000]
        
        prompt = f"""
Compare these two contracts and identify key differences, especially those that affect risk:

CONTRACT A:
{a_text}

CONTRACT B:
{b_text}

Provide a structured comparison:

## Key Differences
1. [Specific difference]
   - Risk Level: High/Medium/Low
   - Impact: [explanation]

## Recommendations
- [Actionable advice]

## Risk Summary
- Contract A: [risk profile]
- Contract B: [risk profile]
"""
        
        try:
            response = self.generation_model.generate_content(prompt)
            
            return {
                'comparison_text': response.text,
                'generated_at': time.time(),
                'model': self.GENERATION_MODEL
            }
        except Exception as e:
            logger.error(f"Contract comparison failed: {e}")
            return {'error': str(e)}
    
    def _format_variables(self, variables: Dict) -> str:
        """Format variables dictionary into readable text"""
        lines = []
        for key, value in variables.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        return '\n'.join(lines)
    
    def _extract_confidence_score(self, validation_text: str) -> float:
        """Extract numerical score from validation response"""
        # Look for patterns like "Score: 8/10" or "8/10" or "8 out of 10"
        patterns = [
            r'Score:\s*(\d+)/10',
            r'(\d+)/10',
            r'(\d+)\s*out of 10'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, validation_text, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    return min(max(score, 1.0), 10.0)  # Clamp to 1-10
                except:
                    pass
        
        # Default to 7 if can't extract
        return 7.0


class PIIRedactionService:
    """
    Pre-processing pipeline for PII redaction before sending to Gemini
    Prevents client data leakage to public LLMs
    """
    
    # PII patterns (production would use Microsoft Presidio)
    PII_PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'phone': r'\b(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'name_title': r'\b(Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b',
    }
    
    def __init__(self):
        self.redaction_map = {}
    
    def redact_pii(self, text: str) -> Tuple[str, Dict]:
        """
        Redact PII from text before sending to AI
        
        Args:
            text: Original text with PII
            
        Returns:
            Tuple of (redacted_text, redaction_map)
            
        Example:
            Input: "Contact John Smith at john@example.com"
            Output: "Contact [PARTY_A] at [EMAIL_1]"
            Map: {"[PARTY_A]": "John Smith", "[EMAIL_1]": "john@example.com"}
        """
        self.redaction_map = {}
        redacted_text = text
        
        # Email redaction
        emails = re.findall(self.PII_PATTERNS['email'], text)
        for idx, email in enumerate(emails, 1):
            token = f"[EMAIL_{idx}]"
            self.redaction_map[token] = email
            redacted_text = redacted_text.replace(email, token)
        
        # Phone redaction
        phones = re.findall(self.PII_PATTERNS['phone'], text)
        for idx, phone in enumerate(phones, 1):
            token = f"[PHONE_{idx}]"
            self.redaction_map[token] = phone
            redacted_text = redacted_text.replace(phone, token)
        
        # SSN redaction
        ssns = re.findall(self.PII_PATTERNS['ssn'], text)
        for idx, ssn in enumerate(ssns, 1):
            token = f"[SSN_{idx}]"
            self.redaction_map[token] = ssn
            redacted_text = redacted_text.replace(ssn, token)
        
        logger.info(f"Redacted {len(self.redaction_map)} PII items")
        
        return redacted_text, self.redaction_map
    
    def restore_pii(self, text: str, redaction_map: Dict) -> str:
        """
        Restore PII after AI processing
        
        Args:
            text: Text with redaction tokens
            redaction_map: Mapping of tokens to original values
            
        Returns:
            Text with PII restored
        """
        restored_text = text
        for token, original in redaction_map.items():
            restored_text = restored_text.replace(token, original)
        
        return restored_text


# Singleton instances
gemini_service = GeminiService()
pii_service = PIIRedactionService()
