"""Debate Only When Necessary (DOWN) adaptive gating pattern."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent
from thinking.reflection import ReflectionPattern

logger = get_logger(__name__)

@dataclass
class ConfidenceMetrics:
    """Confidence metrics for debate gating decisions."""
    agent_confidence: float = 0.0
    reasoning_clarity: float = 0.0
    evidence_strength: float = 0.0
    consensus_score: float = 0.0
    uncertainty_flags: List[str] = field(default_factory=list)

@dataclass
class DebateDecision:
    """Decision on whether to trigger debate."""
    should_debate: bool = False
    confidence_threshold: float = 0.0
    reasoning: str = ""
    metrics: Optional[ConfidenceMetrics] = None

class DownAdaptivePattern:
    """Confidence-gated debate trigger that skips debate on high-confidence answers."""
    
    def __init__(
        self,     
        confidence_threshold: float = 0.85,     
        min_agents_for_debate: int = 2,     
        max_debate_rounds: int = 3
    , **kwargs):
        """Initialize DOWN adaptive gating pattern."""
        self.confidence_threshold = confidence_threshold
        self.min_agents_for_debate = min_agents_for_debate
        self.max_debate_rounds = max_debate_rounds
        self.reflection = ReflectionPattern()
        
        # Adaptive threshold adjustments
        self.threshold_history: List[float] = []
        self.accuracy_history: List[bool] = []
        self.efficiency_gains: List[float] = []
        
    async def should_trigger_debate(
        self,
        initial_response: Dict[str, Any],
        agents: List[BaseAgent],
        context: Dict[str, Any]
    ) -> DebateDecision:
        """Determine if debate is necessary based on confidence metrics."""
        try:
            # Calculate confidence metrics
            metrics = await self._calculate_confidence_metrics(
                initial_response, agents, context
            )
            
            # Determine if debate should be triggered
            should_debate = await self._evaluate_debate_necessity(metrics)
            
            # Build decision object
            decision = DebateDecision(
                should_debate=should_debate,
                confidence_threshold=self.confidence_threshold,
                reasoning=self._build_decision_reasoning(metrics, should_debate),
                metrics=metrics
            )
            
            logger.info(f"Debate decision: {should_debate}, confidence: {metrics.agent_confidence:.3f}")
            
            return decision
            
        except Exception as e:
            handle_error(e)
            # Default to debate on error for safety
            return DebateDecision(
                should_debate=True,
                confidence_threshold=self.confidence_threshold,
                reasoning="Error in confidence assessment - defaulting to debate"
            )
    
    async def _calculate_confidence_metrics(
        self,
        response: Dict[str, Any],
        agents: List[BaseAgent],
        context: Dict[str, Any]
    ) -> ConfidenceMetrics:
        """Calculate comprehensive confidence metrics."""
        metrics = ConfidenceMetrics()
        
        # Agent confidence from response
        metrics.agent_confidence = response.get('confidence', 0.0)
        
        # Reasoning clarity analysis
        metrics.reasoning_clarity = await self._assess_reasoning_clarity(response)
        
        # Evidence strength evaluation
        metrics.evidence_strength = await self._evaluate_evidence_strength(response, context)
        
        # Consensus score from initial agent agreement
        metrics.consensus_score = await self._calculate_consensus_score(response, agents)
        
        # Uncertainty flags
        metrics.uncertainty_flags = self._detect_uncertainty_flags(response)
        
        return metrics
    
    async def _assess_reasoning_clarity(self, response: Dict[str, Any]) -> float:
        """Assess clarity and coherence of reasoning."""
        reasoning = response.get('reasoning', '')
        if not reasoning:
            return 0.0
            
        # Simple heuristics for reasoning clarity
        clarity_score = 0.0
        
        # Length and structure
        if len(reasoning.split()) > 20:  # Sufficient detail
            clarity_score += 0.3
            
        # Logical connectors
        logical_words = ['because', 'therefore', 'since', 'thus', 'consequently']
        if any(word in reasoning.lower() for word in logical_words):
            clarity_score += 0.2
            
        # Citations or references
        if 'ref' in reasoning.lower() or 'equation' in reasoning.lower():
            clarity_score += 0.2
            
        # Mathematical expressions
        if any(char in reasoning for char in ['=', '∂', '∇', '∫']):
            clarity_score += 0.3
            
        return min(clarity_score, 1.0)
    
    async def _evaluate_evidence_strength(
        self,
        response: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Evaluate strength of supporting evidence."""
        evidence_score = 0.0
        
        # Citations count
        citations = response.get('citations', [])
        if citations:
            evidence_score += min(len(citations) * 0.1, 0.4)
            
        # Experimental data references
        content = str(response.get('content', ''))
        experimental_keywords = ['experiment', 'measurement', 'observation', 'data']
        if any(keyword in content.lower() for keyword in experimental_keywords):
            evidence_score += 0.3
            
        # Theoretical foundation
        theory_keywords = ['principle', 'law', 'theorem', 'axiom']
        if any(keyword in content.lower() for keyword in theory_keywords):
            evidence_score += 0.3
            
        return min(evidence_score, 1.0)
    
    async def _calculate_consensus_score(
        self,
        response: Dict[str, Any],
        agents: List[BaseAgent]
    ) -> float:
        """Calculate consensus score from agent agreement."""
        if len(agents) < 2:
            return 1.0  # No disagreement possible
            
        # Simulate quick consensus check
        # In real implementation, this would poll agents for quick agreement
        confidence = response.get('confidence', 0.0)
        
        # High confidence suggests likely consensus
        return min(confidence + 0.2, 1.0)
    
    def _detect_uncertainty_flags(self, response: Dict[str, Any]) -> List[str]:
        """Detect linguistic markers of uncertainty."""
        flags = []
        content = str(response.get('content', '')).lower()
        
        uncertainty_markers = {
            'might': 'hedging',
            'possibly': 'hedging', 
            'unclear': 'ambiguity',
            'uncertain': 'explicit_uncertainty',
            'depends': 'conditional',
            'assume': 'assumption',
            'approximat': 'approximation'
        }
        
        for marker, flag_type in uncertainty_markers.items():
            if marker in content:
                flags.append(flag_type)
                
        return flags
    
    async def _evaluate_debate_necessity(self, metrics: ConfidenceMetrics) -> bool:
        """Evaluate if debate is necessary based on metrics."""
        # Weighted confidence score
        weights = {
            'agent_confidence': 0.4,
            'reasoning_clarity': 0.2,
            'evidence_strength': 0.25,
            'consensus_score': 0.15
        }
        
        weighted_confidence = (
            metrics.agent_confidence * weights['agent_confidence'] +
            metrics.reasoning_clarity * weights['reasoning_clarity'] +
            metrics.evidence_strength * weights['evidence_strength'] +
            metrics.consensus_score * weights['consensus_score']
        )
        
        # Penalty for uncertainty flags
        uncertainty_penalty = min(len(metrics.uncertainty_flags) * 0.1, 0.3)
        final_confidence = max(weighted_confidence - uncertainty_penalty, 0.0)
        
        # Debate if confidence below threshold
        return final_confidence < self.confidence_threshold
    
    def _build_decision_reasoning(
        self,
        metrics: ConfidenceMetrics,
        should_debate: bool
    ) -> str:
        """Build human-readable reasoning for the decision."""
        confidence_summary = (
            f"Agent confidence: {metrics.agent_confidence:.3f}, "
            f"reasoning clarity: {metrics.reasoning_clarity:.3f}, "
            f"evidence strength: {metrics.evidence_strength:.3f}, "
            f"consensus: {metrics.consensus_score:.3f}"
        )
        
        if should_debate:
            return f"Debate triggered - {confidence_summary}. Uncertainty flags: {metrics.uncertainty_flags}"
        else:
            return f"Skipping debate - {confidence_summary}. High confidence threshold met."
    
    async def run_adaptive_debate(
        self,
        query: str,
        agents: List[BaseAgent],
        initial_response: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run debate with adaptive gating."""
        start_time = asyncio.get_event_loop().time()
        
        # Check if debate is necessary
        decision = await self.should_trigger_debate(initial_response, agents, context)
        
        if not decision.should_debate:
            # Return initial response with efficiency metrics
            end_time = asyncio.get_event_loop().time()
            efficiency_gain = self._calculate_efficiency_gain(end_time - start_time)
            
            return {
                'response': initial_response,
                'debate_skipped': True,
                'efficiency_gain': efficiency_gain,
                'decision_reasoning': decision.reasoning,
                'confidence_metrics': decision.metrics
            }
        
        # Run full debate
        debate_result = await self._conduct_debate(query, agents, initial_response, context)
        
        end_time = asyncio.get_event_loop().time()
        
        return {
            'response': debate_result,
            'debate_skipped': False,
            'debate_duration': end_time - start_time,
            'decision_reasoning': decision.reasoning,
            'confidence_metrics': decision.metrics
        }
    
    async def _conduct_debate(
        self,
        query: str,
        agents: List[BaseAgent],
        initial_response: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Conduct multi-agent debate."""
        debate_history = [initial_response]
        current_response = initial_response
        
        for round_num in range(self.max_debate_rounds):
            logger.info(f"Debate round {round_num + 1}")
            
            # Get responses from other agents
            round_responses = []
            for agent in agents[:self.min_agents_for_debate]:
                try:
                    agent_response = await agent.process(
                        query,
                        context={
                            **context,
                            'previous_responses': debate_history,
                            'debate_round': round_num + 1
                        }
                    )
                    round_responses.append(agent_response)
                except Exception as e:
                    handle_error(e)
                    continue
            
            # Synthesize responses
            if round_responses:
                current_response = await self._synthesize_debate_round(
                    query, debate_history, round_responses
                )
                debate_history.append(current_response)
            
            # Check for convergence
            if await self._check_convergence(debate_history):
                logger.info(f"Debate converged after {round_num + 1} rounds")
                break
        
        return current_response
    
    async def _synthesize_debate_round(
        self,
        query: str,
        history: List[Dict[str, Any]],
        responses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synthesize responses from a debate round."""
        # Simple synthesis - in practice would use more sophisticated merging
        best_response = max(responses, key=lambda r: r.get('confidence', 0.0))
        
        # Combine insights from all responses
        combined_reasoning = []
        for response in responses:
            if response.get('reasoning'):
                combined_reasoning.append(response['reasoning'])
        
        return {
            'content': best_response.get('content', ''),
            'confidence': best_response.get('confidence', 0.0),
            'reasoning': ' '.join(combined_reasoning),
            'citations': best_response.get('citations', []),
            'debate_synthesis': True
        }
    
    async def _check_convergence(self, history: List[Dict[str, Any]]) -> bool:
        """Check if debate has converged."""
        if len(history) < 2:
            return False
            
        # Simple convergence check based on confidence stabilization
        recent_confidences = [r.get('confidence', 0.0) for r in history[-2:]]
        confidence_diff = abs(recent_confidences[0] - recent_confidences[1])
        
        return confidence_diff < 0.05  # 5% threshold
    
    def _calculate_efficiency_gain(self, time_saved: float) -> float:
        """Calculate efficiency gain from skipping debate."""
        # Estimate average debate time (would be measured in practice)
        avg_debate_time = 30.0  # seconds
        return max(avg_debate_time - time_saved, 0.0) / avg_debate_time
    
    async def adapt_threshold(self, accuracy_feedback: bool) -> None:
        """Adapt confidence threshold based on accuracy feedback."""
        self.accuracy_history.append(accuracy_feedback)
        
        # Keep history manageable
        if len(self.accuracy_history) > 100:
            self.accuracy_history = self.accuracy_history[-50:]
        
        # Calculate recent accuracy
        recent_accuracy = sum(self.accuracy_history[-10:]) / min(len(self.accuracy_history), 10)
        
        # Adjust threshold
        if recent_accuracy < 0.8:  # Too many wrong skips
            self.confidence_threshold = min(self.confidence_threshold + 0.02, 0.95)
            logger.info(f"Increased confidence threshold to {self.confidence_threshold:.3f}")
        elif recent_accuracy > 0.95:  # Can afford to be more aggressive
            self.confidence_threshold = max(self.confidence_threshold - 0.01, 0.7)
            logger.info(f"Decreased confidence threshold to {self.confidence_threshold:.3f}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the adaptive gating."""
        recent_accuracy = 0.0
        if self.accuracy_history:
            recent_accuracy = sum(self.accuracy_history[-20:]) / min(len(self.accuracy_history), 20)
        
        avg_efficiency = 0.0
        if self.efficiency_gains:
            avg_efficiency = sum(self.efficiency_gains) / len(self.efficiency_gains)
        
        return {
            'current_threshold': self.confidence_threshold,
            'recent_accuracy': recent_accuracy,
            'avg_efficiency_gain': avg_efficiency,
            'total_decisions': len(self.accuracy_history),
            'threshold_adaptations': len(self.threshold_history)
        }