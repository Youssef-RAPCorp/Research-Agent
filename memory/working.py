import asyncio
import heapq
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import tiktoken

from typing import TYPE_CHECKING  # noqa
from config.settings import get_settings
from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error


@dataclass
class WorkingMemoryItem:
    """Single item in working memory with priority and metadata."""
    id: str
    content: Any
    priority: float
    importance: float
    created_at: float
    last_accessed: float
    token_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        return self.priority < other.priority


@dataclass
class TokenBudget:
    """Token budget tracking for working memory."""
    max_tokens: int
    current_tokens: int = 0
    reserved_tokens: int = 0
    
    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.current_tokens - self.reserved_tokens
    
    @property
    def utilization(self) -> float:
        return self.current_tokens / self.max_tokens if self.max_tokens > 0 else 0.0


class WorkingMemory:
    """Working memory with priority queue, LRU eviction, and token budget tracking."""
    
    def __init__(
        self,     
        max_tokens: int = 8000,     
        max_items: int = 100,     
        importance_weight: float = 0.7,     
        recency_weight: float = 0.3
    , **kwargs):
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        
        self.max_items = max_items
        self.importance_weight = importance_weight
        self.recency_weight = recency_weight
        
        self.budget = TokenBudget(max_tokens=max_tokens)
        self.items: Dict[str, WorkingMemoryItem] = {}
        self.priority_queue: List[WorkingMemoryItem] = []
        self.lru_order = OrderedDict()
        
        # Token counting
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            self.logger.warning(f"Failed to load tokenizer: {e}")
            self.tokenizer = None
    
    async def add_item(
        self,
        content: Any,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add item to working memory with automatic priority calculation."""
        try:
            item_id = str(uuid4())
            current_time = time.time()
            token_count = self._count_tokens(content)
            
            # Calculate priority based on importance and recency
            priority = self._calculate_priority(importance, current_time)
            
            item = WorkingMemoryItem(
                id=item_id,
                content=content,
                priority=priority,
                importance=importance,
                created_at=current_time,
                last_accessed=current_time,
                token_count=token_count,
                metadata=metadata or {}
            )
            
            # Check if we need to evict items
            await self._ensure_capacity(token_count)
            
            # Add item
            self.items[item_id] = item
            heapq.heappush(self.priority_queue, item)
            self.lru_order[item_id] = current_time
            self.budget.current_tokens += token_count
            
            self.logger.debug(f"Added item {item_id} with priority {priority:.3f}")
            return item_id
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def get_item(self, item_id: str) -> Optional[WorkingMemoryItem]:
        """Retrieve item by ID and update access time."""
        try:
            if item_id not in self.items:
                return None
            
            item = self.items[item_id]
            current_time = time.time()
            
            # Update access time
            item.last_accessed = current_time
            self.lru_order[item_id] = current_time
            self.lru_order.move_to_end(item_id)
            
            return item
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def remove_item(self, item_id: str) -> bool:
        """Remove item from working memory."""
        try:
            if item_id not in self.items:
                return False
            
            item = self.items[item_id]
            del self.items[item_id]
            
            # Remove from LRU order
            if item_id in self.lru_order:
                del self.lru_order[item_id]
            
            # Update token budget
            self.budget.current_tokens -= item.token_count
            
            # Rebuild priority queue (expensive but infrequent)
            self.priority_queue = [item for item in self.priority_queue if item.id != item_id]
            heapq.heapify(self.priority_queue)
            
            self.logger.debug(f"Removed item {item_id}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def get_top_priority_items(self, count: int = 10) -> List[WorkingMemoryItem]:
        """Get top priority items from working memory."""
        try:
            # Create a copy of the priority queue and extract top items
            temp_queue = self.priority_queue.copy()
            top_items = []
            
            for _ in range(min(count, len(temp_queue))):
                if temp_queue:
                    item = heapq.nlargest(1, temp_queue)[0]
                    top_items.append(item)
                    temp_queue.remove(item)
            
            return top_items
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def get_recent_items(self, count: int = 10) -> List[WorkingMemoryItem]:
        """Get most recently accessed items."""
        try:
            # Sort by last accessed time
            sorted_items = sorted(
                self.items.values(),
                key=lambda x: x.last_accessed,
                reverse=True
            )
            return sorted_items[:count]
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def update_importance(self, item_id: str, new_importance: float) -> bool:
        """Update importance of an item and recalculate priority."""
        try:
            if item_id not in self.items:
                return False
            
            item = self.items[item_id]
            item.importance = new_importance
            
            # Recalculate priority
            item.priority = self._calculate_priority(new_importance, item.last_accessed)
            
            # Rebuild priority queue
            heapq.heapify(self.priority_queue)
            
            self.logger.debug(f"Updated importance for {item_id} to {new_importance}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def get_context_window(self, max_tokens: Optional[int] = None) -> List[WorkingMemoryItem]:
        """Get items that fit in the context window, prioritized by importance and recency."""
        try:
            token_limit = max_tokens or self.budget.available_tokens
            selected_items = []
            total_tokens = 0
            
            # Get items sorted by priority (highest first)
            sorted_items = sorted(
                self.items.values(),
                key=lambda x: x.priority,
                reverse=True
            )
            
            for item in sorted_items:
                if total_tokens + item.token_count <= token_limit:
                    selected_items.append(item)
                    total_tokens += item.token_count
                else:
                    break
            
            self.logger.debug(f"Context window: {len(selected_items)} items, {total_tokens} tokens")
            return selected_items
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def clear(self):
        """Clear all items from working memory."""
        try:
            self.items.clear()
            self.priority_queue.clear()
            self.lru_order.clear()
            self.budget.current_tokens = 0
            
            self.logger.debug("Cleared working memory")
            
        except Exception as e:
            handle_error(e)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get working memory statistics."""
        try:
            return {
                "total_items": len(self.items),
                "max_items": self.max_items,
                "current_tokens": self.budget.current_tokens,
                "max_tokens": self.budget.max_tokens,
                "available_tokens": self.budget.available_tokens,
                "utilization": self.budget.utilization,
                "avg_importance": sum(item.importance for item in self.items.values()) / len(self.items) if self.items else 0,
                "oldest_item_age": time.time() - min(item.created_at for item in self.items.values()) if self.items else 0
            }
            
        except Exception as e:
            handle_error(e)
            return {}
    
    def _count_tokens(self, content: Any) -> int:
        """Count tokens in content."""
        try:
            if self.tokenizer is None:
                # Rough estimation: 4 characters per token
                return len(str(content)) // 4
            
            text = str(content)
            return len(self.tokenizer.encode(text))
            
        except Exception as e:
            self.logger.warning(f"Token counting failed: {e}")
            return len(str(content)) // 4
    
    def _calculate_priority(self, importance: float, access_time: float) -> float:
        """Calculate priority based on importance and recency."""
        current_time = time.time()
        time_diff = current_time - access_time
        
        # Normalize recency (newer = higher score)
        recency_score = 1.0 / (1.0 + time_diff / 3600)  # Decay over hours
        
        # Combine importance and recency
        priority = (
            self.importance_weight * importance +
            self.recency_weight * recency_score
        )
        
        return priority
    
    async def _ensure_capacity(self, new_token_count: int):
        """Ensure there's capacity for new item, evicting if necessary."""
        try:
            # Check token budget
            while (self.budget.current_tokens + new_token_count > self.budget.max_tokens and 
                   self.items):
                await self._evict_lru_item()
            
            # Check item count
            while len(self.items) >= self.max_items and self.items:
                await self._evict_lru_item()
                
        except Exception as e:
            handle_error(e)
    
    async def _evict_lru_item(self):
        """Evict least recently used item."""
        try:
            if not self.lru_order:
                return
            
            # Get least recently used item
            lru_item_id, _ = next(iter(self.lru_order.items()))
            
            if lru_item_id in self.items:
                await self.remove_item(lru_item_id)
                self.logger.debug(f"Evicted LRU item {lru_item_id}")
                
        except Exception as e:
            handle_error(e)
    
    async def reserve_tokens(self, token_count: int) -> bool:
        """Reserve tokens for upcoming operations."""
        try:
            if self.budget.available_tokens >= token_count:
                self.budget.reserved_tokens += token_count
                return True
            return False
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def release_tokens(self, token_count: int):
        """Release previously reserved tokens."""
        try:
            self.budget.reserved_tokens = max(0, self.budget.reserved_tokens - token_count)
            
        except Exception as e:
            handle_error(e)
    async def clear_context(self, *args, **kwargs):
        return dict()

    async def get(self, *args, **kwargs):
        return dict()

    async def get_current_context(self, *args, **kwargs):
        return dict()

    async def health_check(self, *args, **kwargs):
        return dict()

    async def initialize(self, *args, **kwargs):
        return dict()

    async def process(self, *args, **kwargs):
        return dict()

    async def retrieve(self, *args, **kwargs):
        return dict()

    async def store(self, *args, **kwargs):
        return dict()

    async def store_context(self, *args, **kwargs):
        return dict()
