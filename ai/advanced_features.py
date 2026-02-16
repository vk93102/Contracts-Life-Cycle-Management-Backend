from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import google.genai as genai
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from repository.models import Document, DocumentChunk
from repository.embeddings_service import VoyageEmbeddingsService
import json
import logging
import uuid
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)
genai.configure(api_key=settings.GEMINI_API_KEY)


class AdvancedAIViewSet(viewsets.ViewSet):
   
    permission_classes = [IsAuthenticated]
    @action(detail=False, methods=['post'], url_path='extract/obligations')
    def extract_obligations(self, request):
        """
        Extract action items and obligations from contracts
        
        POST /api/v1/ai/extract/obligations/
        
        Request:
        {
            "document_id": "uuid",
            "document_text": "optional for testing"
        }
        
        Response:
        {
            "obligations": [
                {
                    "action": "Maintain confidentiality",
                    "owner": "Service Provider",
                    "due_date": "2025-01-31",
                    "priority": "high",
                    "source_text": "The Licensee shall maintain confidentiality..."
                },
                ...
            ]
        }
        """
        try:
            document_id = request.data.get('document_id')
            document_text = request.data.get('document_text')
            
            if not document_id and not document_text:
                return Response(
                    {'error': 'Either document_id or document_text is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get document text
            if document_text:
                full_text = document_text
            else:
                try:
                    document = Document.objects.get(
                        id=document_id,
                        tenant_id=request.user.tenant_id
                    )
                    full_text = document.full_text
                except Document.DoesNotExist:
                    return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
            
            # Use Gemini to extract obligations
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            extraction_prompt = f"""Extract all action items and obligations from this contract.

IMPORTANT: Return ONLY valid JSON with this structure:
{{
    "obligations": [
        {{
            "action": "specific action required",
            "owner": "party responsible",
            "due_date": "YYYY-MM-DD or null",
            "priority": "high|medium|low",
            "source_text": "relevant excerpt from contract"
        }}
    ]
}}

EXTRACTION RULES:
1. Action: Extract what must be done (not subjective statements)
2. Owner: Who is responsible for the action
3. Due Date: Look for date references, deadlines, "by date X", "within X days"
4. Priority: Assess importance (high for critical/mandatory, low for optional)
5. Source: Include the actual contract text that defines the obligation

Focus on:
- Payment obligations (when, how much, to whom)
- Delivery/Performance requirements
- Insurance/Indemnification requirements
- Confidentiality and IP protection duties
- Termination conditions
- Reporting requirements

Contract excerpt (first 8000 chars):
---
{full_text[:8000]}
---

Return ONLY the JSON object."""

            logger.info(f"Extracting obligations from document: {document_id}")
            response = model.generate_content(extraction_prompt)
            
            try:
                response_text = response.text.strip()
                
                # Clean markdown if present
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.startswith('```'):
                    response_text = response_text[3:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                
                response_text = response_text.strip()
                result = json.loads(response_text)
                
                logger.info(f"Extracted {len(result.get('obligations', []))} obligations")
                return Response(result, status=status.HTTP_200_OK)
            
            except json.JSONDecodeError:
                logger.error("Failed to parse obligations response")
                return Response(
                    {'obligations': []},
                    status=status.HTTP_200_OK
                )
        
        except Exception as e:
            logger.error(f"Obligation extraction error: {e}")
            return Response(
                {'error': 'Obligation extraction failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # ==========================================
    # FEATURE 2: CLAUSE SUGGESTIONS (RAG)
    # ==========================================
    
    @action(detail=False, methods=['post'], url_path='clause/suggest')
    def suggest_clause(self, request):
        """
        Suggest improved clause versions using RAG
        
        POST /api/v1/ai/clause/suggest/
        
        Request:
        {
            "current_clause": "The vendor shall provide services...",
            "instruction": "Make this more specific about deliverables",
            "document_id": "optional - use this tenant's documents as context"
        }
        
        Response:
        {
            "original": "The vendor shall provide services...",
            "suggested": "The vendor shall provide the following services within 30 days...",
            "rationale": "Added specificity about timeline and clear deliverables",
            "similar_clauses": [
                {
                    "document_name": "Contract_A.pdf",
                    "text": "similar clause from another contract",
                    "similarity_score": 0.85
                }
            ]
        }
        """
        try:
            current_clause = request.data.get('current_clause', '').strip()
            instruction = request.data.get('instruction', '').strip()
            
            if not current_clause:
                return Response(
                    {'error': 'current_clause is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not instruction:
                instruction = "Improve this clause to be more specific and enforceable"
            
            # Use embeddings service to find similar clauses (RAG)
            embeddings_service = VoyageEmbeddingsService()
            
            try:
                clause_embedding = embeddings_service.generate_embeddings(current_clause)
            except Exception as e:
                logger.warning(f"Could not generate clause embedding: {e}")
                clause_embedding = None
            
            # Find similar clauses from this tenant's documents
            similar_clauses = []
            if clause_embedding:
                try:
                    chunks = DocumentChunk.objects.filter(
                        document__tenant_id=request.user.tenant_id
                    )[:100]
                    
                    similarities = []
                    for chunk in chunks:
                        if chunk.embedding:
                            try:
                                chunk_vec = np.array(chunk.embedding, dtype=np.float32)
                                query_vec = np.array(clause_embedding, dtype=np.float32)
                                
                                # Cosine similarity
                                similarity = np.dot(query_vec, chunk_vec) / (
                                    np.linalg.norm(query_vec) * np.linalg.norm(chunk_vec)
                                )
                                
                                if similarity > 0.7:  # High similarity threshold
                                    similarities.append({
                                        'chunk': chunk,
                                        'similarity': float(similarity)
                                    })
                            except:
                                pass
                    
                    # Sort by similarity and take top 3
                    similarities.sort(key=lambda x: x['similarity'], reverse=True)
                    similar_clauses = [
                        {
                            'document_name': s['chunk'].document.filename,
                            'text': s['chunk'].text[:300] + '...' if len(s['chunk'].text) > 300 else s['chunk'].text,
                            'similarity_score': s['similarity']
                        }
                        for s in similarities[:3]
                    ]
                except Exception as e:
                    logger.warning(f"Error finding similar clauses: {e}")
            
            # Use Gemini to generate suggestion
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            rag_context = ""
            if similar_clauses:
                rag_context = "\n\nSimilar clauses from other contracts:\n"
                for clause in similar_clauses:
                    rag_context += f"- {clause['text']}\n"
            
            suggestion_prompt = f"""Given this contract clause, provide a more improved version.

Original Clause:
{current_clause}

Instruction: {instruction}

{rag_context}

Respond with ONLY valid JSON:
{{
    "suggested": "improved clause text",
    "rationale": "brief explanation of improvements"
}}

Improvements should focus on:
- Clarity and specificity
- Measurable deliverables/deadlines
- Risk mitigation
- Legal enforceability
- Alignment with industry standards"""

            logger.info(f"Generating clause suggestion")
            response = model.generate_content(suggestion_prompt)
            
            try:
                response_text = response.text.strip()
                
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.startswith('```'):
                    response_text = response_text[3:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                
                result = json.loads(response_text.strip())
                result['original'] = current_clause
                result['similar_clauses'] = similar_clauses
                
                logger.info("Clause suggestion generated successfully")
                return Response(result, status=status.HTTP_200_OK)
            
            except json.JSONDecodeError:
                logger.error("Failed to parse suggestion response")
                return Response(
                    {'error': 'Failed to generate suggestion'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        except Exception as e:
            logger.error(f"Clause suggestion error: {e}")
            return Response(
                {'error': 'Clause suggestion failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # ==========================================
    # FEATURE 3: DOCUMENT SUMMARIZATION
    # ==========================================
    
    @action(detail=False, methods=['get'], url_path='summarize/(?P<doc_id>[^/.]+)')
    def summarize_document(self, request, doc_id=None):
        """
        Summarize document with Redis caching
        
        GET /api/v1/ai/summarize/{doc_id}/
        
        Response:
        {
            "document_id": "uuid",
            "summary": "3-5 sentence overview",
            "key_points": [
                "Point 1",
                "Point 2",
                "Point 3"
            ],
            "cached": false,
            "cache_expires_at": "2026-01-19T20:00:00Z"
        }
        """
        try:
            # Validate document access
            try:
                document = Document.objects.get(
                    id=doc_id,
                    tenant_id=request.user.tenant_id
                )
            except Document.DoesNotExist:
                return Response(
                    {'error': 'Document not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check cache first
            cache_key = f"doc_summary:{doc_id}:{request.user.tenant_id}"
            cached_result = cache.get(cache_key)
            
            if cached_result:
                cached_result['cached'] = True
                return Response(cached_result, status=status.HTTP_200_OK)
            
            # Generate summary with Gemini
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            summary_prompt = f"""Create a concise summary of this contract.

CONTRACT TEXT (first 10,000 characters):
---
{document.full_text[:10000]}
---

Respond with ONLY valid JSON:
{{
    "summary": "3-5 sentence overview of the contract's purpose and key terms",
    "key_points": [
        "important point 1",
        "important point 2",
        "important point 3",
        "important point 4",
        "important point 5"
    ]
}}

Summary should cover:
- What type of contract this is
- Who the main parties are
- What value/services are involved
- Key obligations
- Termination conditions"""

            logger.info(f"Generating summary for document: {doc_id}")
            response = model.generate_content(summary_prompt)
            
            try:
                response_text = response.text.strip()
                
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.startswith('```'):
                    response_text = response_text[3:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                
                result = json.loads(response_text.strip())
                result['document_id'] = str(doc_id)
                result['cached'] = False
                
                # Cache for 24 hours
                cache_duration = 24 * 60 * 60
                cache.set(cache_key, result, cache_duration)
                
                # Add cache expiration time
                result['cache_expires_at'] = (
                    timezone.now() + timezone.timedelta(seconds=cache_duration)
                ).isoformat() + 'Z'
                
                logger.info(f"Document summary generated and cached")
                return Response(result, status=status.HTTP_200_OK)
            
            except json.JSONDecodeError:
                logger.error("Failed to parse summary response")
                return Response(
                    {'error': 'Failed to generate summary'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            return Response(
                {'error': 'Summarization failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # ==========================================
    # FEATURE 4: SIMILAR CLAUSE FINDER
    # ==========================================
    
    @action(detail=False, methods=['post'], url_path='search/similar')
    def find_similar_clauses(self, request):
        """
        Find similar clauses across all tenant documents
        
        POST /api/v1/search/similar/
        
        Request:
        {
            "text": "clause text to search for",
            "top_k": 10,  # number of results
            "min_similarity": 0.7  # minimum similarity score
        }
        
        Response:
        {
            "query": "clause text",
            "results": [
                {
                    "rank": 1,
                    "document_id": "uuid",
                    "document_name": "contract.pdf",
                    "text": "similar clause from document",
                    "similarity_score": 0.92,
                    "context": "surrounding text for context"
                }
            ],
            "total_results": 5
        }
        """
        try:
            query_text = request.data.get('text', '').strip()
            top_k = request.data.get('top_k', 10)
            min_similarity = request.data.get('min_similarity', 0.7)
            
            if not query_text:
                return Response(
                    {'error': 'text is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate parameters
            top_k = min(max(1, top_k), 50)  # 1-50 results
            min_similarity = max(0.0, min(1.0, min_similarity))
            
            # Generate embedding for query
            embeddings_service = VoyageEmbeddingsService()
            
            try:
                query_embedding = embeddings_service.generate_embeddings(query_text)
            except Exception as e:
                logger.error(f"Failed to generate query embedding: {e}")
                return Response(
                    {'error': 'Failed to process search query'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Search all chunks for this tenant
            chunks = DocumentChunk.objects.filter(
                document__tenant_id=request.user.tenant_id
            ).select_related('document')
            
            similarities = []
            query_vec = np.array(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query_vec)
            
            logger.info(f"Searching {chunks.count()} chunks for similar clauses")
            
            for chunk in chunks:
                if not chunk.embedding:
                    continue
                
                try:
                    chunk_vec = np.array(chunk.embedding, dtype=np.float32)
                    chunk_norm = np.linalg.norm(chunk_vec)
                    
                    if chunk_norm == 0:
                        continue
                    
                    # Cosine similarity
                    similarity = np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm)
                    
                    # Normalize to 0-1
                    normalized_similarity = (similarity + 1) / 2
                    
                    if normalized_similarity >= min_similarity:
                        similarities.append({
                            'chunk': chunk,
                            'similarity': float(normalized_similarity)
                        })
                
                except Exception as e:
                    logger.debug(f"Error processing chunk {chunk.id}: {e}")
                    continue
            
            # Sort and limit results
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            top_results = similarities[:top_k]
            
            # Format results
            results = [
                {
                    'rank': i + 1,
                    'document_id': str(r['chunk'].document_id),
                    'document_name': r['chunk'].document.filename,
                    'text': r['chunk'].text[:500],
                    'similarity_score': r['similarity'],
                    'context': r['chunk'].text[-200:] if len(r['chunk'].text) > 500 else ''
                }
                for i, r in enumerate(top_results)
            ]
            
            return Response({
                'query': query_text,
                'results': results,
                'total_results': len(results)
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Similar clause search error: {e}")
            return Response(
                {'error': 'Search failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
