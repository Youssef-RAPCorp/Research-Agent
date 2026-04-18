import asyncio
import math
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from collections import defaultdict
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
import re

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error
from knowledge.qdrant_store import QdrantStore
from knowledge.embedder import Embedder

@dataclass
class SearchResult:
    """Single search result with metadata."""
    content: str
    score: float
    source: str
    metadata: Dict[str, Any]
    doc_id: str

@dataclass
class RetrievalConfig:
    """Configuration for retrieval parameters."""
    dense_weight: float = 0.6
    sparse_weight: float = 0.3
    rerank_weight: float = 0.1
    top_k_dense: int = 50
    top_k_sparse: int = 50
    top_k_final: int = 20
    enable_reranking: bool = True
    min_score_threshold: float = 0.1

class RetrievalEngine:
    """Hybrid retrieval engine combining dense vector search, BM25, and cross-encoder reranking."""
    
    def __init__(self,      config: Optional[RetrievalConfig] = None, **kwargs):
        """Initialize retrieval engine with configuration."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.config = config or RetrievalConfig()
        
        self.qdrant_store = QdrantStore()
        self.embedder = Embedder()
        
        # BM25 components
        self.bm25_index = None
        self.bm25_documents = []
        self.bm25_metadata = []
        
        # Cross-encoder for reranking
        self.cross_encoder = None
        self._initialize_cross_encoder()
        
        # Document cache
        self._doc_cache: Dict[str, Dict[str, Any]] = {}
        
    def _initialize_cross_encoder(self):
        """Initialize cross-encoder model for reranking."""
        try:
            # TODO: Make cross-encoder model configurable
            self.cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-2-v2')
            self.logger.info("Cross-encoder initialized successfully")
        except Exception as e:
            self.logger.warning(f"Failed to initialize cross-encoder: {e}")
            self.cross_encoder = None
    
    async def index_documents(self, documents: List[Dict[str, Any]]):
        """Index documents for both dense and sparse retrieval."""
        try:
            # Index in Qdrant for dense retrieval
            await self.qdrant_store.add_documents(documents)
            
            # Build BM25 index for sparse retrieval
            await self._build_bm25_index(documents)
            
            # Update document cache
            for doc in documents:
                self._doc_cache[doc.get('id', '')] = doc
            
            self.logger.info(f"Indexed {len(documents)} documents")
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def _build_bm25_index(self, documents: List[Dict[str, Any]]):
        """Build BM25 index from documents."""
        try:
            self.bm25_documents = []
            self.bm25_metadata = []
            
            for doc in documents:
                content = doc.get('content', '')
                # Tokenize content for BM25
                tokens = self._tokenize_text(content)
                self.bm25_documents.append(tokens)
                self.bm25_metadata.append({
                    'id': doc.get('id', ''),
                    'content': content,
                    'metadata': doc.get('metadata', {}),
                    'source': doc.get('source', 'unknown')
                })
            
            if self.bm25_documents:
                self.bm25_index = BM25Okapi(self.bm25_documents)
                self.logger.info(f"Built BM25 index with {len(self.bm25_documents)} documents")
            
        except Exception as e:
            self.logger.error(f"Failed to build BM25 index: {e}")
            raise
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for BM25 indexing."""
        # Simple tokenization - could be improved with proper NLP tokenization
        text = text.lower()
        # Remove punctuation and split on whitespace
        tokens = re.findall(r'\b\w+\b', text)
        return tokens
    
    async def search(self, query: str, top_k: Optional[int] = None, **kwargs) -> List[SearchResult]:
        """Perform hybrid search combining dense, sparse, and reranking."""
        try:
            top_k = top_k or self.config.top_k_final
            
            # Run dense and sparse searches in parallel
            dense_task = self._dense_search(query, self.config.top_k_dense)
            sparse_task = self._sparse_search(query, self.config.top_k_sparse)
            
            dense_results, sparse_results = await asyncio.gather(
                dense_task, sparse_task, return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(dense_results, Exception):
                self.logger.warning(f"Dense search failed: {dense_results}")
                dense_results = []
            if isinstance(sparse_results, Exception):
                self.logger.warning(f"Sparse search failed: {sparse_results}")
                sparse_results = []
            
            # Fuse results
            fused_results = self._fuse_results(query, dense_results, sparse_results)
            
            # Rerank if enabled
            if self.config.enable_reranking and self.cross_encoder:
                fused_results = await self._rerank_results(query, fused_results)
            
            # Apply final filtering and sorting
            final_results = self._finalize_results(fused_results, top_k)
            
            self.logger.info(f"Retrieved {len(final_results)} results for query")
            return final_results
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def _dense_search(self, query: str, top_k: int) -> List[SearchResult]:
        """Perform dense vector search using Qdrant."""
        try:
            results = await self.qdrant_store.search(query, top_k=top_k)
            
            search_results = []
            for result in results:
                search_results.append(SearchResult(
                    content=result.get('content', ''),
                    score=result.get('score', 0.0),
                    source=result.get('source', 'dense'),
                    metadata=result.get('metadata', {}),
                    doc_id=result.get('id', '')
                ))
            
            return search_results
            
        except Exception as e:
            self.logger.error(f"Dense search failed: {e}")
            return []
    
    async def _sparse_search(self, query: str, top_k: int) -> List[SearchResult]:
        """Perform sparse search using BM25."""
        try:
            if not self.bm25_index or not self.bm25_documents:
                self.logger.warning("BM25 index not available")
                return []
            
            # Tokenize query
            query_tokens = self._tokenize_text(query)
            
            # Get BM25 scores
            scores = self.bm25_index.get_scores(query_tokens)
            
            # Get top-k results
            top_indices = np.argsort(scores)[::-1][:top_k]
            
            search_results = []
            for idx in top_indices:
                if scores[idx] > 0:  # Only include results with positive scores
                    metadata = self.bm25_metadata[idx]
                    search_results.append(SearchResult(
                        content=metadata['content'],
                        score=float(scores[idx]),
                        source='sparse',
                        metadata=metadata['metadata'],
                        doc_id=metadata['id']
                    ))
            
            return search_results
            
        except Exception as e:
            self.logger.error(f"Sparse search failed: {e}")
            return []
    
    def _fuse_results(self, query: str, dense_results: List[SearchResult], 
                     sparse_results: List[SearchResult]) -> List[SearchResult]:
        """Fuse dense and sparse search results."""
        try:
            # Create a map to combine results by document ID
            result_map: Dict[str, SearchResult] = {}
            
            # Normalize dense scores
            if dense_results:
                max_dense_score = max(r.score for r in dense_results)
                if max_dense_score > 0:
                    for result in dense_results:
                        normalized_score = result.score / max_dense_score
                        weighted_score = normalized_score * self.config.dense_weight
                        
                        if result.doc_id in result_map:
                            result_map[result.doc_id].score += weighted_score
                        else:
                            new_result = SearchResult(
                                content=result.content,
                                score=weighted_score,
                                source=f"{result.source}+dense",
                                metadata=result.metadata,
                                doc_id=result.doc_id
                            )
                            result_map[result.doc_id] = new_result
            
            # Normalize sparse scores
            if sparse_results:
                max_sparse_score = max(r.score for r in sparse_results)
                if max_sparse_score > 0:
                    for result in sparse_results:
                        normalized_score = result.score / max_sparse_score
                        weighted_score = normalized_score * self.config.sparse_weight
                        
                        if result.doc_id in result_map:
                            result_map[result.doc_id].score += weighted_score
                            result_map[result.doc_id].source += "+sparse"
                        else:
                            new_result = SearchResult(
                                content=result.content,
                                score=weighted_score,
                                source=f"{result.source}+sparse",
                                metadata=result.metadata,
                                doc_id=result.doc_id
                            )
                            result_map[result.doc_id] = new_result
            
            # Convert back to list and sort by score
            fused_results = list(result_map.values())
            fused_results.sort(key=lambda x: x.score, reverse=True)
            
            return fused_results
            
        except Exception as e:
            self.logger.error(f"Result fusion failed: {e}")
            return dense_results + sparse_results
    
    async def _rerank_results(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Rerank results using cross-encoder."""
        try:
            if not self.cross_encoder or not results:
                return results
            
            # Prepare query-document pairs
            pairs = [(query, result.content[:512]) for result in results]  # Truncate for efficiency
            
            # Get cross-encoder scores
            rerank_scores = self.cross_encoder.predict(pairs)
            
            # Normalize rerank scores
            if len(rerank_scores) > 0:
                min_score = float(np.min(rerank_scores))
                max_score = float(np.max(rerank_scores))
                if max_score > min_score:
                    normalized_scores = [(score - min_score) / (max_score - min_score) 
                                       for score in rerank_scores]
                else:
                    normalized_scores = [0.5] * len(rerank_scores)
            else:
                normalized_scores = []
            
            # Update results with rerank scores
            for i, result in enumerate(results):
                if i < len(normalized_scores):
                    rerank_contribution = normalized_scores[i] * self.config.rerank_weight
                    result.score = (result.score * (1 - self.config.rerank_weight) + 
                                  rerank_contribution)
                    result.source += "+reranked"
            
            # Re-sort by updated scores
            results.sort(key=lambda x: x.score, reverse=True)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Reranking failed: {e}")
            return results
    
    def _finalize_results(self, results: List[SearchResult], top_k: int) -> List[SearchResult]:
        """Apply final filtering and return top-k results."""
        try:
            # Filter by minimum score threshold
            filtered_results = [
                r for r in results 
                if r.score >= self.config.min_score_threshold
            ]
            
            # Return top-k
            return filtered_results[:top_k]
            
        except Exception as e:
            self.logger.error(f"Result finalization failed: {e}")
            return results[:top_k]
    
    async def get_similar_documents(self, doc_id: str, top_k: int = 10) -> List[SearchResult]:
        """Find documents similar to a given document."""
        try:
            if doc_id not in self._doc_cache:
                self.logger.warning(f"Document {doc_id} not found in cache")
                return []
            
            doc_content = self._doc_cache[doc_id].get('content', '')
            return await self.search(doc_content, top_k)
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def update_config(self, new_config: RetrievalConfig):
        """Update retrieval configuration."""
        self.config = new_config
        self.logger.info("Retrieval configuration updated")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get retrieval engine statistics."""
        return {
            'dense_index_size': len(self._doc_cache),
            'sparse_index_size': len(self.bm25_documents) if self.bm25_documents else 0,
            'cross_encoder_available': self.cross_encoder is not None,
            'config': {
                'dense_weight': self.config.dense_weight,
                'sparse_weight': self.config.sparse_weight,
                'rerank_weight': self.config.rerank_weight,
                'enable_reranking': self.config.enable_reranking
            }
        }
KnowledgeRetriever = RetrievalEngine  # auto-alias by repair.py

KnowledgeRetrieval = RetrievalEngine  # auto-alias by repair.py

RetrievalService = RetrievalEngine  # auto-alias by repair.py

RetrievalSystem = RetrievalEngine  # auto-alias by repair.py
