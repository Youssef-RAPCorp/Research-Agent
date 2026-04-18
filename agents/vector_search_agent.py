import asyncio
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent
from agents.comm_bus import CommunicationBus
from knowledge.qdrant_store import QdrantStore
from knowledge.embedder import Embedder
from knowledge.retrieval import RetrievalSystem
from memory.semantic import SemanticMemory

logger = get_logger(__name__)
settings = get_settings()

@dataclass
class SearchResult:
    """Single search result with content and metadata."""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]
    source: str
    timestamp: datetime

@dataclass
class SearchQuery:
    """Search query with parameters and filters."""
    text: str
    top_k: int = 10
    threshold: float = 0.7
    filters: Optional[Dict[str, Any]] = None
    hybrid_alpha: float = 0.7

class VectorSearchAgent(BaseAgent):
    """Semantic search agent for querying the vector knowledge base."""
    
    def __init__(self,       comm_bus=None, **kwargs):
        super().__init__(agent_id="search_result", name="SearchResult")
        self.qdrant_store = QdrantStore()
        self.embedder = Embedder()
        self.retrieval_system = RetrievalSystem()
        self.semantic_memory = SemanticMemory()
        self.search_cache: Dict[str, List[SearchResult]] = {}
        
    async def initialize(self) -> None:
        """Initialize agent and connections."""
        try:
            await self.qdrant_store.initialize()
            await self.embedder.initialize()
            await self.retrieval_system.initialize()
            await self.semantic_memory.initialize()
            logger.info("Vector search agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize vector search agent: {e}")
            handle_error(e)
            raise

    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming search requests."""
        try:
            message_type = message.get("type")
            
            if message_type == "semantic_search":
                return await self._handle_semantic_search(message)
            elif message_type == "hybrid_search":
                return await self._handle_hybrid_search(message)
            elif message_type == "similarity_search":
                return await self._handle_similarity_search(message)
            elif message_type == "context_search":
                return await self._handle_context_search(message)
            elif message_type == "batch_search":
                return await self._handle_batch_search(message)
            elif message_type is None:
                return await self._handle_semantic_search(message)
            else:
                return {"status": "error", "message": f"Unknown message type: {message_type}"}
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            handle_error(e)
            return {"status": "error", "message": str(e)}

    async def _handle_semantic_search(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle semantic search requests."""
        query = SearchQuery(
            text=message["query"],
            top_k=message.get("top_k", settings.retrieval_top_k),
            threshold=message.get("threshold", 0.7),
            filters=message.get("filters")
        )
        
        results = await self.semantic_search(query)
        
        # Store in semantic memory for context
        await self._store_search_context(query, results)
        
        return {
            "status": "success",
            "results": [self._format_result(r) for r in results],
            "query": query.text,
            "count": len(results)
        }

    async def _handle_hybrid_search(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle hybrid search combining semantic and keyword search."""
        query = SearchQuery(
            text=message["query"],
            top_k=message.get("top_k", settings.retrieval_top_k),
            threshold=message.get("threshold", 0.7),
            filters=message.get("filters"),
            hybrid_alpha=message.get("alpha", 0.7)
        )
        
        results = await self.hybrid_search(query)
        
        return {
            "status": "success",
            "results": [self._format_result(r) for r in results],
            "query": query.text,
            "count": len(results),
            "search_type": "hybrid"
        }

    async def _handle_similarity_search(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle similarity search against specific documents."""
        target_id = message["target_id"]
        top_k = message.get("top_k", 10)
        threshold = message.get("threshold", 0.8)
        
        results = await self.similarity_search(target_id, top_k, threshold)
        
        return {
            "status": "success",
            "results": [self._format_result(r) for r in results],
            "target_id": target_id,
            "count": len(results)
        }

    async def _handle_context_search(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle context-aware search using conversation history."""
        query_text = message["query"]
        context = message.get("context", [])
        
        # Enhance query with context
        enhanced_query = await self._enhance_query_with_context(query_text, context)
        
        query = SearchQuery(
            text=enhanced_query,
            top_k=message.get("top_k", settings.retrieval_top_k),
            threshold=message.get("threshold", 0.7),
            filters=message.get("filters")
        )
        
        results = await self.semantic_search(query)
        
        return {
            "status": "success",
            "results": [self._format_result(r) for r in results],
            "original_query": query_text,
            "enhanced_query": enhanced_query,
            "count": len(results)
        }

    async def _handle_batch_search(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle batch search for multiple queries."""
        queries = message["queries"]
        batch_results = []
        
        for query_text in queries:
            query = SearchQuery(
                text=query_text,
                top_k=message.get("top_k", settings.retrieval_top_k),
                threshold=message.get("threshold", 0.7)
            )
            
            results = await self.semantic_search(query)
            batch_results.append({
                "query": query_text,
                "results": [self._format_result(r) for r in results],
                "count": len(results)
            })
        
        return {
            "status": "success",
            "batch_results": batch_results,
            "total_queries": len(queries)
        }

    async def semantic_search(self, query: SearchQuery) -> List[SearchResult]:
        """Perform semantic search using vector embeddings."""
        cache_key = self._get_cache_key(query)
        if cache_key in self.search_cache:
            logger.debug(f"Cache hit for query: {query.text[:50]}...")
            return self.search_cache[cache_key]
        
        try:
            # Generate query embedding
            query_embedding = await self.embedder.embed_text(query.text)
            
            # Search vector store
            raw_results = await self.qdrant_store.search(
                query_vector=query_embedding,
                limit=query.top_k,
                score_threshold=query.threshold,
                filters=query.filters
            )
            
            # Convert to SearchResult objects
            results = []
            for result in raw_results:
                search_result = SearchResult(
                    id=result.id,
                    content=result.payload.get("content", ""),
                    score=result.score,
                    metadata=result.payload,
                    source=result.payload.get("source", "unknown"),
                    timestamp=datetime.now()
                )
                results.append(search_result)
            
            # Cache results
            self.search_cache[cache_key] = results
            
            logger.info(f"Semantic search completed: {len(results)} results for '{query.text[:50]}...'")
            return results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            handle_error(e)
            return []

    async def hybrid_search(self, query: SearchQuery) -> List[SearchResult]:
        """Perform hybrid search combining semantic and keyword search."""
        try:
            # Get semantic results
            semantic_results = await self.semantic_search(query)
            
            # Get keyword results
            keyword_results = await self.retrieval_system.keyword_search(
                query.text, 
                top_k=query.top_k,
                filters=query.filters
            )
            
            # Combine and rank results
            combined_results = await self._combine_search_results(
                semantic_results, 
                keyword_results, 
                query.hybrid_alpha
            )
            
            logger.info(f"Hybrid search completed: {len(combined_results)} results")
            return combined_results
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            handle_error(e)
            return []

    async def similarity_search(self, target_id: str, top_k: int, threshold: float, **kwargs) -> List[SearchResult]:
        """Find documents similar to a specific target document."""
        try:
            # Get target document embedding
            target_vector = await self.qdrant_store.get_vector(target_id)
            if not target_vector:
                logger.warning(f"Target document not found: {target_id}")
                return []
            
            # Search for similar documents
            raw_results = await self.qdrant_store.search(
                query_vector=target_vector,
                limit=top_k + 1,  # +1 to exclude self
                score_threshold=threshold
            )
            
            # Filter out the target document itself
            filtered_results = [r for r in raw_results if r.id != target_id][:top_k]
            
            # Convert to SearchResult objects
            results = []
            for result in filtered_results:
                search_result = SearchResult(
                    id=result.id,
                    content=result.payload.get("content", ""),
                    score=result.score,
                    metadata=result.payload,
                    source=result.payload.get("source", "unknown"),
                    timestamp=datetime.now()
                )
                results.append(search_result)
            
            logger.info(f"Similarity search completed: {len(results)} results for {target_id}")
            return results
            
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            handle_error(e)
            return []

    async def _enhance_query_with_context(self, query: str, context: List[str]) -> str:
        """Enhance query using conversation context."""
        if not context:
            return query
        
        # Extract key terms from context
        context_text = " ".join(context[-3:])  # Use last 3 context items
        
        # Simple enhancement - add context terms that aren't already in query
        context_terms = set(context_text.lower().split())
        query_terms = set(query.lower().split())
        
        additional_terms = context_terms - query_terms
        if additional_terms:
            # Select most relevant additional terms (simple heuristic)
            relevant_terms = [term for term in additional_terms 
                            if len(term) > 3 and term.isalpha()][:3]
            if relevant_terms:
                enhanced = f"{query} {' '.join(relevant_terms)}"
                logger.debug(f"Enhanced query: {query} -> {enhanced}")
                return enhanced
        
        return query

    async def _combine_search_results(
        self, 
        semantic_results: List[SearchResult], 
        keyword_results: List[SearchResult], 
        alpha: float
    ) -> List[SearchResult]:
        """Combine semantic and keyword search results with weighted ranking."""
        combined_map = {}
        
        # Add semantic results with alpha weight
        for result in semantic_results:
            combined_map[result.id] = SearchResult(
                id=result.id,
                content=result.content,
                score=result.score * alpha,
                metadata=result.metadata,
                source=result.source,
                timestamp=result.timestamp
            )
        
        # Add/merge keyword results with (1-alpha) weight
        for result in keyword_results:
            if result.id in combined_map:
                # Combine scores
                existing = combined_map[result.id]
                combined_score = existing.score + (result.score * (1 - alpha))
                combined_map[result.id] = SearchResult(
                    id=result.id,
                    content=result.content,
                    score=combined_score,
                    metadata=result.metadata,
                    source=result.source,
                    timestamp=result.timestamp
                )
            else:
                combined_map[result.id] = SearchResult(
                    id=result.id,
                    content=result.content,
                    score=result.score * (1 - alpha),
                    metadata=result.metadata,
                    source=result.source,
                    timestamp=result.timestamp
                )
        
        # Sort by combined score
        combined_results = list(combined_map.values())
        combined_results.sort(key=lambda x: x.score, reverse=True)
        
        return combined_results

    async def _store_search_context(self, query: SearchQuery, results: List[SearchResult]) -> None:
        """Store search context in semantic memory for future reference."""
        try:
            context_data = {
                "query": query.text,
                "result_count": len(results),
                "top_results": [r.id for r in results[:3]],
                "timestamp": datetime.now().isoformat()
            }
            
            await self.semantic_memory.store_context("search", context_data)
            
        except Exception as e:
            logger.warning(f"Failed to store search context: {e}")

    def _format_result(self, result: SearchResult) -> Dict[str, Any]:
        """Format search result for response."""
        return {
            "id": result.id,
            "content": result.content[:500] + "..." if len(result.content) > 500 else result.content,
            "score": round(result.score, 4),
            "source": result.source,
            "metadata": {
                "title": result.metadata.get("title", ""),
                "authors": result.metadata.get("authors", []),
                "date": result.metadata.get("date", ""),
                "category": result.metadata.get("category", ""),
                "arxiv_id": result.metadata.get("arxiv_id", ""),
                "doi": result.metadata.get("doi", "")
            }
        }

    def _get_cache_key(self, query: SearchQuery) -> str:
        """Generate cache key for query."""
        filters_str = str(sorted(query.filters.items())) if query.filters else ""
        return f"{query.text}:{query.top_k}:{query.threshold}:{filters_str}"

    async def clear_cache(self) -> None:
        """Clear search result cache."""
        self.search_cache.clear()
        logger.info("Search cache cleared")

    async def get_search_stats(self) -> Dict[str, Any]:
        """Get search statistics and performance metrics."""
        return {
            "cache_size": len(self.search_cache),
            "vector_store_status": await self.qdrant_store.get_collection_info(),
            "embedding_model": settings.embedding_model,
            "default_top_k": settings.retrieval_top_k
        }

    async def shutdown(self) -> None:
        """Shutdown agent and cleanup resources."""
        try:
            await self.qdrant_store.close()
            self.search_cache.clear()
            logger.info("Vector search agent shutdown completed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            handle_error(e)
    async def _process_cycle(self, *args, **kwargs):
        pass

    async def on_message_received(self, message=None, *args, **kwargs):
        pass

    async def process_task(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def get_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def run(self, *args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'semantic_search'})
