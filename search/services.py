"""
Search Services - Production Implementation
Uses PostgreSQL FTS + Voyage AI Embeddings (Pre-trained Legal Model)
"""
import os
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, F, Value, FloatField
from django.db.models.functions import Cast
from django.conf import settings

from pgvector.django import CosineDistance

logger = logging.getLogger(__name__)


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

class ModelConfig:
    """Centralized model configuration"""
    
    # Voyage AI - Legal Document Embedding Model
    VOYAGE_MODEL = "voyage-law-2"
    VOYAGE_EMBEDDING_DIMENSION = 1024
    VOYAGE_API_KEY = settings.VOYAGE_API_KEY
    
    # Search Strategy
    FTS_STRATEGY = "PostgreSQL FTS + GIN Index"
    SEMANTIC_STRATEGY = "pgvector + Voyage AI Embeddings"
    HYBRID_STRATEGY = "Weighted Hybrid (60% semantic + 30% FTS + 10% recency)"


# ============================================================================
# 1. EMBEDDING SERVICE (Voyage AI)
# ============================================================================

class EmbeddingService:
    """
    Generate embeddings using Voyage AI (Pre-trained Legal Model)
    - Model: voyage-law-2 (specialized for legal documents)
    - Dimension: 1024
    - Type: Pre-trained, no training required
    """
    
    MODEL = ModelConfig.VOYAGE_MODEL
    DIMENSION = ModelConfig.VOYAGE_EMBEDDING_DIMENSION
    API_KEY = ModelConfig.VOYAGE_API_KEY
    
    _client = None
    
    @classmethod
    def _get_client(cls):
        """Lazy load Voyage AI client"""
        if cls._client is None and cls.API_KEY:
            try:
                import voyageai
                cls._client = voyageai.Client(api_key=cls.API_KEY)
                logger.info(f"Initialized Voyage AI client with model: {cls.MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize Voyage AI: {str(e)}")
        return cls._client
    
    @staticmethod
    def generate(text: str, input_type: str = "document") -> Optional[List[float]]:
        """
        Generate embedding using Voyage AI
        
        Args:
            text: Text to embed
            input_type: "document" for documents, "query" for search queries
        
        Returns:
            1024-dimensional embedding or None on failure
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            client = EmbeddingService._get_client()
            
            if not client:
                logger.error("Voyage AI client not initialized")
                return None
            
            # Call Voyage AI API
            response = client.embed(
                [text[:2000]],  # Limit to 2000 chars
                model=EmbeddingService.MODEL,
                input_type=input_type
            )
            
            if response and response.embeddings and len(response.embeddings) > 0:
                embedding = response.embeddings[0]
                logger.debug(f"Generated {len(embedding)}-dim embedding for text ({len(text)} chars)")
                return embedding
            else:
                logger.error("Empty response from Voyage AI")
                return None
        
        except Exception as e:
            logger.error(f"Voyage AI embedding failed: {str(e)}")
            return None
    
    @staticmethod
    def batch_generate(texts: List[str], input_type: str = "document") -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts
        
        Args:
            texts: List of texts to embed
            input_type: "document" or "query"
        
        Returns:
            List of embeddings (some may be None on failure)
        """
        try:
            client = EmbeddingService._get_client()
            
            if not client or len(texts) == 0:
                return [None] * len(texts)
            
            # Limit each text to 2000 chars
            texts_limited = [t[:2000] if t else "" for t in texts]
            
            response = client.embed(
                texts_limited,
                model=EmbeddingService.MODEL,
                input_type=input_type
            )
            
            if response and response.embeddings:
                logger.info(f"Generated {len(response.embeddings)} embeddings via Voyage AI")
                return response.embeddings
            else:
                logger.error("Empty batch response from Voyage AI")
                return [None] * len(texts)
        
        except Exception as e:
            logger.error(f"Batch embedding failed: {str(e)}")
            return [None] * len(texts)


# ============================================================================
# 2. FULL-TEXT SEARCH SERVICE (PostgreSQL FTS)
# ============================================================================

class FullTextSearchService:
    """
    Full-text search using PostgreSQL FTS + GIN indexes
    
    - Strategy: PostgreSQL FTS (Full-Text Search)
    - Index Type: GIN (Generalized Inverted Index)
    - Performance: O(log n) lookup time
    - Best for: Exact keywords, legal terms, exact phrase matching
    """
    
    @staticmethod
    def search(query: str, tenant_id: str, limit: int = 50, entity_type: str | None = None):
        """
        Perform PostgreSQL FTS search
        
        Args:
            query: Search query (e.g., "service agreement")
            tenant_id: Filter by tenant
            limit: Max results to return
        
        Returns:
            List of matching documents sorted by relevance (highest first)
        """
        from .models import SearchIndexModel
        
        try:
            # Create search query with PostgreSQL FTS
            search_query = SearchQuery(query, search_type='plain')
            
            base = SearchIndexModel.objects.filter(tenant_id=tenant_id)
            if entity_type:
                base = base.filter(entity_type=entity_type)

            qs = base.annotate(
                rank=SearchRank('search_vector', search_query),
                trigram=TrigramSimilarity('title', query),
            )

            # Accept either strong FTS match or decent fuzzy (trigram) match.
            qs = qs.filter(Q(search_vector=search_query) | Q(trigram__gte=0.2)).annotate(
                score=(0.85 * F('rank')) + (0.15 * F('trigram'))
            )

            results = qs.order_by('-score')[:limit]
            
            logger.info(f"FTS Search: '{query}' returned {len(results)} results (strategy={ModelConfig.FTS_STRATEGY})")
            return results
        
        except Exception as e:
            logger.error(f"FTS search failed: {str(e)}")
            return SearchIndexModel.objects.none()
    
    @staticmethod
    def get_search_metadata(results: list) -> list:
        """Format search results with metadata (no dummy values)"""
        return [
            {
                'id': str(r.id),
                'entity_type': getattr(r, 'entity_type', 'document'),
                'entity_id': str(getattr(r, 'entity_id', '')),
                'title': getattr(r, 'title', 'Unknown'),
                'content': getattr(r, 'content', '')[:500],
                'keywords': getattr(r, 'keywords', []),
                'metadata': getattr(r, 'metadata', {}) or {},
                'relevance_score': float(getattr(r, 'rank', 0.0)),
                'search_strategy': ModelConfig.FTS_STRATEGY,
                'created_at': r.created_at.isoformat() if hasattr(r, 'created_at') and r.created_at else None,
                'updated_at': r.updated_at.isoformat() if hasattr(r, 'updated_at') and r.updated_at else None,
            }
            for r in results
        ]



# ============================================================================
# 3. SEMANTIC SEARCH SERVICE (pgvector + Voyage AI)
# ============================================================================

class SemanticSearchService:
    """
    Semantic search using pgvector + Voyage AI embeddings
    
    - Model: voyage-law-2 (legal documents specialist)
    - Dimension: 1024
    - Performance: O(log n) with IVFFLAT index
    - Best for: Meaning-based search, synonyms, paraphrases, legal concepts
    """
    
    @staticmethod
    def search(query: str, tenant_id: str, 
               similarity_threshold: float = 0.6, 
               limit: int = 50,
               entity_type: str | None = None) -> list:
        """
        Perform semantic search using Voyage AI embeddings
        
        Args:
            query: Search query text
            tenant_id: Filter by tenant
            similarity_threshold: Min cosine similarity (0-1)
            limit: Max results to return
        
        Returns:
            Results sorted by semantic similarity (highest first)
        """
        from .models import SearchIndexModel
        
        try:
            # Step 1: Generate query embedding with Voyage AI
            query_embedding = EmbeddingService.generate(
                query,
                input_type="query"
            )
            
            if not query_embedding:
                logger.warning(f"Failed to generate query embedding, falling back to FTS: '{query}'")
                return FullTextSearchService.search(query, tenant_id, limit=limit)
            
            # Step 2: Vector similarity via pgvector (cosine distance)
            # Cosine similarity = 1 - cosine_distance
            base = SearchIndexModel.objects.filter(tenant_id=tenant_id, embedding__isnull=False)
            if entity_type:
                base = base.filter(entity_type=entity_type)

            qs = (
                base
                .annotate(distance=CosineDistance('embedding', query_embedding))
                .annotate(similarity=Value(1.0, output_field=FloatField()) - F('distance'))
                .filter(similarity__gte=similarity_threshold)
                .order_by('-similarity')[:limit]
            )

            results = list(qs)
            logger.info(
                f"Semantic search (pgvector+Voyage): '{query}' returned {len(results)} results "
                f"(threshold={similarity_threshold})"
            )
            return results
        
        except Exception as e:
            logger.error(f"Semantic search failed: {str(e)}")
            # Fallback to full-text search
            return FullTextSearchService.search(query, tenant_id, limit=limit)
    
    @staticmethod
    def get_semantic_metadata(results: list) -> list:
        """Format semantic results with Voyage AI similarity scores"""
        return [
            {
                'id': str(r.id),
                'entity_type': getattr(r, 'entity_type', 'document'),
                'entity_id': str(getattr(r, 'entity_id', '')),
                'title': getattr(r, 'title', 'Unknown'),
                'content': getattr(r, 'content', '')[:500],
                'relevance_score': float(getattr(r, 'similarity', getattr(r, 'rank', 0.0))),
                'metadata': getattr(r, 'metadata', {}) or {},
                'embedding_model': ModelConfig.VOYAGE_MODEL,
                'embedding_dimension': ModelConfig.VOYAGE_EMBEDDING_DIMENSION,
                'created_at': r.created_at.isoformat() if hasattr(r, 'created_at') and r.created_at else None,
            }
            for r in results
        ]



# ============================================================================
# 4. HYBRID SEARCH SERVICE (FTS + Semantic)
# ============================================================================

class HybridSearchService:
    """
    Hybrid search combining FTS + semantic with weighted ranking
    
    - Strategy: voyage-law-2 embeddings + PostgreSQL FTS
    - Formula: 60% semantic + 30% FTS + 10% recency
    - Best for: Balanced search combining accuracy + meaning
    """
    
    @staticmethod
    def search(query: str, tenant_id: str, limit: int = 20) -> list:
        """
        Perform hybrid search combining multiple strategies
        
        Args:
            query: Search query
            tenant_id: Filter by tenant
            limit: Max results
        
        Returns:
            Results sorted by hybrid score (highest first)
        """
        
        # Step 1: Get FTS results
        fts_results = FullTextSearchService.search(query, tenant_id, limit=100)
        
        # Step 2: Get semantic results
        semantic_results = SemanticSearchService.search(query, tenant_id, limit=100)
        
        # Step 3: Merge and score
        merged = {}
        
        # Add FTS scores
        for idx, result in enumerate(fts_results):
            fts_score = 1.0 - (idx / max(len(fts_results), 1))  # Normalize by position
            merged[str(result.id)] = {
                'object': result,
                'fts_score': fts_score,
                'semantic_score': 0.0,
                'recency_score': HybridSearchService._get_recency_boost(result),
                'source': 'fts'
            }
        
        # Add semantic scores
        for idx, result in enumerate(semantic_results):
            semantic_score = 1.0 - (idx / max(len(semantic_results), 1))
            result_id = str(result.id)
            
            if result_id in merged:
                merged[result_id]['semantic_score'] = semantic_score
                merged[result_id]['source'] = 'hybrid'
            else:
                merged[result_id] = {
                    'object': result,
                    'fts_score': 0.0,
                    'semantic_score': semantic_score,
                    'recency_score': HybridSearchService._get_recency_boost(result),
                    'source': 'semantic'
                }
        
        # Step 4: Calculate final scores using weights
        for result_id, scores in merged.items():
            scores['final_score'] = (
                (0.6 * scores['semantic_score']) +
                (0.3 * scores['fts_score']) +
                (0.1 * scores['recency_score'])
            )

            # Attach scores onto the model object for serialization/metadata.
            obj = scores.get('object')
            try:
                setattr(obj, 'final_score', scores['final_score'])
                setattr(obj, 'fts_score', scores['fts_score'])
                setattr(obj, 'semantic_score', scores['semantic_score'])
                setattr(obj, 'recency_score', scores['recency_score'])
                setattr(obj, 'hybrid_source', scores.get('source'))
            except Exception:
                pass
        
        # Step 5: Sort by final score
        sorted_results = sorted(
            merged.items(),
            key=lambda x: x[1]['final_score'],
            reverse=True
        )
        
        logger.info(f"Hybrid search: '{query}' returned {min(len(sorted_results), limit)} results (strategy={ModelConfig.HYBRID_STRATEGY})")
        return [item[1]['object'] for item in sorted_results[:limit]]
    
    @staticmethod
    def _get_recency_boost(obj) -> float:
        """Boost recently updated documents"""
        from django.utils import timezone
        from datetime import timedelta
        
        try:
            if not hasattr(obj, 'created_at') or not obj.created_at:
                return 0.5
            
            age = (timezone.now() - obj.created_at).days
            if age < 7:
                return 1.0
            elif age < 30:
                return 0.8
            elif age < 90:
                return 0.6
            else:
                return 0.5
        except:
            return 0.5
    
    @staticmethod
    def get_hybrid_metadata(results: list) -> list:
        """Format hybrid results with all component scores (no dummy values)"""
        return [
            {
                'id': str(r.id),
                'entity_type': getattr(r, 'entity_type', 'document'),
                'title': getattr(r, 'title', 'Unknown'),
                'content': getattr(r, 'content', '')[:500],
                'relevance_score': float(getattr(r, 'final_score', 0.0)),
                'full_text_score': float(getattr(r, 'fts_score', 0.0)),
                'semantic_score': float(getattr(r, 'semantic_score', 0.0)),
                'embedding_model': ModelConfig.VOYAGE_MODEL,
                'search_strategy': ModelConfig.HYBRID_STRATEGY,
                'created_at': r.created_at.isoformat() if hasattr(r, 'created_at') and r.created_at else None,
            }
            for r in results
        ]



# ============================================================================
# 5. FILTERING SERVICE
# ============================================================================

class FilteringService:
    """
    Advanced SQL filtering with multiple criteria
    """
    
    @staticmethod
    def apply_filters(queryset, filters: Dict) -> list:
        """
        Apply WHERE clauses for:
        - entity_type: Exact match
        - date_from/date_to: Range filter
        - keywords: Any keyword match
        - status: Metadata filter
        """
        
        # Filter by entity type
        if filters.get('entity_type'):
            queryset = queryset.filter(entity_type=filters['entity_type'])
        
        # Filter by date range
        if filters.get('date_from'):
            queryset = queryset.filter(created_at__gte=filters['date_from'])
        
        if filters.get('date_to'):
            queryset = queryset.filter(created_at__lte=filters['date_to'])
        
        # Filter by keywords
        if filters.get('keywords'):
            keyword_q = Q()
            for keyword in filters['keywords']:
                keyword_q |= Q(keywords__contains=[keyword])
            queryset = queryset.filter(keyword_q)
        
        # Filter by status
        if filters.get('status'):
            queryset = queryset.filter(metadata__status=filters['status'])
        
        return list(queryset)


# ============================================================================
# 6. FACETED SEARCH SERVICE
# ============================================================================

class FacetedSearchService:
    """
    Navigation facets and aggregation
    """
    
    @staticmethod
    def get_facets(tenant_id: str) -> Dict:
        """
        Returns available facets for navigation
        """
        from .models import SearchIndexModel
        from django.db.models import Count
        
        try:
            # Entity type facets
            entity_types = SearchIndexModel.objects.filter(
                tenant_id=tenant_id
            ).values('entity_type').annotate(count=Count('id'))
            
            # Keywords facets (simplified)
            keywords = SearchIndexModel.objects.filter(
                tenant_id=tenant_id
            ).values_list('keywords', flat=True).distinct()
            
            from django.db.models import Min, Max

            # Date range
            date_range_data = SearchIndexModel.objects.filter(
                tenant_id=tenant_id
            ).aggregate(
                earliest=Min('created_at'),
                latest=Max('created_at')
            )
            
            return {
                'entity_types': [
                    {'name': e['entity_type'], 'count': e['count']}
                    for e in entity_types
                ],
                'keywords': [
                    {'name': k, 'count': 1}
                    for k in keywords[:20]  # Top 20
                ],
                'date_range': {
                    'earliest': str(date_range_data['earliest']),
                    'latest': str(date_range_data['latest'])
                },
                'total_documents': SearchIndexModel.objects.filter(
                    tenant_id=tenant_id
                ).count()
            }
        
        except Exception as e:
            logger.error(f"Facet aggregation failed: {str(e)}")
            return {
                'entity_types': [],
                'keywords': [],
                'date_range': {},
                'total_documents': 0
            }
    
    @staticmethod
    def apply_facet_filters(queryset, facet_filters: Dict) -> list:
        """Apply user-selected facets"""
        
        if facet_filters.get('entity_types'):
            queryset = queryset.filter(
                entity_type__in=facet_filters['entity_types']
            )
        
        if facet_filters.get('keywords'):
            keyword_q = Q()
            for keyword in facet_filters['keywords']:
                keyword_q |= Q(keywords__contains=[keyword])
            queryset = queryset.filter(keyword_q)
        
        return list(queryset)


# ============================================================================
# 7. SEARCH INDEXING SERVICE
# ============================================================================

class SearchIndexingService:
    """
    Index management: Create, update, delete
    """
    
    @staticmethod
    def create_index(
        entity_type: str,
        entity_id: str,
        title: str,
        content: str,
        tenant_id: str,
        keywords: List[str] = None,
        metadata: Dict | None = None,
    ) -> Tuple:
        """
        Create or update search index entry
        
        Returns:
            (index_instance, created_flag)
        """
        from .models import SearchIndexModel
        
        try:
            # Generate embedding (best-effort). If the embeddings provider is not
            # configured (or key is invalid), still create the index entry.
            embedding = None
            try:
                embedding = EmbeddingService.generate(
                    f"{title}\n\n{content}",
                    input_type="document",
                )
            except Exception as e:
                logger.warning(f"Embedding generation failed (continuing without embedding): {str(e)}")
            
            qs = SearchIndexModel.objects.filter(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )

            # Defensive: older data can contain duplicates (no unique constraint).
            # Keep the newest row and delete the rest to prevent update_or_create()
            # from raising MultipleObjectsReturned.
            existing = qs.order_by('-updated_at', '-created_at').first()
            try:
                if qs.count() > 1 and existing:
                    qs.exclude(id=existing.id).delete()
            except Exception:
                pass
            existing_md = (getattr(existing, 'metadata', None) or {}) if existing else {}

            merged_md = {
                **(existing_md if isinstance(existing_md, dict) else {}),
                **(metadata if isinstance(metadata, dict) else {}),
                'embedding_hash': hash(str(embedding)[:100]),
                'indexed_by': 'SearchIndexingService',
            }

            if existing:
                # Update in-place (avoids any chance of MultipleObjectsReturned)
                existing.title = title
                existing.content = content
                existing.keywords = keywords or []
                existing.embedding = embedding
                existing.metadata = merged_md
                existing.save(update_fields=['title', 'content', 'keywords', 'embedding', 'metadata', 'updated_at'])
                index_obj, created = existing, False
            else:
                index_obj = SearchIndexModel.objects.create(
                    tenant_id=tenant_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    title=title,
                    content=content,
                    keywords=keywords or [],
                    embedding=embedding,
                    metadata=merged_md,
                )
                created = True
            
            # Update FTS vector
            from django.contrib.postgres.search import SearchVector
            SearchIndexModel.objects.filter(id=index_obj.id).update(
                search_vector=SearchVector('title', weight='A') + 
                             SearchVector('content', weight='B')
            )
            
            logger.info(f"Index {'created' if created else 'updated'}: {entity_id}")
            return index_obj, created
        
        except Exception as e:
            logger.error(f"Index creation failed: {str(e)}")
            raise
    
    @staticmethod
    def bulk_index(items: List[Dict], tenant_id: str) -> int:
        """Bulk create/update indexes"""
        count = 0
        for item in items:
            try:
                SearchIndexingService.create_index(
                    entity_type=item['entity_type'],
                    entity_id=item['entity_id'],
                    title=item['title'],
                    content=item['content'],
                    tenant_id=tenant_id,
                    keywords=item.get('keywords', [])
                )
                count += 1
            except Exception as e:
                logger.error(f"Bulk index failed for {item['entity_id']}: {str(e)}")
                continue
        
        return count
    
    @staticmethod
    def delete_index(entity_id: str):
        """Remove from search index"""
        from .models import SearchIndexModel
        
        try:
            deleted, _ = SearchIndexModel.objects.filter(
                entity_id=entity_id
            ).delete()
            logger.info(f"Index deleted: {entity_id}")
            return deleted
        except Exception as e:
            logger.error(f"Index deletion failed: {str(e)}")
            return 0


# ============================================================================
# 8. HELPER FUNCTIONS
# ============================================================================

def find_similar_contracts(source_contract_id: str, tenant_id: str, 
                          limit: int = 10) -> list:
    """Find similar contracts using embeddings"""
    from .models import ContractChunkModel
    
    try:
        # Get source contract embedding
        source = ContractChunkModel.objects.get(
            contract_id=source_contract_id,
            tenant_id=tenant_id
        )
        
        if not source.embedding:
            return []
        
        source_embedding = source.embedding
        
        # Find similar (using pgvector distance)
        similar = ContractChunkModel.objects.filter(
            tenant_id=tenant_id
        ).exclude(
            contract_id=source_contract_id
        ).extra(
            select={'distance': f"embedding <-> '{{{','.join(map(str, source_embedding))}}}'::vector"}
        ).order_by('distance')[:limit]
        
        return list(similar)
    
    except Exception as e:
        logger.error(f"Similar search failed: {str(e)}")
        return []
