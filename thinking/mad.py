"""Multi-Agent Debate (MAD) pattern implementation for physics discovery."""

import asyncio
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

from config.logger import get_logger
from config.settings import get_settings
from config.errors import handle_error
from agents.base_agent import BaseAgent

logger = get_logger(__name__)
settings = get_settings()

class AgentRole(Enum):
    """Roles for MAD agents."""
    THEORIST = "theorist"
    EXPERIMENTALIST = "experimentalist"
    SKEPTIC = "skeptic"

@dataclass
class DebateArgument:
    """Individual argument in the debate."""
    agent_role: AgentRole
    content: str
    confidence: float
    citations: List[str]
    round_number: int
    timestamp: float

@dataclass
class DebateRound:
    """Complete round of debate."""
    round_number: int
    arguments: List[DebateArgument]
    consensus_score: float
    converged: bool

class MADAgent(BaseAgent):
    """Agent participating in multi-agent debate."""
    
    def __init__(self,      role=None,      persona_prompt=None, **kwargs):
        """Initialize MAD agent with specific role."""
        super().__init__(f"mad_{role.value}")
        self.role = role
        self.persona_prompt = persona_prompt
        self.debate_history: List[DebateArgument] = []
    
    async def generate_argument(self, 
                              topic: str,
                              previous_arguments: List[DebateArgument],
                              round_number: int) -> DebateArgument:
        """Generate argument for current debate round."""
        try:
            # Build context from previous arguments
            context = self._build_debate_context(previous_arguments)
            
            # Create role-specific prompt
            prompt = self._create_argument_prompt(topic, context, round_number)
            
            # Generate response
            response = await self.generate_response(prompt)
            
            # Parse response for confidence and citations
            argument_data = self._parse_argument_response(response)
            
            argument = DebateArgument(
                agent_role=self.role,
                content=argument_data["content"],
                confidence=argument_data["confidence"],
                citations=argument_data["citations"],
                round_number=round_number,
                timestamp=asyncio.get_event_loop().time()
            )
            
            self.debate_history.append(argument)
            return argument
            
        except Exception as e:
            handle_error(e)
            # Return fallback argument
            return DebateArgument(
                agent_role=self.role,
                content=f"Unable to generate argument due to error: {str(e)}",
                confidence=0.1,
                citations=[],
                round_number=round_number,
                timestamp=asyncio.get_event_loop().time()
            )
    
    def _build_debate_context(self, previous_arguments: List[DebateArgument]) -> str:
        """Build context string from previous debate arguments."""
        if not previous_arguments:
            return "This is the beginning of the debate."
        
        context_parts = ["Previous arguments in this debate:"]
        for arg in previous_arguments[-6:]:  # Last 6 arguments for context
            context_parts.append(
                f"- {arg.agent_role.value.title()}: {arg.content[:200]}... "
                f"(confidence: {arg.confidence:.2f})"
            )
        
        return "\n".join(context_parts)
    
    def _create_argument_prompt(self, topic: str, context: str, round_number: int) -> str:
        """Create role-specific prompt for argument generation."""
        base_prompt = f"""
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

{self.persona_prompt}

DEBATE TOPIC: {topic}

{context}

This is round {round_number} of the debate. Based on your role and the previous arguments, 
provide your perspective on this physics topic. Your response should include:
1. Your main argument (2-3 paragraphs)
2. Confidence level (0.0 to 1.0)
3. Relevant citations or references

Format your response as JSON:
{{
    "content": "Your detailed argument here...",
    "confidence": 0.8,
    "citations": ["reference1", "reference2"]
}}
"""
        
        if self.role == AgentRole.THEORIST:
            base_prompt += "\nFocus on theoretical consistency, mathematical elegance, and conceptual frameworks."
        elif self.role == AgentRole.EXPERIMENTALIST:
            base_prompt += "\nFocus on experimental evidence, measurable predictions, and practical verification."
        elif self.role == AgentRole.SKEPTIC:
            base_prompt += "\nFocus on potential flaws, alternative explanations, and critical analysis."
        
        return base_prompt
    
    def _parse_argument_response(self, response: str) -> Dict[str, Any]:
        """Parse agent response into structured argument data."""
        try:
            data = json.loads(response)
            return {
                "content": data.get("content", response),
                "confidence": float(data.get("confidence", 0.5)),
                "citations": data.get("citations", [])
            }
        except (json.JSONDecodeError, ValueError):
            # Fallback parsing
            return {
                "content": response,
                "confidence": 0.5,
                "citations": []
            }

class MADPattern:
    """Multi-Agent Debate pattern for physics discovery."""
    
    def __init__(self,     
                 max_rounds: int = 5,     
                 consensus_threshold: float = 0.8,     
                 min_confidence_delta: float = 0.1, **kwargs):
        """Initialize MAD pattern."""
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold
        self.min_confidence_delta = min_confidence_delta
        
        # Initialize agents with specific personas
        self.agents = self._initialize_agents()
        self.debate_history: List[DebateRound] = []
    
    def _initialize_agents(self) -> Dict[AgentRole, MADAgent]:
        """Initialize the three MAD agents with specific personas."""
        personas = {
            AgentRole.THEORIST: """
You are a theoretical physicist focused on developing elegant mathematical frameworks 
and conceptual models. You prioritize theoretical consistency, mathematical beauty, 
and fundamental principles. You think in terms of symmetries, conservation laws, 
and deep structural insights.
""".strip(),
            
            AgentRole.EXPERIMENTALIST: """
You are an experimental physicist focused on empirical evidence and measurable 
phenomena. You prioritize experimental verification, testable predictions, and 
practical applications. You think in terms of what can be measured, observed, 
and verified in the laboratory.
""".strip(),
            
            AgentRole.SKEPTIC: """
You are a critical physicist focused on identifying potential flaws and alternative 
explanations. You prioritize rigorous analysis, devil's advocate questioning, and 
comprehensive consideration of alternative hypotheses. You think in terms of what 
could be wrong, what's missing, and what other explanations might exist.
""".strip()
        }
        
        return {
            role: MADAgent(role, persona) 
            for role, persona in personas.items()
        }
    
    async def run_debate(self, topic: str) -> List[DebateRound]:
        """Run complete multi-agent debate on given topic."""
        logger.info(f"Starting MAD debate on topic: {topic}")
        
        all_arguments: List[DebateArgument] = []
        
        for round_num in range(1, self.max_rounds + 1):
            logger.info(f"Starting debate round {round_num}")
            
            # Generate arguments from all agents
            round_arguments = await self._run_debate_round(
                topic, all_arguments, round_num
            )
            
            # Calculate consensus score
            consensus_score = self._calculate_consensus_score(round_arguments)
            
            # Check convergence
            converged = self._check_convergence(
                round_arguments, consensus_score, round_num
            )
            
            # Create round summary
            debate_round = DebateRound(
                round_number=round_num,
                arguments=round_arguments,
                consensus_score=consensus_score,
                converged=converged
            )
            
            self.debate_history.append(debate_round)
            all_arguments.extend(round_arguments)
            
            logger.info(f"Round {round_num} consensus score: {consensus_score:.3f}")
            
            if converged:
                logger.info(f"Debate converged after {round_num} rounds")
                break
        
        return self.debate_history
    
    async def _run_debate_round(self,
                               topic: str,
                               previous_arguments: List[DebateArgument],
                               round_number: int) -> List[DebateArgument]:
        """Run single round of debate with all agents."""
        round_arguments = []
        
        # Agents speak in order: Theorist, Experimentalist, Skeptic
        agent_order = [
            AgentRole.THEORIST,
            AgentRole.EXPERIMENTALIST, 
            AgentRole.SKEPTIC
        ]
        
        for role in agent_order:
            agent = self.agents[role]
            
            # Include arguments from current round so agents can respond to each other
            current_context = previous_arguments + round_arguments
            
            argument = await agent.generate_argument(
                topic, current_context, round_number
            )
            
            round_arguments.append(argument)
            logger.debug(f"{role.value} argument confidence: {argument.confidence:.3f}")
        
        return round_arguments
    
    def _calculate_consensus_score(self, arguments: List[DebateArgument]) -> float:
        """Calculate consensus score for current round."""
        if len(arguments) < 2:
            return 0.0
        
        # Simple consensus based on confidence convergence
        confidences = [arg.confidence for arg in arguments]
        mean_confidence = sum(confidences) / len(confidences)
        
        # Calculate variance in confidences
        variance = sum((c - mean_confidence) ** 2 for c in confidences) / len(confidences)
        
        # Lower variance = higher consensus
        consensus_score = max(0.0, 1.0 - (variance * 2))
        
        return consensus_score
    
    def _check_convergence(self,
                          round_arguments: List[DebateArgument],
                          consensus_score: float,
                          round_number: int) -> bool:
        """Check if debate has converged."""
        # Primary convergence criterion: consensus threshold
        if consensus_score >= self.consensus_threshold:
            return True
        
        # Secondary criterion: confidence stability over rounds
        if round_number >= 2:
            current_confidences = [arg.confidence for arg in round_arguments]
            prev_round_args = [
                arg for arg in self.debate_history[-1].arguments
                if arg.round_number == round_number - 1
            ] if self.debate_history else []
            
            if prev_round_args:
                prev_confidences = [arg.confidence for arg in prev_round_args]
                
                # Check if confidence changes are minimal
                confidence_deltas = [
                    abs(curr - prev) 
                    for curr, prev in zip(current_confidences, prev_confidences)
                ]
                
                if all(delta < self.min_confidence_delta for delta in confidence_deltas):
                    logger.info("Debate converged due to confidence stability")
                    return True
        
        return False
    
    def get_final_synthesis(self) -> Optional[Dict[str, Any]]:
        """Generate final synthesis from complete debate."""
        if not self.debate_history:
            return None
        
        final_round = self.debate_history[-1]
        
        # Aggregate insights from all agents
        all_arguments = []
        for round_data in self.debate_history:
            all_arguments.extend(round_data.arguments)
        
        # Group by agent role
        role_arguments = {role: [] for role in AgentRole}
        for arg in all_arguments:
            role_arguments[arg.agent_role].append(arg)
        
        # Extract key insights
        synthesis = {
            "converged": final_round.converged,
            "final_consensus_score": final_round.consensus_score,
            "total_rounds": len(self.debate_history),
            "theoretical_insights": self._extract_role_insights(
                role_arguments[AgentRole.THEORIST]
            ),
            "experimental_insights": self._extract_role_insights(
                role_arguments[AgentRole.EXPERIMENTALIST]
            ),
            "critical_concerns": self._extract_role_insights(
                role_arguments[AgentRole.SKEPTIC]
            ),
            "debate_summary": self._create_debate_summary()
        }
        
        return synthesis
    
    def _extract_role_insights(self, arguments: List[DebateArgument]) -> List[str]:
        """Extract key insights from arguments of specific role."""
        if not arguments:
            return []
        
        # Get highest confidence arguments
        sorted_args = sorted(arguments, key=lambda x: x.confidence, reverse=True)
        
        # Extract main points from top arguments
        insights = []
        for arg in sorted_args[:3]:  # Top 3 arguments
            # Simple extraction - in practice could use NLP
            insights.append(arg.content[:200] + "...")
        
        return insights
    
    def _create_debate_summary(self) -> str:
        """Create overall summary of the debate."""
        if not self.debate_history:
            return "No debate rounds completed."
        
        summary_parts = [
            f"Multi-agent debate completed in {len(self.debate_history)} rounds.",
            f"Final consensus score: {self.debate_history[-1].consensus_score:.3f}",
            f"Convergence achieved: {self.debate_history[-1].converged}"
        ]
        
        return " ".join(summary_parts)
    
    def reset(self) -> None:
        """Reset debate state for new topic."""
        self.debate_history.clear()
        for agent in self.agents.values():
            agent.debate_history.clear()
EXPERIMENTALIST = type('EXPERIMENTALIST', (), {})  # auto-stub: not found in project

SKEPTIC = type('SKEPTIC', (), {})  # auto-stub: not found in project

THEORIST = type('THEORIST', (), {})  # auto-stub: not found in project
