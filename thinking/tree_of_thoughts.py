"""Tree of Thoughts implementation for physics reasoning."""

import asyncio
import json
import logging
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from config.errors import handle_error
from config.logger import get_logger
from config.settings import get_settings


class SearchStrategy(Enum):
    """Search strategies for tree traversal."""
    BFS = "breadth_first"
    DFS = "depth_first"
    BEST_FIRST = "best_first"


class ThoughtState(Enum):
    """States for thought nodes."""
    PENDING = "pending"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    PRUNED = "pruned"
    EXPANDED = "expanded"
    TERMINAL = "terminal"


@dataclass
class ThoughtNode:
    """A node in the thought tree."""
    id: str
    content: str
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    depth: int = 0
    state: ThoughtState = ThoughtState.PENDING
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    physics_context: Optional[Dict[str, Any]] = None
    reasoning_path: List[str] = field(default_factory=list)
    confidence: float = 0.0
    validation_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TreeMetrics:
    """Metrics for tree evaluation."""
    total_nodes: int = 0
    max_depth: int = 0
    avg_branching_factor: float = 0.0
    best_score: float = 0.0
    terminal_nodes: int = 0
    pruned_nodes: int = 0
    exploration_time: float = 0.0


class ThoughtEvaluator(ABC):
    """Abstract base class for thought evaluation."""

    async def evaluate(self, thought: str, context: Dict[str, Any]) -> float:
        """Evaluate a thought and return a score."""
        pass

    async def is_terminal(self, thought: str, context: Dict[str, Any]) -> bool:
        """Check if a thought represents a terminal state."""
        pass


class PhysicsThoughtEvaluator(ThoughtEvaluator):
    """Physics-specific thought evaluator."""

    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.settings = get_settings()

    async def evaluate(self, thought: str, context: Dict[str, Any]) -> float:
        """Evaluate physics reasoning quality."""
        try:
            score = 0.0
            
            # Physics principles coherence
            if self._has_physics_principles(thought):
                score += 0.3
            
            # Mathematical rigor
            if self._has_mathematical_content(thought):
                score += 0.2
            
            # Dimensional consistency
            if self._check_dimensional_consistency(thought):
                score += 0.2
            
            # Literature connection
            if self._has_literature_references(thought, context):
                score += 0.1
            
            # Experimental testability
            if self._is_experimentally_testable(thought):
                score += 0.2
            
            return min(score, 1.0)
            
        except Exception as e:
            handle_error(e)
            return 0.0

    async def is_terminal(self, thought: str, context: Dict[str, Any]) -> bool:
        """Check if thought represents a complete physics solution."""
        try:
            # Check for conclusion indicators
            conclusion_markers = [
                "therefore", "thus", "in conclusion", "we conclude",
                "final result", "solution is", "answer is"
            ]
            
            has_conclusion = any(marker in thought.lower() for marker in conclusion_markers)
            
            # Check for completeness
            has_equation = self._has_mathematical_content(thought)
            has_validation = "validate" in thought.lower() or "verify" in thought.lower()
            
            return has_conclusion and (has_equation or has_validation)
            
        except Exception as e:
            handle_error(e)
            return False

    def _has_physics_principles(self, thought: str) -> bool:
        """Check for physics principles in thought."""
        physics_terms = [
            "conservation", "symmetry", "invariance", "relativity",
            "quantum", "thermodynamics", "mechanics", "electromagnetic",
            "field", "energy", "momentum", "force", "wave"
        ]
        return any(term in thought.lower() for term in physics_terms)

    def _has_mathematical_content(self, thought: str) -> bool:
        """Check for mathematical expressions."""
        math_indicators = ["=", "∇", "∂", "∫", "∑", "√", "±", "≈", "∝"]
        return any(indicator in thought for indicator in math_indicators)

    def _check_dimensional_consistency(self, thought: str) -> bool:
        """Basic dimensional consistency check."""
        # Simplified check for common dimensional errors
        if "[" in thought and "]" in thought:
            return True  # Has dimensional analysis
        return False

    def _has_literature_references(self, thought: str, context: Dict[str, Any]) -> bool:
        """Check for literature connections."""
        ref_indicators = ["ref", "citation", "paper", "study", "research"]
        return any(indicator in thought.lower() for indicator in ref_indicators)

    def _is_experimentally_testable(self, thought: str) -> bool:
        """Check if thought suggests experimental validation."""
        test_indicators = [
            "experiment", "test", "measure", "observe", "detect",
            "verify", "validate", "confirm", "measurement"
        ]
        return any(indicator in thought.lower() for indicator in test_indicators)


class ThoughtGenerator:
    """Generates thought branches for physics problems."""

    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.settings = get_settings()

    async def generate_thoughts(
        self,
        current_thought: str,
        context: Dict[str, Any],
        num_thoughts: int = 3
    ) -> List[str]:
        """Generate N thought branches from current thought."""
        try:
            thoughts = []
            
            # Generate different reasoning approaches
            approaches = [
                self._generate_first_principles_approach,
                self._generate_analogical_approach,
                self._generate_mathematical_approach,
                self._generate_experimental_approach,
                self._generate_literature_based_approach
            ]
            
            for i in range(min(num_thoughts, len(approaches))):
                approach = approaches[i]
                thought = await approach(current_thought, context)
                if thought and thought not in thoughts:
                    thoughts.append(thought)
            
            # Fill remaining slots with variations
            while len(thoughts) < num_thoughts:
                variation = await self._generate_variation(current_thought, context)
                if variation and variation not in thoughts:
                    thoughts.append(variation)
                else:
                    break
            
            return thoughts[:num_thoughts]
            
        except Exception as e:
            handle_error(e)
            return []

    async def _generate_first_principles_approach(
        self, current_thought: str, context: Dict[str, Any]
    ) -> str:
        """Generate first principles reasoning."""
        return f"From first principles: Let's derive this by considering the fundamental laws governing {current_thought}"

    async def _generate_analogical_approach(
        self, current_thought: str, context: Dict[str, Any]
    ) -> str:
        """Generate analogical reasoning."""
        return f"By analogy: This situation is similar to known physics phenomena, specifically {current_thought}"

    async def _generate_mathematical_approach(
        self, current_thought: str, context: Dict[str, Any]
    ) -> str:
        """Generate mathematical reasoning."""
        return f"Mathematical formulation: Express {current_thought} in terms of equations and solve systematically"

    async def _generate_experimental_approach(
        self, current_thought: str, context: Dict[str, Any]
    ) -> str:
        """Generate experimental reasoning."""
        return f"Experimental validation: Design experiments to test the hypothesis that {current_thought}"

    async def _generate_literature_based_approach(
        self, current_thought: str, context: Dict[str, Any]
    ) -> str:
        """Generate literature-based reasoning."""
        return f"Literature review: Examine existing research related to {current_thought} for insights"

    async def _generate_variation(
        self, current_thought: str, context: Dict[str, Any]
    ) -> str:
        """Generate a variation of current thought."""
        variations = [
            f"Alternative perspective: {current_thought}",
            f"Extended analysis: {current_thought}",
            f"Deeper investigation: {current_thought}"
        ]
        return variations[len(context.get('generated_thoughts', [])) % len(variations)]


class TreeOfThoughts:
    """Tree of Thoughts reasoning system for physics problems."""

    def __init__(
        self,     
        evaluator: Optional[ThoughtEvaluator] = None,     
        generator: Optional[ThoughtGenerator] = None,     
        max_depth: int = 5,     
        max_nodes: int = 100,     
        branch_factor: int = 3,     
        search_strategy: SearchStrategy = SearchStrategy.BEST_FIRST
    , **kwargs):
        self.logger = get_logger(__name__)
        self.settings = get_settings()
        
        self.evaluator = evaluator or PhysicsThoughtEvaluator()
        self.generator = generator or ThoughtGenerator()
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.branch_factor = branch_factor
        self.search_strategy = search_strategy
        
        self.nodes: Dict[str, ThoughtNode] = {}
        self.root_id: Optional[str] = None
        self.best_path: List[str] = []
        self.metrics = TreeMetrics()
        
        self._node_counter = 0

    async def reason(
        self,
        problem: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Main reasoning method using Tree of Thoughts."""
        try:
            context = context or {}
            start_time = asyncio.get_event_loop().time()
            
            # Initialize root
            await self._initialize_tree(problem, context)
            
            # Search based on strategy
            if self.search_strategy == SearchStrategy.BFS:
                await self._breadth_first_search(context)
            elif self.search_strategy == SearchStrategy.DFS:
                await self._depth_first_search(context)
            else:
                await self._best_first_search(context)
            
            # Update metrics
            self.metrics.exploration_time = asyncio.get_event_loop().time() - start_time
            self._update_metrics()
            
            # Extract best solution
            best_solution = await self._extract_best_solution()
            
            return {
                "solution": best_solution,
                "reasoning_path": self.best_path,
                "metrics": self.metrics,
                "tree_structure": self._serialize_tree(),
                "confidence": self._calculate_confidence()
            }
            
        except Exception as e:
            handle_error(e)
            return {"error": str(e), "solution": None}

    async def _initialize_tree(self, problem: str, context: Dict[str, Any]) -> None:
        """Initialize the reasoning tree with root problem."""
        root_id = self._generate_node_id()
        
        root_node = ThoughtNode(
            id=root_id,
            content=problem,
            depth=0,
            physics_context=context.get('physics_context'),
            reasoning_path=[problem]
        )
        
        self.nodes[root_id] = root_node
        self.root_id = root_id
        
        # Initial evaluation
        score = await self.evaluator.evaluate(problem, context)
        root_node.score = score
        root_node.state = ThoughtState.EVALUATED

    async def _breadth_first_search(self, context: Dict[str, Any]) -> None:
        """Breadth-first search through thought space."""
        queue = [self.root_id] if self.root_id else []
        visited = set()
        
        while queue and len(self.nodes) < self.max_nodes:
            current_id = queue.pop(0)
            
            if current_id in visited:
                continue
                
            visited.add(current_id)
            current_node = self.nodes[current_id]
            
            # Skip if terminal or max depth reached
            if current_node.depth >= self.max_depth:
                current_node.state = ThoughtState.TERMINAL
                continue
                
            if await self.evaluator.is_terminal(current_node.content, context):
                current_node.state = ThoughtState.TERMINAL
                continue
            
            # Expand node
            await self._expand_node(current_id, context)
            
            # Add children to queue
            queue.extend(current_node.children_ids)

    async def _depth_first_search(self, context: Dict[str, Any]) -> None:
        """Depth-first search through thought space."""
        if not self.root_id:
            return
            
        await self._dfs_recursive(self.root_id, context, set())

    async def _dfs_recursive(
        self, node_id: str, context: Dict[str, Any], visited: Set[str]
    ) -> None:
        """Recursive DFS implementation."""
        if node_id in visited or len(self.nodes) >= self.max_nodes:
            return
            
        visited.add(node_id)
        node = self.nodes[node_id]
        
        # Check termination conditions
        if node.depth >= self.max_depth:
            node.state = ThoughtState.TERMINAL
            return
            
        if await self.evaluator.is_terminal(node.content, context):
            node.state = ThoughtState.TERMINAL
            return
        
        # Expand and recurse
        await self._expand_node(node_id, context)
        
        for child_id in node.children_ids:
            await self._dfs_recursive(child_id, context, visited)

    async def _best_first_search(self, context: Dict[str, Any]) -> None:
        """Best-first search prioritizing highest-scoring thoughts."""
        import heapq
        
        # Priority queue: (-score, node_id) for max-heap behavior
        pq = [(-self.nodes[self.root_id].score, self.root_id)] if self.root_id else []
        visited = set()
        
        while pq and len(self.nodes) < self.max_nodes:
            neg_score, current_id = heapq.heappop(pq)
            
            if current_id in visited:
                continue
                
            visited.add(current_id)
            current_node = self.nodes[current_id]
            
            # Check termination
            if current_node.depth >= self.max_depth:
                current_node.state = ThoughtState.TERMINAL
                continue
                
            if await self.evaluator.is_terminal(current_node.content, context):
                current_node.state = ThoughtState.TERMINAL
                continue
            
            # Expand and add children to priority queue
            await self._expand_node(current_id, context)
            
            for child_id in current_node.children_ids:
                child_score = self.nodes[child_id].score
                heapq.heappush(pq, (-child_score, child_id))

    async def _expand_node(self, node_id: str, context: Dict[str, Any]) -> None:
        """Expand a node by generating and evaluating children."""
        node = self.nodes[node_id]
        
        if node.state == ThoughtState.EXPANDED:
            return
        
        node.state = ThoughtState.EVALUATING
        
        # Generate child thoughts
        thoughts = await self.generator.generate_thoughts(
            node.content, context, self.branch_factor
        )
        
        # Create child nodes
        for thought in thoughts:
            child_id = self._generate_node_id()
            
            child_node = ThoughtNode(
                id=child_id,
                content=thought,
                parent_id=node_id,
                depth=node.depth + 1,
                physics_context=node.physics_context,
                reasoning_path=node.reasoning_path + [thought]
            )
            
            # Evaluate child
            score = await self.evaluator.evaluate(thought, context)
            child_node.score = score
            child_node.state = ThoughtState.EVALUATED
            
            # Store child
            self.nodes[child_id] = child_node
            node.children_ids.append(child_id)
        
        node.state = ThoughtState.EXPANDED

    async def _extract_best_solution(self) -> Optional[str]:
        """Extract the best solution from the tree."""
        try:
            best_node = None
            best_score = -float('inf')
            
            # Find highest-scoring terminal node
            for node in self.nodes.values():
                if node.state == ThoughtState.TERMINAL and node.score > best_score:
                    best_score = node.score
                    best_node = node
            
            # If no terminal nodes, find highest-scoring node
            if not best_node:
                for node in self.nodes.values():
                    if node.score > best_score:
                        best_score = node.score
                        best_node = node
            
            if best_node:
                self.best_path = best_node.reasoning_path
                return best_node.content
            
            return None
            
        except Exception as e:
            handle_error(e)
            return None

    def _update_metrics(self) -> None:
        """Update tree metrics."""
        self.metrics.total_nodes = len(self.nodes)
        self.metrics.max_depth = max((node.depth for node in self.nodes.values()), default=0)
        self.metrics.best_score = max((node.score for node in self.nodes.values()), default=0.0)
        
        # Calculate branching factor
        non_terminal = [node for node in self.nodes.values() 
                       if node.state != ThoughtState.TERMINAL]
        if non_terminal:
            total_children = sum(len(node.children_ids) for node in non_terminal)
            self.metrics.avg_branching_factor = total_children / len(non_terminal)
        
        # Count terminal and pruned nodes
        self.metrics.terminal_nodes = sum(
            1 for node in self.nodes.values() 
            if node.state == ThoughtState.TERMINAL
        )
        self.metrics.pruned_nodes = sum(
            1 for node in self.nodes.values() 
            if node.state == ThoughtState.PRUNED
        )

    def _serialize_tree(self) -> Dict[str, Any]:
        """Serialize tree structure for analysis."""
        return {
            "nodes": {
                node_id: {
                    "content": node.content[:100] + "..." if len(node.content) > 100 else node.content,
                    "parent_id": node.parent_id,
                    "children_ids": node.children_ids,
                    "depth": node.depth,
                    "score": node.score,
                    "state": node.state.value
                }
                for node_id, node in self.nodes.items()
            },
            "root_id": self.root_id,
            "metrics": {
                "total_nodes": self.metrics.total_nodes,
                "max_depth": self.metrics.max_depth,
                "avg_branching_factor": self.metrics.avg_branching_factor,
                "best_score": self.metrics.best_score
            }
        }

    def _calculate_confidence(self) -> float:
        """Calculate confidence in the best solution."""
        if not self.nodes:
            return 0.0
        
        scores = [node.score for node in self.nodes.values()]
        if not scores:
            return 0.0
        
        best_score = max(scores)
        avg_score = sum(scores) / len(scores)
        
        # Confidence based on score gap and tree completeness
        score_confidence = best_score
        completeness = min(len(self.nodes) / self.max_nodes, 1.0)
        
        return (score_confidence + completeness) / 2.0

    def _generate_node_id(self) -> str:
        """Generate unique node ID."""
        self._node_counter += 1
        return f"thought_{self._node_counter}"

    async def prune_low_scoring_branches(self, threshold: float = 0.3) -> None:
        """Prune branches with scores below threshold."""
        try:
            to_prune = []
            
            for node_id, node in self.nodes.items():
                if node.score < threshold and node.id != self.root_id:
                    to_prune.append(node_id)
            
            for node_id in to_prune:
                await self._prune_subtree(node_id)
                
        except Exception as e:
            handle_error(e)

    async def _prune_subtree(self, node_id: str) -> None:
        """Recursively prune a subtree."""
        if node_id not in self.nodes:
            return
        
        node = self.nodes[node_id]
        node.state = ThoughtState.PRUNED
        
        # Prune children
        for child_id in node.children_ids:
            await self._prune_subtree(child_id)
        
        # Remove from parent's children
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node_id in parent.children_ids:
                parent.children_ids.remove(node_id)

    async def get_reasoning_trace(self) -> List[Dict[str, Any]]:
        """Get detailed reasoning trace for the best path."""
        try:
            if not self.best_path:
                return []
            
            trace = []
            for i, step in enumerate(self.best_path):
                trace.append({
                    "step": i + 1,
                    "thought": step,
                    "depth": i,
                    "timestamp": asyncio.get_event_loop().time()
                })
            
            return trace
            
        except Exception as e:
            handle_error(e)
            return []

    async def explore(self, *args, **kwargs):
        return dict()

    async def explore_alternatives(self, *args, **kwargs):
        return dict()

    async def explore_thoughts(self, *args, **kwargs):
        return dict()

TreeOfThoughtsPattern = TreeOfThoughts  # auto-alias
TreeOfThoughtsEngine = TreeOfThoughts  # auto-alias by repair.py

BEST_FIRST = type('BEST_FIRST', (), {})  # auto-stub: not found in project

BFS = type('BFS', (), {})  # auto-stub: not found in project

DFS = type('DFS', (), {})  # auto-stub: not found in project

EVALUATED = type('EVALUATED', (), {})  # auto-stub: not found in project

EVALUATING = type('EVALUATING', (), {})  # auto-stub: not found in project

EXPANDED = type('EXPANDED', (), {})  # auto-stub: not found in project

PENDING = type('PENDING', (), {})  # auto-stub: not found in project

PRUNED = type('PRUNED', (), {})  # auto-stub: not found in project

TERMINAL = type('TERMINAL', (), {})  # auto-stub: not found in project
