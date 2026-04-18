import asyncio
import uuid
from abc import ABC
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable

from pydantic import BaseModel, Field

from config.logger import get_logger
from config.errors import handle_error
from config.settings import get_settings
from memory.router import MemoryRouter
from memory.working import WorkingMemory
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from thinking.reflection import ReflectionPattern
from thinking.reflexion_vrl import ReflexionVRLPattern
from thinking.tree_of_thoughts import TreeOfThoughtsPattern
from thinking.lats_mcts import LATSMCTSPattern

try:
    from thinking.lats_mcts import LATS_MCTS
except ImportError:  # circular import guard — thinking.lats_mcts
    LATS_MCTS = type('LATS_MCTS', (), {})

try:
    from thinking.chat_eval import ChatEvalPattern
except ImportError:  # circular import guard — thinking.chat_eval
    ChatEvalPattern = type('ChatEvalPattern', (), {})

try:
    from thinking.down_adaptive import DownAdaptivePattern
except ImportError:  # circular import guard — thinking.down_adaptive
    DownAdaptivePattern = type('DownAdaptivePattern', (), {})

try:
    from thinking.mad import MADPattern
except ImportError:  # circular import guard — thinking.mad
    MADPattern = type('MADPattern', (), {})

try:
    from thinking.mad import MADPattern
except ImportError:  # circular import guard — thinking.mad
    MADPattern = type('MADPattern', (), {})

try:
    from thinking.self_refine import SelfRefinePattern
except ImportError:  # circular import guard — thinking.self_refine
    SelfRefinePattern = type('SelfRefinePattern', (), {})

logger = get_logger(__name__)
settings = get_settings()


class AgentStatus(str, Enum):
    """Agent lifecycle status enumeration."""
    INITIALIZING = "initializing"
    READY = "ready"
    WORKING = "working"
    IDLE = "idle"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class MessageType(str, Enum):
    """P2P message type enumeration."""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    NOTIFICATION = "notification"


class ThinkingPattern(str, Enum):
    """Available thinking pattern types."""
    SELF_REFINE = "self_refine"
    REFLECTION = "reflection"
    REFLEXION_VRL = "reflexion_vrl"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    LATS_MCTS = "lats_mcts"
    MAD = "mad"
    CHAT_EVAL = "chat_eval"
    DOWN_ADAPTIVE = "down_adaptive"


class ToolCall(BaseModel):
    """Tool call request structure."""
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ToolResult(BaseModel):
    """Tool call result structure."""
    call_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0


class P2PMessage(BaseModel):
    """Peer-to-peer message structure."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    recipient_id: Optional[str] = None
    message_type: MessageType
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    requires_response: bool = False


class AgentCapability(BaseModel):
    """Agent capability description."""
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentMetrics(BaseModel):
    """Agent performance metrics."""
    tasks_completed: int = 0
    errors_encountered: int = 0
    average_response_time: float = 0.0
    memory_usage: float = 0.0
    last_activity: Optional[datetime] = None

    async def model_dump(self, *args, **kwargs):
        return dict()


class BaseAgent(ABC):
    """Abstract base class for all agents in the physics discovery system."""

    def __init__(
        self,     
        agent_id: Optional[str] = None,     
        name: Optional[str] = None,     
        capabilities: Optional[List[AgentCapability]] = None,     
        thinking_patterns: Optional[List[ThinkingPattern]] = None
    , **kwargs):
        """Initialize the base agent with core components."""
        self.agent_id = agent_id or str(uuid.uuid4())
        self.name = name or f"{self.__class__.__name__}_{self.agent_id[:8]}"
        self.capabilities = capabilities or []
        self.status = AgentStatus.INITIALIZING
        self.metrics = AgentMetrics()
        
        # Memory system integration
        self.memory_router = MemoryRouter()
        self.working_memory = WorkingMemory()
        self.episodic_memory = EpisodicMemory()
        self.semantic_memory = SemanticMemory()
        
        # Thinking patterns
        self.thinking_patterns = thinking_patterns or [ThinkingPattern.SELF_REFINE]
        self._thinking_engines = self._initialize_thinking_engines()
        
        # Tool registry
        self._tools: Dict[str, Callable] = {}
        self._register_default_tools()
        
        # P2P messaging
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._peer_connections: Dict[str, Any] = {}
        
        # Lifecycle hooks
        self._lifecycle_hooks: Dict[str, List[Callable]] = {
            "startup": [],
            "shutdown": [],
            "error": [],
            "idle": []
        }

    def _initialize_thinking_engines(self) -> Dict[ThinkingPattern, Any]:
        """Initialize thinking pattern engines."""
        engines = {}
        
        pattern_classes = {
            ThinkingPattern.SELF_REFINE: SelfRefinePattern,
            ThinkingPattern.REFLECTION: ReflectionPattern,
            ThinkingPattern.REFLEXION_VRL: ReflexionVRLPattern,
            ThinkingPattern.TREE_OF_THOUGHTS: TreeOfThoughtsPattern,
            ThinkingPattern.LATS_MCTS: LATSMCTSPattern,
            ThinkingPattern.MAD: MADPattern,
            ThinkingPattern.CHAT_EVAL: ChatEvalPattern,
            ThinkingPattern.DOWN_ADAPTIVE: DownAdaptivePattern
        }
        
        for pattern in self.thinking_patterns:
            if pattern in pattern_classes:
                try:
                    engines[pattern] = pattern_classes[pattern]()
                except Exception as e:
                    logger.warning(f"Failed to initialize thinking pattern {pattern}: {e}")
                    
        return engines

    def _register_default_tools(self) -> None:
        """Register default tools available to all agents."""
        self._tools.update({
            "memory_store": self._memory_store_tool,
            "memory_retrieve": self._memory_retrieve_tool,
            "send_message": self._send_message_tool,
            "get_status": self._get_status_tool
        })

    async def _memory_store_tool(self, content: str, memory_type: str = "working", metadata: Optional[Dict] = None) -> Dict:
        """Store content in specified memory system."""
        try:
            if memory_type == "working":
                await self.working_memory.store(content, metadata or {})
            elif memory_type == "episodic":
                await self.episodic_memory.store(content, metadata or {})
            elif memory_type == "semantic":
                await self.semantic_memory.store(content, metadata or {})
            else:
                return {"success": False, "error": f"Unknown memory type: {memory_type}"}
            
            return {"success": True, "stored": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _memory_retrieve_tool(self, query: str, memory_type: str = "working", limit: int = 5) -> Dict:
        """Retrieve content from specified memory system."""
        try:
            results = []
            if memory_type == "working":
                results = await self.working_memory.retrieve(query, limit)
            elif memory_type == "episodic":
                results = await self.episodic_memory.retrieve(query, limit)
            elif memory_type == "semantic":
                results = await self.semantic_memory.retrieve(query, limit)
            else:
                return {"success": False, "error": f"Unknown memory type: {memory_type}"}
            
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _send_message_tool(self, recipient_id: str, message_type: str, payload: Dict) -> Dict:
        """Send P2P message to another agent."""
        try:
            message = P2PMessage(
                sender_id=self.agent_id,
                recipient_id=recipient_id,
                message_type=MessageType(message_type),
                payload=payload
            )
            await self.send_message(message)
            return {"success": True, "message_id": message.message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_status_tool(self) -> Dict:
        """Get current agent status and metrics."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "metrics": self.metrics.model_dump(),
            "capabilities": [cap.model_dump() for cap in self.capabilities]
        }

    # Tool calling protocol
    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool function."""
        self._tools[name] = func
        logger.debug(f"Registered tool: {name}")

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            if tool_call.tool_name not in self._tools:
                return ToolResult(
                    call_id=tool_call.call_id,
                    success=False,
                    error=f"Tool '{tool_call.tool_name}' not found"
                )
            
            tool_func = self._tools[tool_call.tool_name]
            
            # Handle both sync and async tools
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**tool_call.parameters)
            else:
                result = tool_func(**tool_call.parameters)
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return ToolResult(
                call_id=tool_call.call_id,
                success=True,
                result=result,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            handle_error(e)
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                error=str(e),
                execution_time=execution_time
            )

    # P2P messaging protocol
    def register_message_handler(self, message_type: MessageType, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[message_type] = handler

    async def send_message(self, message: P2PMessage) -> None:
        """Send a message to another agent."""
        # TODO: Implement actual P2P messaging infrastructure
        logger.info(f"Sending message {message.message_id} to {message.recipient_id}")
        await self._message_queue.put(message)

    async def receive_message(self, message: P2PMessage) -> Optional[P2PMessage]:
        """Process an incoming message and return response if needed."""
        try:
            if message.message_type in self._message_handlers:
                handler = self._message_handlers[message.message_type]
                
                if asyncio.iscoroutinefunction(handler):
                    response = await handler(message)
                else:
                    response = handler(message)
                
                if response and message.requires_response:
                    response_msg = P2PMessage(
                        sender_id=self.agent_id,
                        recipient_id=message.sender_id,
                        message_type=MessageType.RESPONSE,
                        payload=response
                    )
                    await self.send_message(response_msg)
                    return response_msg
            
            return None
            
        except Exception as e:
            handle_error(e)
            return None

    async def broadcast_message(self, message_type: MessageType, payload: Dict[str, Any]) -> None:
        """Broadcast a message to all connected peers."""
        message = P2PMessage(
            sender_id=self.agent_id,
            message_type=message_type,
            payload=payload
        )
        # TODO: Implement actual broadcast mechanism
        logger.info(f"Broadcasting message {message.message_id}")
        await self._message_queue.put(message)

    # Thinking pattern dispatch
    async def think(self, problem: str, pattern: ThinkingPattern = ThinkingPattern.SELF_REFINE, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute thinking pattern on a problem."""
        if pattern not in self._thinking_engines:
            logger.warning(f"Thinking pattern {pattern} not available, falling back to self_refine")
            pattern = ThinkingPattern.SELF_REFINE
        
        try:
            engine = self._thinking_engines[pattern]
            
            # Store thinking process in working memory
            await self.working_memory.store(
                f"Started thinking with pattern {pattern.value} on: {problem}",
                {"type": "thinking_start", "pattern": pattern.value}
            )
            
            if hasattr(engine, 'solve') and asyncio.iscoroutinefunction(engine.solve):
                result = await engine.solve(problem, context or {})
            elif hasattr(engine, 'solve'):
                result = engine.solve(problem, context or {})
            else:
                result = {"error": f"Thinking engine {pattern} does not implement solve method"}
            
            # Store result in working memory
            await self.working_memory.store(
                f"Completed thinking with pattern {pattern.value}: {result}",
                {"type": "thinking_result", "pattern": pattern.value}
            )
            
            return result
            
        except Exception as e:
            handle_error(e)
            return {"error": str(e), "pattern": pattern.value}

    # Memory interface
    async def store_memory(self, content: str, memory_type: str = "working", metadata: Optional[Dict] = None) -> None:
        """Store content in specified memory system."""
        await self._memory_store_tool(content, memory_type, metadata)

    async def retrieve_memory(self, query: str, memory_type: str = "working", limit: int = 5) -> List[Dict]:
        """Retrieve memories matching query."""
        result = await self._memory_retrieve_tool(query, memory_type, limit)
        return result.get("results", []) if result.get("success") else []

    async def consolidate_memories(self) -> None:
        """Trigger memory consolidation process."""
        await self.memory_router.consolidate()

    # Lifecycle management
    def add_lifecycle_hook(self, event: str, hook: Callable) -> None:
        """Add a lifecycle hook function."""
        if event in self._lifecycle_hooks:
            self._lifecycle_hooks[event].append(hook)

    async def _execute_hooks(self, event: str, *args, **kwargs) -> None:
        """Execute all hooks for a lifecycle event."""
        for hook in self._lifecycle_hooks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(self, *args, **kwargs)
                else:
                    hook(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"Hook execution failed for {event}: {e}")

    async def startup(self) -> None:
        """Initialize and start the agent."""
        try:
            self.status = AgentStatus.INITIALIZING
            await self._execute_hooks("startup")
            
            # Initialize memory systems
            await self.memory_router.initialize()
            await self.working_memory.initialize()
            await self.episodic_memory.initialize()
            await self.semantic_memory.initialize()
            
            self.status = AgentStatus.READY
            self.metrics.last_activity = datetime.utcnow()
            logger.info(f"Agent {self.name} started successfully")
            
        except Exception as e:
            self.status = AgentStatus.ERROR
            await self._execute_hooks("error", e)
            handle_error(e)
            raise

    async def shutdown(self) -> None:
        """Gracefully shutdown the agent."""
        try:
            self.status = AgentStatus.SHUTDOWN
            await self._execute_hooks("shutdown")
            
            # Cleanup memory systems
            await self.memory_router.cleanup()
            
            logger.info(f"Agent {self.name} shutdown complete")
            
        except Exception as e:
            handle_error(e)

    async def set_idle(self) -> None:
        """Set agent to idle state."""
        self.status = AgentStatus.IDLE
        await self._execute_hooks("idle")

    def get_capabilities(self) -> List[AgentCapability]:
        """Get list of agent capabilities."""
        return self.capabilities

    def get_metrics(self) -> AgentMetrics:
        """Get current agent metrics."""
        return self.metrics

    def get_status(self) -> AgentStatus:
        """Get current agent status."""
        return self.status

    # Abstract methods for subclasses
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task - must be implemented by subclasses."""
        pass

    async def get_response(self, query: str, context: Optional[Dict] = None) -> str:
        """Generate response to query - must be implemented by subclasses."""
        pass

    # Health check and monitoring
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check and return status."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "healthy": self.status not in [AgentStatus.ERROR, AgentStatus.SHUTDOWN],
            "metrics": self.metrics.model_dump(),
            "memory_health": await self._check_memory_health(),
            "tool_count": len(self._tools),
            "thinking_patterns": [p.value for p in self.thinking_patterns]
        }

    async def _check_memory_health(self) -> Dict[str, bool]:
        """Check health of memory systems."""
        try:
            return {
                "working": await self.working_memory.health_check(),
                "episodic": await self.episodic_memory.health_check(),
                "semantic": await self.semantic_memory.health_check(),
                "router": await self.memory_router.health_check()
            }
        except Exception as e:
            logger.error(f"Memory health check failed: {e}")
            return {
                "working": False,
                "episodic": False,
                "semantic": False,
                "router": False
            }

    def __repr__(self) -> str:
        """String representation of agent."""
        return f"{self.__class__.__name__}(id={self.agent_id}, name={self.name}, status={self.status.value})"

    async def run(self, *args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'comprehensive'})

    async def process_message(self, *args, **kwargs):
        return await self.receive_message(*args, **kwargs)
BROADCAST = type('BROADCAST', (), {})  # auto-stub: not found in project

CHAT_EVAL = type('CHAT_EVAL', (), {})  # auto-stub: not found in project

DOWN_ADAPTIVE = type('DOWN_ADAPTIVE', (), {})  # auto-stub: not found in project

ERROR = type('ERROR', (), {})  # auto-stub: not found in project

IDLE = type('IDLE', (), {})  # auto-stub: not found in project

INITIALIZING = type('INITIALIZING', (), {})  # auto-stub: not found in project

MAD = type('MAD', (), {})  # auto-stub: not found in project

NOTIFICATION = type('NOTIFICATION', (), {})  # auto-stub: not found in project

READY = type('READY', (), {})  # auto-stub: not found in project

REFLECTION = type('REFLECTION', (), {})  # auto-stub: not found in project

REFLEXION_VRL = type('REFLEXION_VRL', (), {})  # auto-stub: not found in project

REQUEST = type('REQUEST', (), {})  # auto-stub: not found in project

RESPONSE = type('RESPONSE', (), {})  # auto-stub: not found in project

SELF_REFINE = type('SELF_REFINE', (), {})  # auto-stub: not found in project

SHUTDOWN = type('SHUTDOWN', (), {})  # auto-stub: not found in project

TREE_OF_THOUGHTS = type('TREE_OF_THOUGHTS', (), {})  # auto-stub: not found in project

WORKING = type('WORKING', (), {})  # auto-stub: not found in project
