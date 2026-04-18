"""Language Agent Tree Search (LATS) with MCTS for reasoning path optimization."""

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from config.logger import get_logger
from config.settings import get_settings
from memory.working import WorkingMemory
from memory.reflexion_store import ReflexionStore
from thinking.reflection import ReflectionEngine

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class LATSNode:
    """LATS tree node representing a reasoning step."""
    
    node_id: str = field(default_factory=lambda: str(uuid4()))
    content: str = ""
    parent: Optional["LATSNode"] = None
    children: List["LATSNode"] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0
    ucb_score: float = 0.0
    depth: int = 0
    is_terminal: bool = False
    reflection_feedback: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class LATSState:
    """Current state in LATS reasoning process."""
    
    query: str
    current_solution: str = ""
    step_count: int = 0
    max_steps: int = 10
    confidence: float = 0.0
    reflection_history: List[str] = field(default_factory=list)
    

class LATSMCTS:
    """Language Agent Tree Search with Monte Carlo Tree Search."""
    
    def __init__(
        self,     
        working_memory: Optional[WorkingMemory] = None,     
        reflexion_store: Optional[ReflexionStore] = None,     
        reflection_engine: Optional[ReflectionEngine] = None,     
        max_iterations: int = 50,     
        max_depth: int = 8,     
        exploration_constant: float = 1.4,     
        simulation_depth: int = 5,     
        min_visits_expand: int = 3
    , **kwargs):
        """Initialize LATS-MCTS engine."""
        self.working_memory = working_memory or WorkingMemory()
        self.reflexion_store = reflexion_store or ReflexionStore()
        self.reflection_engine = reflection_engine or ReflectionEngine()
        
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.exploration_constant = exploration_constant
        self.simulation_depth = simulation_depth
        self.min_visits_expand = min_visits_expand
        
        self.root: Optional[LATSNode] = None
        self.iteration_count = 0
        
    async def search(self, query: str, initial_context: str = "", **kwargs) -> Tuple[str, float]:
        """Execute LATS search to find optimal reasoning path."""
        logger.info(f"Starting LATS search for query: {query}")
        
        # Initialize root node
        self.root = LATSNode(
            content=f"Query: {query}\nContext: {initial_context}",
            depth=0
        )
        
        state = LATSState(query=query)
        
        # MCTS iterations
        for self.iteration_count in range(self.max_iterations):
            logger.debug(f"LATS iteration {self.iteration_count + 1}/{self.max_iterations}")
            
            # SELECT: Traverse tree using UCB1
            selected_node = await self._select(self.root)
            
            # EXPAND: Add new child nodes
            expanded_node = await self._expand(selected_node, state)
            
            # SIMULATE: Rollout from expanded node
            simulation_result = await self._simulate(expanded_node, state)
            
            # REFLECT: Get reflection feedback
            reflection_feedback = await self._reflect(expanded_node, simulation_result, state)
            expanded_node.reflection_feedback = reflection_feedback
            
            # BACKPROPAGATE: Update node values
            await self._backpropagate(expanded_node, simulation_result, reflection_feedback)
            
            # Check for early termination
            if self._should_terminate(state):
                break
        
        # Extract best solution path
        best_path = self._extract_best_path()
        confidence = self._calculate_confidence()
        
        logger.info(f"LATS search completed after {self.iteration_count + 1} iterations")
        return best_path, confidence
    
    async def _select(self, node: LATSNode) -> LATSNode:
        """SELECT phase: Traverse tree using UCB1 until leaf node."""
        current = node
        
        while current.children and not current.is_terminal:
            # Calculate UCB1 scores for all children
            for child in current.children:
                child.ucb_score = self._calculate_ucb1(child, current.visits)
            
            # Select child with highest UCB1 score
            current = max(current.children, key=lambda c: c.ucb_score)
            
        return current
    
    async def _expand(self, node: LATSNode, state: LATSState) -> LATSNode:
        """EXPAND phase: Generate new reasoning steps from current node."""
        if node.visits < self.min_visits_expand or node.depth >= self.max_depth:
            return node
            
        # Generate expansion prompts
        expansion_prompts = await self._generate_expansion_prompts(node, state)
        
        for prompt in expansion_prompts:
            child_content = await self._generate_reasoning_step(prompt, node, state)
            
            child = LATSNode(
                content=child_content,
                parent=node,
                depth=node.depth + 1,
                is_terminal=self._is_terminal_state(child_content, state)
            )
            
            node.children.append(child)
        
        # Return first new child for simulation
        return node.children[0] if node.children else node
    
    async def _simulate(self, node: LATSNode, state: LATSState) -> Dict[str, Any]:
        """SIMULATE phase: Rollout reasoning path to estimate value."""
        simulation_state = LATSState(
            query=state.query,
            current_solution=node.content,
            step_count=node.depth,
            max_steps=min(node.depth + self.simulation_depth, self.max_depth),
            confidence=0.0
        )
        
        current_content = node.content
        
        # Simulate reasoning steps
        for _ in range(self.simulation_depth):
            if simulation_state.step_count >= simulation_state.max_steps:
                break
                
            next_step = await self._simulate_step(current_content, simulation_state)
            current_content += f"\n{next_step}"
            simulation_state.current_solution = current_content
            simulation_state.step_count += 1
            
            if self._is_terminal_state(current_content, simulation_state):
                break
        
        # Evaluate simulation result
        result = await self._evaluate_simulation(current_content, simulation_state)
        return result
    
    async def _reflect(
        self, 
        node: LATSNode, 
        simulation_result: Dict[str, Any], 
        state: LATSState
    ) -> str:
        """REFLECT phase: Generate reflection feedback on reasoning quality."""
        reflection_prompt = f"""
        Analyze this reasoning step and simulation result:
        
        Reasoning Step: {node.content}
        Simulation Result: {simulation_result.get('solution', 'N/A')}
        Simulation Score: {simulation_result.get('score', 0.0)}
        
        Provide brief feedback on:
        1. Logical consistency
        2. Problem-solving progress
        3. Potential improvements
        
        Feedback:
        """
        
        feedback = await self.reflection_engine.reflect(
            reflection_prompt,
            context={"node": node, "simulation": simulation_result, "state": state}
        )
        
        # Store reflection in memory
        await self.reflexion_store.store_reflection(
            query=state.query,
            reasoning=node.content,
            feedback=feedback,
            score=simulation_result.get('score', 0.0)
        )
        
        return feedback
    
    async def _backpropagate(
        self, 
        node: LATSNode, 
        simulation_result: Dict[str, Any],
        reflection_feedback: str
    ) -> None:
        """BACKPROPAGATE phase: Update node values up the tree."""
        current = node
        result_score = simulation_result.get('score', 0.0)
        
        # Apply reflection feedback to score adjustment
        feedback_adjustment = self._parse_reflection_score(reflection_feedback)
        adjusted_score = result_score * (1.0 + feedback_adjustment)
        
        while current is not None:
            current.visits += 1
            current.value += adjusted_score
            current = current.parent
    
    def _calculate_ucb1(self, node: LATSNode, parent_visits: int) -> float:
        """Calculate UCB1 score for node selection."""
        if node.visits == 0:
            return float('inf')
        
        exploitation = node.value / node.visits
        exploration = self.exploration_constant * math.sqrt(
            math.log(parent_visits) / node.visits
        )
        
        return exploitation + exploration
    
    async def _generate_expansion_prompts(
        self, 
        node: LATSNode, 
        state: LATSState
    ) -> List[str]:
        """Generate prompts for expanding reasoning from current node."""
        prompts = [
            f"Continue reasoning from: {node.content}\nNext logical step:",
            f"Alternative approach to: {node.content}\nDifferent perspective:",
            f"Verify and refine: {node.content}\nCheck assumptions:"
        ]
        
        return prompts[:2]  # Limit expansion branching
    
    async def _generate_reasoning_step(
        self, 
        prompt: str, 
        parent: LATSNode, 
        state: LATSState
    ) -> str:
        """Generate a single reasoning step from prompt."""
        context = {
            "query": state.query,
            "parent_reasoning": parent.content,
            "depth": parent.depth + 1,
            "max_depth": self.max_depth
        }
        
        # Use working memory to generate step
        reasoning_step = await self.working_memory.process(
            prompt, 
            context=context,
            max_length=200
        )
        
        return reasoning_step.get('response', f"Step {parent.depth + 1}: Continue reasoning...")
    
    async def _simulate_step(self, current_content: str, state: LATSState) -> str:
        """Simulate a single reasoning step during rollout."""
        prompt = f"Continue this reasoning: {current_content}\nNext step:"
        
        result = await self.working_memory.process(
            prompt,
            context={"simulation": True, "step": state.step_count},
            max_length=100
        )
        
        return result.get('response', f"Simulation step {state.step_count}")
    
    async def _evaluate_simulation(
        self, 
        content: str, 
        state: LATSState
    ) -> Dict[str, Any]:
        """Evaluate the quality of a simulated reasoning path."""
        evaluation_prompt = f"""
        Evaluate this reasoning for the query: {state.query}
        
        Reasoning: {content}
        
        Score (0.0-1.0) based on:
        - Logical consistency
        - Progress toward solution
        - Clarity and coherence
        
        Score: """
        
        eval_result = await self.working_memory.process(
            evaluation_prompt,
            context={"evaluation": True},
            max_length=50
        )
        
        # Parse score from response
        score_text = eval_result.get('response', '0.5')
        try:
            score = float(score_text.split()[-1])
            score = max(0.0, min(1.0, score))  # Clamp to [0,1]
        except (ValueError, IndexError):
            score = 0.5  # Default score
        
        return {
            'solution': content,
            'score': score,
            'evaluation': eval_result.get('response', ''),
            'step_count': state.step_count
        }
    
    def _is_terminal_state(self, content: str, state: LATSState) -> bool:
        """Check if reasoning has reached a terminal state."""
        # Check for solution indicators
        solution_keywords = ['therefore', 'conclusion', 'answer is', 'result is', 'solution:']
        content_lower = content.lower()
        
        has_solution = any(keyword in content_lower for keyword in solution_keywords)
        at_max_depth = state.step_count >= state.max_steps
        
        return has_solution or at_max_depth
    
    def _parse_reflection_score(self, feedback: str) -> float:
        """Parse reflection feedback for score adjustment."""
        feedback_lower = feedback.lower()
        
        # Positive indicators
        positive_words = ['good', 'correct', 'logical', 'clear', 'excellent', 'sound']
        negative_words = ['wrong', 'unclear', 'inconsistent', 'flawed', 'poor']
        
        positive_count = sum(1 for word in positive_words if word in feedback_lower)
        negative_count = sum(1 for word in negative_words if word in feedback_lower)
        
        # Calculate adjustment (-0.2 to +0.2)
        adjustment = (positive_count - negative_count) * 0.1
        return max(-0.2, min(0.2, adjustment))
    
    def _should_terminate(self, state: LATSState) -> bool:
        """Check if search should terminate early."""
        if not self.root or not self.root.children:
            return False
            
        # Check if best solution is confident enough
        best_child = max(self.root.children, key=lambda c: c.value / max(c.visits, 1))
        best_confidence = best_child.value / max(best_child.visits, 1)
        
        return best_confidence > 0.9 and best_child.visits > 5
    
    def _extract_best_path(self) -> str:
        """Extract the best reasoning path from the tree."""
        if not self.root:
            return "No solution found"
        
        path_parts = [self.root.content]
        current = self.root
        
        # Follow path of highest-value nodes
        while current.children:
            best_child = max(current.children, key=lambda c: c.value / max(c.visits, 1))
            path_parts.append(best_child.content)
            current = best_child
        
        return "\n".join(path_parts)
    
    def _calculate_confidence(self) -> float:
        """Calculate confidence in the best solution."""
        if not self.root or not self.root.children:
            return 0.0
        
        best_child = max(self.root.children, key=lambda c: c.value / max(c.visits, 1))
        confidence = best_child.value / max(best_child.visits, 1)
        
        # Adjust based on number of iterations and visits
        iteration_factor = min(1.0, self.iteration_count / self.max_iterations)
        visit_factor = min(1.0, best_child.visits / 10)
        
        return confidence * iteration_factor * visit_factor
    
    def get_tree_stats(self) -> Dict[str, Any]:
        """Get statistics about the search tree."""
        if not self.root:
            return {}
        
        def count_nodes(node: LATSNode) -> int:
            return 1 + sum(count_nodes(child) for child in node.children)
        
        total_nodes = count_nodes(self.root)
        max_depth = self._get_max_depth(self.root)
        total_visits = sum(self._get_total_visits(self.root))
        
        return {
            'total_nodes': total_nodes,
            'max_depth': max_depth,
            'total_visits': total_visits,
            'iterations': self.iteration_count,
            'root_children': len(self.root.children)
        }
    
    def _get_max_depth(self, node: LATSNode) -> int:
        """Get maximum depth of tree rooted at node."""
        if not node.children:
            return node.depth
        return max(self._get_max_depth(child) for child in node.children)
    
    def _get_total_visits(self, node: LATSNode) -> int:
        """Get total visits for subtree rooted at node."""
        return node.visits + sum(self._get_total_visits(child) for child in node.children)
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        self.root = None
        self.iteration_count = 0
        logger.info("LATS-MCTS cleanup completed")

LATSMCTSPattern = LATSMCTS  # auto-alias

LATS_MCTS = LATSMCTS  # auto-alias
IndexError = type('IndexError', (), {})  # auto-stub: not found in project
