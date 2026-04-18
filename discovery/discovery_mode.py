"""Discovery Mode Engine - Abductive reasoning for hypothesis evolution."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent
from agents.math_agent import MathAgent
from agents.research_agent import ResearchAgent
from agents.theory_architect import TheoryArchitect
from agents.peer_review import PeerReviewAgent
from physics.hypothesis import HypothesisGenerator, Hypothesis
from physics.first_principles import FirstPrinciplesEngine
from physics.sympy_engine import SympyEngine
from physics.theory_validator import TheoryValidator
from physics.contradictions import ContradictionDetector
from discovery.hypothesis_tracker import HypothesisTracker
from discovery.evidence_search import EvidenceSearchEngine
from memory.working import WorkingMemory
from thinking.tree_of_thoughts import TreeOfThoughts
from thinking.lats_mcts import LATS_MCTS


class DiscoveryPhase(Enum):
    """Discovery process phases."""
    GENESIS = "genesis"
    SCAFFOLDING = "scaffolding"
    SEARCH = "search"
    EVOLUTION = "evolution"
    SYNTHESIS = "synthesis"


@dataclass
class HypothesisNode:
    """Node in hypothesis evolution tree."""
    id: str
    hypothesis: Hypothesis
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    support_evidence: List[Dict[str, Any]] = field(default_factory=list)
    challenge_evidence: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    mathematical_scaffolding: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class DiscoverySession:
    """Complete discovery session state."""
    session_id: str
    query: str
    phase: DiscoveryPhase = DiscoveryPhase.GENESIS
    hypothesis_tree: Dict[str, HypothesisNode] = field(default_factory=dict)
    root_hypotheses: List[str] = field(default_factory=list)
    active_nodes: List[str] = field(default_factory=list)
    evidence_cache: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    search_history: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class DiscoveryMode:
    """Abductive reasoning engine for hypothesis generation and evolution."""
    
    def __init__(self, **kwargs):
        """Initialize discovery mode engine."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        
        # Core components
        self.hypothesis_generator = HypothesisGenerator()
        self.hypothesis_tracker = HypothesisTracker()
        self.evidence_search = EvidenceSearchEngine()
        self.working_memory = WorkingMemory()
        
        # Physics engines
        self.first_principles = FirstPrinciplesEngine()
        self.sympy_engine = SympyEngine()
        self.theory_validator = TheoryValidator()
        self.contradiction_detector = ContradictionDetector()
        
        # Reasoning systems
        self.tree_of_thoughts = TreeOfThoughts()
        self.lats_mcts = LATS_MCTS()
        
        # Agents
        self.math_agent = MathAgent()
        self.research_agent = ResearchAgent()
        self.theory_architect = TheoryArchitect()
        self.peer_review_agent = PeerReviewAgent()
        
        # Session management
        self.active_sessions: Dict[str, DiscoverySession] = {}
        self.session_timeout = timedelta(hours=6)
        
    async def start_discovery(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Start new discovery session with abductive reasoning."""
        session_id = str(uuid.uuid4())
        
        try:
            session = DiscoverySession(
                session_id=session_id,
                query=query
            )
            
            self.active_sessions[session_id] = session
            
            # Initialize working memory with context
            if context:
                await self.working_memory.store_context(session_id, context)
            
            self.logger.info(f"Started discovery session {session_id} for query: {query}")
            
            # Begin hypothesis genesis phase
            await self._run_genesis_phase(session)
            
            return session_id
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Failed to start discovery session: {e}")
            raise
    
    async def _run_genesis_phase(self, session: DiscoverySession) -> None:
        """Generate initial hypotheses through abductive reasoning."""
        session.phase = DiscoveryPhase.GENESIS
        
        try:
            # Generate multiple initial hypotheses
            hypotheses = await self.hypothesis_generator.generate_hypotheses(
                query=session.query,
                num_hypotheses=5,
                reasoning_mode="abductive"
            )
            
            # Create root nodes in hypothesis tree
            for hypothesis in hypotheses:
                node_id = str(uuid.uuid4())
                node = HypothesisNode(
                    id=node_id,
                    hypothesis=hypothesis,
                    confidence_score=hypothesis.initial_confidence
                )
                
                session.hypothesis_tree[node_id] = node
                session.root_hypotheses.append(node_id)
                session.active_nodes.append(node_id)
            
            session.updated_at = datetime.now()
            
            # Proceed to mathematical scaffolding
            await self._run_scaffolding_phase(session)
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Genesis phase failed for session {session.session_id}: {e}")
            raise
    
    async def _run_scaffolding_phase(self, session: DiscoverySession) -> None:
        """Build mathematical scaffolding for each hypothesis."""
        session.phase = DiscoveryPhase.SCAFFOLDING
        
        try:
            scaffolding_tasks = []
            
            for node_id in session.active_nodes:
                node = session.hypothesis_tree[node_id]
                task = self._create_mathematical_scaffolding(node)
                scaffolding_tasks.append(task)
            
            # Execute scaffolding in parallel
            scaffolding_results = await asyncio.gather(*scaffolding_tasks, return_exceptions=True)
            
            # Update nodes with scaffolding
            for i, result in enumerate(scaffolding_results):
                if not isinstance(result, Exception):
                    node_id = session.active_nodes[i]
                    session.hypothesis_tree[node_id].mathematical_scaffolding = result
            
            session.updated_at = datetime.now()
            
            # Proceed to parallel search phase
            await self._run_search_phase(session)
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Scaffolding phase failed for session {session.session_id}: {e}")
            raise
    
    async def _create_mathematical_scaffolding(self, node: HypothesisNode) -> Dict[str, Any]:
        """Create mathematical framework for hypothesis."""
        hypothesis = node.hypothesis
        
        # Generate mathematical expressions
        expressions = await self.sympy_engine.generate_expressions(
            hypothesis.statement,
            hypothesis.variables
        )
        
        # Check dimensional consistency
        dimensional_analysis = await self.first_principles.analyze_dimensions(
            expressions
        )
        
        # Create theory structure
        theory_structure = await self.theory_architect.build_theory_framework(
            hypothesis.statement,
            expressions
        )
        
        return {
            "expressions": expressions,
            "dimensional_analysis": dimensional_analysis,
            "theory_structure": theory_structure,
            "mathematical_validity": dimensional_analysis.get("valid", False)
        }
    
    async def _run_search_phase(self, session: DiscoverySession) -> None:
        """Parallel support and challenge evidence search."""
        session.phase = DiscoveryPhase.SEARCH
        
        try:
            search_tasks = []
            
            for node_id in session.active_nodes:
                node = session.hypothesis_tree[node_id]
                
                # Search for supporting evidence
                support_task = self._search_supporting_evidence(node)
                # Search for challenging evidence  
                challenge_task = self._search_challenging_evidence(node)
                
                search_tasks.extend([support_task, challenge_task])
            
            # Execute searches in parallel
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Update nodes with evidence
            await self._update_nodes_with_evidence(session, search_results)
            
            session.updated_at = datetime.now()
            
            # Proceed to evolution phase
            await self._run_evolution_phase(session)
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Search phase failed for session {session.session_id}: {e}")
            raise
    
    async def _search_supporting_evidence(self, node: HypothesisNode) -> Tuple[str, List[Dict[str, Any]]]:
        """Search for evidence supporting the hypothesis."""
        evidence = await self.evidence_search.search_supporting_evidence(
            hypothesis=node.hypothesis,
            max_results=10
        )
        return (node.id, evidence)
    
    async def _search_challenging_evidence(self, node: HypothesisNode) -> Tuple[str, List[Dict[str, Any]]]:
        """Search for evidence challenging the hypothesis."""
        evidence = await self.evidence_search.search_contradicting_evidence(
            hypothesis=node.hypothesis,
            max_results=10
        )
        return (node.id, evidence)
    
    async def _update_nodes_with_evidence(self, session: DiscoverySession, search_results: List[Any]) -> None:
        """Update hypothesis nodes with search evidence."""
        for i in range(0, len(search_results), 2):
            if i + 1 < len(search_results):
                support_result = search_results[i]
                challenge_result = search_results[i + 1]
                
                if not isinstance(support_result, Exception):
                    node_id, evidence = support_result
                    if node_id in session.hypothesis_tree:
                        session.hypothesis_tree[node_id].support_evidence.extend(evidence)
                
                if not isinstance(challenge_result, Exception):
                    node_id, evidence = challenge_result
                    if node_id in session.hypothesis_tree:
                        session.hypothesis_tree[node_id].challenge_evidence.extend(evidence)
    
    async def _run_evolution_phase(self, session: DiscoverySession) -> None:
        """Evolve hypotheses based on evidence and reasoning."""
        session.phase = DiscoveryPhase.EVOLUTION
        
        try:
            evolution_tasks = []
            
            for node_id in session.active_nodes.copy():
                node = session.hypothesis_tree[node_id]
                task = self._evolve_hypothesis(session, node)
                evolution_tasks.append(task)
            
            # Execute evolution in parallel
            evolution_results = await asyncio.gather(*evolution_tasks, return_exceptions=True)
            
            # Update session with evolved hypotheses
            new_active_nodes = []
            for result in evolution_results:
                if not isinstance(result, Exception) and result:
                    new_active_nodes.extend(result)
            
            session.active_nodes = new_active_nodes
            session.updated_at = datetime.now()
            
            # Proceed to synthesis if we have viable hypotheses
            if session.active_nodes:
                await self._run_synthesis_phase(session)
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Evolution phase failed for session {session.session_id}: {e}")
            raise
    
    async def _evolve_hypothesis(self, session: DiscoverySession, node: HypothesisNode) -> List[str]:
        """Evolve a single hypothesis based on evidence."""
        # Calculate confidence score
        confidence = await self._calculate_confidence(node)
        node.confidence_score = confidence
        
        # If confidence is very low, prune this branch
        if confidence < 0.2:
            return []
        
        # If confidence is moderate, try to refine
        if 0.2 <= confidence < 0.7:
            refined_hypotheses = await self._refine_hypothesis(node)
            child_nodes = []
            
            for refined_hyp in refined_hypotheses:
                child_id = str(uuid.uuid4())
                child_node = HypothesisNode(
                    id=child_id,
                    hypothesis=refined_hyp,
                    parent_id=node.id,
                    confidence_score=refined_hyp.initial_confidence
                )
                
                session.hypothesis_tree[child_id] = child_node
                node.children_ids.append(child_id)
                child_nodes.append(child_id)
            
            return child_nodes
        
        # If confidence is high, keep exploring this path
        return [node.id]
    
    async def _calculate_confidence(self, node: HypothesisNode) -> float:
        """Calculate confidence score based on evidence and validity."""
        support_weight = len(node.support_evidence) * 0.1
        challenge_weight = len(node.challenge_evidence) * -0.1
        
        math_validity = 0.0
        if node.mathematical_scaffolding:
            math_validity = 0.3 if node.mathematical_scaffolding.get("mathematical_validity", False) else -0.2
        
        base_confidence = node.hypothesis.initial_confidence
        
        return max(0.0, min(1.0, base_confidence + support_weight + challenge_weight + math_validity))
    
    async def _refine_hypothesis(self, node: HypothesisNode) -> List[Hypothesis]:
        """Refine hypothesis based on contradictions and evidence."""
        contradictions = await self.contradiction_detector.find_contradictions(
            node.hypothesis,
            node.challenge_evidence
        )
        
        if contradictions:
            # Generate refined hypotheses that address contradictions
            return await self.hypothesis_generator.refine_hypothesis(
                node.hypothesis,
                contradictions,
                node.support_evidence
            )
        
        return [node.hypothesis]  # Return original if no contradictions
    
    async def _run_synthesis_phase(self, session: DiscoverySession) -> None:
        """Synthesize best hypotheses into coherent theories."""
        session.phase = DiscoveryPhase.SYNTHESIS
        
        try:
            # Get top hypotheses by confidence
            top_nodes = sorted(
                [session.hypothesis_tree[node_id] for node_id in session.active_nodes],
                key=lambda n: n.confidence_score,
                reverse=True
            )[:3]
            
            if not top_nodes:
                self.logger.warning(f"No viable hypotheses for synthesis in session {session.session_id}")
                return
            
            # Synthesize top hypotheses
            synthesis_result = await self.theory_architect.synthesize_theories(
                [node.hypothesis for node in top_nodes]
            )
            
            # Store synthesis insights
            session.insights.append(f"Synthesis result: {synthesis_result}")
            session.updated_at = datetime.now()
            
            self.logger.info(f"Discovery session {session.session_id} synthesis complete")
            
        except Exception as e:
            handle_error(e)
            self.logger.error(f"Synthesis phase failed for session {session.session_id}: {e}")
            raise
    
    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of discovery session."""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Clean up expired sessions
        if datetime.now() - session.updated_at > self.session_timeout:
            del self.active_sessions[session_id]
            return None
        
        return {
            "session_id": session_id,
            "query": session.query,
            "phase": session.phase.value,
            "num_hypotheses": len(session.hypothesis_tree),
            "active_nodes": len(session.active_nodes),
            "insights": session.insights,
            "started_at": session.started_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
    
    async def get_hypothesis_tree(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get complete hypothesis evolution tree."""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Convert tree to serializable format
        tree_data = {}
        for node_id, node in session.hypothesis_tree.items():
            tree_data[node_id] = {
                "id": node.id,
                "hypothesis": {
                    "statement": node.hypothesis.statement,
                    "variables": node.hypothesis.variables,
                    "domain": node.hypothesis.domain
                },
                "parent_id": node.parent_id,
                "children_ids": node.children_ids,
                "confidence_score": node.confidence_score,
                "support_evidence_count": len(node.support_evidence),
                "challenge_evidence_count": len(node.challenge_evidence),
                "mathematical_validity": node.mathematical_scaffolding.get("mathematical_validity", False) if node.mathematical_scaffolding else False,
                "created_at": node.created_at.isoformat()
            }
        
        return {
            "session_id": session_id,
            "root_hypotheses": session.root_hypotheses,
            "active_nodes": session.active_nodes,
            "tree": tree_data
        }
    
    async def get_best_hypotheses(self, session_id: str, top_k: int = 3) -> Optional[List[Dict[str, Any]]]:
        """Get top-k hypotheses by confidence score."""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Sort all nodes by confidence
        all_nodes = list(session.hypothesis_tree.values())
        top_nodes = sorted(all_nodes, key=lambda n: n.confidence_score, reverse=True)[:top_k]
        
        results = []
        for node in top_nodes:
            results.append({
                "id": node.id,
                "hypothesis": {
                    "statement": node.hypothesis.statement,
                    "variables": node.hypothesis.variables,
                    "domain": node.hypothesis.domain
                },
                "confidence_score": node.confidence_score,
                "support_evidence_count": len(node.support_evidence),
                "challenge_evidence_count": len(node.challenge_evidence),
                "mathematical_scaffolding": node.mathematical_scaffolding
            })
        
        return results
    
    async def stop_session(self, session_id: str) -> bool:
        """Stop and cleanup discovery session."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            await self.working_memory.clear_context(session_id)
            self.logger.info(f"Stopped discovery session {session_id}")
            return True
        return False
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired discovery sessions."""
        expired_sessions = []
        current_time = datetime.now()
        
        for session_id, session in self.active_sessions.items():
            if current_time - session.updated_at > self.session_timeout:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.stop_session(session_id)
        
        return len(expired_sessions)
EVOLUTION = type('EVOLUTION', (), {})  # auto-stub: not found in project

GENESIS = type('GENESIS', (), {})  # auto-stub: not found in project

SCAFFOLDING = type('SCAFFOLDING', (), {})  # auto-stub: not found in project

SEARCH = type('SEARCH', (), {})  # auto-stub: not found in project

SYNTHESIS = type('SYNTHESIS', (), {})  # auto-stub: not found in project
