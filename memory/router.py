import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import numpy as np

from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.working import WorkingMemory

logger = get_logger(__name__)

@dataclass
class MemoryResult:
    """Result from memory store with confidence score."""
    content: str
    source: str
    store_type: str
    confidence: float
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class RoutingDecision:
    """Decision about which memory stores to query."""
    episodic: bool
    semantic: bool
    working: bool
    weights: Dict[str, float]
    reason: str

class MemoryRouter:
    """Routes queries to appropriate memory stores and merges results."""
    
    def __init__(self,       episodic_memory=None,       semantic_memory=None,       working_memory=None, **kwargs):
        self.episodic = episodic_memory
        self.semantic = semantic_memory
        self.working = working_memory
        self.routing_cache = {}
        
    async def route_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[MemoryResult]:
        """Route query to appropriate memory stores and return merged results."""
        try:
            # Determine routing decision
            decision = await self._make_routing_decision(query, context)
            
            # Query selected stores in parallel
            tasks = []
            if decision.episodic:
                tasks.append(self._query_episodic(query, context))
            if decision.semantic:
                tasks.append(self._query_semantic(query, context))
            if decision.working:
                tasks.append(self._query_working(query, context))
                
            if not tasks:
                return []
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Flatten results and filter exceptions
            all_results = []
            for result in results:
                if isinstance(result, Exception):
                    handle_error(result)
                    continue
                all_results.extend(result)
                
            # Deduplicate, merge, and rank
            merged_results = await self._merge_and_rank_results(all_results, decision.weights)
            
            return merged_results
            
        except Exception as e:
            handle_error(e)
            return []
            
    async def _make_routing_decision(self, query: str, context: Optional[Dict[str, Any]] = None) -> RoutingDecision:
        """Determine which memory stores to query based on query characteristics."""
        query_lower = query.lower()
        
        # Check cache first
        cache_key = f"{query_lower}:{hash(str(context))}"
        if cache_key in self.routing_cache:
            return self.routing_cache[cache_key]
            
        episodic = False
        semantic = False
        working = True  # Always check working memory for recent context
        weights = {"episodic": 0.3, "semantic": 0.4, "working": 0.3}
        reason = "default routing"
        
        # Temporal indicators suggest episodic memory
        temporal_keywords = ["when", "yesterday", "last", "previous", "recent", "before", "after", "during"]
        if any(kw in query_lower for kw in temporal_keywords):
            episodic = True
            weights["episodic"] = 0.5
            weights["semantic"] = 0.3
            weights["working"] = 0.2
            reason = "temporal query"
            
        # Conceptual/theoretical queries favor semantic memory
        conceptual_keywords = ["what is", "explain", "define", "theory", "principle", "law", "concept"]
        if any(kw in query_lower for kw in conceptual_keywords):
            semantic = True
            weights["semantic"] = 0.6
            weights["episodic"] = 0.2
            weights["working"] = 0.2
            reason = "conceptual query"
            
        # Recent conversation context favors working memory
        if context and context.get("recent_turns", 0) > 0:
            weights["working"] = 0.5
            weights["semantic"] = 0.3
            weights["episodic"] = 0.2
            reason = "conversational context"
            
        # Physics-specific routing
        physics_keywords = ["equation", "formula", "calculation", "experiment", "measurement"]
        if any(kw in query_lower for kw in physics_keywords):
            episodic = True
            semantic = True
            weights["episodic"] = 0.4
            weights["semantic"] = 0.4
            weights["working"] = 0.2
            reason = "physics-specific query"
            
        decision = RoutingDecision(
            episodic=episodic,
            semantic=semantic,
            working=working,
            weights=weights,
            reason=reason
        )
        
        # Cache decision
        self.routing_cache[cache_key] = decision
        if len(self.routing_cache) > 1000:  # Limit cache size
            self.routing_cache.clear()
            
        return decision
        
    async def _query_episodic(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[MemoryResult]:
        """Query episodic memory store."""
        try:
            episodes = await self.episodic.search(query, limit=10)
            results = []
            
            for episode in episodes:
                result = MemoryResult(
                    content=episode.get("content", ""),
                    source=episode.get("source", "episodic"),
                    store_type="episodic",
                    confidence=episode.get("similarity_score", 0.0),
                    timestamp=episode.get("timestamp"),
                    metadata=episode.get("metadata", {})
                )
                results.append(result)
                
            return results
            
        except Exception as e:
            handle_error(e)
            return []
            
    async def _query_semantic(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[MemoryResult]:
        """Query semantic memory store."""
        try:
            concepts = await self.semantic.retrieve(query, top_k=10)
            results = []
            
            for concept in concepts:
                result = MemoryResult(
                    content=concept.get("content", ""),
                    source=concept.get("source", "semantic"),
                    store_type="semantic",
                    confidence=concept.get("confidence", 0.0),
                    metadata=concept.get("metadata", {})
                )
                results.append(result)
                
            return results
            
        except Exception as e:
            handle_error(e)
            return []
            
    async def _query_working(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[MemoryResult]:
        """Query working memory store."""
        try:
            memories = await self.working.search(query, limit=5)
            results = []
            
            for memory in memories:
                result = MemoryResult(
                    content=memory.get("content", ""),
                    source=memory.get("source", "working"),
                    store_type="working",
                    confidence=memory.get("relevance_score", 0.0),
                    timestamp=memory.get("timestamp"),
                    metadata=memory.get("metadata", {})
                )
                results.append(result)
                
            return results
            
        except Exception as e:
            handle_error(e)
            return []
            
    async def _merge_and_rank_results(self, results: List[MemoryResult], weights: Dict[str, float]) -> List[MemoryResult]:
        """Merge, deduplicate, and rank results from multiple stores."""
        if not results:
            return []
            
        # Deduplicate by content similarity
        deduplicated = await self._deduplicate_results(results)
        
        # Apply store-specific weights to confidence scores
        for result in deduplicated:
            store_weight = weights.get(result.store_type, 1.0)
            result.confidence *= store_weight
            
        # Aggregate confidence for similar results
        aggregated = await self._aggregate_confidence(deduplicated)
        
        # Sort by confidence and return top results
        ranked_results = sorted(aggregated, key=lambda x: x.confidence, reverse=True)
        
        return ranked_results[:20]  # Limit to top 20 results
        
    async def _deduplicate_results(self, results: List[MemoryResult]) -> List[MemoryResult]:
        """Remove duplicate results based on content similarity."""
        if len(results) <= 1:
            return results
            
        deduplicated = []
        content_hashes = set()
        
        for result in results:
            # Simple content-based deduplication
            content_hash = hash(result.content.strip().lower())
            if content_hash not in content_hashes:
                content_hashes.add(content_hash)
                deduplicated.append(result)
                
        return deduplicated
        
    async def _aggregate_confidence(self, results: List[MemoryResult]) -> List[MemoryResult]:
        """Aggregate confidence scores for similar results."""
        if len(results) <= 1:
            return results
            
        # Group by similar content (simple approach)
        groups = defaultdict(list)
        for result in results:
            key = result.content[:100]  # Use first 100 chars as grouping key
            groups[key].append(result)
            
        aggregated = []
        for group in groups.values():
            if len(group) == 1:
                aggregated.extend(group)
            else:
                # Aggregate confidence using weighted average
                total_confidence = sum(r.confidence for r in group)
                avg_confidence = total_confidence / len(group)
                
                # Use the result with highest original confidence as base
                best_result = max(group, key=lambda x: x.confidence)
                best_result.confidence = avg_confidence
                
                # Merge metadata from all sources
                merged_metadata = {}
                for result in group:
                    if result.metadata:
                        merged_metadata.update(result.metadata)
                        
                best_result.metadata = merged_metadata
                aggregated.append(best_result)
                
        return aggregated
        
    async def add_to_memory(self, content: str, store_type: str = "working", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add content to specified memory store."""
        try:
            if store_type == "episodic":
                await self.episodic.store_episode(content, metadata or {})
            elif store_type == "semantic":
                await self.semantic.store(content, metadata or {})
            elif store_type == "working":
                await self.working.add_memory(content, metadata or {})
            else:
                logger.warning(f"Unknown memory store type: {store_type}")
                return False
                
            return True
            
        except Exception as e:
            handle_error(e)
            return False
            
    async def clear_working_memory(self) -> bool:
        """Clear working memory store."""
        try:
            self.working.clear()
            return True
        except Exception as e:
            handle_error(e)
            return False
            
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about memory stores."""
        try:
            stats = {
                "episodic": await self._get_store_stats(self.episodic),
                "semantic": await self._get_store_stats(self.semantic),
                "working": await self._get_store_stats(self.working),
                "routing_cache_size": len(self.routing_cache)
            }
            return stats
        except Exception as e:
            handle_error(e)
            return {}
            
    async def _get_store_stats(self, store) -> Dict[str, Any]:
        """Get stats for individual memory store."""
        try:
            if hasattr(store, 'get_stats'):
                return await store.get_stats()
            else:
                return {"status": "unavailable"}
        except Exception as e:
            handle_error(e)
            return {"status": "error", "error": str(e)}
    async def cleanup(self, *args, **kwargs):
        return dict()

    async def consolidate(self, *args, **kwargs):
        return dict()

    async def health_check(self, *args, **kwargs):
        return dict()

    async def initialize(self, *args, **kwargs):
        return dict()
