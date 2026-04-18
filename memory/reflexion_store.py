from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import asyncio
from pathlib import Path

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error
from memory.persistence import MemoryPersistence

@dataclass
class EpisodeReflection:
    """Stores reflection data for a single episode."""
    episode_id: str
    timestamp: datetime
    task_description: str
    initial_approach: str
    failure_points: List[str]
    successful_strategies: List[str]
    key_insights: List[str]
    performance_score: float
    reasoning_chain: List[str]
    corrective_actions: List[str]
    patterns_identified: List[str]

@dataclass
class FailurePattern:
    """Represents a recurring failure pattern."""
    pattern_id: str
    description: str
    frequency: int
    episodes: List[str]
    root_causes: List[str]
    mitigation_strategies: List[str]
    last_occurrence: datetime
    severity_score: float

@dataclass
class SuccessStrategy:
    """Represents a successful strategy pattern."""
    strategy_id: str
    description: str
    success_rate: float
    applicable_contexts: List[str]
    episodes: List[str]
    key_steps: List[str]
    prerequisites: List[str]
    last_used: datetime
    effectiveness_score: float

class ReflexionStore:
    """Stores and manages verbal RL reflections, failure patterns, and success strategies."""
    
    def __init__(self,      storage_path: Optional[str] = None, **kwargs):
        """Initialize the reflexion store with optional custom storage path."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.storage_path = Path(storage_path) if storage_path else Path("data/reflexion")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize persistence layer
        self.persistence = MemoryPersistence(self.storage_path)
        
        # In-memory caches
        self.reflections: Dict[str, EpisodeReflection] = {}
        self.failure_patterns: Dict[str, FailurePattern] = {}
        self.success_strategies: Dict[str, SuccessStrategy] = {}
        
        # Load existing data
        asyncio.create_task(self._load_data())
    
    async def _load_data(self) -> None:
        """Load existing reflections and patterns from storage."""
        try:
            # Load reflections
            reflections_data = await self.persistence.load("reflections.json")
            if reflections_data:
                for reflection_data in reflections_data:
                    reflection = EpisodeReflection(**reflection_data)
                    self.reflections[reflection.episode_id] = reflection
            
            # Load failure patterns
            patterns_data = await self.persistence.load("failure_patterns.json")
            if patterns_data:
                for pattern_data in patterns_data:
                    pattern = FailurePattern(**pattern_data)
                    self.failure_patterns[pattern.pattern_id] = pattern
            
            # Load success strategies
            strategies_data = await self.persistence.load("success_strategies.json")
            if strategies_data:
                for strategy_data in strategies_data:
                    strategy = SuccessStrategy(**strategy_data)
                    self.success_strategies[strategy.strategy_id] = strategy
            
            self.logger.info(f"Loaded {len(self.reflections)} reflections, {len(self.failure_patterns)} patterns, {len(self.success_strategies)} strategies")
            
        except Exception as e:
            handle_error(e)
            self.logger.warning("Failed to load existing data, starting fresh")
    
    async def add_reflection(self, reflection: EpisodeReflection) -> None:
        """Add a new episode reflection to the store."""
        try:
            self.reflections[reflection.episode_id] = reflection
            await self._update_patterns(reflection)
            await self._update_strategies(reflection)
            await self._save_reflections()
            self.logger.info(f"Added reflection for episode {reflection.episode_id}")
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Failed to add reflection: {e}")
    
    async def _update_patterns(self, reflection: EpisodeReflection) -> None:
        """Update failure patterns based on new reflection."""
        for failure_point in reflection.failure_points:
            pattern_id = self._generate_pattern_id(failure_point)
            
            if pattern_id in self.failure_patterns:
                # Update existing pattern
                pattern = self.failure_patterns[pattern_id]
                pattern.frequency += 1
                pattern.episodes.append(reflection.episode_id)
                pattern.last_occurrence = reflection.timestamp
                
                # Update severity based on frequency
                pattern.severity_score = min(1.0, pattern.frequency * 0.1)
                
            else:
                # Create new pattern
                pattern = FailurePattern(
                    pattern_id=pattern_id,
                    description=failure_point,
                    frequency=1,
                    episodes=[reflection.episode_id],
                    root_causes=reflection.patterns_identified,
                    mitigation_strategies=reflection.corrective_actions,
                    last_occurrence=reflection.timestamp,
                    severity_score=0.1
                )
                self.failure_patterns[pattern_id] = pattern
        
        await self._save_patterns()
    
    async def _update_strategies(self, reflection: EpisodeReflection) -> None:
        """Update success strategies based on new reflection."""
        for strategy in reflection.successful_strategies:
            strategy_id = self._generate_strategy_id(strategy)
            
            if strategy_id in self.success_strategies:
                # Update existing strategy
                existing_strategy = self.success_strategies[strategy_id]
                existing_strategy.episodes.append(reflection.episode_id)
                existing_strategy.last_used = reflection.timestamp
                
                # Update success rate based on performance
                total_episodes = len(existing_strategy.episodes)
                existing_strategy.success_rate = (existing_strategy.success_rate * (total_episodes - 1) + reflection.performance_score) / total_episodes
                existing_strategy.effectiveness_score = existing_strategy.success_rate
                
            else:
                # Create new strategy
                new_strategy = SuccessStrategy(
                    strategy_id=strategy_id,
                    description=strategy,
                    success_rate=reflection.performance_score,
                    applicable_contexts=[reflection.task_description],
                    episodes=[reflection.episode_id],
                    key_steps=reflection.reasoning_chain,
                    prerequisites=[],
                    last_used=reflection.timestamp,
                    effectiveness_score=reflection.performance_score
                )
                self.success_strategies[strategy_id] = new_strategy
        
        await self._save_strategies()
    
    def _generate_pattern_id(self, description: str) -> str:
        """Generate a consistent pattern ID from description."""
        import hashlib
        return hashlib.md5(description.lower().encode()).hexdigest()[:8]
    
    def _generate_strategy_id(self, description: str) -> str:
        """Generate a consistent strategy ID from description."""
        import hashlib
        return hashlib.md5(description.lower().encode()).hexdigest()[:8]
    
    async def get_relevant_failures(self, task_description: str, limit: int = 5) -> List[FailurePattern]:
        """Get failure patterns relevant to the current task."""
        try:
            relevant_patterns = []
            
            for pattern in self.failure_patterns.values():
                # Simple relevance scoring based on keyword matching
                relevance_score = self._calculate_relevance(task_description, pattern.description)
                if relevance_score > 0.3:  # Threshold for relevance
                    relevant_patterns.append((pattern, relevance_score))
            
            # Sort by relevance and severity
            relevant_patterns.sort(key=lambda x: (x[1] * x[0].severity_score), reverse=True)
            
            return [pattern for pattern, _ in relevant_patterns[:limit]]
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def get_relevant_strategies(self, task_description: str, limit: int = 5) -> List[SuccessStrategy]:
        """Get success strategies relevant to the current task."""
        try:
            relevant_strategies = []
            
            for strategy in self.success_strategies.values():
                # Check if task matches applicable contexts
                context_relevance = any(
                    self._calculate_relevance(task_description, context) > 0.3
                    for context in strategy.applicable_contexts
                )
                
                if context_relevance:
                    relevance_score = max(
                        self._calculate_relevance(task_description, context)
                        for context in strategy.applicable_contexts
                    )
                    relevant_strategies.append((strategy, relevance_score))
            
            # Sort by relevance and effectiveness
            relevant_strategies.sort(key=lambda x: (x[1] * x[0].effectiveness_score), reverse=True)
            
            return [strategy for strategy, _ in relevant_strategies[:limit]]
            
        except Exception as e:
            handle_error(e)
            return []
    
    def _calculate_relevance(self, text1: str, text2: str) -> float:
        """Calculate simple relevance score between two texts."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    async def get_episode_history(self, episode_id: str) -> Optional[EpisodeReflection]:
        """Get reflection data for a specific episode."""
        return self.reflections.get(episode_id)
    
    async def get_pattern_statistics(self) -> Dict[str, Any]:
        """Get statistics about failure patterns and success strategies."""
        try:
            total_reflections = len(self.reflections)
            total_patterns = len(self.failure_patterns)
            total_strategies = len(self.success_strategies)
            
            # Calculate average performance
            if total_reflections > 0:
                avg_performance = sum(r.performance_score for r in self.reflections.values()) / total_reflections
            else:
                avg_performance = 0.0
            
            # Find most common failure patterns
            common_patterns = sorted(
                self.failure_patterns.values(),
                key=lambda p: p.frequency,
                reverse=True
            )[:5]
            
            # Find most effective strategies
            effective_strategies = sorted(
                self.success_strategies.values(),
                key=lambda s: s.effectiveness_score,
                reverse=True
            )[:5]
            
            return {
                "total_reflections": total_reflections,
                "total_patterns": total_patterns,
                "total_strategies": total_strategies,
                "average_performance": avg_performance,
                "most_common_patterns": [p.description for p in common_patterns],
                "most_effective_strategies": [s.description for s in effective_strategies]
            }
            
        except Exception as e:
            handle_error(e)
            return {}
    
    async def generate_improvement_suggestions(self, task_description: str) -> List[str]:
        """Generate improvement suggestions based on historical patterns."""
        try:
            suggestions = []
            
            # Get relevant failure patterns
            failure_patterns = await self.get_relevant_failures(task_description, limit=3)
            for pattern in failure_patterns:
                suggestions.extend(pattern.mitigation_strategies)
            
            # Get relevant success strategies
            success_strategies = await self.get_relevant_strategies(task_description, limit=3)
            for strategy in success_strategies:
                suggestions.extend(strategy.key_steps)
            
            # Remove duplicates and return unique suggestions
            return list(set(suggestions))
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def _save_reflections(self) -> None:
        """Save reflections to persistent storage."""
        try:
            data = [asdict(reflection) for reflection in self.reflections.values()]
            await self.persistence.save("reflections.json", data)
        except Exception as e:
            handle_error(e)
    
    async def _save_patterns(self) -> None:
        """Save failure patterns to persistent storage."""
        try:
            data = [asdict(pattern) for pattern in self.failure_patterns.values()]
            await self.persistence.save("failure_patterns.json", data)
        except Exception as e:
            handle_error(e)
    
    async def _save_strategies(self) -> None:
        """Save success strategies to persistent storage."""
        try:
            data = [asdict(strategy) for strategy in self.success_strategies.values()]
            await self.persistence.save("success_strategies.json", data)
        except Exception as e:
            handle_error(e)
    
    async def clear_old_data(self, days_threshold: int = 30) -> None:
        """Clear old reflection data beyond threshold."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_threshold)
            
            # Remove old reflections
            old_episodes = [
                episode_id for episode_id, reflection in self.reflections.items()
                if reflection.timestamp < cutoff_date
            ]
            
            for episode_id in old_episodes:
                del self.reflections[episode_id]
            
            # Update patterns and strategies to remove references to old episodes
            for pattern in self.failure_patterns.values():
                pattern.episodes = [ep for ep in pattern.episodes if ep not in old_episodes]
            
            for strategy in self.success_strategies.values():
                strategy.episodes = [ep for ep in strategy.episodes if ep not in old_episodes]
            
            # Save updated data
            await self._save_reflections()
            await self._save_patterns()
            await self._save_strategies()
            
            self.logger.info(f"Cleared {len(old_episodes)} old episodes")
            
        except Exception as e:
            handle_error(e)
    async def store_reflection(self, *args, **kwargs):
        return dict()
