import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from typing import TYPE_CHECKING  # noqa
from config.settings import get_settings
from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error
from discovery.discovery_mode import DiscoveryMode
from discovery.hypothesis_tracker import HypothesisTracker
from discovery.evidence_search import EvidenceSearchEngine
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agents.orchestrator import PhysicsOrchestrator
from thinking.self_refine import SelfRefiner
from physics.hypothesis import HypothesisGenerator

logger = get_logger(__name__)
settings = get_settings()

class LoopState(Enum):
    """Discovery loop execution state"""
    INITIALIZING = "initializing"
    GENERATING = "generating"
    SEARCHING = "searching"
    EVALUATING = "evaluating"
    REFINING = "refining"
    CONVERGED = "converged"
    EXHAUSTED = "exhausted"
    ERROR = "error"

@dataclass
class LoopMetrics:
    """Performance metrics for discovery loop"""
    cycles_completed: int = 0
    hypotheses_generated: int = 0
    evidence_found: int = 0
    tokens_consumed: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    convergence_score: float = 0.0

class ConvergenceDetector:
    """Detects when hypothesis evolution has converged"""
    
    def __init__(self,      threshold: float = 0.95,      window: int = 3, **kwargs):
        self.threshold = threshold
        self.window = window
        self.score_history: List[float] = []
        
    def update(self, score: float, **kwargs) -> bool:
        """Update with new convergence score and check if converged"""
        self.score_history.append(score)
        if len(self.score_history) > self.window:
            self.score_history.pop(0)
            
        if len(self.score_history) >= self.window:
            recent_avg = sum(self.score_history) / len(self.score_history)
            return recent_avg >= self.threshold
            
        return False

class ContinuousDiscoveryLoop:
    """Async overnight engine for continuous hypothesis generation and refinement"""
    
    def __init__(self, **kwargs):
        self.state = LoopState.INITIALIZING
        self.metrics = LoopMetrics()
        self.hypothesis_tracker = HypothesisTracker()
        self.evidence_search = EvidenceSearchEngine()
        self.orchestrator = PhysicsOrchestrator()
        self.hypothesis_generator = HypothesisGenerator()
        self.refiner = SelfRefiner()
        self.convergence_detector = ConvergenceDetector()
        self.max_cycles = 50
        self.max_tokens = 1000000
        self.cycle_delay = 60  # seconds between cycles
        
    async def run_continuous_discovery(
        self, 
        initial_query: str,
        mode: DiscoveryMode = DiscoveryMode.GUIDED_SEARCH,
        max_duration_hours: int = 8
    ) -> Dict[str, Any]:
        """Run continuous discovery loop until convergence or budget exhausted"""
        
        try:
            self.metrics.start_time = datetime.now()
            max_end_time = self.metrics.start_time + timedelta(hours=max_duration_hours)
            
            logger.info(f"Starting continuous discovery loop for: {initial_query}")
            
            # Initialize with seed hypotheses
            await self._initialize_seed_hypotheses(initial_query, mode)
            
            cycle_count = 0
            while (
                cycle_count < self.max_cycles and
                self.metrics.tokens_consumed < self.max_tokens and
                datetime.now() < max_end_time and
                self.state not in [LoopState.CONVERGED, LoopState.EXHAUSTED, LoopState.ERROR]
            ):
                cycle_count += 1
                logger.info(f"Starting discovery cycle {cycle_count}")
                
                # Run single discovery cycle
                cycle_result = await self._run_discovery_cycle(initial_query, mode)
                
                # Update metrics
                self.metrics.cycles_completed = cycle_count
                self.metrics.tokens_consumed += cycle_result.get('tokens_used', 0)
                
                # Check convergence
                convergence_score = await self._calculate_convergence_score()
                self.metrics.convergence_score = convergence_score
                
                if self.convergence_detector.update(convergence_score):
                    self.state = LoopState.CONVERGED
                    logger.info(f"Convergence detected after {cycle_count} cycles")
                    break
                    
                # Inter-cycle delay
                await asyncio.sleep(self.cycle_delay)
                
            self.metrics.end_time = datetime.now()
            
            if self.state not in [LoopState.CONVERGED, LoopState.ERROR]:
                self.state = LoopState.EXHAUSTED
                
            return await self._generate_final_report()
            
        except Exception as e:
            self.state = LoopState.ERROR
            handle_error(e)
            return {"error": str(e), "state": self.state.value}
            
    async def _initialize_seed_hypotheses(self, query: str, mode: DiscoveryMode) -> None:
        """Initialize with seed hypotheses from query"""
        
        self.state = LoopState.GENERATING
        
        # Generate initial hypotheses
        seed_hypotheses = await self.hypothesis_generator.generate_hypotheses(
            query, count=5
        )
        
        for hypothesis in seed_hypotheses:
            await self.hypothesis_tracker.add_hypothesis(hypothesis)
            self.metrics.hypotheses_generated += 1
            
        logger.info(f"Initialized with {len(seed_hypotheses)} seed hypotheses")
        
    async def _run_discovery_cycle(self, query: str, mode: DiscoveryMode) -> Dict[str, Any]:
        """Run single cycle of discovery: generate -> search -> evaluate -> refine"""
        
        cycle_results = {
            'hypotheses_generated': 0,
            'evidence_found': 0,
            'tokens_used': 0,
            'refinements': 0
        }
        
        try:
            # Phase 1: Generate new hypotheses from current best
            self.state = LoopState.GENERATING
            new_hypotheses = await self._generate_evolved_hypotheses()
            cycle_results['hypotheses_generated'] = len(new_hypotheses)
            
            # Phase 2: Search for evidence
            self.state = LoopState.SEARCHING
            evidence_results = await self._search_evidence_for_hypotheses(new_hypotheses)
            cycle_results['evidence_found'] = len(evidence_results)
            
            # Phase 3: Evaluate hypotheses with evidence
            self.state = LoopState.EVALUATING
            evaluation_results = await self._evaluate_hypotheses_with_evidence(
                new_hypotheses, evidence_results
            )
            
            # Phase 4: Refine top hypotheses
            self.state = LoopState.REFINING
            refinement_results = await self._refine_top_hypotheses(evaluation_results)
            cycle_results['refinements'] = len(refinement_results)
            
            # Estimate token usage (simplified)
            cycle_results['tokens_used'] = (
                len(new_hypotheses) * 500 +  # hypothesis generation
                len(evidence_results) * 200 +  # evidence search
                len(evaluation_results) * 300 +  # evaluation
                len(refinement_results) * 400   # refinement
            )
            
            return cycle_results
            
        except Exception as e:
            handle_error(e)
            return cycle_results
            
    async def _generate_evolved_hypotheses(self) -> List[Dict[str, Any]]:
        """Generate new hypotheses based on current best performers"""
        
        # Get top performing hypotheses
        top_hypotheses = await self.hypothesis_tracker.get_top_hypotheses(limit=3)
        
        new_hypotheses = []
        
        for base_hypothesis in top_hypotheses:
            # Generate variations/evolutions
            evolved = await self.hypothesis_generator.evolve_hypothesis(
                base_hypothesis, mutation_rate=0.3
            )
            new_hypotheses.extend(evolved)
            
        # Add some completely new hypotheses for exploration
        random_hypotheses = await self.hypothesis_generator.generate_random_hypotheses(
            count=2
        )
        new_hypotheses.extend(random_hypotheses)
        
        # Track all new hypotheses
        for hypothesis in new_hypotheses:
            await self.hypothesis_tracker.add_hypothesis(hypothesis)
            
        self.metrics.hypotheses_generated += len(new_hypotheses)
        
        return new_hypotheses
        
    async def _search_evidence_for_hypotheses(
        self, 
        hypotheses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Search for evidence supporting each hypothesis"""
        
        all_evidence = []
        
        for hypothesis in hypotheses:
            try:
                # Generate search queries from hypothesis
                search_queries = await self._generate_search_queries(hypothesis)
                
                # Search for evidence
                for query in search_queries[:3]:  # Limit queries per hypothesis
                    evidence = await self.evidence_search.search_evidence(
                        query, limit=5
                    )
                    all_evidence.extend(evidence)
                    
            except Exception as e:
                handle_error(e)
                continue
                
        self.metrics.evidence_found += len(all_evidence)
        
        return all_evidence
        
    async def _generate_search_queries(self, hypothesis: Dict[str, Any]) -> List[str]:
        """Generate search queries to find evidence for hypothesis"""
        
        # Use orchestrator to generate targeted search queries
        result = await self.orchestrator.run(
            f"Generate 3 specific search queries to find evidence for this hypothesis: {hypothesis.get('statement', '')}",
            mode="search_generation",
            pattern="evidence_search"
        )
        
        # Extract queries from result
        queries = []
        if isinstance(result.get('response'), str):
            # Simple extraction - in production would use more sophisticated parsing
            lines = result['response'].split('\n')
            for line in lines:
                if line.strip() and ('?' in line or 'search' in line.lower()):
                    queries.append(line.strip())
                    
        return queries[:3]  # Return max 3 queries
        
    async def _evaluate_hypotheses_with_evidence(
        self,
        hypotheses: List[Dict[str, Any]], 
        evidence: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Evaluate how well evidence supports each hypothesis"""
        
        evaluations = []
        
        for hypothesis in hypotheses:
            try:
                # Find relevant evidence for this hypothesis
                relevant_evidence = await self._match_evidence_to_hypothesis(
                    hypothesis, evidence
                )
                
                # Evaluate hypothesis with evidence
                evaluation_result = await self.orchestrator.run(
                    f"Evaluate hypothesis with evidence. Hypothesis: {hypothesis.get('statement')}. Evidence: {relevant_evidence[:3]}",
                    mode="evaluation",
                    pattern="hypothesis_evaluation"
                )
                
                evaluation = {
                    'hypothesis_id': hypothesis.get('id'),
                    'hypothesis': hypothesis,
                    'evidence_count': len(relevant_evidence),
                    'support_score': self._extract_support_score(evaluation_result),
                    'evaluation': evaluation_result,
                    'timestamp': datetime.now()
                }
                
                evaluations.append(evaluation)
                
                # Update hypothesis tracker with evaluation
                await self.hypothesis_tracker.update_hypothesis_score(
                    hypothesis.get('id'), 
                    evaluation['support_score']
                )
                
            except Exception as e:
                handle_error(e)
                continue
                
        return evaluations
        
    async def _match_evidence_to_hypothesis(
        self, 
        hypothesis: Dict[str, Any], 
        all_evidence: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find evidence most relevant to a specific hypothesis"""
        
        # Simple relevance matching - in production would use embeddings
        hypothesis_text = hypothesis.get('statement', '').lower()
        relevant_evidence = []
        
        for evidence in all_evidence:
            evidence_text = evidence.get('content', '').lower()
            
            # Check for keyword overlap
            hypothesis_words = set(hypothesis_text.split())
            evidence_words = set(evidence_text.split())
            
            overlap = len(hypothesis_words.intersection(evidence_words))
            if overlap >= 3:  # Minimum overlap threshold
                evidence['relevance_score'] = overlap
                relevant_evidence.append(evidence)
                
        # Sort by relevance
        relevant_evidence.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return relevant_evidence
        
    def _extract_support_score(self, evaluation_result: Dict[str, Any]) -> float:
        """Extract numerical support score from evaluation result"""
        
        # Simple extraction - in production would use more sophisticated parsing
        response = evaluation_result.get('response', '')
        
        # Look for score patterns
        import re
        score_patterns = [
            r'score[:\s]+([0-9.]+)',
            r'support[:\s]+([0-9.]+)',
            r'([0-9.]+)/10',
            r'([0-9.]+)%'
        ]
        
        for pattern in score_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    # Normalize to 0-1 range
                    if score > 1:
                        score = score / 100 if score <= 100 else score / 10
                    return min(1.0, max(0.0, score))
                except ValueError:
                    continue
                    
        # Default score based on positive/negative sentiment
        positive_words = ['support', 'confirm', 'evidence', 'valid', 'correct']
        negative_words = ['contradict', 'refute', 'invalid', 'wrong', 'false']
        
        pos_count = sum(1 for word in positive_words if word in response.lower())
        neg_count = sum(1 for word in negative_words if word in response.lower())
        
        if pos_count > neg_count:
            return 0.7
        elif neg_count > pos_count:
            return 0.3
        else:
            return 0.5
            
    async def _refine_top_hypotheses(
        self, 
        evaluations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Refine the top-scoring hypotheses"""
        
        # Sort evaluations by support score
        evaluations.sort(key=lambda x: x.get('support_score', 0), reverse=True)
        
        refinements = []
        
        # Refine top 3 hypotheses
        for evaluation in evaluations[:3]:
            try:
                hypothesis = evaluation['hypothesis']
                evidence_summary = self._summarize_evidence(evaluation)
                
                # Use self-refiner to improve hypothesis
                refined_hypothesis = await self.refiner.refine_hypothesis(
                    hypothesis, evidence_summary
                )
                
                # Add refined version to tracker
                await self.hypothesis_tracker.add_hypothesis(refined_hypothesis)
                
                refinement = {
                    'original_hypothesis': hypothesis,
                    'refined_hypothesis': refined_hypothesis,
                    'evidence_used': evidence_summary,
                    'timestamp': datetime.now()
                }
                
                refinements.append(refinement)
                
            except Exception as e:
                handle_error(e)
                continue
                
        return refinements
        
    def _summarize_evidence(self, evaluation: Dict[str, Any]) -> str:
        """Create summary of evidence for refinement"""
        
        evidence_count = evaluation.get('evidence_count', 0)
        support_score = evaluation.get('support_score', 0)
        
        return f"Evidence count: {evidence_count}, Support score: {support_score:.2f}"
        
    async def _calculate_convergence_score(self) -> float:
        """Calculate how much hypotheses have converged"""
        
        try:
            # Get recent hypothesis scores
            recent_hypotheses = await self.hypothesis_tracker.get_recent_hypotheses(
                limit=10
            )
            
            if len(recent_hypotheses) < 3:
                return 0.0
                
            # Calculate score variance
            scores = [h.get('score', 0) for h in recent_hypotheses]
            mean_score = sum(scores) / len(scores)
            variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
            
            # Lower variance indicates convergence
            convergence_score = max(0, 1 - variance)
            
            return convergence_score
            
        except Exception as e:
            handle_error(e)
            return 0.0
            
    async def _generate_final_report(self) -> Dict[str, Any]:
        """Generate comprehensive discovery report"""
        
        try:
            # Get final hypothesis rankings
            top_hypotheses = await self.hypothesis_tracker.get_top_hypotheses(limit=10)
            
            # Calculate runtime
            duration = None
            if self.metrics.start_time and self.metrics.end_time:
                duration = self.metrics.end_time - self.metrics.start_time
                
            report = {
                'discovery_summary': {
                    'state': self.state.value,
                    'cycles_completed': self.metrics.cycles_completed,
                    'hypotheses_generated': self.metrics.hypotheses_generated,
                    'evidence_found': self.metrics.evidence_found,
                    'tokens_consumed': self.metrics.tokens_consumed,
                    'convergence_score': self.metrics.convergence_score,
                    'duration': str(duration) if duration else None
                },
                'top_hypotheses': top_hypotheses,
                'performance_metrics': {
                    'hypotheses_per_cycle': (
                        self.metrics.hypotheses_generated / max(1, self.metrics.cycles_completed)
                    ),
                    'evidence_per_cycle': (
                        self.metrics.evidence_found / max(1, self.metrics.cycles_completed)
                    ),
                    'tokens_per_cycle': (
                        self.metrics.tokens_consumed / max(1, self.metrics.cycles_completed)
                    )
                },
                'convergence_analysis': {
                    'converged': self.state == LoopState.CONVERGED,
                    'final_score': self.metrics.convergence_score,
                    'score_history': self.convergence_detector.score_history
                }
            }
            
            return report
            
        except Exception as e:
            handle_error(e)
            return {'error': str(e)}
            
    async def get_live_status(self) -> Dict[str, Any]:
        """Get current status of discovery loop"""
        
        return {
            'state': self.state.value,
            'metrics': {
                'cycles_completed': self.metrics.cycles_completed,
                'hypotheses_generated': self.metrics.hypotheses_generated,
                'evidence_found': self.metrics.evidence_found,
                'tokens_consumed': self.metrics.tokens_consumed,
                'convergence_score': self.metrics.convergence_score
            },
            'runtime': str(datetime.now() - self.metrics.start_time) if self.metrics.start_time else None
        }
        
    async def stop_loop(self) -> None:
        """Gracefully stop the discovery loop"""
        
        logger.info("Stopping continuous discovery loop")
        self.state = LoopState.EXHAUSTED
        self.metrics.end_time = datetime.now()

    async def run_discovery(self, *args, **kwargs):
        return dict()
CONVERGED = type('CONVERGED', (), {})  # auto-stub: not found in project

ERROR = type('ERROR', (), {})  # auto-stub: not found in project

EVALUATING = type('EVALUATING', (), {})  # auto-stub: not found in project

EXHAUSTED = type('EXHAUSTED', (), {})  # auto-stub: not found in project

GENERATING = type('GENERATING', (), {})  # auto-stub: not found in project

INITIALIZING = type('INITIALIZING', (), {})  # auto-stub: not found in project

REFINING = type('REFINING', (), {})  # auto-stub: not found in project

SEARCHING = type('SEARCHING', (), {})  # auto-stub: not found in project
