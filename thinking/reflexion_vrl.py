import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
from abc import ABC

from config.logger import get_logger
from config.errors import handle_error
from memory.episodic import EpisodicMemory
from memory.reflexion_store import ReflexionStore
from knowledge.retrieval import KnowledgeRetrieval
from knowledge.citations import CitationManager
from knowledge.validator import KnowledgeValidator
from thinking.reflection import ReflectionEngine
try:
    from thinking.chat_eval import ChatEvaluator
except ImportError:  # circular import guard — thinking.chat_eval
    ChatEvaluator = type('ChatEvaluator', (), {})


logger = get_logger(__name__)


@dataclass
class ReflexionTrial:
    """Represents a single trial in the Reflexion VRL process."""
    trial_id: str
    action: str
    observation: str
    reward: float
    reflection: str
    citations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    external_evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReflexionMemory:
    """Memory structure for storing reflexion history."""
    trials: List[ReflexionTrial] = field(default_factory=list)
    reflections: List[str] = field(default_factory=list)
    successful_strategies: List[str] = field(default_factory=list)
    failed_strategies: List[str] = field(default_factory=list)
    performance_history: List[float] = field(default_factory=list)


class ReflexionActor:
    """Actor component that generates actions based on observations and reflections."""
    
    def __init__(self,      evaluator=None, **kwargs):
        self.evaluator = evaluator
        self.logger = get_logger(__name__)
    
    async def act(self, observation: str, reflection_history: List[str], 
                  context: Dict[str, Any]) -> str:
        """Generate action based on observation and reflection history."""
        try:
            reflection_context = "\n".join(reflection_history[-3:])  # Last 3 reflections
            
            prompt = f"""
            Based on the observation and reflection history, generate the next action.
            
            Observation: {observation}
            
            Recent Reflections:
            {reflection_context}
            
            Context: {json.dumps(context, indent=2)}
            
            Generate a specific, actionable next step.
            """
            
            response = await self.evaluator.evaluate_response(
                prompt, context, use_citations=True
            )
            
            return response.get('action', response.get('content', ''))
            
        except Exception as e:
            self.logger.error(f"Error in actor: {e}")
            handle_error(e)
            return "Continue with standard approach"


class ReflexionEvaluator:
    """Evaluator component that assesses the quality of actions and outcomes."""
    
    def __init__(self,      chat_evaluator=None,      
                 knowledge_validator=None, **kwargs):
        self.chat_evaluator = chat_evaluator
        self.knowledge_validator = knowledge_validator
        self.logger = get_logger(__name__)
    
    async def evaluate(self, action: str, observation: str, 
                      context: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Evaluate the quality of an action-observation pair."""
        try:
            # Evaluate with chat evaluator
            eval_prompt = f"""
            Evaluate the effectiveness of this action and its outcome:
            
            Action: {action}
            Observation: {observation}
            
            Rate the effectiveness on a scale of -1.0 to 1.0 where:
            -1.0: Completely ineffective or counterproductive
             0.0: Neutral or no clear progress
             1.0: Highly effective and productive
            
            Provide a numerical score and brief justification.
            """
            
            eval_result = await self.chat_evaluator.evaluate_response(
                eval_prompt, context, use_citations=True
            )
            
            # Extract numerical score
            score = self._extract_score(eval_result.get('content', ''))
            
            # Validate against knowledge base
            validation_result = await self.knowledge_validator.validate_claim(
                f"Action: {action}. Result: {observation}"
            )
            
            # Combine scores
            final_score = (score + validation_result.confidence_score) / 2
            
            return final_score, {
                'chat_eval': eval_result,
                'validation': validation_result.__dict__,
                'raw_score': score,
                'final_score': final_score
            }
            
        except Exception as e:
            self.logger.error(f"Error in evaluator: {e}")
            handle_error(e)
            return 0.0, {'error': str(e)}
    
    def _extract_score(self, text: str) -> float:
        """Extract numerical score from evaluation text."""
        try:
            # Look for patterns like "Score: 0.8" or "Rating: -0.3"
            import re
            score_pattern = r'(?:score|rating|effectiveness)[\s:]*(-?\d*\.?\d+)'
            match = re.search(score_pattern, text.lower())
            
            if match:
                score = float(match.group(1))
                return max(-1.0, min(1.0, score))  # Clamp to [-1, 1]
            
            # Fallback: analyze sentiment
            if 'effective' in text.lower() or 'good' in text.lower():
                return 0.5
            elif 'ineffective' in text.lower() or 'poor' in text.lower():
                return -0.5
            else:
                return 0.0
                
        except Exception:
            return 0.0


class ReflexionSelfReflector:
    """Self-reflection component that generates insights from failures and successes."""
    
    def __init__(self,      reflection_engine=None,     
                 knowledge_retrieval=None,     
                 citation_manager=None, **kwargs):
        self.reflection_engine = reflection_engine
        self.knowledge_retrieval = knowledge_retrieval
        self.citation_manager = citation_manager
        self.logger = get_logger(__name__)
    
    async def reflect(self, trial: ReflexionTrial, memory: ReflexionMemory,
                     context: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Generate reflection based on trial outcome and historical memory."""
        try:
            # Gather external evidence
            external_evidence = await self._gather_evidence(
                trial.action, trial.observation, context
            )
            
            # Create reflection prompt with evidence
            reflection_prompt = self._create_reflection_prompt(
                trial, memory, external_evidence
            )
            
            # Generate reflection
            reflection_result = await self.reflection_engine.reflect_on_response(
                reflection_prompt, context, use_citations=True
            )
            
            reflection_text = reflection_result.get('content', '')
            citations = reflection_result.get('citations', [])
            
            # Extract actionable insights
            insights = self._extract_insights(reflection_text)
            
            return reflection_text, citations
            
        except Exception as e:
            self.logger.error(f"Error in self-reflection: {e}")
            handle_error(e)
            return "Continue with current approach", []
    
    async def _gather_evidence(self, action: str, observation: str,
                              context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Gather external evidence to ground reflections."""
        try:
            # Search for relevant knowledge
            search_query = f"Action: {action}. Observation: {observation}"
            
            retrieval_results = await self.knowledge_retrieval.retrieve(
                search_query, top_k=5, context=context
            )
            
            evidence = []
            for result in retrieval_results:
                evidence.append({
                    'source': result.get('source', 'unknown'),
                    'content': result.get('content', ''),
                    'relevance_score': result.get('score', 0.0),
                    'citations': result.get('citations', [])
                })
            
            return evidence
            
        except Exception as e:
            self.logger.error(f"Error gathering evidence: {e}")
            return []
    
    def _create_reflection_prompt(self, trial: ReflexionTrial,
                                 memory: ReflexionMemory,
                                 evidence: List[Dict[str, Any]]) -> str:
        """Create comprehensive reflection prompt."""
        evidence_text = "\n".join([
            f"Evidence {i+1}: {ev['content']} (Score: {ev['relevance_score']})"
            for i, ev in enumerate(evidence[:3])
        ])
        
        recent_trials = memory.trials[-5:] if len(memory.trials) >= 5 else memory.trials
        trial_history = "\n".join([
            f"Trial {i}: Action={t.action[:100]}..., Reward={t.reward:.2f}"
            for i, t in enumerate(recent_trials)
        ])
        
        return f"""
        Reflect on this trial outcome and generate actionable insights:
        
        Current Trial:
        Action: {trial.action}
        Observation: {trial.observation}
        Reward: {trial.reward}
        
        Recent Trial History:
        {trial_history}
        
        External Evidence:
        {evidence_text}
        
        Previous Successful Strategies:
        {'; '.join(memory.successful_strategies[-3:])}
        
        Previous Failed Strategies:
        {'; '.join(memory.failed_strategies[-3:])}
        
        Provide:
        1. Analysis of what went well/poorly
        2. Specific insights for future actions
        3. Strategic recommendations
        4. Citations to supporting evidence
        """
    
    def _extract_insights(self, reflection_text: str) -> List[str]:
        """Extract actionable insights from reflection text."""
        insights = []
        
        # Look for insight markers
        insight_markers = [
            'insight:', 'lesson:', 'recommendation:', 'strategy:',
            'should:', 'avoid:', 'try:', 'focus on:'
        ]
        
        lines = reflection_text.split('\n')
        for line in lines:
            line = line.strip()
            if any(marker in line.lower() for marker in insight_markers):
                insights.append(line)
        
        return insights[:5]  # Limit to top 5 insights


class ReflexionVRLPattern:
    """Complete Reflexion (Verbal Reinforcement Learning) implementation."""
    
    def __init__(self, **kwargs):
        """Initialize Reflexion VRL components."""
        self.logger = get_logger(__name__)
        self.memory = ReflexionMemory()
        
        # Initialize components (will be set via dependency injection)
        self.episodic_memory: Optional[EpisodicMemory] = None
        self.reflexion_store: Optional[ReflexionStore] = None
        self.knowledge_retrieval: Optional[KnowledgeRetrieval] = None
        self.citation_manager: Optional[CitationManager] = None
        self.knowledge_validator: Optional[KnowledgeValidator] = None
        self.reflection_engine: Optional[ReflectionEngine] = None
        self.chat_evaluator: Optional[ChatEvaluator] = None
        
        # Components initialized after dependencies
        self.actor: Optional[ReflexionActor] = None
        self.evaluator: Optional[ReflexionEvaluator] = None
        self.self_reflector: Optional[ReflexionSelfReflector] = None
        
        self.trial_count = 0
        self.performance_threshold = 0.7
        self.max_trials = 10
    
    def initialize_dependencies(self, episodic_memory: EpisodicMemory,
                               reflexion_store: ReflexionStore,
                               knowledge_retrieval: KnowledgeRetrieval,
                               citation_manager: CitationManager,
                               knowledge_validator: KnowledgeValidator,
                               reflection_engine: ReflectionEngine,
                               chat_evaluator: ChatEvaluator):
        """Initialize all dependencies."""
        self.episodic_memory = episodic_memory
        self.reflexion_store = reflexion_store
        self.knowledge_retrieval = knowledge_retrieval
        self.citation_manager = citation_manager
        self.knowledge_validator = knowledge_validator
        self.reflection_engine = reflection_engine
        self.chat_evaluator = chat_evaluator
        
        # Initialize components
        self.actor = ReflexionActor(self.chat_evaluator)
        self.evaluator = ReflexionEvaluator(self.chat_evaluator, self.knowledge_validator)
        self.self_reflector = ReflexionSelfReflector(
            self.reflection_engine, self.knowledge_retrieval, self.citation_manager
        )
    
    async def run_reflexion_loop(self, initial_observation: str,
                                task_context: Dict[str, Any],
                                max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """Run the complete Reflexion VRL loop."""
        try:
            if not self._check_dependencies():
                raise RuntimeError("Dependencies not properly initialized")
            
            max_iter = max_iterations or self.max_trials
            current_observation = initial_observation
            iteration = 0
            
            results = {
                'trials': [],
                'final_performance': 0.0,
                'total_iterations': 0,
                'converged': False,
                'best_action': '',
                'best_score': -1.0
            }
            
            while iteration < max_iter:
                # Generate action
                action = await self.actor.act(
                    current_observation,
                    self.memory.reflections,
                    task_context
                )
                
                # Execute action (simulate or get real observation)
                new_observation = await self._execute_action(action, task_context)
                
                # Evaluate action-observation pair
                reward, eval_details = await self.evaluator.evaluate(
                    action, new_observation, task_context
                )
                
                # Create trial record
                trial = ReflexionTrial(
                    trial_id=f"trial_{self.trial_count}_{iteration}",
                    action=action,
                    observation=new_observation,
                    reward=reward
                )
                
                # Generate reflection if reward is below threshold
                if reward < self.performance_threshold:
                    reflection, citations = await self.self_reflector.reflect(
                        trial, self.memory, task_context
                    )
                    trial.reflection = reflection
                    trial.citations = citations
                    
                    self.memory.reflections.append(reflection)
                    
                    # Update strategy lists
                    if reward < 0:
                        self.memory.failed_strategies.append(action[:100])
                    else:
                        self.memory.successful_strategies.append(action[:100])
                
                # Update memory
                self.memory.trials.append(trial)
                self.memory.performance_history.append(reward)
                
                # Store in persistent memory
                await self._store_trial(trial, task_context)
                
                # Track best performance
                if reward > results['best_score']:
                    results['best_score'] = reward
                    results['best_action'] = action
                
                results['trials'].append({
                    'iteration': iteration,
                    'action': action,
                    'observation': new_observation,
                    'reward': reward,
                    'reflection': trial.reflection,
                    'citations': trial.citations
                })
                
                # Check convergence
                if reward >= self.performance_threshold:
                    results['converged'] = True
                    break
                
                # Update for next iteration
                current_observation = new_observation
                iteration += 1
            
            results['total_iterations'] = iteration
            results['final_performance'] = self.memory.performance_history[-1] if self.memory.performance_history else 0.0
            
            self.trial_count += 1
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in reflexion loop: {e}")
            handle_error(e)
            return {
                'error': str(e),
                'trials': [],
                'final_performance': 0.0,
                'total_iterations': 0,
                'converged': False
            }
    
    async def _execute_action(self, action: str, context: Dict[str, Any]) -> str:
        """Execute action and return observation (placeholder for actual implementation)."""
        # This would interface with the actual environment/system
        # For now, return a simulated observation based on the action
        return f"Executed action: {action}. Awaiting results..."
    
    async def _store_trial(self, trial: ReflexionTrial, context: Dict[str, Any]):
        """Store trial in persistent memory."""
        try:
            if self.reflexion_store:
                await self.reflexion_store.store_trial(trial)
            
            if self.episodic_memory:
                await self.episodic_memory.store_episode({
                    'type': 'reflexion_trial',
                    'trial_id': trial.trial_id,
                    'action': trial.action,
                    'observation': trial.observation,
                    'reward': trial.reward,
                    'reflection': trial.reflection,
                    'citations': trial.citations,
                    'timestamp': trial.timestamp.isoformat(),
                    'context': context
                })
        
        except Exception as e:
            self.logger.error(f"Error storing trial: {e}")
    
    def _check_dependencies(self) -> bool:
        """Check if all dependencies are properly initialized."""
        required_deps = [
            'actor', 'evaluator', 'self_reflector',
            'episodic_memory', 'reflexion_store',
            'knowledge_retrieval', 'citation_manager'
        ]
        
        for dep in required_deps:
            if getattr(self, dep, None) is None:
                self.logger.error(f"Missing dependency: {dep}")
                return False
        
        return True
    
    async def get_memory_summary(self) -> Dict[str, Any]:
        """Get summary of current reflexion memory."""
        return {
            'total_trials': len(self.memory.trials),
            'average_performance': sum(self.memory.performance_history) / len(self.memory.performance_history) if self.memory.performance_history else 0.0,
            'successful_strategies_count': len(self.memory.successful_strategies),
            'failed_strategies_count': len(self.memory.failed_strategies),
            'total_reflections': len(self.memory.reflections),
            'recent_performance_trend': self.memory.performance_history[-5:] if len(self.memory.performance_history) >= 5 else self.memory.performance_history
        }
    
    async def reset_memory(self):
        """Reset the reflexion memory."""
        self.memory = ReflexionMemory()
        self.trial_count = 0