from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse
from .models import AIInferenceModel, DraftGenerationTask, ClauseAnchor
from .serializers import AIInferenceSerializer, DraftGenerationTaskSerializer, ClauseAnchorSerializer
from .tasks import generate_draft_async
from .pii_protection import PIIScrubber, ScrubberAuditLog
from django.utils import timezone
import uuid
import logging
import json
from repository.models import Document
from repository.embeddings_service import VoyageEmbeddingsService
import google.generativeai as genai
from django.conf import settings
import numpy as np
from contracts.models import Clause

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)


class AIViewSet(viewsets.ViewSet):
    """
    AI Endpoints for draft generation, metadata extraction, and classification
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='generate/draft')
    def generate_draft(self, request):
        """
        Endpoint 3: Draft Generation (Async)
        POST /api/v1/ai/generate/draft/
        """
        contract_type = request.data.get('contract_type')
        input_params = request.data.get('input_params', {})
        template_id = request.data.get('template_id')

        if not contract_type:
            return Response(
                {'error': 'contract_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create task record in DB
        task = DraftGenerationTask.objects.create(
            tenant_id=request.user.tenant_id,
            user_id=request.user.user_id,
            contract_type=contract_type,
            input_params=input_params,
            template_id=template_id,
            task_id=str(uuid.uuid4()),  # Placeholder, will be updated by celery
            status='pending'
        )

        # Queue Celery task
        celery_task = generate_draft_async.delay(
            task_id=str(task.id),
            tenant_id=str(request.user.tenant_id),
            contract_type=contract_type,
            input_params=input_params,
            template_id=template_id
        )
        
        # Update task with actual Celery task ID
        task.task_id = celery_task.id
        task.save()

        serializer = DraftGenerationTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['get'], url_path='generate/status/(?P<task_id>[^/.]+)')
    def get_draft_status(self, request, task_id=None):
        """
        GET /api/v1/ai/generate/status/{task_id}/
        """
        try:
            task = DraftGenerationTask.objects.get(
                task_id=task_id,
                tenant_id=request.user.tenant_id
            )
            serializer = DraftGenerationTaskSerializer(task)
            return Response(serializer.data)
        except DraftGenerationTask.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'], url_path='extract/metadata')
    def extract_metadata(self, request):
        """
        Endpoint 4: Metadata Extraction
        POST /api/v1/ai/extract/metadata/
        """
        text = request.data.get('text')
        if not text:
            return Response({'error': 'text is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Scrub PII before sending to Gemini
            scrubbed_text, redactions = PIIScrubber.scrub(text)
            
            # Log the scrubbing operation
            ScrubberAuditLog.log_scrub_operation(
                user_id=str(request.user.user_id),
                tenant_id=str(request.user.tenant_id),
                text_length=len(text),
                redactions=redactions,
                operation_type='metadata_extraction'
            )
            
            if redactions:
                logger.info(f"Scrubbed {sum(len(v) for v in redactions.values())} PII instances before metadata extraction")

            model = genai.GenerativeModel('gemini-2.0-flash')
            
            prompt = f"""
            Extract the following metadata from this contract text.
            Return the output as a valid JSON object with the specified keys.

            Schema:
            {{
                "parties": [
                    {{"name": "string", "role": "string (e.g., 'Landlord', 'Tenant')"}},
                    {{"name": "string", "role": "string"}}
                ],
                "effective_date": "YYYY-MM-DD or null",
                "termination_date": "YYYY-MM-DD or null",
                "contract_value": {{
                    "amount": "number or null",
                    "currency": "string (e.g., 'USD') or null"
                }}
            }}

            Contract Text:
            ---
            {scrubbed_text[:8000]}
            ---
            """
            
            response = model.generate_content(prompt)
            
            # Basic parsing and validation
            import json
            try:
                # Gemini often wraps JSON in ```json ... ```
                clean_response = response.text.strip().replace('```json', '').replace('```', '').strip()
                extracted_data = json.loads(clean_response)
                return Response({'metadata': extracted_data}, status=status.HTTP_200_OK)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse Gemini response for metadata extraction: {e}")
                return Response({'error': 'Failed to parse AI response', 'details': response.text}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Metadata extraction error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=False, methods=['post'], url_path='classify/clause')
    def classify_clause(self, request):
        """
        Endpoint 5: Clause Classification
        POST /api/v1/ai/classify/clause/
        """
        clause_text = request.data.get('clause_text')
        if not clause_text:
            return Response({'error': 'clause_text is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get all active anchor clauses with embeddings
            anchors = ClauseAnchor.objects.filter(is_active=True, embedding__isnull=False)
            if not anchors.exists():
                return Response({'error': 'No anchor clauses configured for classification'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Generate embedding for input text
            embeddings_service = VoyageEmbeddingsService()
            query_embedding = embeddings_service.embed_query(clause_text)

            if not query_embedding:
                return Response({'error': 'Failed to generate embedding for input text'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            query_vec = np.array(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query_vec)

            scores = []
            for anchor in anchors:
                anchor_vec = np.array(anchor.embedding, dtype=np.float32)
                anchor_norm = np.linalg.norm(anchor_vec)
                
                if anchor_norm > 0 and query_norm > 0:
                    similarity = np.dot(query_vec, anchor_vec) / (query_norm * anchor_norm)
                    scores.append({
                        'label': anchor.label,
                        'category': anchor.category,
                        'confidence': float(similarity)
                    })

            if not scores:
                return Response({'error': 'Could not classify clause'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Find nearest anchor by cosine distance
            best_match = max(scores, key=lambda x: x['confidence'])

            return Response(best_match, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Clause classification error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='generate/template-stream')
    def generate_template_stream(self, request):
        """Stream AI-generated template edits as Server-Sent Events (SSE).

        POST /api/v1/ai/generate/template-stream/

        Body:
          - prompt: string (required)
          - current_text: string (required)
          - contract_type: string (optional)

        Emits SSE events:
          - event: delta, data: {"delta": "..."}
          - event: done,  data: {"ok": true}
          - event: error, data: {"error": "..."}
        """

        prompt = (request.data.get('prompt') or '').strip()
        current_text = request.data.get('current_text')
        contract_type = (request.data.get('contract_type') or '').strip() or None

        if not prompt:
            return Response({'error': 'prompt is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(current_text, str) or not current_text.strip():
            return Response({'error': 'current_text is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not (settings.GEMINI_API_KEY or '').strip():
            return Response({'error': 'GEMINI_API_KEY is not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        model_name = getattr(settings, 'GEMINI_CONTRACT_EDIT_MODEL', None) or 'gemini-2.5-pro'

        # Retrieve relevant clauses using Voyage Law-2.
        def _pick_relevant_clauses() -> list[dict]:
            try:
                embeddings_service = VoyageEmbeddingsService()
                query_embedding = embeddings_service.embed_query(prompt)
                if not query_embedding:
                    return []

                qs = Clause.objects.filter(tenant_id=request.user.tenant_id, status='published')
                if contract_type:
                    qs = qs.filter(contract_type=contract_type)

                items = list(qs.order_by('-updated_at')[:40])
                if not items:
                    return []

                texts = [f"{c.name}\n\n{c.content}"[:8000] for c in items]
                embeddings = embeddings_service.embed_batch(texts)

                q = np.array(query_embedding, dtype=np.float32)
                qn = float(np.linalg.norm(q))
                if qn <= 0:
                    return []

                scored: list[tuple[float, Clause]] = []
                for clause, emb in zip(items, embeddings):
                    if not emb:
                        continue
                    v = np.array(emb, dtype=np.float32)
                    vn = float(np.linalg.norm(v))
                    if vn <= 0:
                        continue
                    sim = float(np.dot(q, v) / (qn * vn))
                    scored.append((sim, clause))

                scored.sort(key=lambda x: x[0], reverse=True)
                out = []
                for sim, clause in scored[:5]:
                    out.append(
                        {
                            'clause_id': clause.clause_id,
                            'name': clause.name,
                            'similarity': round(sim, 4),
                            'content': clause.content,
                        }
                    )
                return out
            except Exception:
                return []

        relevant = _pick_relevant_clauses()
        clauses_block = ''
        if relevant:
            blocks = []
            for c in relevant:
                blocks.append(f"- [{c['clause_id']}] {c['name']} (sim={c['similarity']})\n{c['content']}")
            clauses_block = "\n\n".join(blocks)[:12000]

        base_text = (current_text or '')[:20000]
        user_instruction = prompt[:4000]

        generation_prompt = f"""
You are a senior legal contract drafting assistant.

Task:
- Apply the user's instruction to the existing contract text.
- Keep the contract coherent and legally styled.
- Preserve headings/numbering where possible.
- If the user asks to insert a clause, add it in the most appropriate section.
- If the user asks to update a term, change it consistently everywhere.

Output rules:
- Return ONLY the full revised contract as plain text.
- Do not include markdown fences, commentary, or JSON.

User instruction:
{user_instruction}

Existing contract text:
---
{base_text}
---

Relevant clause library (optional):
---
{clauses_block or '(none)'}
---
""".strip()

        def event_stream():
            try:
                yield f"event: meta\ndata: {json.dumps({'model': model_name})}\n\n"
            except Exception:
                pass

            try:
                model = genai.GenerativeModel(model_name)
                for chunk in model.generate_content(generation_prompt, stream=True):
                    delta = getattr(chunk, 'text', None)
                    if not delta:
                        continue
                    yield f"event: delta\ndata: {json.dumps({'delta': delta})}\n\n"
                yield f"event: done\ndata: {json.dumps({'ok': True})}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        resp = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        resp['Cache-Control'] = 'no-cache'
        resp['X-Accel-Buffering'] = 'no'
        return resp

