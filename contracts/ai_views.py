"""
AI-Powered API Endpoints for CLM System
Provides: Hybrid search, contract analysis, document processing, templates
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging

from .models import Contract
from .serializers import ContractSerializer
from .ai_services import gemini_service, pii_service
from .search_services import hybrid_search_service
from .tasks import generate_contract_async, generate_embeddings_for_contract, process_ocr_document

logger = logging.getLogger(__name__)


class SearchViewSet(viewsets.ViewSet):
    """
    Hybrid Search API
    
    Endpoints:
    - POST /api/search/global/ - Global hybrid search
    - GET /api/search/suggestions/ - Autocomplete suggestions
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='global')
    def global_search(self, request):
        """
        Global hybrid search across contracts
        
        Request Body:
        {
            "query": "employment agreement",
            "mode": "hybrid",  // or "keyword", "semantic"
            "filters": {
                "status": "active",
                "date_gte": "2024-01-01",
                "contract_type": "MSA"
            },
            "limit": 10
        }
        
        Response:
        {
            "results": [
                {
                    "id": "uuid",
                    "title": "...",
                    "score": 0.85,
                    "match_type": "hybrid",
                    "contract": {...}
                }
            ],
            "total": 25,
            "mode": "hybrid",
            "query": "employment agreement"
        }
        """
        query = request.data.get('query', '')
        mode = request.data.get('mode', 'hybrid')
        filters = request.data.get('filters', {})
        limit = request.data.get('limit', 10)
        
        if not query:
            return Response(
                {'error': 'Query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tenant_id = str(request.user.tenant_id)
        
        try:
            results = hybrid_search_service.search_contracts(
                query=query,
                tenant_id=tenant_id,
                mode=mode,
                filters=filters,
                limit=limit
            )
            
            # Enrich with full contract data
            enriched_results = []
            for result in results:
                try:
                    contract = Contract.objects.get(id=result['id'], tenant_id=tenant_id)
                    enriched_results.append({
                        **result,
                        'contract': ContractSerializer(contract).data
                    })
                except Contract.DoesNotExist:
                    continue
            
            return Response({
                'results': enriched_results,
                'total': len(enriched_results),
                'mode': mode,
                'query': query
            })
            
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='suggestions')
    def suggestions(self, request):
        """
        Autocomplete suggestions for search
        
        Query Params:
        - q: Partial query string
        - limit: Max suggestions (default 5)
        
        Response:
        {
            "suggestions": ["Employment Agreement", "NDA Template", ...]
        }
        """
        partial_query = request.query_params.get('q', '')
        limit = int(request.query_params.get('limit', 5))
        tenant_id = str(request.user.tenant_id)
        
        if len(partial_query) < 2:
            return Response({'suggestions': []})
        
        try:
            suggestions = hybrid_search_service.get_search_suggestions(
                partial_query=partial_query,
                tenant_id=tenant_id,
                limit=limit
            )
            
            return Response({'suggestions': suggestions})
            
        except Exception as e:
            logger.error(f"Suggestions failed: {e}", exc_info=True)
            return Response({'suggestions': []})


class AIAnalysisViewSet(viewsets.ViewSet):
    """
    AI-Powered Analysis Endpoints
    
    Endpoints:
    - POST /api/analysis/compare/ - Compare two contracts
    - GET /api/contracts/{id}/related/ - Find related contracts
    - POST /api/analysis/clause-summary/ - Summarize clause
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='compare')
    def compare_contracts(self, request):
        """
        AI-powered contract comparison
        
        Request Body:
        {
            "contract_a_id": "uuid",
            "contract_b_id": "uuid"
        }
        
        Response:
        {
            "summary": "...",
            "key_differences": [...],
            "risk_assessment": "...",
            "recommendation": "..."
        }
        """
        contract_a_id = request.data.get('contract_a_id')
        contract_b_id = request.data.get('contract_b_id')
        tenant_id = str(request.user.tenant_id)
        
        if not contract_a_id or not contract_b_id:
            return Response(
                {'error': 'Both contract_a_id and contract_b_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            contract_a = get_object_or_404(Contract, id=contract_a_id, tenant_id=tenant_id)
            contract_b = get_object_or_404(Contract, id=contract_b_id, tenant_id=tenant_id)
            
            # Get contract text
            text_a = contract_a.metadata.get('generated_text', contract_a.description or contract_a.title)
            text_b = contract_b.metadata.get('generated_text', contract_b.description or contract_b.title)
            
            # AI comparison
            comparison = gemini_service.compare_contracts(text_a, text_b)
            
            return Response({
                'contract_a': {
                    'id': str(contract_a.id),
                    'title': contract_a.title
                },
                'contract_b': {
                    'id': str(contract_b.id),
                    'title': contract_b.title
                },
                'comparison': comparison
            })
            
        except Exception as e:
            logger.error(f"Contract comparison failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='related')
    def related_contracts(self, request, pk=None):
        """
        Find semantically related contracts
        
        URL: GET /api/contracts/{id}/related/
        
        Query Params:
        - limit: Max results (default 5)
        
        Response:
        {
            "related": [
                {
                    "id": "uuid",
                    "title": "...",
                    "similarity_score": 0.92,
                    "contract": {...}
                }
            ]
        }
        """
        tenant_id = str(request.user.tenant_id)
        limit = int(request.query_params.get('limit', 5))
        
        try:
            contract = get_object_or_404(Contract, id=pk, tenant_id=tenant_id)
            
            # Check if this contract has an embedding yet
            if not contract.metadata or not contract.metadata.get('embedding'):
                return Response(
                    {
                        'message': 'This contract is still processing its embedding.',
                        'status': 'processing',
                        'related': []
                    },
                    status=status.HTTP_202_ACCEPTED
                )
            
            # Find similar contracts
            similar = hybrid_search_service.find_similar_contracts(
                contract_id=str(contract.id),
                tenant_id=tenant_id,
                limit=limit
            )
            
            # Enrich with full data
            enriched = []
            for item in similar:
                try:
                    related_contract = Contract.objects.get(id=item['id'], tenant_id=tenant_id)
                    enriched.append({
                        'id': item['id'],
                        'similarity_score': item['score'],
                        'contract': ContractSerializer(related_contract).data
                    })
                except Contract.DoesNotExist:
                    continue
            
            return Response({
                'source_contract': {
                    'id': str(contract.id),
                    'title': contract.title
                },
                'related': enriched
            })
            
        except Exception as e:
            logger.error(f"Related contracts search failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='clause-summary')
    def clause_summary(self, request):
        """
        Generate plain-English summary of legal clause
        
        Request Body:
        {
            "clause_text": "Party A hereby indemnifies..."  // or "text"
        }
        
        Response:
        {
            "original_text": "...",
            "summary": "This means Party A agrees to cover any legal costs...",
            "key_points": [...]
        }
        """
        # Accept both 'clause_text' and 'text' for flexibility
        clause_text = request.data.get('clause_text') or request.data.get('text') or ''
        
        if not clause_text:
            return Response(
                {'error': 'clause_text or text parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            summary = gemini_service.generate_clause_summary(clause_text)
            
            return Response({
                'original_text': clause_text,
                'summary': summary
            })
            
        except Exception as e:
            logger.error(f"Clause summary failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DocumentProcessingViewSet(viewsets.ViewSet):
    """
    Document Processing Endpoints (OCR, Extraction)
    
    Endpoints:
    - POST /api/documents/{id}/reprocess/ - Reprocess OCR
    - GET /api/documents/{id}/ocr-status/ - Check OCR status
    - GET /api/documents/{id}/extracted-text/ - Get extracted text
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['post'], url_path='reprocess')
    def reprocess_ocr(self, request, pk=None):
        """
        Trigger OCR reprocessing for a document
        
        URL: POST /api/documents/{id}/reprocess/
        
        Response:
        {
            "status": "processing",
            "task_id": "celery-task-uuid",
            "message": "OCR processing started"
        }
        """
        tenant_id = str(request.user.tenant_id)
        
        # Note: In production, you'd have a Document model
        # For now, we'll use contract metadata
        try:
            contract = get_object_or_404(Contract, id=pk, tenant_id=tenant_id)
            
            # Start OCR task (django-background-tasks)
            process_ocr_document(str(contract.id))
            
            # Update contract metadata
            contract.metadata = contract.metadata or {}
            contract.metadata['ocr_status'] = 'processing'
            contract.save(update_fields=['metadata'])
            
            return Response({
                'status': 'processing',
                'message': 'OCR processing started'
            })
            
        except Exception as e:
            logger.error(f"OCR reprocess failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='ocr-status')
    def ocr_status(self, request, pk=None):
        """
        Check OCR processing status
        
        URL: GET /api/documents/{id}/ocr-status/
        
        Response:
        {
            "status": "completed|processing|failed",
            "progress": 75,
            "error": null
        }
        """
        tenant_id = str(request.user.tenant_id)
        
        try:
            contract = get_object_or_404(Contract, id=pk, tenant_id=tenant_id)
            
            ocr_status = contract.metadata.get('ocr_status', 'not_started')
            
            return Response({
                'status': ocr_status,
                'task_id': contract.metadata.get('ocr_task_id'),
                'message': f'OCR status: {ocr_status}'
            })
            
        except Exception as e:
            logger.error(f"OCR status check failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='extracted-text')
    def extracted_text(self, request, pk=None):
        """
        Get OCR extracted text
        
        URL: GET /api/documents/{id}/extracted-text/
        
        Response:
        {
            "text": "...",
            "confidence": 0.95,
            "word_count": 1234
        }
        """
        tenant_id = str(request.user.tenant_id)
        
        try:
            contract = get_object_or_404(Contract, id=pk, tenant_id=tenant_id)
            
            extracted_text = contract.metadata.get('ocr_text', '')
            
            return Response({
                'text': extracted_text,
                'confidence': contract.metadata.get('ocr_confidence', 0),
                'word_count': len(extracted_text.split())
            })
            
        except Exception as e:
            logger.error(f"Extract text retrieval failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AsyncContractGenerationViewSet(viewsets.ViewSet):
    """
    Async Contract Generation with WebSocket Updates
    
    Endpoints:
    - POST /api/generation/start/ - Start async generation
    - GET /api/generation/{task_id}/status/ - Check status
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='start')
    def start_generation(self, request):
        """
        Start async contract generation
        
        Request Body:
        {
            "title": "Service Agreement",
            "contract_type": "MSA",
            "description": "...",
            "variables": {
                "party_a": "Acme Corp",
                "party_b": "Client Inc",
                "term": "12 months"
            },
            "special_instructions": "Include termination clause"
        }
        
        Response (202 Accepted):
        {
            "task_id": "celery-task-uuid",
            "contract_id": "contract-uuid",
            "status": "processing",
            "message": "Contract generation started. You will be notified when ready."
        }
        """
        tenant_id = str(request.user.tenant_id)
        user_id = str(request.user.user_id)
        
        title = request.data.get('title', '')
        contract_type = request.data.get('contract_type', 'General')
        description = request.data.get('description', '')
        variables = request.data.get('variables', {})
        special_instructions = request.data.get('special_instructions', '')
        
        if not title:
            return Response(
                {'error': 'Title is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Create contract record
            contract = Contract.objects.create(
                tenant_id=tenant_id,
                created_by=user_id,
                title=title,
                contract_type=contract_type,
                description=description,
                status='draft',
                metadata={
                    'generation_status': 'queued',
                    'variables': variables,
                    'special_instructions': special_instructions
                }
            )
            
            # Start async generation (django-background-tasks)
            generate_contract_async(
                contract_id=str(contract.id),
                template_type=contract_type,
                variables=variables,
                special_instructions=special_instructions
            )
            
            # Store task info
            contract.metadata['generation_task_started'] = True
            contract.save(update_fields=['metadata'])
            
            logger.info(f"Started async generation for contract {contract.id}")
            
            return Response({
                'contract_id': str(contract.id),
                'status': 'processing',
                'message': 'Contract generation started. You will be notified when ready.'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Failed to start generation: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='status')
    def generation_status(self, request, pk=None):
        """
        Check contract generation status
        
        URL: GET /api/generation/{contract_id}/status/
        
        Response:
        {
            "status": "completed|processing|failed",
            "progress": 75,
            "confidence_score": 8,
            "error": null
        }
        """
        tenant_id = str(request.user.tenant_id)
        
        try:
            contract = get_object_or_404(Contract, id=pk, tenant_id=tenant_id)
            
            generation_status = contract.metadata.get('generation_status', 'not_started')
            
            response_data = {
                'contract_id': str(contract.id),
                'status': generation_status,
                'task_id': contract.metadata.get('generation_task_id')
            }
            
            if generation_status == 'completed':
                metadata = contract.metadata.get('generation_metadata', {})
                response_data['confidence_score'] = metadata.get('confidence_score', 0)
                response_data['generated_text'] = contract.metadata.get('generated_text', '')
            elif generation_status == 'failed':
                response_data['error'] = contract.metadata.get('generation_error', 'Unknown error')
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Status check failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
