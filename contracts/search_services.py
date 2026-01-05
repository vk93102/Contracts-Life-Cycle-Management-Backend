"""
Production-Level Hybrid Search Implementation
Combines keyword (PostgreSQL tsvector) + semantic (vector similarity) search
Uses Reciprocal Rank Fusion (RRF) to merge results
"""
import logging
from typing import List, Dict, Optional, Tuple
from django.db.models import Q, F
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from .models import Contract, ContractTemplate, Clause
from .ai_services import gemini_service
import numpy as np

logger = logging.getLogger(__name__)


class HybridSearchService:
    """
    Production-level hybrid search combining:
    1. Keyword search (PostgreSQL full-text search)
    2. Semantic search (Vector similarity with Gemini embeddings)
    3. Reciprocal Rank Fusion (RRF) for result merging
    """
    
    def __init__(self):
        self.gemini = gemini_service
    
    def search_contracts(
        self,
        query: str,
        tenant_id: str,
        mode: str = 'hybrid',
        filters: Optional[Dict] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        The "Google" for Contracts - Multi-modal search
        
        Args:
            query: User search query
            tenant_id: Tenant UUID for isolation
            mode: 'hybrid', 'semantic', or 'keyword'
            filters: Additional filters (status, date_gt, etc.)
            limit: Max results to return
            
        Returns:
            List of ranked contracts with scores
            
        Algorithm:
        1. Keyword Search: PostgreSQL tsvector ranks by TF-IDF
        2. Semantic Search: Gemini embedding + cosine similarity
        3. RRF Fusion: Merge using formula: score = Σ(1/(k + rank))
        """
        logger.info(f"Searching contracts: query='{query}', mode={mode}")
        
        # Build base queryset with filters
        base_qs = Contract.objects.filter(tenant_id=tenant_id)
        
        if filters:
            base_qs = self._apply_filters(base_qs, filters)
        
        if mode == 'keyword':
            return self._keyword_search(query, base_qs, limit)
        elif mode == 'semantic':
            return self._semantic_search(query, base_qs, limit)
        else:  # hybrid
            return self._hybrid_search(query, base_qs, limit)
    
    def _keyword_search(
        self,
        query: str,
        queryset,
        limit: int
    ) -> List[Dict]:
        """
        PostgreSQL full-text search using tsvector
        
        Searches across:
        - Contract title
        - Description
        - Content text (if available)
        """
        # Create search vector combining multiple fields
        search_vector = (
            SearchVector('title', weight='A') +
            SearchVector('description', weight='B')
        )
        
        search_query = SearchQuery(query)
        
        results = queryset.annotate(
            search=search_vector,
            rank=SearchRank(search_vector, search_query)
        ).filter(
            search=search_query
        ).order_by('-rank')[:limit]
        
        # Format results
        formatted = []
        for idx, contract in enumerate(results, 1):
            formatted.append({
                'id': str(contract.id),
                'title': contract.title,
                'contract_type': contract.contract_type,
                'status': contract.status,
                'created_at': contract.created_at,
                'score': float(contract.rank) if hasattr(contract, 'rank') else 0,
                'rank': idx,
                'match_type': 'keyword'
            })
        
        logger.info(f"Keyword search returned {len(formatted)} results")
        return formatted
    
    def _semantic_search(
        self,
        query: str,
        queryset,
        limit: int
    ) -> List[Dict]:
        """
        Vector similarity search using Gemini embeddings
        
        Process:
        1. Generate query embedding
        2. Compare with stored contract embeddings
        3. Rank by cosine similarity
        
        Note: Requires contracts to have stored embeddings in metadata
        """
        # Generate query embedding
        query_vector = self.gemini.generate_query_embedding(query)
        
        if not query_vector:
            logger.warning("Failed to generate query embedding, falling back to keyword")
            return self._keyword_search(query, queryset, limit)
        
        # Get contracts with embeddings
        contracts_with_embeddings = queryset.exclude(
            metadata__embedding__isnull=True
        )
        
        # Calculate cosine similarity for each
        results = []
        for contract in contracts_with_embeddings:
            embedding = contract.metadata.get('embedding')
            if embedding and isinstance(embedding, list):
                similarity = self._cosine_similarity(query_vector, embedding)
                results.append((contract, similarity))
        
        # Sort by similarity (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:limit]
        
        # Format results
        formatted = []
        for idx, (contract, similarity) in enumerate(results, 1):
            formatted.append({
                'id': str(contract.id),
                'title': contract.title,
                'contract_type': contract.contract_type,
                'status': contract.status,
                'created_at': contract.created_at,
                'score': similarity,
                'rank': idx,
                'match_type': 'semantic'
            })
        
        logger.info(f"Semantic search returned {len(formatted)} results")
        return formatted
    
    def _hybrid_search(
        self,
        query: str,
        queryset,
        limit: int
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) combining keyword + semantic
        
        RRF Formula: score = Σ(1 / (k + rank))
        where k = 60 (standard constant)
        
        This gives higher weight to items that rank well in both searches
        """
        K = 60  # RRF constant
        
        # Get results from both search modes
        keyword_results = self._keyword_search(query, queryset, limit * 2)
        semantic_results = self._semantic_search(query, queryset, limit * 2)
        
        # Build RRF scores
        rrf_scores = {}
        
        # Add keyword ranks
        for result in keyword_results:
            contract_id = result['id']
            rank = result['rank']
            rrf_scores[contract_id] = 1.0 / (K + rank)
        
        # Add semantic ranks
        for result in semantic_results:
            contract_id = result['id']
            rank = result['rank']
            score = 1.0 / (K + rank)
            
            if contract_id in rrf_scores:
                rrf_scores[contract_id] += score  # Boost if in both
            else:
                rrf_scores[contract_id] = score
        
        # Sort by RRF score
        sorted_ids = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        # Fetch and format results
        contract_map = {
            str(c.id): c
            for c in queryset.filter(id__in=[cid for cid, _ in sorted_ids])
        }
        
        formatted = []
        for idx, (contract_id, rrf_score) in enumerate(sorted_ids, 1):
            contract = contract_map.get(contract_id)
            if contract:
                formatted.append({
                    'id': str(contract.id),
                    'title': contract.title,
                    'contract_type': contract.contract_type,
                    'status': contract.status,
                    'created_at': contract.created_at,
                    'score': rrf_score,
                    'rank': idx,
                    'match_type': 'hybrid'
                })
        
        logger.info(f"Hybrid search returned {len(formatted)} results")
        return formatted
    
    def find_similar_contracts(
        self,
        contract_id: str,
        tenant_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Find contracts similar to a given contract
        Uses stored vector embeddings for nearest neighbor search
        
        Args:
            contract_id: Contract to find similar to
            tenant_id: Tenant isolation
            limit: Max similar contracts
            
        Returns:
            List of similar contracts with similarity scores
        """
        try:
            reference_contract = Contract.objects.get(
                id=contract_id,
                tenant_id=tenant_id
            )
        except Contract.DoesNotExist:
            logger.error(f"Contract {contract_id} not found")
            return []
        
        # Get reference embedding
        ref_embedding = reference_contract.metadata.get('embedding')
        if not ref_embedding:
            logger.warning(f"Contract {contract_id} has no embedding")
            return []
        
        # Find similar contracts
        similar_contracts = []
        candidates = Contract.objects.filter(
            tenant_id=tenant_id
        ).exclude(
            id=contract_id
        ).exclude(
            metadata__embedding__isnull=True
        )
        
        for contract in candidates:
            embedding = contract.metadata.get('embedding')
            if embedding:
                similarity = self._cosine_similarity(ref_embedding, embedding)
                similar_contracts.append((contract, similarity))
        
        # Sort by similarity
        similar_contracts.sort(key=lambda x: x[1], reverse=True)
        similar_contracts = similar_contracts[:limit]
        
        # Format results
        formatted = []
        for contract, similarity in similar_contracts:
            formatted.append({
                'id': str(contract.id),
                'title': contract.title,
                'contract_type': contract.contract_type,
                'status': contract.status,
                'similarity_score': similarity,
                'created_at': contract.created_at
            })
        
        logger.info(f"Found {len(formatted)} similar contracts")
        return formatted
    
    def get_search_suggestions(
        self,
        partial_query: str,
        tenant_id: str,
        limit: int = 10
    ) -> List[str]:
        """
        Autocomplete suggestions based on existing contracts
        
        Args:
            partial_query: Partial user input
            tenant_id: Tenant isolation
            limit: Max suggestions
            
        Returns:
            List of suggested search terms
        """
        if len(partial_query) < 2:
            return []
        
        # Search in titles and contract types
        suggestions = set()
        
        # Title suggestions
        title_matches = Contract.objects.filter(
            tenant_id=tenant_id,
            title__icontains=partial_query
        ).values_list('title', flat=True)[:limit]
        
        suggestions.update(title_matches)
        
        # Contract type suggestions
        type_matches = Contract.objects.filter(
            tenant_id=tenant_id,
            contract_type__icontains=partial_query
        ).values_list('contract_type', flat=True).distinct()[:5]
        
        suggestions.update(type_matches)
        
        return sorted(list(suggestions))[:limit]
    
    def _apply_filters(self, queryset, filters: Dict):
        """
        Apply additional filters to queryset
        
        Supported filters:
        - status: exact match
        - date_gt: created_at greater than
        - date_lt: created_at less than
        - contract_type: exact match
        - value_gte: contract value >= 
        - value_lte: contract value <=
        """
        if 'status' in filters:
            queryset = queryset.filter(status=filters['status'])
        
        if 'date_gt' in filters:
            queryset = queryset.filter(created_at__gt=filters['date_gt'])
        
        if 'date_lt' in filters:
            queryset = queryset.filter(created_at__lt=filters['date_lt'])
        
        if 'contract_type' in filters:
            queryset = queryset.filter(contract_type=filters['contract_type'])
        
        if 'value_gte' in filters:
            queryset = queryset.filter(value__gte=filters['value_gte'])
        
        if 'value_lte' in filters:
            queryset = queryset.filter(value__lte=filters['value_lte'])
        
        return queryset
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors
        
        Formula: similarity = (A · B) / (||A|| * ||B||)
        
        Returns: Float between -1 and 1 (typically 0 to 1 for embeddings)
        """
        try:
            a = np.array(vec1)
            b = np.array(vec2)
            
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            similarity = dot_product / (norm_a * norm_b)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Cosine similarity calculation failed: {e}")
            return 0.0


# Singleton instance
hybrid_search_service = HybridSearchService()
