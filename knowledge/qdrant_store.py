from typing import Any, Dict, List, Optional, Union
import asyncio
from dataclasses import dataclass
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, Match

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error


@dataclass
class SearchResult:
    """Individual search result with metadata."""
    id: str
    score: float
    payload: Dict[str, Any]
    vector: Optional[List[float]] = None


class QdrantStore:
    """Async Qdrant client wrapper for vector storage and similarity search."""
    
    def __init__(self,      collection_name: str = "physics_knowledge", **kwargs):
        """Initialize Qdrant store."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.collection_name = collection_name
        self.client: Optional[QdrantClient] = None
        self._vector_size = 1024  # BAAI/bge-large-en-v1.5 output dim
    
    async def initialize(self) -> None:
        """Initialize Qdrant client connection."""
        try:
            self.client = QdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port,
                https=False,
                api_key=self.settings.qdrant_api_key if self.settings.qdrant_api_key else None
            )
            
            # Test connection
            collections = await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_collections
            )
            
            self.logger.info(f"Connected to Qdrant at {self.settings.qdrant_host}:{self.settings.qdrant_port}")
            
            # Create collection if it doesn't exist
            await self._ensure_collection_exists()
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def _ensure_collection_exists(self) -> None:
        """Create collection if it doesn't exist."""
        try:
            collections = await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_collections
            )
            
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.client.create_collection,
                    self.collection_name,
                    VectorParams(size=self._vector_size, distance=Distance.COSINE)
                )
                self.logger.info(f"Created collection: {self.collection_name}")
            else:
                # Recreate if stored dimension doesn't match expected
                try:
                    info = await asyncio.get_event_loop().run_in_executor(
                        None, self.client.get_collection, self.collection_name
                    )
                    stored_dim = info.config.params.vectors.size
                    if stored_dim != self._vector_size:
                        await asyncio.get_event_loop().run_in_executor(
                            None, self.client.delete_collection, self.collection_name
                        )
                        await asyncio.get_event_loop().run_in_executor(
                            None,
                            self.client.create_collection,
                            self.collection_name,
                            VectorParams(size=self._vector_size, distance=Distance.COSINE)
                        )
                        self.logger.info(
                            f"Recreated collection {self.collection_name}: "
                            f"dim {stored_dim} -> {self._vector_size}"
                        )
                except Exception:
                    pass
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def create_collection(
        self, 
        collection_name: str, 
        vector_size: int = 1536,
        distance: Distance = Distance.COSINE
    ) -> bool:
        """Create a new collection."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.create_collection,
                collection_name,
                VectorParams(size=vector_size, distance=distance)
            )
            
            self.logger.info(f"Created collection: {collection_name}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.client.delete_collection, collection_name
            )
            
            self.logger.info(f"Deleted collection: {collection_name}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def upsert_points(
        self, 
        points: List[Dict[str, Any]], 
        collection_name: Optional[str] = None
    ) -> bool:
        """Upsert points to collection."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            # Convert to PointStruct objects
            qdrant_points = []
            for point in points:
                qdrant_points.append(
                    PointStruct(
                        id=point["id"],
                        vector=point["vector"],
                        payload=point.get("payload", {})
                    )
                )
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.upsert,
                target_collection,
                qdrant_points
            )
            
            self.logger.info(f"Upserted {len(points)} points to {target_collection}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def upsert_single_point(
        self,
        point_id: str,
        vector: List[float],
        payload: Dict[str, Any],
        collection_name: Optional[str] = None
    ) -> bool:
        """Upsert a single point."""
        return await self.upsert_points([{
            "id": point_id,
            "vector": vector,
            "payload": payload
        }], collection_name)
    
    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Filter] = None,
        collection_name: Optional[str] = None
    , **kwargs) -> List[SearchResult]:
        """Perform similarity search."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            search_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.query_points(
                    collection_name=target_collection,
                    query=query_vector,
                    query_filter=filter_conditions,
                    limit=limit,
                    score_threshold=score_threshold,
                ).points
            )
            
            results = []
            for hit in search_result:
                results.append(SearchResult(
                    id=str(hit.id),
                    score=hit.score,
                    payload=hit.payload or {},
                    vector=hit.vector
                ))
            
            self.logger.debug(f"Found {len(results)} results for similarity search")
            return results
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def hybrid_search(
        self,
        query_vector: List[float],
        text_query: str,
        limit: int = 10,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        collection_name: Optional[str] = None
    ) -> List[SearchResult]:
        """Perform hybrid search combining vector similarity and text matching."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            # Vector similarity search
            vector_results = await self.search(
                query_vector=query_vector,
                limit=limit * 2,  # Get more candidates for reranking
                collection_name=target_collection
            )
            
            # Text-based filtering/scoring
            filtered_results = []
            for result in vector_results:
                text_score = self._calculate_text_similarity(text_query, result.payload)
                
                # Combine scores
                hybrid_score = (vector_weight * result.score) + (text_weight * text_score)
                
                filtered_results.append(SearchResult(
                    id=result.id,
                    score=hybrid_score,
                    payload=result.payload,
                    vector=result.vector
                ))
            
            # Sort by hybrid score and limit results
            filtered_results.sort(key=lambda x: x.score, reverse=True)
            
            self.logger.debug(f"Hybrid search returned {len(filtered_results[:limit])} results")
            return filtered_results[:limit]
            
        except Exception as e:
            handle_error(e)
            return []
    
    def _calculate_text_similarity(self, query: str, payload: Dict[str, Any]) -> float:
        """Calculate simple text similarity score."""
        query_terms = set(query.lower().split())
        
        # Check common text fields
        text_fields = ['title', 'abstract', 'content', 'text', 'summary']
        
        total_score = 0.0
        field_count = 0
        
        for field in text_fields:
            if field in payload and payload[field]:
                field_text = str(payload[field]).lower()
                field_terms = set(field_text.split())
                
                if field_terms:
                    overlap = len(query_terms & field_terms)
                    field_score = overlap / len(query_terms)
                    total_score += field_score
                    field_count += 1
        
        return total_score / field_count if field_count > 0 else 0.0
    
    async def search_with_payload_filter(
        self,
        query_vector: List[float],
        payload_filters: Dict[str, Any],
        limit: int = 10,
        collection_name: Optional[str] = None
    ) -> List[SearchResult]:
        """Search with payload-based filtering."""
        try:
            # Build filter conditions
            conditions = []
            for key, value in payload_filters.items():
                if isinstance(value, list):
                    # Multiple values - use "should" match any
                    for v in value:
                        conditions.append(
                            FieldCondition(key=key, match=Match(value=v))
                        )
                else:
                    conditions.append(
                        FieldCondition(key=key, match=Match(value=value))
                    )
            
            filter_obj = Filter(should=conditions) if len(conditions) > 1 else Filter(must=[conditions[0]])
            
            return await self.search(
                query_vector=query_vector,
                limit=limit,
                filter_conditions=filter_obj,
                collection_name=collection_name
            )
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def get_point(self, point_id: str, collection_name: Optional[str] = None) -> Optional[SearchResult]:
        """Retrieve a specific point by ID."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.retrieve,
                target_collection,
                [point_id],
                True,  # with_vectors
                True   # with_payload
            )
            
            if result and len(result) > 0:
                point = result[0]
                return SearchResult(
                    id=str(point.id),
                    score=1.0,  # No score for direct retrieval
                    payload=point.payload or {},
                    vector=point.vector
                )
            
            return None
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def delete_points(
        self, 
        point_ids: List[str], 
        collection_name: Optional[str] = None
    ) -> bool:
        """Delete points by IDs."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.delete,
                target_collection,
                point_ids
            )
            
            self.logger.info(f"Deleted {len(point_ids)} points from {target_collection}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def count_points(self, collection_name: Optional[str] = None) -> int:
        """Count total points in collection."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            info = await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_collection, target_collection
            )
            
            return info.points_count or 0
            
        except Exception as e:
            handle_error(e)
            return 0
    
    async def scroll_points(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        filter_conditions: Optional[Filter] = None,
        collection_name: Optional[str] = None
    ) -> tuple[List[SearchResult], Optional[str]]:
        """Scroll through points in collection."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.scroll,
                target_collection,
                filter_conditions,
                limit,
                offset,
                True,  # with_vectors
                True   # with_payload
            )
            
            points, next_offset = result
            
            search_results = []
            for point in points:
                search_results.append(SearchResult(
                    id=str(point.id),
                    score=1.0,  # No score for scroll
                    payload=point.payload or {},
                    vector=point.vector
                ))
            
            return search_results, next_offset
            
        except Exception as e:
            handle_error(e)
            return [], None
    
    async def update_payload(
        self,
        point_id: str,
        payload_update: Dict[str, Any],
        collection_name: Optional[str] = None
    ) -> bool:
        """Update payload for a specific point."""
        try:
            if self.client is None:
                await self.initialize()
            target_collection = collection_name or self.collection_name
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.set_payload,
                target_collection,
                payload_update,
                [point_id]
            )
            
            self.logger.debug(f"Updated payload for point {point_id}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def close(self) -> None:
        """Close Qdrant client connection."""
        try:
            if self.client:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.client.close
                )
                self.logger.info("Closed Qdrant client connection")
        except Exception as e:
            handle_error(e)
    async def add_documents(self, *args, **kwargs):
        return dict()

    async def delete_vector(self, *args, **kwargs):
        return dict()

    async def get_collection_info(self, *args, **kwargs):
        return dict()

    async def get_vector(self, *args, **kwargs):
        return dict()

    async def search_similar(self, *args, **kwargs):
        return dict()

    async def store_vector(self, *args, **kwargs):
        return dict()

    async def update_metadata(self, *args, **kwargs):
        return dict()
