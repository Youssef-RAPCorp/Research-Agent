from typing import Dict, List, Any, Optional, Union, Callable
import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
import logging

from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent


class RefinePhase(Enum):
    """Phases of the self-refinement process."""
    GENERATE = "generate"
    CRITIQUE = "critique"
    REFINE = "refine"


@dataclass
class RubricCriterion:
    """A single criterion in the evaluation rubric."""
    name: str
    description: str
    weight: float = 1.0
    min_score: int = 1
    max_score: int = 10


@dataclass
class QualityScore:
    """Quality assessment with scores per criterion."""
    total_score: float
    criterion_scores: Dict[str, float] = field(default_factory=dict)
    feedback: str = ""
    passed_threshold: bool = False


@dataclass
class RefineIteration:
    """Single iteration of the generate-critique-refine loop."""
    cycle: int
    phase: RefinePhase
    content: str
    quality_score: Optional[QualityScore] = None
    timestamp: str = ""


class SelfRefiner:
    """Generate→Critique→Refine loop with explicit rubric scoring."""
    
    def __init__(
        self,     
        agent=None,     
        max_cycles: int = 3,     
        quality_threshold: float = 7.0,     
        rubric: Optional[List[RubricCriterion]] = None
    , **kwargs):
        """Initialize self-refiner with configurable parameters."""
        self.agent = agent
        self.max_cycles = min(max_cycles, 3)
        self.quality_threshold = quality_threshold
        self.logger = get_logger(__name__)
        
        # Default rubric for physics research
        self.rubric = rubric or [
            RubricCriterion("accuracy", "Mathematical and scientific accuracy", 2.0),
            RubricCriterion("clarity", "Clear and understandable presentation", 1.5),
            RubricCriterion("completeness", "Comprehensive coverage of topic", 1.5),
            RubricCriterion("rigor", "Scientific rigor and methodology", 2.0),
            RubricCriterion("novelty", "Original insights or approaches", 1.0)
        ]
        
        self.iterations: List[RefineIteration] = []
        self.current_cycle = 0
    
    async def refine(
        self,
        initial_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        custom_rubric: Optional[List[RubricCriterion]] = None
    ) -> Dict[str, Any]:
        """Execute the self-refinement loop."""
        try:
            if custom_rubric:
                self.rubric = custom_rubric
                
            self.iterations.clear()
            self.current_cycle = 0
            
            current_content = ""
            best_content = ""
            best_score = 0.0
            
            for cycle in range(self.max_cycles):
                self.current_cycle = cycle + 1
                self.logger.info(f"Starting refinement cycle {self.current_cycle}")
                
                # Generation phase
                generated_content = await self._generate_content(
                    initial_prompt, current_content, context
                )
                
                self._record_iteration(
                    cycle + 1, RefinePhase.GENERATE, generated_content
                )
                
                # Critique phase
                quality_score = await self._critique_content(generated_content)
                
                self._record_iteration(
                    cycle + 1, RefinePhase.CRITIQUE, 
                    f"Score: {quality_score.total_score:.2f}\n{quality_score.feedback}",
                    quality_score
                )
                
                # Check if quality threshold is met
                if quality_score.total_score > best_score:
                    best_score = quality_score.total_score
                    best_content = generated_content
                
                if quality_score.passed_threshold:
                    self.logger.info(
                        f"Quality threshold met in cycle {self.current_cycle}: "
                        f"{quality_score.total_score:.2f}"
                    )
                    break
                
                # Refine phase (except on last cycle)
                if cycle < self.max_cycles - 1:
                    current_content = await self._refine_content(
                        generated_content, quality_score
                    )
                    
                    self._record_iteration(
                        cycle + 1, RefinePhase.REFINE, current_content
                    )
                else:
                    current_content = generated_content
            
            return {
                "final_content": best_content,
                "final_score": best_score,
                "cycles_completed": self.current_cycle,
                "iterations": [
                    {
                        "cycle": it.cycle,
                        "phase": it.phase.value,
                        "content": it.content,
                        "quality_score": it.quality_score.__dict__ if it.quality_score else None
                    }
                    for it in self.iterations
                ],
                "rubric_used": [
                    {
                        "name": c.name,
                        "description": c.description,
                        "weight": c.weight
                    }
                    for c in self.rubric
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Error in self-refinement: {e}")
            handle_error(e)
            raise
    
    async def _generate_content(
        self,
        prompt: str,
        previous_content: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Generate content based on prompt and context."""
        try:
            if self.current_cycle == 1:
                # Initial generation
                generation_prompt = f"""
Generate a comprehensive response to the following request:

{prompt}

Ensure your response is accurate, clear, complete, rigorous, and demonstrates original thinking.
"""
            else:
                # Refinement generation
                generation_prompt = f"""
Improve the following content based on the critique received:

Original request: {prompt}

Previous content:
{previous_content}

Generate an improved version that addresses the identified issues while maintaining the strengths.
"""
            
            if context:
                generation_prompt += f"\n\nAdditional context: {json.dumps(context, indent=2)}"
            
            response = await self.agent.process_message(generation_prompt)
            return response.get("content", "")
            
        except Exception as e:
            self.logger.error(f"Error generating content: {e}")
            raise
    
    async def _critique_content(self, content: str) -> QualityScore:
        """Critique content using the defined rubric."""
        try:
            rubric_description = "\n".join([
                f"- {c.name} (weight {c.weight}): {c.description}"
                for c in self.rubric
            ])
            
            critique_prompt = f"""
Evaluate the following content using this rubric (scale 1-10 for each criterion):

{rubric_description}

Content to evaluate:
{content}

Provide:
1. A score (1-10) for each criterion
2. Detailed feedback explaining the scores
3. Specific suggestions for improvement

Format your response as JSON:
{{
    "scores": {{"criterion_name": score, ...}},
    "feedback": "detailed feedback text",
    "suggestions": ["suggestion 1", "suggestion 2", ...]
}}
"""
            
            response = await self.agent.process_message(critique_prompt)
            critique_text = response.get("content", "")
            
            # Parse the critique response
            try:
                critique_data = json.loads(critique_text)
                scores = critique_data.get("scores", {})
                feedback = critique_data.get("feedback", "")
                
                # Calculate weighted total score
                total_weight = sum(c.weight for c in self.rubric)
                weighted_score = sum(
                    scores.get(c.name, 5.0) * c.weight
                    for c in self.rubric
                ) / total_weight
                
                quality_score = QualityScore(
                    total_score=weighted_score,
                    criterion_scores=scores,
                    feedback=feedback,
                    passed_threshold=weighted_score >= self.quality_threshold
                )
                
                return quality_score
                
            except json.JSONDecodeError:
                # Fallback scoring if JSON parsing fails
                self.logger.warning("Failed to parse critique JSON, using fallback scoring")
                return QualityScore(
                    total_score=5.0,
                    feedback=critique_text,
                    passed_threshold=False
                )
                
        except Exception as e:
            self.logger.error(f"Error critiquing content: {e}")
            # Return minimal score to continue process
            return QualityScore(total_score=1.0, feedback=f"Error in critique: {e}")
    
    async def _refine_content(self, content: str, quality_score: QualityScore) -> str:
        """Refine content based on critique feedback."""
        try:
            refine_prompt = f"""
Refine the following content based on this quality assessment:

Current content:
{content}

Quality score: {quality_score.total_score:.2f}/{max(c.max_score for c in self.rubric)}

Detailed feedback:
{quality_score.feedback}

Criterion scores:
{json.dumps(quality_score.criterion_scores, indent=2)}

Create an improved version that addresses the feedback while preserving the existing strengths.
Focus especially on the lowest-scoring criteria.
"""
            
            response = await self.agent.process_message(refine_prompt)
            return response.get("content", content)
            
        except Exception as e:
            self.logger.error(f"Error refining content: {e}")
            return content  # Return original if refinement fails
    
    def _record_iteration(
        self,
        cycle: int,
        phase: RefinePhase,
        content: str,
        quality_score: Optional[QualityScore] = None
    ) -> None:
        """Record an iteration in the refinement process."""
        import datetime
        
        iteration = RefineIteration(
            cycle=cycle,
            phase=phase,
            content=content,
            quality_score=quality_score,
            timestamp=datetime.datetime.now().isoformat()
        )
        
        self.iterations.append(iteration)
    
    def get_refinement_history(self) -> List[Dict[str, Any]]:
        """Get the complete refinement history."""
        return [
            {
                "cycle": it.cycle,
                "phase": it.phase.value,
                "content": it.content[:200] + "..." if len(it.content) > 200 else it.content,
                "quality_score": it.quality_score.__dict__ if it.quality_score else None,
                "timestamp": it.timestamp
            }
            for it in self.iterations
        ]
    
    def set_custom_rubric(self, rubric: List[RubricCriterion]) -> None:
        """Set a custom evaluation rubric."""
        self.rubric = rubric
        self.logger.info(f"Updated rubric with {len(rubric)} criteria")
    
    def get_current_rubric(self) -> List[Dict[str, Any]]:
        """Get the current evaluation rubric."""
        return [
            {
                "name": c.name,
                "description": c.description,
                "weight": c.weight,
                "min_score": c.min_score,
                "max_score": c.max_score
            }
            for c in self.rubric
        ]

    async def refine_hypothesis(self, *args, **kwargs):
        return dict()

SelfRefinePattern = SelfRefiner  # auto-alias

SelfRefine = SelfRefiner  # auto-alias
CRITIQUE = type('CRITIQUE', (), {})  # auto-stub: not found in project

GENERATE = type('GENERATE', (), {})  # auto-stub: not found in project

REFINE = type('REFINE', (), {})  # auto-stub: not found in project
