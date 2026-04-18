"""
Episodic Memory Module
Provides per-agent timestamped storage of observations, actions, outcomes, and valence.
"""

import asyncio
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np

from config.logger import get_logger
from config.errors import handle_error

logger = get_logger(__name__)


@dataclass
class EpisodeEntry:
    """Single episodic memory entry with timestamp and valence."""
    timestamp: datetime
    agent_id: str
    observation: Dict[str, Any]
    action: Dict[str, Any]
    outcome: Dict[str, Any]
    valence: float  # -1.0 to 1.0, emotion-analogue
    context: Optional[Dict[str, Any]] = None
    episode_id: Optional[str] = None


class EpisodicMemory:
    """Per-agent episodic memory store with temporal queries and decay."""
    
    def __init__(
        self,     
        db_path: str = "episodic_memory.db",     
        decay_half_life_hours: float = 168.0,       # 1 week
        max_entries_per_agent: int = 10000
    , **kwargs):
        """Initialize episodic memory with SQLite backend."""
        self.db_path = Path(db_path)
        self.decay_half_life_hours = decay_half_life_hours
        self.max_entries_per_agent = max_entries_per_agent
        self._lock = threading.RLock()
        self._init_database()
        
    def _init_database(self) -> None:
        """Initialize SQLite database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS episodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        observation TEXT NOT NULL,
                        action TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        valence REAL NOT NULL,
                        context TEXT,
                        episode_id TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_agent_timestamp 
                    ON episodes(agent_id, timestamp)
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_valence 
                    ON episodes(agent_id, valence)
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_episode_id 
                    ON episodes(episode_id)
                """)
                
                conn.commit()
                logger.info(f"Initialized episodic memory database at {self.db_path}")
                
        except Exception as e:
            handle_error(e)
            raise
            
    async def store_episode(self, entry: EpisodeEntry) -> str:
        """Store a new episodic memory entry."""
        try:
            with self._lock:
                # Generate episode ID if not provided
                if not entry.episode_id:
                    entry.episode_id = f"{entry.agent_id}_{entry.timestamp.isoformat()}_{hash(str(entry.observation))}"
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        INSERT INTO episodes 
                        (timestamp, agent_id, observation, action, outcome, valence, context, episode_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        entry.timestamp.isoformat(),
                        entry.agent_id,
                        json.dumps(entry.observation),
                        json.dumps(entry.action),
                        json.dumps(entry.outcome),
                        entry.valence,
                        json.dumps(entry.context) if entry.context else None,
                        entry.episode_id
                    ))
                    
                    conn.commit()
                    
                # Clean up old entries if needed
                await self._cleanup_agent_entries(entry.agent_id)
                
                logger.debug(f"Stored episode {entry.episode_id} for agent {entry.agent_id}")
                return entry.episode_id
                
        except Exception as e:
            handle_error(e)
            raise
            
    async def get_recent_episodes(
        self,
        agent_id: str,
        limit: int = 50,
        hours_back: Optional[float] = None
    ) -> List[EpisodeEntry]:
        """Get recent episodes for an agent."""
        try:
            with self._lock:
                query = """
                    SELECT timestamp, agent_id, observation, action, outcome, valence, context, episode_id
                    FROM episodes
                    WHERE agent_id = ?
                """
                params = [agent_id]
                
                if hours_back:
                    cutoff = datetime.now() - timedelta(hours=hours_back)
                    query += " AND timestamp >= ?"
                    params.append(cutoff.isoformat())
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(query, params)
                    rows = cursor.fetchall()
                    
                episodes = []
                for row in rows:
                    episodes.append(EpisodeEntry(
                        timestamp=datetime.fromisoformat(row[0]),
                        agent_id=row[1],
                        observation=json.loads(row[2]),
                        action=json.loads(row[3]),
                        outcome=json.loads(row[4]),
                        valence=row[5],
                        context=json.loads(row[6]) if row[6] else None,
                        episode_id=row[7]
                    ))
                    
                return episodes
                
        except Exception as e:
            handle_error(e)
            return []
            
    async def get_episodes_by_valence(
        self,
        agent_id: str,
        min_valence: float = 0.5,
        limit: int = 20
    ) -> List[EpisodeEntry]:
        """Get episodes filtered by valence threshold."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT timestamp, agent_id, observation, action, outcome, valence, context, episode_id
                        FROM episodes
                        WHERE agent_id = ? AND valence >= ?
                        ORDER BY valence DESC, timestamp DESC
                        LIMIT ?
                    """, (agent_id, min_valence, limit))
                    
                    rows = cursor.fetchall()
                    
                episodes = []
                for row in rows:
                    episodes.append(EpisodeEntry(
                        timestamp=datetime.fromisoformat(row[0]),
                        agent_id=row[1],
                        observation=json.loads(row[2]),
                        action=json.loads(row[3]),
                        outcome=json.loads(row[4]),
                        valence=row[5],
                        context=json.loads(row[6]) if row[6] else None,
                        episode_id=row[7]
                    ))
                    
                return episodes
                
        except Exception as e:
            handle_error(e)
            return []
            
    async def get_temporal_pattern(
        self,
        agent_id: str,
        pattern_hours: float = 24.0,
        min_entries: int = 5
    ) -> Dict[str, Any]:
        """Analyze temporal patterns in episodic memory."""
        try:
            episodes = await self.get_recent_episodes(
                agent_id, 
                limit=1000, 
                hours_back=pattern_hours
            )
            
            if len(episodes) < min_entries:
                return {"pattern": "insufficient_data", "count": len(episodes)}
                
            valences = [ep.valence for ep in episodes]
            timestamps = [ep.timestamp for ep in episodes]
            
            # Calculate statistics
            avg_valence = np.mean(valences)
            valence_trend = np.polyfit(range(len(valences)), valences, 1)[0]
            
            # Time intervals between episodes
            intervals = []
            for i in range(1, len(timestamps)):
                delta = (timestamps[i-1] - timestamps[i]).total_seconds() / 3600
                intervals.append(delta)
                
            avg_interval = np.mean(intervals) if intervals else 0
            
            return {
                "pattern": "temporal_analysis",
                "count": len(episodes),
                "avg_valence": float(avg_valence),
                "valence_trend": float(valence_trend),
                "avg_interval_hours": float(avg_interval),
                "valence_std": float(np.std(valences)),
                "time_span_hours": pattern_hours
            }
            
        except Exception as e:
            handle_error(e)
            return {"pattern": "error", "error": str(e)}
            
    async def search_episodes(
        self,
        agent_id: str,
        query_terms: List[str],
        limit: int = 20
    ) -> List[EpisodeEntry]:
        """Search episodes by content in observations, actions, or outcomes."""
        try:
            with self._lock:
                # Build LIKE conditions for each query term
                like_conditions = []
                params = [agent_id]
                
                for term in query_terms:
                    like_pattern = f"%{term}%"
                    like_conditions.append("""
                        (observation LIKE ? OR action LIKE ? OR outcome LIKE ?)
                    """)
                    params.extend([like_pattern, like_pattern, like_pattern])
                
                if not like_conditions:
                    return []
                    
                query = f"""
                    SELECT timestamp, agent_id, observation, action, outcome, valence, context, episode_id
                    FROM episodes
                    WHERE agent_id = ? AND ({' OR '.join(like_conditions)})
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params.append(limit)
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(query, params)
                    rows = cursor.fetchall()
                    
                episodes = []
                for row in rows:
                    episodes.append(EpisodeEntry(
                        timestamp=datetime.fromisoformat(row[0]),
                        agent_id=row[1],
                        observation=json.loads(row[2]),
                        action=json.loads(row[3]),
                        outcome=json.loads(row[4]),
                        valence=row[5],
                        context=json.loads(row[6]) if row[6] else None,
                        episode_id=row[7]
                    ))
                    
                return episodes
                
        except Exception as e:
            handle_error(e)
            return []
            
    async def get_episode_by_id(self, episode_id: str) -> Optional[EpisodeEntry]:
        """Retrieve a specific episode by ID."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT timestamp, agent_id, observation, action, outcome, valence, context, episode_id
                        FROM episodes
                        WHERE episode_id = ?
                    """, (episode_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        return EpisodeEntry(
                            timestamp=datetime.fromisoformat(row[0]),
                            agent_id=row[1],
                            observation=json.loads(row[2]),
                            action=json.loads(row[3]),
                            outcome=json.loads(row[4]),
                            valence=row[5],
                            context=json.loads(row[6]) if row[6] else None,
                            episode_id=row[7]
                        )
                    
                return None
                
        except Exception as e:
            handle_error(e)
            return None
            
    async def get_valence_weighted_episodes(
        self,
        agent_id: str,
        limit: int = 50,
        decay_factor: bool = True
    ) -> List[Tuple[EpisodeEntry, float]]:
        """Get episodes weighted by valence and optionally time decay."""
        try:
            episodes = await self.get_recent_episodes(agent_id, limit=limit * 2)
            
            weighted_episodes = []
            now = datetime.now()
            
            for episode in episodes:
                weight = episode.valence
                
                if decay_factor:
                    # Apply exponential decay based on time
                    hours_ago = (now - episode.timestamp).total_seconds() / 3600
                    decay = np.exp(-hours_ago / self.decay_half_life_hours)
                    weight *= decay
                    
                weighted_episodes.append((episode, weight))
                
            # Sort by weight descending
            weighted_episodes.sort(key=lambda x: x[1], reverse=True)
            
            return weighted_episodes[:limit]
            
        except Exception as e:
            handle_error(e)
            return []
            
    async def get_agent_summary(self, agent_id: str) -> Dict[str, Any]:
        """Get summary statistics for an agent's episodic memory."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT 
                            COUNT(*) as total_episodes,
                            AVG(valence) as avg_valence,
                            MIN(valence) as min_valence,
                            MAX(valence) as max_valence,
                            MIN(timestamp) as earliest_episode,
                            MAX(timestamp) as latest_episode
                        FROM episodes
                        WHERE agent_id = ?
                    """, (agent_id,))
                    
                    row = cursor.fetchone()
                    
                    if row and row[0] > 0:
                        return {
                            "agent_id": agent_id,
                            "total_episodes": row[0],
                            "avg_valence": float(row[1]) if row[1] else 0.0,
                            "min_valence": float(row[2]) if row[2] else 0.0,
                            "max_valence": float(row[3]) if row[3] else 0.0,
                            "earliest_episode": row[4],
                            "latest_episode": row[5],
                            "memory_span_hours": (
                                (datetime.fromisoformat(row[5]) - datetime.fromisoformat(row[4])).total_seconds() / 3600
                                if row[4] and row[5] else 0
                            )
                        }
                    else:
                        return {
                            "agent_id": agent_id,
                            "total_episodes": 0,
                            "avg_valence": 0.0,
                            "memory_span_hours": 0
                        }
                        
        except Exception as e:
            handle_error(e)
            return {"agent_id": agent_id, "error": str(e)}
            
    async def _cleanup_agent_entries(self, agent_id: str) -> None:
        """Remove old entries if agent exceeds max_entries_per_agent."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM episodes WHERE agent_id = ?
                """, (agent_id,))
                
                count = cursor.fetchone()[0]
                
                if count > self.max_entries_per_agent:
                    # Remove oldest entries
                    excess = count - self.max_entries_per_agent
                    conn.execute("""
                        DELETE FROM episodes 
                        WHERE agent_id = ? 
                        AND id IN (
                            SELECT id FROM episodes 
                            WHERE agent_id = ? 
                            ORDER BY timestamp ASC 
                            LIMIT ?
                        )
                    """, (agent_id, agent_id, excess))
                    
                    conn.commit()
                    logger.info(f"Cleaned up {excess} old episodes for agent {agent_id}")
                    
        except Exception as e:
            handle_error(e)
            
    async def delete_episodes(
        self,
        agent_id: str,
        episode_ids: Optional[List[str]] = None,
        older_than_hours: Optional[float] = None
    ) -> int:
        """Delete episodes by IDs or age criteria."""
        try:
            with self._lock:
                if episode_ids:
                    placeholders = ','.join(['?' for _ in episode_ids])
                    query = f"""
                        DELETE FROM episodes 
                        WHERE agent_id = ? AND episode_id IN ({placeholders})
                    """
                    params = [agent_id] + episode_ids
                    
                elif older_than_hours:
                    cutoff = datetime.now() - timedelta(hours=older_than_hours)
                    query = """
                        DELETE FROM episodes 
                        WHERE agent_id = ? AND timestamp < ?
                    """
                    params = [agent_id, cutoff.isoformat()]
                    
                else:
                    return 0
                    
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(query, params)
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                logger.info(f"Deleted {deleted_count} episodes for agent {agent_id}")
                return deleted_count
                
        except Exception as e:
            handle_error(e)
            return 0
            
    async def export_agent_memory(
        self,
        agent_id: str,
        format_type: str = "json"
    ) -> Union[str, Dict[str, Any]]:
        """Export an agent's episodic memory in specified format."""
        try:
            episodes = await self.get_recent_episodes(agent_id, limit=None)
            
            if format_type == "json":
                export_data = {
                    "agent_id": agent_id,
                    "export_timestamp": datetime.now().isoformat(),
                    "episode_count": len(episodes),
                    "episodes": [asdict(ep) for ep in episodes]
                }
                
                # Convert datetime objects to strings for JSON serialization
                for ep_dict in export_data["episodes"]:
                    ep_dict["timestamp"] = ep_dict["timestamp"].isoformat()
                    
                return json.dumps(export_data, indent=2)
                
            elif format_type == "dict":
                return {
                    "agent_id": agent_id,
                    "episodes": episodes,
                    "export_timestamp": datetime.now()
                }
                
            else:
                raise ValueError(f"Unsupported export format: {format_type}")
                
        except Exception as e:
            handle_error(e)
            return {} if format_type == "dict" else "{}"

    async def health_check(self, *args, **kwargs):
        return dict()

    async def initialize(self, *args, **kwargs):
        return dict()

    async def retrieve(self, *args, **kwargs):
        return dict()

    async def search(self, *args, **kwargs):
        return dict()

    async def store(self, *args, **kwargs):
        return dict()

EpisodicMemoryManager = EpisodicMemory  # auto-alias