"""ChatEval Consensus implementation with diverse persona panel for physics discovery."""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

from config.logger import get_logger
from config.settings import get_settings
from config.errors import handle_error
try:
    from agents.base_agent import BaseAgent
except ImportError:  # circular import guard — agents.base_agent
    BaseAgent = type('BaseAgent', (), {})
from memory.working import WorkingMemory

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class PersonaConfig:
    """Configuration for evaluation persona."""
    name: str
    role: str
    expertise: List[str]
    evaluation_criteria: List[str]
    response_style: str
    bias_tendencies: List[str] = field(default_factory=list)


@dataclass
class EvaluationRound:
    """Represents one round of multi-agent evaluation."""
    round_id: int
    topic: str
    content: str
    evaluations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    consensus_score: Optional[float] = None
    synthesis: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConsensusResult:
    """Final consensus evaluation result."""
    overall_score: float
    confidence: float
    synthesis: str
    reasoning: str
    agent_scores: Dict[str, float]
    convergence_rounds: int
    dissenting_opinions: List[str]
    consensus_quality: str


class PersonaAgent(BaseAgent):
    """Individual evaluation agent with specific persona."""
    
    def __init__(self,      config=None,      memory=None, **kwargs):
        super().__init__(f"persona_{config.name.lower()}", memory)
        self.config = config
        self.evaluation_history: List[Dict] = []
        
    async def evaluate_content(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate content according to persona's criteria."""
        try:
            prompt = self._build_evaluation_prompt(content, context)
            
            response = await self._get_llm_response(prompt)
            evaluation = self._parse_evaluation_response(response)
            
            # Store in history
            self.evaluation_history.append({
                'content': content,
                'evaluation': evaluation,
                'timestamp': datetime.now()
            })
            
            return evaluation
            
        except Exception as e:
            handle_error(e)
            return self._default_evaluation()
    
    def _build_evaluation_prompt(self, content: str, context: Dict[str, Any]) -> str:
        """Build persona-specific evaluation prompt."""
        return f"""
    async def process_task(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def get_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def run(self, *args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'comprehensive'})

    async def process_message(self, *args, **kwargs):
        return args[0] if args else dict()

You are {self.config.name}, a {self.config.role} with expertise in {', '.join(self.config.expertise)}.

Evaluate the following physics content according to your expertise and perspective:

CONTENT:
{content}

CONTEXT:
{json.dumps(context, indent=2)}

EVALUATION CRITERIA:
{chr(10).join(f'- {criterion}' for criterion in self.config.evaluation_criteria)}

RESPONSE STYLE: {self.config.response_style}

Provide your evaluation in this JSON format:
{{
    "score": <float 0-10>,
    "confidence": <float 0-1>,
    "strengths": ["strength1", "strength2"],
    "weaknesses": ["weakness1", "weakness2"],
    "reasoning": "detailed explanation",
    "recommendations": ["rec1", "rec2"],
    "domain_specific_notes": "notes specific to your expertise"
}}

Be thorough but concise. Consider your role's perspective and potential biases.
"""
    
    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM evaluation response."""
        try:
            # Extract JSON from response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            else:
                return self._default_evaluation()
                
        except Exception as e:
            logger.warning(f"Failed to parse evaluation response: {e}")
            return self._default_evaluation()
    
    def _default_evaluation(self) -> Dict[str, Any]:
        """Default evaluation when parsing fails."""
        return {
            'score': 5.0,
            'confidence': 0.5,
            'strengths': ['Unable to evaluate'],
            'weaknesses': ['Evaluation failed'],
            'reasoning': 'Evaluation parsing failed',
            'recommendations': ['Retry evaluation'],
            'domain_specific_notes': 'Error in evaluation process'
        }
    
    async def critique_peer_evaluation(self, peer_name: str, peer_evaluation: Dict[str, Any], 
                                     original_content: str) -> Dict[str, Any]:
        """Critique another agent's evaluation."""
        try:
            prompt = f"""
As {self.config.name}, review the evaluation provided by {peer_name}.

ORIGINAL CONTENT:
{original_content}

PEER EVALUATION:
{json.dumps(peer_evaluation, indent=2)}

Provide constructive critique focusing on:
1. Accuracy of their assessment
2. Completeness of their analysis
3. Alignment with physics principles
4. Potential blind spots or biases

Respond in JSON format:
{{
    "agreement_level": <float 0-1>,
    "critique_points": ["point1", "point2"],
    "alternative_perspective": "your alternative view",
    "consensus_suggestions": ["suggestion1", "suggestion2"]
}}
"""
            
            response = await self._get_llm_response(prompt)
            return self._parse_critique_response(response)
            
        except Exception as e:
            handle_error(e)
            return {'agreement_level': 0.5, 'critique_points': ['Critique failed']}
    
    def _parse_critique_response(self, response: str) -> Dict[str, Any]:
        """Parse critique response."""
        try:
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            else:
                return {'agreement_level': 0.5, 'critique_points': ['Parse failed']}
                
        except Exception as e:
            return {'agreement_level': 0.5, 'critique_points': ['Parse failed']}


class ConsensusEngine:
    """Engine for reaching consensus among diverse agent evaluations."""
    
    def __init__(self, **kwargs):
        self.convergence_threshold = 0.8
        self.max_rounds = 5
        self.min_agents = 3
        
    async def find_consensus(self, evaluations: Dict[str, Dict[str, Any]], 
                           content: str) -> ConsensusResult:
        """Find consensus among agent evaluations."""
        try:
            if len(evaluations) < self.min_agents:
                raise ValueError(f"Need at least {self.min_agents} evaluations")
            
            consensus_reached = False
            rounds = 0
            current_evaluations = evaluations.copy()
            
            while not consensus_reached and rounds < self.max_rounds:
                rounds += 1
                
                # Calculate convergence
                convergence = self._calculate_convergence(current_evaluations)
                
                if convergence >= self.convergence_threshold:
                    consensus_reached = True
                    break
                
                # If not converged, facilitate discussion round
                current_evaluations = await self._discussion_round(
                    current_evaluations, content, rounds
                )
            
            # Synthesize final result
            return await self._synthesize_consensus(current_evaluations, rounds, content)
            
        except Exception as e:
            handle_error(e)
            return self._default_consensus()
    
    def _calculate_convergence(self, evaluations: Dict[str, Dict[str, Any]]) -> float:
        """Calculate convergence level of evaluations."""
        scores = [eval_data['score'] for eval_data in evaluations.values()]
        
        if not scores:
            return 0.0
        
        # Calculate coefficient of variation
        mean_score = sum(scores) / len(scores)
        if mean_score == 0:
            return 1.0
        
        variance = sum((score - mean_score) ** 2 for score in scores) / len(scores)
        std_dev = variance ** 0.5
        cv = std_dev / mean_score
        
        # Convert to convergence score (lower CV = higher convergence)
        convergence = max(0, 1 - cv)
        return min(1.0, convergence)
    
    async def _discussion_round(self, evaluations: Dict[str, Dict[str, Any]], 
                              content: str, round_num: int) -> Dict[str, Dict[str, Any]]:
        """Facilitate discussion round between agents."""
        logger.info(f"Starting discussion round {round_num}")
        
        updated_evaluations = {}
        
        for agent_name, evaluation in evaluations.items():
            # Get other agents' evaluations for comparison
            peer_evaluations = {k: v for k, v in evaluations.items() if k != agent_name}
            
            # Update evaluation based on peer input
            updated_eval = await self._update_evaluation_with_peers(
                agent_name, evaluation, peer_evaluations, content
            )
            
            updated_evaluations[agent_name] = updated_eval
        
        return updated_evaluations
    
    async def _update_evaluation_with_peers(self, agent_name: str, 
                                          evaluation: Dict[str, Any],
                                          peer_evaluations: Dict[str, Dict[str, Any]],
                                          content: str) -> Dict[str, Any]:
        """Update agent evaluation considering peer input."""
        try:
            # Calculate peer average
            peer_scores = [pe['score'] for pe in peer_evaluations.values()]
            peer_avg = sum(peer_scores) / len(peer_scores) if peer_scores else 0
            
            # Adjust score towards consensus with confidence weighting
            original_score = evaluation['score']
            confidence = evaluation.get('confidence', 0.5)
            
            # Higher confidence agents adjust less
            adjustment_factor = (1 - confidence) * 0.3
            adjusted_score = original_score + adjustment_factor * (peer_avg - original_score)
            
            updated_evaluation = evaluation.copy()
            updated_evaluation['score'] = max(0, min(10, adjusted_score))
            updated_evaluation['peer_influence'] = abs(adjusted_score - original_score)
            
            return updated_evaluation
            
        except Exception as e:
            handle_error(e)
            return evaluation
    
    async def _synthesize_consensus(self, evaluations: Dict[str, Dict[str, Any]], 
                                  rounds: int, content: str) -> ConsensusResult:
        """Synthesize final consensus result."""
        try:
            scores = [eval_data['score'] for eval_data in evaluations.values()]
            confidences = [eval_data.get('confidence', 0.5) for eval_data in evaluations.values()]
            
            # Weighted average by confidence
            total_weight = sum(confidences)
            if total_weight > 0:
                overall_score = sum(s * c for s, c in zip(scores, confidences)) / total_weight
            else:
                overall_score = sum(scores) / len(scores)
            
            # Calculate consensus confidence
            convergence = self._calculate_convergence(evaluations)
            consensus_confidence = (convergence + sum(confidences) / len(confidences)) / 2
            
            # Identify dissenting opinions
            dissenting = self._find_dissenting_opinions(evaluations, overall_score)
            
            # Generate synthesis
            synthesis = await self._generate_synthesis(evaluations, content)
            
            # Determine consensus quality
            quality = self._assess_consensus_quality(convergence, rounds, len(evaluations))
            
            return ConsensusResult(
                overall_score=overall_score,
                confidence=consensus_confidence,
                synthesis=synthesis,
                reasoning=f"Consensus reached after {rounds} rounds with {convergence:.2f} convergence",
                agent_scores={name: eval_data['score'] for name, eval_data in evaluations.items()},
                convergence_rounds=rounds,
                dissenting_opinions=dissenting,
                consensus_quality=quality
            )
            
        except Exception as e:
            handle_error(e)
            return self._default_consensus()
    
    def _find_dissenting_opinions(self, evaluations: Dict[str, Dict[str, Any]], 
                                overall_score: float) -> List[str]:
        """Identify significantly dissenting opinions."""
        dissenting = []
        threshold = 2.0  # Score difference threshold
        
        for agent_name, evaluation in evaluations.items():
            score_diff = abs(evaluation['score'] - overall_score)
            if score_diff > threshold:
                reason = evaluation.get('reasoning', 'No reasoning provided')
                dissenting.append(f"{agent_name}: {reason}")
        
        return dissenting
    
    async def _generate_synthesis(self, evaluations: Dict[str, Dict[str, Any]], 
                                content: str) -> str:
        """Generate synthesis of all evaluations."""
        strengths = []
        weaknesses = []
        recommendations = []
        
        for evaluation in evaluations.values():
            strengths.extend(evaluation.get('strengths', []))
            weaknesses.extend(evaluation.get('weaknesses', []))
            recommendations.extend(evaluation.get('recommendations', []))
        
        # Remove duplicates while preserving order
        unique_strengths = list(dict.fromkeys(strengths))
        unique_weaknesses = list(dict.fromkeys(weaknesses))
        unique_recommendations = list(dict.fromkeys(recommendations))
        
        synthesis = f"""
CONSENSUS EVALUATION SYNTHESIS:

Key Strengths:
{chr(10).join(f'• {s}' for s in unique_strengths[:5])}

Areas for Improvement:
{chr(10).join(f'• {w}' for w in unique_weaknesses[:5])}

Recommendations:
{chr(10).join(f'• {r}' for r in unique_recommendations[:5])}
""".strip()
        
        return synthesis
    
    def _assess_consensus_quality(self, convergence: float, rounds: int, 
                                num_agents: int) -> str:
        """Assess quality of reached consensus."""
        if convergence >= 0.9 and rounds <= 2:
            return "High"
        elif convergence >= 0.8 and rounds <= 3:
            return "Good"
        elif convergence >= 0.7 and rounds <= 4:
            return "Moderate"
        else:
            return "Low"
    
    def _default_consensus(self) -> ConsensusResult:
        """Default consensus when synthesis fails."""
        return ConsensusResult(
            overall_score=5.0,
            confidence=0.3,
            synthesis="Consensus synthesis failed",
            reasoning="Unable to reach consensus",
            agent_scores={},
            convergence_rounds=0,
            dissenting_opinions=[],
            consensus_quality="Failed"
        )


class ChatEvaluator:
    """Main chat evaluation system with diverse persona panel."""
    
    def __init__(self,      memory=None, **kwargs):
        self.memory = memory
        self.personas = self._initialize_personas()
        self.agents: Dict[str, PersonaAgent] = {}
        self.consensus_engine = ConsensusEngine()
        self.evaluation_history: List[EvaluationRound] = []
        
    def _initialize_personas(self) -> List[PersonaConfig]:
        """Initialize diverse evaluation personas."""
        return [
            PersonaConfig(
                name="GeneralPhysicist",
                role="General Physics Researcher",
                expertise=["Classical Mechanics", "Thermodynamics", "Electromagnetism"],
                evaluation_criteria=[
                    "Scientific accuracy",
                    "Mathematical rigor",
                    "Clarity of explanation",
                    "Experimental feasibility"
                ],
                response_style="Balanced and methodical",
                bias_tendencies=["Conservative towards new theories"]
            ),
            
            PersonaConfig(
                name="CriticalReviewer",
                role="Peer Review Specialist",
                expertise=["Research Methodology", "Statistical Analysis", "Academic Writing"],
                evaluation_criteria=[
                    "Logical consistency",
                    "Evidence quality",
                    "Reproducibility",
                    "Citation accuracy",
                    "Potential flaws"
                ],
                response_style="Skeptical and detail-oriented",
                bias_tendencies=["Emphasis on weaknesses", "High standards"]
            ),
            
            PersonaConfig(
                name="TheoreticalPhysicist",
                role="Theoretical Physics Expert",
                expertise=["Quantum Mechanics", "Relativity", "Field Theory", "Mathematical Physics"],
                evaluation_criteria=[
                    "Theoretical depth",
                    "Mathematical sophistication",
                    "Conceptual innovation",
                    "Consistency with established theory"
                ],
                response_style="Abstract and rigorous",
                bias_tendencies=["Preference for mathematical elegance"]
            ),
            
            PersonaConfig(
                name="ExperimentalPhysicist",
                role="Experimental Physics Specialist",
                expertise=["Instrumentation", "Data Analysis", "Laboratory Techniques"],
                evaluation_criteria=[
                    "Experimental design",
                    "Measurement precision",
                    "Error analysis",
                    "Practical implementation"
                ],
                response_style="Practical and evidence-focused",
                bias_tendencies=["Skeptical of purely theoretical claims"]
            ),
            
            PersonaConfig(
                name="AppliedPhysicist",
                role="Applied Physics Researcher",
                expertise=["Engineering Physics", "Technology Applications", "Industry Applications"],
                evaluation_criteria=[
                    "Practical utility",
                    "Technological feasibility",
                    "Economic viability",
                    "Real-world impact"
                ],
                response_style="Application-oriented and pragmatic",
                bias_tendencies=["Focus on practical applications"]
            )
        ]
    
    async def initialize_agents(self) -> None:
        """Initialize persona agents."""
        for persona in self.personas:
            agent = PersonaAgent(persona, self.memory)
            await agent.initialize()
            self.agents[persona.name] = agent
        
        logger.info(f"Initialized {len(self.agents)} evaluation agents")
    
    async def evaluate_content(self, content: str, context: Optional[Dict[str, Any]] = None) -> ConsensusResult:
        """Evaluate content using diverse persona panel."""
        try:
            if not self.agents:
                await self.initialize_agents()
            
            if context is None:
                context = {}
            
            # Initial evaluation round
            logger.info("Starting multi-agent evaluation")
            initial_evaluations = {}
            
            # Gather initial evaluations from all agents
            evaluation_tasks = []
            for name, agent in self.agents.items():
                task = self._safe_evaluate(agent, content, context, name)
                evaluation_tasks.append(task)
            
            # Execute evaluations concurrently
            results = await asyncio.gather(*evaluation_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                agent_name = list(self.agents.keys())[i]
                if isinstance(result, Exception):
                    logger.warning(f"Agent {agent_name} evaluation failed: {result}")
                    initial_evaluations[agent_name] = self._default_evaluation()
                else:
                    initial_evaluations[agent_name] = result
            
            # Store evaluation round
            round_data = EvaluationRound(
                round_id=1,
                topic="Multi-agent evaluation",
                content=content,
                evaluations=initial_evaluations
            )
            self.evaluation_history.append(round_data)
            
            # Reach consensus
            consensus_result = await self.consensus_engine.find_consensus(
                initial_evaluations, content
            )
            
            logger.info(f"Consensus reached: score={consensus_result.overall_score:.2f}, "
                       f"confidence={consensus_result.confidence:.2f}")
            
            return consensus_result
            
        except Exception as e:
            handle_error(e)
            return self._default_consensus_result()
    
    async def _safe_evaluate(self, agent: PersonaAgent, content: str, 
                           context: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
        """Safely evaluate content with timeout."""
        try:
            # Add timeout for individual agent evaluation
            return await asyncio.wait_for(
                agent.evaluate_content(content, context),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"Agent {agent_name} evaluation timed out")
            return self._default_evaluation()
        except Exception as e:
            logger.warning(f"Agent {agent_name} evaluation error: {e}")
            return self._default_evaluation()
    
    def _default_evaluation(self) -> Dict[str, Any]:
        """Default evaluation for failed cases."""
        return {
            'score': 5.0,
            'confidence': 0.3,
            'strengths': ['Evaluation unavailable'],
            'weaknesses': ['Unable to assess'],
            'reasoning': 'Agent evaluation failed',
            'recommendations': ['Retry evaluation'],
            'domain_specific_notes': 'Error in evaluation process'
        }
    
    def _default_consensus_result(self) -> ConsensusResult:
        """Default consensus result for failed cases."""
        return ConsensusResult(
            overall_score=5.0,
            confidence=0.2,
            synthesis="Evaluation system temporarily unavailable",
            reasoning="System error prevented consensus evaluation",
            agent_scores={},
            convergence_rounds=0,
            dissenting_opinions=[],
            consensus_quality="Failed"
        )
    
    async def get_detailed_evaluation(self, content: str, 
                                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get detailed evaluation with individual agent perspectives."""
        consensus = await self.evaluate_content(content, context)
        
        # Get latest evaluation round
        latest_round = self.evaluation_history[-1] if self.evaluation_history else None
        
        return {
            'consensus_result': consensus,
            'individual_evaluations': latest_round.evaluations if latest_round else {},
            'evaluation_metadata': {
                'timestamp': datetime.now(),
                'num_agents': len(self.agents),
                'convergence_rounds': consensus.convergence_rounds,
                'consensus_quality': consensus.consensus_quality
            }
        }
    
    async def critique_mode_evaluation(self, content: str, 
                                     focus_areas: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run evaluation in critique mode with enhanced critical analysis."""
        try:
            # Standard evaluation
            initial_result = await self.evaluate_content(content)
            
            # Enhanced critique round
            if focus_areas:
                critique_context = {'focus_areas': focus_areas}
            else:
                critique_context = {}
            
            # Run critique-focused evaluation
            critique_evaluations = {}
            for name, agent in self.agents.items():
                if name == "CriticalReviewer":
                    # Give critic agent double weight in critique mode
                    critique_eval = await agent.evaluate_content(content, critique_context)
                    critique_evaluations[f"{name}_primary"] = critique_eval
                    critique_evaluations[f"{name}_secondary"] = critique_eval
                else:
                    critique_eval = await agent.evaluate_content(content, critique_context)
                    critique_evaluations[name] = critique_eval
            
            # Generate critique consensus
            critique_consensus = await self.consensus_engine.find_consensus(
                critique_evaluations, content
            )
            
            return {
                'standard_evaluation': initial_result,
                'critique_evaluation': critique_consensus,
                'critique_focus': focus_areas or ['General critique'],
                'comparison': {
                    'score_difference': critique_consensus.overall_score - initial_result.overall_score,
                    'confidence_difference': critique_consensus.confidence - initial_result.confidence
                }
            }
            
        except Exception as e:
            handle_error(e)
            return {
                'error': str(e),
                'standard_evaluation': self._default_consensus_result(),
                'critique_evaluation': self._default_consensus_result()
            }
    
    def get_agent_statistics(self) -> Dict[str, Any]:
        """Get statistics about agent evaluations."""
        stats = {}
        
        for name, agent in self.agents.items():
            if agent.evaluation_history:
                scores = [eval_data['evaluation']['score'] for eval_data in agent.evaluation_history]
                confidences = [eval_data['evaluation'].get('confidence', 0.5) for eval_data in agent.evaluation_history]
                
                stats[name] = {
                    'total_evaluations': len(agent.evaluation_history),
                    'avg_score': sum(scores) / len(scores),
                    'avg_confidence': sum(confidences) / len(confidences),
                    'score_std': (sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores))**0.5,
                    'persona_role': agent.config.role
                }
            else:
                stats[name] = {
                    'total_evaluations': 0,
                    'persona_role': agent.config.role
                }
        
        return stats
    
    async def shutdown(self) -> None:
        """Shutdown evaluation system."""
        logger.info("Shutting down ChatEvaluator")
        
        # Shutdown all agents
        shutdown_tasks = []
        for agent in self.agents.values():
            if hasattr(agent, 'shutdown'):
                shutdown_tasks.append(agent.shutdown())
        
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        # Clear agents
        self.agents.clear()
        logger.info("ChatEvaluator shutdown complete")

ChatEvalPattern = ChatEvaluator  # auto-alias