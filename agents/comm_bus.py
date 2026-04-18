"""P2P Communication Bus for agent-to-agent messaging."""

import asyncio
import uuid
import time
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import json

from config.logger import get_logger
from config.errors import handle_error

logger = get_logger(__name__)


class MessageType(Enum):
    """Message types for communication."""
    PUBLISH = "publish"
    REQUEST = "request"
    REPLY = "reply"
    BROADCAST = "broadcast"


class DeliveryMode(Enum):
    """Delivery guarantee modes."""
    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"


@dataclass
class Message:
    """Communication message."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.PUBLISH
    topic: str = ""
    payload: Any = None
    sender: str = ""
    timestamp: float = field(default_factory=time.time)
    reply_to: Optional[str] = None
    delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    attempts: int = 0
    max_attempts: int = 3
    ttl: float = 300.0  # 5 minutes


@dataclass
class Subscription:
    """Topic subscription."""
    agent_id: str
    topic: str
    callback: Callable
    filter_func: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)


class CommunicationBus:
    """P2P communication bus with pub/sub, request-reply, and delivery guarantees."""
    
    def __init__(self, **kwargs):
        """Initialize the communication bus."""
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._delivery_confirmations: Dict[str, Set[str]] = defaultdict(set)
        self._processed_messages: Set[str] = set()
        self._failed_messages: Dict[str, Message] = {}
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start the communication bus."""
        if self._running:
            return
            
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())
        logger.info("Communication bus started")
        
    async def stop(self) -> None:
        """Stop the communication bus."""
        if not self._running:
            return
            
        self._running = False
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
                
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Communication bus stopped")
        
    async def subscribe(
        self,
        agent_id: str,
        topic: str,
        callback: Callable,
        filter_func: Optional[Callable] = None
    ) -> str:
        """Subscribe to a topic."""
        subscription = Subscription(
            agent_id=agent_id,
            topic=topic,
            callback=callback,
            filter_func=filter_func
        )
        
        self._subscriptions[topic].append(subscription)
        logger.info(f"Agent {agent_id} subscribed to topic: {topic}")
        return subscription.agent_id
        
    async def unsubscribe(self, agent_id: str, topic: str) -> bool:
        """Unsubscribe from a topic."""
        if topic not in self._subscriptions:
            return False
            
        original_count = len(self._subscriptions[topic])
        self._subscriptions[topic] = [
            sub for sub in self._subscriptions[topic]
            if sub.agent_id != agent_id
        ]
        
        removed = len(self._subscriptions[topic]) < original_count
        if removed:
            logger.info(f"Agent {agent_id} unsubscribed from topic: {topic}")
            
        return removed
        
    async def publish(
        self,
        topic: str,
        payload: Any,
        sender: str,
        delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    ) -> str:
        """Publish a message to a topic."""
        message = Message(
            type=MessageType.PUBLISH,
            topic=topic,
            payload=payload,
            sender=sender,
            delivery_mode=delivery_mode
        )
        
        await self._message_queue.put(message)
        logger.debug(f"Message published to topic {topic} by {sender}")
        return message.id
        
    async def broadcast(
        self,
        payload: Any,
        sender: str,
        delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    ) -> str:
        """Broadcast a message to all subscribers."""
        message = Message(
            type=MessageType.BROADCAST,
            topic="*",
            payload=payload,
            sender=sender,
            delivery_mode=delivery_mode
        )
        
        await self._message_queue.put(message)
        logger.debug(f"Broadcast message sent by {sender}")
        return message.id
        
    async def request(
        self,
        topic: str,
        payload: Any,
        sender: str,
        timeout: float = 30.0
    ) -> Any:
        """Send a request and wait for reply."""
        message = Message(
            type=MessageType.REQUEST,
            topic=topic,
            payload=payload,
            sender=sender,
            delivery_mode=DeliveryMode.EXACTLY_ONCE
        )
        
        future = asyncio.Future()
        self._pending_requests[message.id] = future
        
        try:
            await self._message_queue.put(message)
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Request {message.id} timed out")
            raise
        finally:
            self._pending_requests.pop(message.id, None)
            
    async def reply(self, request_id: str, payload: Any, sender: str) -> str:
        """Reply to a request."""
        message = Message(
            type=MessageType.REPLY,
            topic="",
            payload=payload,
            sender=sender,
            reply_to=request_id,
            delivery_mode=DeliveryMode.EXACTLY_ONCE
        )
        
        await self._message_queue.put(message)
        logger.debug(f"Reply sent for request {request_id} by {sender}")
        return message.id
        
    async def get_subscribers(self, topic: str) -> List[str]:
        """Get list of subscribers for a topic."""
        return [sub.agent_id for sub in self._subscriptions.get(topic, [])]
        
    async def get_topics(self) -> List[str]:
        """Get list of all topics."""
        return list(self._subscriptions.keys())
        
    async def get_stats(self) -> Dict[str, Any]:
        """Get communication bus statistics."""
        return {
            "total_topics": len(self._subscriptions),
            "total_subscriptions": sum(len(subs) for subs in self._subscriptions.values()),
            "pending_requests": len(self._pending_requests),
            "queue_size": self._message_queue.qsize(),
            "failed_messages": len(self._failed_messages),
            "processed_messages": len(self._processed_messages)
        }
        
    async def _process_messages(self) -> None:
        """Process messages from the queue."""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )
                await self._handle_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                handle_error(e)
                
    async def _handle_message(self, message: Message) -> None:
        """Handle a single message."""
        try:
            # Check TTL
            if time.time() - message.timestamp > message.ttl:
                logger.warning(f"Message {message.id} expired")
                return
                
            # Handle based on message type
            if message.type == MessageType.REPLY:
                await self._handle_reply(message)
            elif message.type == MessageType.BROADCAST:
                await self._handle_broadcast(message)
            else:
                await self._handle_publish_request(message)
                
        except Exception as e:
            await self._handle_failed_message(message, e)
            
    async def _handle_reply(self, message: Message) -> None:
        """Handle reply message."""
        if message.reply_to in self._pending_requests:
            future = self._pending_requests[message.reply_to]
            if not future.done():
                future.set_result(message.payload)
                
    async def _handle_broadcast(self, message: Message) -> None:
        """Handle broadcast message."""
        # Send to all subscribers of all topics
        all_subscribers = set()
        for subscriptions in self._subscriptions.values():
            for sub in subscriptions:
                if sub.agent_id != message.sender:
                    all_subscribers.add(sub)
                    
        await self._deliver_to_subscribers(message, list(all_subscribers))
        
    async def _handle_publish_request(self, message: Message) -> None:
        """Handle publish or request message."""
        subscribers = self._subscriptions.get(message.topic, [])
        
        # Filter out sender and apply filters
        filtered_subscribers = []
        for sub in subscribers:
            if sub.agent_id == message.sender:
                continue
                
            if sub.filter_func and not sub.filter_func(message):
                continue
                
            filtered_subscribers.append(sub)
            
        if not filtered_subscribers:
            logger.debug(f"No subscribers for topic: {message.topic}")
            return
            
        await self._deliver_to_subscribers(message, filtered_subscribers)
        
    async def _deliver_to_subscribers(
        self,
        message: Message,
        subscribers: List[Subscription]
    ) -> None:
        """Deliver message to subscribers with delivery guarantees."""
        if message.delivery_mode == DeliveryMode.AT_MOST_ONCE:
            await self._deliver_at_most_once(message, subscribers)
        elif message.delivery_mode == DeliveryMode.AT_LEAST_ONCE:
            await self._deliver_at_least_once(message, subscribers)
        else:  # EXACTLY_ONCE
            await self._deliver_exactly_once(message, subscribers)
            
    async def _deliver_at_most_once(
        self,
        message: Message,
        subscribers: List[Subscription]
    ) -> None:
        """Deliver message at most once (fire and forget)."""
        tasks = []
        for sub in subscribers:
            task = asyncio.create_task(self._call_callback(sub, message))
            tasks.append(task)
            
        # Don't wait for completion
        for task in tasks:
            task.add_done_callback(lambda t: t.exception())
            
    async def _deliver_at_least_once(
        self,
        message: Message,
        subscribers: List[Subscription]
    ) -> None:
        """Deliver message at least once (with retries)."""
        for sub in subscribers:
            await self._deliver_with_retry(sub, message)
            
    async def _deliver_exactly_once(
        self,
        message: Message,
        subscribers: List[Subscription]
    ) -> None:
        """Deliver message exactly once (deduplication)."""
        if message.id in self._processed_messages:
            return
            
        await self._deliver_at_least_once(message, subscribers)
        self._processed_messages.add(message.id)
        
    async def _deliver_with_retry(
        self,
        subscription: Subscription,
        message: Message
    ) -> None:
        """Deliver message with retry logic."""
        for attempt in range(message.max_attempts):
            try:
                await self._call_callback(subscription, message)
                return
            except Exception as e:
                logger.warning(
                    f"Delivery attempt {attempt + 1} failed for message {message.id}: {e}"
                )
                if attempt == message.max_attempts - 1:
                    await self._handle_failed_message(message, e)
                else:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
    async def _call_callback(self, subscription: Subscription, message: Message) -> None:
        """Call subscription callback."""
        try:
            if asyncio.iscoroutinefunction(subscription.callback):
                await subscription.callback(message)
            else:
                subscription.callback(message)
        except Exception as e:
            logger.error(f"Callback error for {subscription.agent_id}: {e}")
            raise
            
    async def _handle_failed_message(self, message: Message, error: Exception) -> None:
        """Handle failed message delivery."""
        self._failed_messages[message.id] = message
        logger.error(f"Message {message.id} failed after {message.max_attempts} attempts: {error}")
        
    async def _cleanup_expired(self) -> None:
        """Clean up expired messages and confirmations."""
        while self._running:
            try:
                current_time = time.time()
                
                # Clean up processed messages older than 1 hour
                cutoff = current_time - 3600
                expired_ids = [
                    msg_id for msg_id, msg in self._failed_messages.items()
                    if msg.timestamp < cutoff
                ]
                
                for msg_id in expired_ids:
                    self._failed_messages.pop(msg_id, None)
                    self._processed_messages.discard(msg_id)
                    
                # Clean up old delivery confirmations
                for topic in list(self._delivery_confirmations.keys()):
                    if not self._subscriptions.get(topic):
                        self._delivery_confirmations.pop(topic, None)
                        
                await asyncio.sleep(300)  # Clean up every 5 minutes
                
            except Exception as e:
                handle_error(e)
                await asyncio.sleep(60)
AT_LEAST_ONCE = type('AT_LEAST_ONCE', (), {})  # auto-stub: not found in project

AT_MOST_ONCE = type('AT_MOST_ONCE', (), {})  # auto-stub: not found in project

BROADCAST = type('BROADCAST', (), {})  # auto-stub: not found in project

EXACTLY_ONCE = type('EXACTLY_ONCE', (), {})  # auto-stub: not found in project

PUBLISH = type('PUBLISH', (), {})  # auto-stub: not found in project

REPLY = type('REPLY', (), {})  # auto-stub: not found in project

REQUEST = type('REQUEST', (), {})  # auto-stub: not found in project
