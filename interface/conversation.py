import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, AsyncIterator, Any, Callable
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import aiofiles

from memory.episodic import EpisodicMemoryManager
from memory.semantic import SemanticMemoryManager
from interface.agents import AgentManager

logger = logging.getLogger(__name__)

@dataclass
class ConversationMessage:
    """Single message in conversation with metadata."""
    id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMessage':
        """Create from dictionary."""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

@dataclass
class ConversationSession:
    """Conversation session with context and history."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[ConversationMessage]
    context: Dict[str, Any]
    active_agents: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'messages': [msg.to_dict() for msg in self.messages],
            'context': self.context,
            'active_agents': self.active_agents
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationSession':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            title=data['title'],
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            messages=[ConversationMessage.from_dict(msg) for msg in data['messages']],
            context=data['context'],
            active_agents=data['active_agents']
        )

class ConversationManager:
    """Manages multi-turn conversations with memory integration and streaming."""
    
    def __init__(
        self,      
        episodic_memory=None,      
        semantic_memory=None,      
        agent_manager=None,      
        storage_path: str = "data/conversations",      
        max_context_tokens: int = 4000,      
        memory_relevance_threshold: float = 0.7
    , **kwargs):
        """Initialize conversation manager with memory systems."""
        self.episodic_memory = episodic_memory
        self.semantic_memory = semantic_memory
        self.agent_manager = agent_manager
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_context_tokens = max_context_tokens
        self.memory_relevance_threshold = memory_relevance_threshold
        
        self.active_sessions: Dict[str, ConversationSession] = {}
        self.message_handlers: List[Callable] = []
        
    async def create_session(
        self,
        title: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        active_agents: Optional[List[str]] = None
    ) -> str:
        """Create new conversation session."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        session = ConversationSession(
            id=session_id,
            title=title or f"Conversation {session_id[:8]}",
            created_at=now,
            updated_at=now,
            messages=[],
            context=context or {},
            active_agents=active_agents or ['physics_researcher', 'data_analyst']
        )
        
        self.active_sessions[session_id] = session
        await self._save_session(session)
        
        logger.info(f"Created conversation session: {session_id}")
        return session_id

    async def load_session(self, session_id: str) -> Optional[ConversationSession]:
        """Load conversation session from storage."""
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        session_file = self.storage_path / f"{session_id}.json"
        if not session_file.exists():
            return None
        
        try:
            async with aiofiles.open(session_file, 'r') as f:
                data = json.loads(await f.read())
            
            session = ConversationSession.from_dict(data)
            self.active_sessions[session_id] = session
            return session
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationMessage:
        """Add message to conversation session."""
        session = await self.load_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        message = ConversationMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {}
        )
        
        session.messages.append(message)
        session.updated_at = datetime.now(timezone.utc)
        
        # Store in episodic memory
        await self.episodic_memory.store_interaction(
            interaction_type="conversation",
            content=content,
            context={
                'session_id': session_id,
                'role': role,
                'message_id': message.id,
                **session.context,
                **(metadata or {})
            }
        )
        
        await self._save_session(session)
        await self._notify_handlers(session_id, message)
        
        return message

    async def get_conversation_context(
        self,
        session_id: str,
        include_memory: bool = True
    ) -> Dict[str, Any]:
        """Build conversation context with memory retrieval."""
        session = await self.load_session(session_id)
        if not session:
            return {}
        
        context = {
            'session_id': session_id,
            'messages': [msg.to_dict() for msg in session.messages[-10:]],  # Recent messages
            'session_context': session.context,
            'active_agents': session.active_agents
        }
        
        if include_memory and session.messages:
            # Get relevant memories for latest user message
            user_messages = [msg for msg in session.messages if msg.role == 'user']
            if user_messages:
                latest_query = user_messages[-1].content
                
                # Retrieve relevant episodic memories
                episodic_results = await self.episodic_memory.search(
                    query=latest_query,
                    limit=5,
                    similarity_threshold=self.memory_relevance_threshold
                )
                
                # Retrieve relevant semantic knowledge
                semantic_results = await self.semantic_memory.search(
                    query=latest_query,
                    limit=3,
                    similarity_threshold=self.memory_relevance_threshold
                )
                
                context['relevant_memories'] = {
                    'episodic': [mem.to_dict() for mem in episodic_results],
                    'semantic': [mem.to_dict() for mem in semantic_results]
                }
        
        return context

    async def generate_response_stream(
        self,
        session_id: str,
        user_message: str,
        agent_name: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Generate streaming response to user message."""
        # Add user message
        await self.add_message(session_id, 'user', user_message)
        
        # Get conversation context with memory
        context = await self.get_conversation_context(session_id, include_memory=True)
        
        # Select agent
        session = self.active_sessions[session_id]
        target_agent = agent_name or session.active_agents[0] if session.active_agents else 'physics_researcher'
        
        # Stream response from agent
        full_response = ""
        async for chunk in self.agent_manager.generate_response_stream(
            agent_name=target_agent,
            message=user_message,
            context=context
        ):
            full_response += chunk
            yield chunk
        
        # Add assistant message
        await self.add_message(
            session_id,
            'assistant',
            full_response,
            {'agent': target_agent}
        )

    async def update_session_context(
        self,
        session_id: str,
        context_updates: Dict[str, Any]
    ) -> bool:
        """Update session context."""
        session = await self.load_session(session_id)
        if not session:
            return False
        
        session.context.update(context_updates)
        session.updated_at = datetime.now(timezone.utc)
        await self._save_session(session)
        return True

    async def set_active_agents(
        self,
        session_id: str,
        agent_names: List[str]
    ) -> bool:
        """Set active agents for session."""
        session = await self.load_session(session_id)
        if not session:
            return False
        
        session.active_agents = agent_names
        session.updated_at = datetime.now(timezone.utc)
        await self._save_session(session)
        return True

    async def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session summary without full message history."""
        session = await self.load_session(session_id)
        if not session:
            return None
        
        return {
            'id': session.id,
            'title': session.title,
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat(),
            'message_count': len(session.messages),
            'active_agents': session.active_agents,
            'context_keys': list(session.context.keys())
        }

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List conversation sessions."""
        session_files = sorted(
            self.storage_path.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        summaries = []
        for session_file in session_files[offset:offset + limit]:
            session_id = session_file.stem
            summary = await self.get_session_summary(session_id)
            if summary:
                summaries.append(summary)
        
        return summaries

    async def delete_session(self, session_id: str) -> bool:
        """Delete conversation session."""
        session_file = self.storage_path / f"{session_id}.json"
        
        try:
            if session_file.exists():
                session_file.unlink()
            
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            logger.info(f"Deleted session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def add_message_handler(self, handler: Callable) -> None:
        """Add message event handler."""
        self.message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable) -> bool:
        """Remove message event handler."""
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)
            return True
        return False

    async def _save_session(self, session: ConversationSession) -> None:
        """Save session to storage."""
        session_file = self.storage_path / f"{session.id}.json"
        
        try:
            async with aiofiles.open(session_file, 'w') as f:
                await f.write(json.dumps(session.to_dict(), indent=2))
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            raise

    async def _notify_handlers(
        self,
        session_id: str,
        message: ConversationMessage
    ) -> None:
        """Notify message handlers of new message."""
        for handler in self.message_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(session_id, message)
                else:
                    handler(session_id, message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")

    async def cleanup_old_sessions(
        self,
        max_age_days: int = 30,
        max_sessions: int = 1000
    ) -> int:
        """Clean up old conversation sessions."""
        session_files = list(self.storage_path.glob("*.json"))
        session_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        cleaned_count = 0
        cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
        
        # Remove sessions beyond max count
        for session_file in session_files[max_sessions:]:
            session_id = session_file.stem
            await self.delete_session(session_id)
            cleaned_count += 1
        
        # Remove sessions older than max age
        for session_file in session_files[:max_sessions]:
            if session_file.stat().st_mtime < cutoff_time:
                session_id = session_file.stem
                await self.delete_session(session_id)
                cleaned_count += 1
        
        logger.info(f"Cleaned up {cleaned_count} old conversation sessions")
        return cleaned_count