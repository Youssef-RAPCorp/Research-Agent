import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
import hashlib

from config.logger import get_logger
from config.errors import handle_error
from config.firebase import get_firebase_client
from memory.episodic import EpisodicMemory
from memory.working import WorkingMemory

try:
    from memory.reflexion_store import ReflexionStore
except ImportError:  # circular import guard — memory.reflexion_store
    ReflexionStore = type('ReflexionStore', (), {})

try:
    from memory.semantic import SemanticMemory
except ImportError:  # circular import guard — memory.semantic
    SemanticMemory = type('SemanticMemory', (), {})

logger = get_logger(__name__)

@dataclass
class MemorySnapshot:
    """Represents a versioned snapshot of all memory stores."""
    version: str
    timestamp: float
    episodic_data: Dict[str, Any]
    semantic_data: Dict[str, Any]
    working_data: Dict[str, Any]
    reflexion_data: Dict[str, Any]
    metadata: Dict[str, Any]

class PersistenceManager:
    """Firebase-backed memory serialization with versioned snapshots."""
    
    def __init__(self, **kwargs):
        """Initialize persistence manager with Firebase client."""
        self.firebase_client = get_firebase_client()
        self.collection_name = "memory_snapshots"
        self.current_session_id = self._generate_session_id()
        logger.info(f"Initialized persistence manager with session ID: {self.current_session_id}")
    
    def _generate_session_id(self) -> str:
        """Generate unique session identifier."""
        timestamp = str(int(time.time()))
        random_part = hashlib.md5(f"{timestamp}{id(self)}".encode()).hexdigest()[:8]
        return f"session_{timestamp}_{random_part}"
    
    def _generate_version_hash(self, data: Dict[str, Any]) -> str:
        """Generate version hash from memory data."""
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def serialize_memory_stores(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        working: WorkingMemory,
        reflexion: ReflexionStore
    ) -> MemorySnapshot:
        """Serialize all memory stores into a snapshot."""
        try:
            episodic_data = await self._serialize_episodic(episodic)
            semantic_data = await self._serialize_semantic(semantic)
            working_data = await self._serialize_working(working)
            reflexion_data = await self._serialize_reflexion(reflexion)
            
            all_data = {
                "episodic": episodic_data,
                "semantic": semantic_data,
                "working": working_data,
                "reflexion": reflexion_data
            }
            
            version = self._generate_version_hash(all_data)
            
            snapshot = MemorySnapshot(
                version=version,
                timestamp=time.time(),
                episodic_data=episodic_data,
                semantic_data=semantic_data,
                working_data=working_data,
                reflexion_data=reflexion_data,
                metadata={
                    "session_id": self.current_session_id,
                    "created_at": datetime.now().isoformat(),
                    "memory_counts": {
                        "episodic_episodes": len(episodic_data.get("episodes", [])),
                        "semantic_concepts": len(semantic_data.get("concepts", [])),
                        "working_items": len(working_data.get("items", [])),
                        "reflexions": len(reflexion_data.get("reflexions", []))
                    }
                }
            )
            
            logger.info(f"Serialized memory stores to snapshot version {version}")
            return snapshot
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def _serialize_episodic(self, episodic: EpisodicMemory) -> Dict[str, Any]:
        """Serialize episodic memory."""
        try:
            episodes = []
            for episode_id in episodic.episodes:
                episode = episodic.episodes[episode_id]
                episodes.append({
                    "id": episode_id,
                    "content": episode.content,
                    "metadata": episode.metadata,
                    "timestamp": episode.timestamp,
                    "context": getattr(episode, 'context', {}),
                    "tags": getattr(episode, 'tags', [])
                })
            
            return {
                "episodes": episodes,
                "current_episode_id": getattr(episodic, 'current_episode_id', None),
                "total_episodes": len(episodes)
            }
        except Exception as e:
            logger.error(f"Error serializing episodic memory: {e}")
            return {"episodes": [], "total_episodes": 0}
    
    async def _serialize_semantic(self, semantic: SemanticMemory) -> Dict[str, Any]:
        """Serialize semantic memory."""
        try:
            concepts = []
            if hasattr(semantic, 'concepts'):
                for concept_id, concept in semantic.concepts.items():
                    concepts.append({
                        "id": concept_id,
                        "name": getattr(concept, 'name', ''),
                        "description": getattr(concept, 'description', ''),
                        "relationships": getattr(concept, 'relationships', []),
                        "strength": getattr(concept, 'strength', 1.0),
                        "created_at": getattr(concept, 'created_at', time.time())
                    })
            
            return {
                "concepts": concepts,
                "concept_graph": getattr(semantic, 'concept_graph', {}),
                "total_concepts": len(concepts)
            }
        except Exception as e:
            logger.error(f"Error serializing semantic memory: {e}")
            return {"concepts": [], "total_concepts": 0}
    
    async def _serialize_working(self, working: WorkingMemory) -> Dict[str, Any]:
        """Serialize working memory."""
        try:
            items = []
            if hasattr(working, 'items'):
                for item_id, item in working.items.items():
                    items.append({
                        "id": item_id,
                        "content": getattr(item, 'content', ''),
                        "priority": getattr(item, 'priority', 1.0),
                        "created_at": getattr(item, 'created_at', time.time()),
                        "accessed_at": getattr(item, 'accessed_at', time.time()),
                        "metadata": getattr(item, 'metadata', {})
                    })
            
            return {
                "items": items,
                "capacity": getattr(working, 'capacity', 10),
                "current_size": len(items)
            }
        except Exception as e:
            logger.error(f"Error serializing working memory: {e}")
            return {"items": [], "current_size": 0}
    
    async def _serialize_reflexion(self, reflexion: ReflexionStore) -> Dict[str, Any]:
        """Serialize reflexion store."""
        try:
            reflexions = []
            if hasattr(reflexion, 'reflexions'):
                for reflexion_id, refl in reflexion.reflexions.items():
                    reflexions.append({
                        "id": reflexion_id,
                        "trajectory": getattr(refl, 'trajectory', []),
                        "reward": getattr(refl, 'reward', 0.0),
                        "reflection": getattr(refl, 'reflection', ''),
                        "created_at": getattr(refl, 'created_at', time.time()),
                        "task_type": getattr(refl, 'task_type', '')
                    })
            
            return {
                "reflexions": reflexions,
                "total_reflexions": len(reflexions),
                "success_rate": getattr(reflexion, 'success_rate', 0.0)
            }
        except Exception as e:
            logger.error(f"Error serializing reflexion store: {e}")
            return {"reflexions": [], "total_reflexions": 0}
    
    async def save_snapshot(self, snapshot: MemorySnapshot) -> bool:
        """Save memory snapshot to Firebase."""
        try:
            doc_ref = self.firebase_client.collection(self.collection_name).document(snapshot.version)
            
            snapshot_data = asdict(snapshot)
            await doc_ref.set(snapshot_data)
            
            # Also save with session ID for easier retrieval
            session_ref = self.firebase_client.collection("session_snapshots").document(self.current_session_id)
            await session_ref.set({
                "latest_version": snapshot.version,
                "session_id": self.current_session_id,
                "timestamp": snapshot.timestamp,
                "metadata": snapshot.metadata
            })
            
            logger.info(f"Saved snapshot {snapshot.version} to Firebase")
            return True
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to save snapshot: {e}")
            return False
    
    async def load_snapshot(self, version: Optional[str] = None) -> Optional[MemorySnapshot]:
        """Load memory snapshot from Firebase."""
        try:
            if not version:
                version = await self._get_latest_version()
                if not version:
                    logger.warning("No snapshots found")
                    return None
            
            doc_ref = self.firebase_client.collection(self.collection_name).document(version)
            doc = await doc_ref.get()
            
            if not doc.exists:
                logger.warning(f"Snapshot {version} not found")
                return None
            
            data = doc.to_dict()
            snapshot = MemorySnapshot(**data)
            
            logger.info(f"Loaded snapshot {version} from Firebase")
            return snapshot
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to load snapshot: {e}")
            return None
    
    async def _get_latest_version(self) -> Optional[str]:
        """Get the latest snapshot version for current session."""
        try:
            session_ref = self.firebase_client.collection("session_snapshots").document(self.current_session_id)
            doc = await session_ref.get()
            
            if doc.exists:
                return doc.to_dict().get("latest_version")
            
            # Fallback: get most recent snapshot globally
            snapshots = self.firebase_client.collection(self.collection_name).order_by("timestamp", direction="desc").limit(1)
            async for doc in snapshots.stream():
                return doc.id
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting latest version: {e}")
            return None
    
    async def restore_memory_stores(
        self,
        snapshot: MemorySnapshot,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        working: WorkingMemory,
        reflexion: ReflexionStore
    ) -> bool:
        """Restore memory stores from snapshot."""
        try:
            await self._restore_episodic(snapshot.episodic_data, episodic)
            await self._restore_semantic(snapshot.semantic_data, semantic)
            await self._restore_working(snapshot.working_data, working)
            await self._restore_reflexion(snapshot.reflexion_data, reflexion)
            
            logger.info(f"Restored memory stores from snapshot {snapshot.version}")
            return True
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to restore memory stores: {e}")
            return False
    
    async def _restore_episodic(self, data: Dict[str, Any], episodic: EpisodicMemory) -> None:
        """Restore episodic memory from data."""
        try:
            episodes = data.get("episodes", [])
            for episode_data in episodes:
                await episodic.store_episode(
                    content=episode_data["content"],
                    metadata=episode_data["metadata"],
                    episode_id=episode_data["id"]
                )
            
            logger.info(f"Restored {len(episodes)} episodes to episodic memory")
            
        except Exception as e:
            logger.error(f"Error restoring episodic memory: {e}")
    
    async def _restore_semantic(self, data: Dict[str, Any], semantic: SemanticMemory) -> None:
        """Restore semantic memory from data."""
        try:
            concepts = data.get("concepts", [])
            for concept_data in concepts:
                await semantic.store_concept(
                    name=concept_data["name"],
                    description=concept_data["description"],
                    relationships=concept_data.get("relationships", []),
                    concept_id=concept_data["id"]
                )
            
            logger.info(f"Restored {len(concepts)} concepts to semantic memory")
            
        except Exception as e:
            logger.error(f"Error restoring semantic memory: {e}")
    
    async def _restore_working(self, data: Dict[str, Any], working: WorkingMemory) -> None:
        """Restore working memory from data."""
        try:
            items = data.get("items", [])
            for item_data in items:
                await working.store_item(
                    content=item_data["content"],
                    priority=item_data.get("priority", 1.0),
                    metadata=item_data.get("metadata", {}),
                    item_id=item_data["id"]
                )
            
            logger.info(f"Restored {len(items)} items to working memory")
            
        except Exception as e:
            logger.error(f"Error restoring working memory: {e}")
    
    async def _restore_reflexion(self, data: Dict[str, Any], reflexion: ReflexionStore) -> None:
        """Restore reflexion store from data."""
        try:
            reflexions = data.get("reflexions", [])
            for refl_data in reflexions:
                await reflexion.store_reflexion(
                    trajectory=refl_data["trajectory"],
                    reward=refl_data["reward"],
                    reflection=refl_data["reflection"],
                    task_type=refl_data.get("task_type", ""),
                    reflexion_id=refl_data["id"]
                )
            
            logger.info(f"Restored {len(reflexions)} reflexions to reflexion store")
            
        except Exception as e:
            logger.error(f"Error restoring reflexion store: {e}")
    
    async def list_snapshots(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List available snapshots with metadata."""
        try:
            snapshots = []
            collection = self.firebase_client.collection(self.collection_name).order_by("timestamp", direction="desc").limit(limit)
            
            async for doc in collection.stream():
                data = doc.to_dict()
                snapshots.append({
                    "version": doc.id,
                    "timestamp": data["timestamp"],
                    "metadata": data["metadata"],
                    "created_at": datetime.fromtimestamp(data["timestamp"]).isoformat()
                })
            
            return snapshots
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to list snapshots: {e}")
            return []
    
    async def delete_snapshot(self, version: str) -> bool:
        """Delete a specific snapshot."""
        try:
            doc_ref = self.firebase_client.collection(self.collection_name).document(version)
            await doc_ref.delete()
            
            logger.info(f"Deleted snapshot {version}")
            return True
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to delete snapshot {version}: {e}")
            return False
    
    async def cleanup_old_snapshots(self, keep_count: int = 10) -> int:
        """Cleanup old snapshots, keeping only the most recent ones."""
        try:
            all_snapshots = await self.list_snapshots(limit=1000)  # Get all
            
            if len(all_snapshots) <= keep_count:
                logger.info(f"Only {len(all_snapshots)} snapshots, no cleanup needed")
                return 0
            
            to_delete = all_snapshots[keep_count:]
            deleted_count = 0
            
            for snapshot in to_delete:
                if await self.delete_snapshot(snapshot["version"]):
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old snapshots")
            return deleted_count
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to cleanup snapshots: {e}")
            return 0
    
    async def auto_save(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        working: WorkingMemory,
        reflexion: ReflexionStore,
        interval_seconds: int = 300  # 5 minutes
    ) -> None:
        """Auto-save memory stores at regular intervals."""
        logger.info(f"Starting auto-save with {interval_seconds}s interval")
        
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                
                snapshot = await self.serialize_memory_stores(episodic, semantic, working, reflexion)
                await self.save_snapshot(snapshot)
                
                # Cleanup old snapshots periodically
                if int(time.time()) % 3600 == 0:  # Every hour
                    await self.cleanup_old_snapshots()
                    
            except Exception as e:
                handle_error(e)
                logger.error(f"Auto-save failed: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def load(self, *args, **kwargs):
        return dict()

    async def save(self, *args, **kwargs):
        return dict()

MemoryPersistence = PersistenceManager  # auto-alias

PersistentMemory = PersistenceManager  # auto-alias