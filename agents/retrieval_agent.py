"""Retrieval agent for discovering and retrieving relevant information."""

import asyncio
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from pydantic import BaseModel, Field

from config.logger import get_logger
from config.errors import handle_error
from config.settings import get_settings
from agents.base_agent import BaseAgent
from knowledge.retrieval import KnowledgeRetrieval
from knowledge.arxiv_fetcher import ArxivFetcher
from knowledge.qdrant_store import QdrantStore
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.working import WorkingMemory

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class RetrievalRequest:
    """Represents a retrieval request with context and parameters."""
    query: str
    context: Optional[str] = None
    max_results: int = 10
    source_types: List[str] = None
    filters: Dict[str, Any] = None

    def __post_init__(self):
        if self.source_types is None:
            self.source_types = ["vector", "arxiv", "memory"]
        if self.filters is None:
            self.filters = {}


@dataclass
class RetrievalResult:
    """Represents the result of a retrieval operation."""
    documents: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    source: str
    confidence: float
    total_found: int


class RetrievalStrategy(BaseModel):
    """Configuration for retrieval strategies."""
    enable_vector_search: bool = Field(default=True)
    enable_arxiv_search: bool = Field(default=True)
    enable_memory_search: bool = Field(default=True)
    parallel_search: bool = Field(default=True)
    rerank_results: bool = Field(default=True)
    max_total_results: int = Field(default=50)

    async def model_dump(self, *args, **kwargs):
        return dict()


class RetrievalAgent(BaseAgent):
    """Agent responsible for discovering and retrieving relevant information across multiple sources."""

    def __init__(
        self, 
        agent_id: str = "retrieval_agent", 
        knowledge_retrieval: Optional[KnowledgeRetrieval] = None, 
        arxiv_fetcher: Optional[ArxivFetcher] = None, 
        qdrant_store: Optional[QdrantStore] = None, 
        episodic_memory: Optional[EpisodicMemory] = None, 
        semantic_memory: Optional[SemanticMemory] = None, 
        working_memory: Optional[WorkingMemory] = None, 
        strategy: Optional[RetrievalStrategy] = None
    , **kwargs):
        super().__init__(agent_id)
        self.knowledge_retrieval = knowledge_retrieval or KnowledgeRetrieval()
        self.arxiv_fetcher = arxiv_fetcher or ArxivFetcher()
        self.qdrant_store = qdrant_store or QdrantStore()
        self.episodic_memory = episodic_memory or EpisodicMemory()
        self.semantic_memory = semantic_memory or SemanticMemory()
        self.working_memory = working_memory or WorkingMemory()
        self.strategy = strategy or RetrievalStrategy()
        self.cache = {}

    async def process_request(self, request: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Process a retrieval request and return comprehensive results."""
        try:
            if isinstance(request, str):
                retrieval_request = RetrievalRequest(query=request)
            else:
                retrieval_request = RetrievalRequest(**request)

            logger.info(f"Processing retrieval request: {retrieval_request.query}")

            # Check cache first
            cache_key = self._generate_cache_key(retrieval_request)
            if cache_key in self.cache:
                logger.info("Returning cached results")
                return self.cache[cache_key]

            # Perform multi-source retrieval
            results = await self._retrieve_from_sources(retrieval_request)

            # Consolidate and rank results
            consolidated_results = await self._consolidate_results(results, retrieval_request)

            # Cache results
            self.cache[cache_key] = consolidated_results

            # Store successful retrieval in working memory
            await self.working_memory.store({
                "type": "retrieval_success",
                "query": retrieval_request.query,
                "results_count": len(consolidated_results.get("documents", [])),
                "sources_used": list(results.keys()),
                "timestamp": self._get_timestamp()
            })

            return {
                "status": "success",
                "results": consolidated_results,
                "metadata": {
                    "agent_id": self.agent_id,
                    "strategy": self.strategy.model_dump(),
                    "sources_queried": list(results.keys())
                }
            }

        except Exception as e:
            error_msg = f"Retrieval failed: {str(e)}"
            logger.error(error_msg)
            handle_error(e)
            
            # Store failed retrieval attempt
            await self.working_memory.store({
                "type": "retrieval_error",
                "query": retrieval_request.query if 'retrieval_request' in locals() else str(request),
                "error": error_msg,
                "timestamp": self._get_timestamp()
            })

            return {
                "status": "error",
                "message": error_msg,
                "results": RetrievalResult(
                    documents=[],
                    metadata={"error": error_msg},
                    source="error",
                    confidence=0.0,
                    total_found=0
                ),
                "metadata": {"agent_id": self.agent_id}
            }

    async def _retrieve_from_sources(self, request: RetrievalRequest) -> Dict[str, RetrievalResult]:
        """Retrieve information from multiple sources based on strategy."""
        tasks = []
        results = {}

        if self.strategy.enable_vector_search and "vector" in request.source_types:
            tasks.append(("vector", self._search_vector_store(request)))

        if self.strategy.enable_arxiv_search and "arxiv" in request.source_types:
            tasks.append(("arxiv", self._search_arxiv(request)))

        if self.strategy.enable_memory_search and "memory" in request.source_types:
            tasks.append(("memory", self._search_memory(request)))

        if self.strategy.parallel_search:
            # Execute all searches in parallel
            task_results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            for i, (source, _) in enumerate(tasks):
                if isinstance(task_results[i], Exception):
                    logger.warning(f"Search failed for {source}: {str(task_results[i])}")
                    results[source] = self._empty_result(source)
                else:
                    results[source] = task_results[i]
        else:
            # Execute searches sequentially
            for source, task in tasks:
                try:
                    results[source] = await task
                except Exception as e:
                    logger.warning(f"Search failed for {source}: {str(e)}")
                    results[source] = self._empty_result(source)

        return results

    async def _search_vector_store(self, request: RetrievalRequest) -> RetrievalResult:
        """Search the vector store for relevant documents."""
        try:
            search_results = await self.knowledge_retrieval.search(
                query=request.query,
                top_k=request.max_results,
                filters=request.filters
            )

            documents = []
            for result in search_results:
                documents.append({
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0.0),
                    "source": "vector_store"
                })

            return RetrievalResult(
                documents=documents,
                metadata={
                    "search_params": {
                        "query": request.query,
                        "top_k": request.max_results,
                        "filters": request.filters
                    }
                },
                source="vector_store",
                confidence=self._calculate_average_confidence(documents),
                total_found=len(documents)
            )

        except Exception as e:
            logger.error(f"Vector store search failed: {str(e)}")
            return self._empty_result("vector_store")

    async def _search_arxiv(self, request: RetrievalRequest) -> RetrievalResult:
        """Search ArXiv for relevant papers."""
        try:
            papers = await self.arxiv_fetcher.search_papers(
                query=request.query,
                max_results=min(request.max_results, settings.arxiv_max_results)
            )

            documents = []
            for paper in papers:
                documents.append({
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract", ""),
                    "authors": paper.get("authors", []),
                    "published": paper.get("published", ""),
                    "arxiv_id": paper.get("arxiv_id", ""),
                    "url": paper.get("url", ""),
                    "source": "arxiv"
                })

            return RetrievalResult(
                documents=documents,
                metadata={
                    "search_query": request.query,
                    "max_results": min(request.max_results, settings.arxiv_max_results)
                },
                source="arxiv",
                confidence=0.8 if documents else 0.0,  # ArXiv results are generally reliable
                total_found=len(documents)
            )

        except Exception as e:
            logger.error(f"ArXiv search failed: {str(e)}")
            return self._empty_result("arxiv")

    async def _search_memory(self, request: RetrievalRequest) -> RetrievalResult:
        """Search memory stores for relevant information."""
        try:
            documents = []
            
            # Search episodic memory
            episodic_results = await self.episodic_memory.search(
                query=request.query,
                limit=request.max_results // 2
            )
            for result in episodic_results:
                documents.append({
                    "content": result.get("content", ""),
                    "timestamp": result.get("timestamp", ""),
                    "metadata": result.get("metadata", {}),
                    "source": "episodic_memory"
                })

            # Search semantic memory
            semantic_results = await self.semantic_memory.search(
                query=request.query,
                limit=request.max_results // 2
            )
            for result in semantic_results:
                documents.append({
                    "concept": result.get("concept", ""),
                    "definition": result.get("definition", ""),
                    "relationships": result.get("relationships", []),
                    "metadata": result.get("metadata", {}),
                    "source": "semantic_memory"
                })

            return RetrievalResult(
                documents=documents,
                metadata={
                    "episodic_count": len(episodic_results),
                    "semantic_count": len(semantic_results)
                },
                source="memory",
                confidence=self._calculate_memory_confidence(documents),
                total_found=len(documents)
            )

        except Exception as e:
            logger.error(f"Memory search failed: {str(e)}")
            return self._empty_result("memory")

    async def _consolidate_results(self, results: Dict[str, RetrievalResult], request: RetrievalRequest) -> Dict[str, Any]:
        """Consolidate and rank results from multiple sources."""
        all_documents = []
        source_metadata = {}

        # Collect all documents with source information
        for source, result in results.items():
            source_metadata[source] = result.metadata
            for doc in result.documents:
                doc["retrieval_source"] = source
                doc["source_confidence"] = result.confidence
                all_documents.append(doc)

        # Apply reranking if enabled
        if self.strategy.rerank_results:
            all_documents = await self._rerank_documents(all_documents, request.query)

        # Limit total results
        all_documents = all_documents[:self.strategy.max_total_results]

        return {
            "documents": all_documents,
            "source_metadata": source_metadata,
            "total_documents": len(all_documents),
            "sources_used": list(results.keys()),
            "consolidated_confidence": self._calculate_consolidated_confidence(results)
        }

    async def _rerank_documents(self, documents: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Rerank documents based on relevance to the query."""
        try:
            # Simple relevance scoring based on query term presence
            scored_docs = []
            query_terms = query.lower().split()

            for doc in documents:
                score = 0.0
                text_content = self._extract_text_content(doc).lower()
                
                # Score based on query term presence
                for term in query_terms:
                    score += text_content.count(term) * 0.1
                
                # Boost based on source confidence
                score *= doc.get("source_confidence", 0.5)
                
                # Boost recent or high-quality sources
                if doc.get("retrieval_source") == "arxiv":
                    score *= 1.2
                elif doc.get("retrieval_source") == "vector_store":
                    score *= 1.1

                doc["relevance_score"] = score
                scored_docs.append(doc)

            # Sort by relevance score
            scored_docs.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            return scored_docs

        except Exception as e:
            logger.warning(f"Reranking failed: {str(e)}, returning original order")
            return documents

    def _extract_text_content(self, doc: Dict[str, Any]) -> str:
        """Extract text content from a document for scoring."""
        content_fields = ["content", "abstract", "title", "definition"]
        text_parts = []
        
        for field in content_fields:
            if field in doc and doc[field]:
                text_parts.append(str(doc[field]))
        
        return " ".join(text_parts)

    def _calculate_average_confidence(self, documents: List[Dict[str, Any]]) -> float:
        """Calculate average confidence score for documents."""
        if not documents:
            return 0.0
        
        scores = [doc.get("score", 0.0) for doc in documents if "score" in doc]
        return sum(scores) / len(scores) if scores else 0.5

    def _calculate_memory_confidence(self, documents: List[Dict[str, Any]]) -> float:
        """Calculate confidence score for memory-based results."""
        if not documents:
            return 0.0
        
        # Memory results are generally reliable but context-dependent
        return 0.7

    def _calculate_consolidated_confidence(self, results: Dict[str, RetrievalResult]) -> float:
        """Calculate overall confidence from multiple sources."""
        if not results:
            return 0.0
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for source, result in results.items():
            weight = result.total_found  # Weight by number of results
            weighted_sum += result.confidence * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _empty_result(self, source: str) -> RetrievalResult:
        """Create an empty retrieval result for failed searches."""
        return RetrievalResult(
            documents=[],
            metadata={"error": "Search failed"},
            source=source,
            confidence=0.0,
            total_found=0
        )

    def _generate_cache_key(self, request: RetrievalRequest) -> str:
        """Generate a cache key for the retrieval request."""
        import hashlib
        key_data = f"{request.query}_{request.max_results}_{sorted(request.source_types)}_{str(request.filters)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    async def clear_cache(self) -> None:
        """Clear the retrieval cache."""
        self.cache.clear()
        logger.info("Retrieval cache cleared")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": len(self.cache),
            "cache_keys": list(self.cache.keys())
        }

    async def update_strategy(self, strategy: RetrievalStrategy) -> None:
        """Update retrieval strategy."""
        self.strategy = strategy
        await self.clear_cache()  # Clear cache when strategy changes
        logger.info(f"Updated retrieval strategy: {strategy.model_dump()}")
    async def process_task(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def get_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def run(self, *args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'comprehensive'})

    async def process_message(self, *args, **kwargs):
        return await self.process_request(*args, **kwargs)
