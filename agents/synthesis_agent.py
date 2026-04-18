"""Synthesis Agent for aggregating and resolving multi-agent outputs."""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
from datetime import datetime

from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent
from agents.comm_bus import CommunicationBus
from knowledge.citations import CitationManager
from memory.working import WorkingMemory
from physics.contradictions import ContradictionDetector


@dataclass
class Evidence:
    """Individual piece of evidence from an agent."""
    source_agent: str
    content: str
    confidence: float
    citations: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Conflict:
    """Detected conflict between pieces of evidence."""
    evidence_a: Evidence
    evidence_b: Evidence
    conflict_type: str
    severity: float
    resolution_strategy: Optional[str] = None


@dataclass
class SynthesisResult:
    """Final synthesized result."""
    content: str
    confidence: float
    supporting_evidence: List[Evidence]
    resolved_conflicts: List[Conflict]
    citations: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvidenceAggregator:
    """Aggregates evidence from multiple sources."""
    
    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        
    async def aggregate(self, agent_outputs: Dict[str, Any]) -> List[Evidence]:
        """Aggregate evidence from agent outputs."""
        try:
            evidence_list = []
            
            for agent_name, output in agent_outputs.items():
                if not output:
                    continue
                    
                # Extract evidence from different output formats
                if isinstance(output, dict):
                    content = output.get('content', str(output))
                    confidence = output.get('confidence', 0.5)
                    citations = output.get('citations', [])
                    metadata = output.get('metadata', {})
                elif isinstance(output, str):
                    content = output
                    confidence = 0.5
                    citations = []
                    metadata = {}
                else:
                    content = str(output)
                    confidence = 0.5
                    citations = []
                    metadata = {}
                
                evidence = Evidence(
                    source_agent=agent_name,
                    content=content,
                    confidence=confidence,
                    citations=citations,
                    metadata=metadata
                )
                evidence_list.append(evidence)
                
            self.logger.info(f"Aggregated {len(evidence_list)} pieces of evidence")
            return evidence_list
            
        except Exception as e:
            handle_error(e)
            return []


class ConflictResolver:
    """Resolves conflicts between different pieces of evidence."""
    
    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.contradiction_detector = ContradictionDetector()
        
    async def detect_conflicts(self, evidence_list: List[Evidence]) -> List[Conflict]:
        """Detect conflicts between evidence pieces."""
        try:
            conflicts = []
            
            for i, evidence_a in enumerate(evidence_list):
                for j, evidence_b in enumerate(evidence_list[i+1:], i+1):
                    conflict = await self._check_conflict(evidence_a, evidence_b)
                    if conflict:
                        conflicts.append(conflict)
                        
            self.logger.info(f"Detected {len(conflicts)} conflicts")
            return conflicts
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def _check_conflict(self, evidence_a: Evidence, evidence_b: Evidence) -> Optional[Conflict]:
        """Check if two pieces of evidence conflict."""
        try:
            # Use contradiction detector for physics-specific conflicts
            is_contradiction = await self.contradiction_detector.detect_contradiction(
                evidence_a.content, 
                evidence_b.content
            )
            
            if is_contradiction:
                severity = self._calculate_severity(evidence_a, evidence_b)
                return Conflict(
                    evidence_a=evidence_a,
                    evidence_b=evidence_b,
                    conflict_type="logical_contradiction",
                    severity=severity
                )
            
            # Check for semantic conflicts
            if await self._semantic_conflict(evidence_a.content, evidence_b.content):
                severity = self._calculate_severity(evidence_a, evidence_b)
                return Conflict(
                    evidence_a=evidence_a,
                    evidence_b=evidence_b,
                    conflict_type="semantic_conflict",
                    severity=severity
                )
                
            return None
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def _semantic_conflict(self, content_a: str, content_b: str) -> bool:
        """Check for semantic conflicts between content."""
        # Simple keyword-based conflict detection
        negative_indicators = [
            ("increases", "decreases"),
            ("positive", "negative"), 
            ("accelerates", "decelerates"),
            ("expands", "contracts"),
            ("valid", "invalid"),
            ("proven", "disproven")
        ]
        
        content_a_lower = content_a.lower()
        content_b_lower = content_b.lower()
        
        for pos_word, neg_word in negative_indicators:
            if (pos_word in content_a_lower and neg_word in content_b_lower) or \
               (neg_word in content_a_lower and pos_word in content_b_lower):
                return True
                
        return False
    
    def _calculate_severity(self, evidence_a: Evidence, evidence_b: Evidence) -> float:
        """Calculate conflict severity based on evidence confidence."""
        return min(evidence_a.confidence, evidence_b.confidence)
    
    async def resolve_conflicts(self, conflicts: List[Conflict]) -> List[Conflict]:
        """Resolve detected conflicts."""
        try:
            resolved_conflicts = []
            
            for conflict in conflicts:
                resolved_conflict = await self._resolve_single_conflict(conflict)
                resolved_conflicts.append(resolved_conflict)
                
            return resolved_conflicts
            
        except Exception as e:
            handle_error(e)
            return conflicts
    
    async def _resolve_single_conflict(self, conflict: Conflict) -> Conflict:
        """Resolve a single conflict."""
        try:
            # Choose resolution strategy based on conflict type and evidence quality
            if conflict.evidence_a.confidence > conflict.evidence_b.confidence:
                strategy = f"favor_higher_confidence:{conflict.evidence_a.source_agent}"
            elif conflict.evidence_b.confidence > conflict.evidence_a.confidence:
                strategy = f"favor_higher_confidence:{conflict.evidence_b.source_agent}"
            else:
                # Equal confidence - prefer newer evidence
                if conflict.evidence_a.timestamp > conflict.evidence_b.timestamp:
                    strategy = f"favor_newer:{conflict.evidence_a.source_agent}"
                else:
                    strategy = f"favor_newer:{conflict.evidence_b.source_agent}"
            
            conflict.resolution_strategy = strategy
            return conflict
            
        except Exception as e:
            handle_error(e)
            conflict.resolution_strategy = "unresolved"
            return conflict


class ConfidenceWeighter:
    """Weights evidence based on confidence scores and agent reliability."""
    
    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.agent_weights = {
            "theory_architect": 0.9,
            "math_agent": 0.85,
            "research_agent": 0.8,
            "peer_review": 0.9,
            "vector_search_agent": 0.7,
            "arxiv_search_agent": 0.75
        }
        
    async def calculate_weights(self, evidence_list: List[Evidence]) -> Dict[str, float]:
        """Calculate final confidence weights for evidence."""
        try:
            weights = {}
            
            for evidence in evidence_list:
                agent_weight = self.agent_weights.get(evidence.source_agent, 0.5)
                base_confidence = evidence.confidence
                
                # Apply citation bonus
                citation_bonus = min(0.1, len(evidence.citations) * 0.02)
                
                # Apply recency bonus (newer evidence gets slight boost)
                age_hours = (datetime.now() - evidence.timestamp).total_seconds() / 3600
                recency_factor = max(0.9, 1.0 - (age_hours * 0.001))
                
                final_weight = (base_confidence * agent_weight + citation_bonus) * recency_factor
                weights[f"{evidence.source_agent}_{id(evidence)}"] = min(1.0, final_weight)
                
            return weights
            
        except Exception as e:
            handle_error(e)
            return {}
    
    async def filter_by_confidence(self, evidence_list: List[Evidence], 
                                 min_confidence: float = 0.3) -> List[Evidence]:
        """Filter evidence by minimum confidence threshold."""
        try:
            weights = await self.calculate_weights(evidence_list)
            filtered = []
            
            for evidence in evidence_list:
                evidence_key = f"{evidence.source_agent}_{id(evidence)}"
                if weights.get(evidence_key, 0) >= min_confidence:
                    filtered.append(evidence)
                    
            self.logger.info(f"Filtered to {len(filtered)} high-confidence evidence pieces")
            return filtered
            
        except Exception as e:
            handle_error(e)
            return evidence_list


class CitationFormatter:
    """Formats citations for the final synthesis."""
    
    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.citation_manager = CitationManager()
        
    async def format_citations(self, evidence_list: List[Evidence]) -> List[Dict[str, Any]]:
        """Format and deduplicate citations from evidence."""
        try:
            all_citations = []
            seen_citations = set()
            
            for evidence in evidence_list:
                for citation in evidence.citations:
                    # Create citation key for deduplication
                    citation_key = self._create_citation_key(citation)
                    
                    if citation_key not in seen_citations:
                        formatted_citation = await self.citation_manager.format_citation(citation)
                        all_citations.append(formatted_citation)
                        seen_citations.add(citation_key)
                        
            self.logger.info(f"Formatted {len(all_citations)} unique citations")
            return all_citations
            
        except Exception as e:
            handle_error(e)
            return []
    
    def _create_citation_key(self, citation: Dict[str, Any]) -> str:
        """Create unique key for citation deduplication."""
        if isinstance(citation, dict):
            return f"{citation.get('title', '')}_{citation.get('authors', '')}_{citation.get('year', '')}"
        return str(citation)


class SynthesisAgent(BaseAgent):
    """Agent that synthesizes outputs from multiple specialist agents."""
    
    def __init__(self,       comm_bus=None,       working_memory=None, **kwargs):
        super().__init__(agent_id="evidence", name="Evidence")
        self.evidence_aggregator = EvidenceAggregator()
        self.conflict_resolver = ConflictResolver()
        self.confidence_weighter = ConfidenceWeighter()
        self.citation_formatter = CitationFormatter()
        
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process synthesis request."""
        try:
            agent_outputs = request.get('agent_outputs', {})
            if not agent_outputs and "results" in request:
                _parts = []
                for _r in (request.get("results") or []):
                    if not isinstance(_r, dict):
                        continue
                    _nested = _r.get("result", _r)
                    _nested = _nested if isinstance(_nested, dict) else _r
                    for _p in _nested.get("papers", _r.get("papers", [])):
                        if isinstance(_p, dict):
                            _t = _p.get("title", "")
                            _a = _p.get("abstract", _p.get("summary", ""))
                            if _a:
                                _parts.append("Title: " + _t + "\nAbstract: " + _a)
                    _c = _r.get("content", _r.get("text", ""))
                    if isinstance(_c, str) and _c:
                        _parts.append(_c)
                if _parts:
                    agent_outputs = {"research_agent": "\n\n".join(_parts)}
            min_confidence = request.get('min_confidence', 0.3)
            
            # Step 1: Aggregate evidence
            evidence_list = await self.evidence_aggregator.aggregate(agent_outputs)
            
            if not evidence_list:
                return {
                    'success': False,
                    'error': 'No evidence to synthesize',
                    'content': 'Unable to synthesize response - no valid evidence found.'
                }
            
            # Step 2: Detect and resolve conflicts
            conflicts = await self.conflict_resolver.detect_conflicts(evidence_list)
            resolved_conflicts = await self.conflict_resolver.resolve_conflicts(conflicts)
            
            # Step 3: Filter by confidence
            filtered_evidence = await self.confidence_weighter.filter_by_confidence(
                evidence_list, min_confidence
            )
            
            # Step 4: Format citations
            formatted_citations = await self.citation_formatter.format_citations(filtered_evidence)
            
            # Step 5: Synthesize final content
            synthesis_result = await self._synthesize_content(
                filtered_evidence, resolved_conflicts, formatted_citations
            )
            
            return {
                'success': True,
                'content': synthesis_result.content,
                'confidence': synthesis_result.confidence,
                'evidence_count': len(synthesis_result.supporting_evidence),
                'conflicts_resolved': len(synthesis_result.resolved_conflicts),
                'citations': synthesis_result.citations,
                'metadata': synthesis_result.metadata
            }
            
        except Exception as e:
            handle_error(e)
            return {
                'success': False,
                'error': str(e),
                'content': 'Error during synthesis process.'
            }
    
    async def _synthesize_content(self, evidence_list: List[Evidence], 
                                conflicts: List[Conflict], 
                                citations: List[Dict[str, Any]]) -> SynthesisResult:
        """Synthesize final content from filtered evidence."""
        try:
            # Group evidence by agent type for structured synthesis
            evidence_by_agent = defaultdict(list)
            for evidence in evidence_list:
                evidence_by_agent[evidence.source_agent].append(evidence)
            
            # Build synthesis sections
            sections = []
            
            # Theory/Mathematical foundations
            theory_evidence = evidence_by_agent.get('theory_architect', []) + \
                            evidence_by_agent.get('math_agent', [])
            if theory_evidence:
                theory_section = await self._build_theory_section(theory_evidence)
                sections.append(theory_section)
            
            # Research findings
            research_evidence = evidence_by_agent.get('research_agent', []) + \
                              evidence_by_agent.get('vector_search_agent', []) + \
                              evidence_by_agent.get('arxiv_search_agent', [])
            if research_evidence:
                research_section = await self._build_research_section(research_evidence)
                sections.append(research_section)
            
            # Peer review insights
            review_evidence = evidence_by_agent.get('peer_review', [])
            if review_evidence:
                review_section = await self._build_review_section(review_evidence)
                sections.append(review_section)
            
            # Combine sections
            content = "\n\n".join(sections)
            
            # Add conflict resolution notes if any
            if conflicts:
                conflict_notes = await self._build_conflict_notes(conflicts)
                content += f"\n\nNote: {conflict_notes}"
            
            # Calculate overall confidence
            overall_confidence = await self._calculate_overall_confidence(evidence_list)
            
            return SynthesisResult(
                content=content,
                confidence=overall_confidence,
                supporting_evidence=evidence_list,
                resolved_conflicts=conflicts,
                citations=citations,
                metadata={
                    'synthesis_timestamp': datetime.now().isoformat(),
                    'agent_contributions': {agent: len(evs) for agent, evs in evidence_by_agent.items()},
                    'total_evidence_pieces': len(evidence_list)
                }
            )
            
        except Exception as e:
            handle_error(e)
            # Fallback synthesis
            combined_content = "\n\n".join([e.content for e in evidence_list])
            return SynthesisResult(
                content=combined_content,
                confidence=0.5,
                supporting_evidence=evidence_list,
                resolved_conflicts=conflicts,
                citations=citations
            )
    
    async def _build_theory_section(self, theory_evidence: List[Evidence]) -> str:
        """Build theoretical foundations section."""
        if not theory_evidence:
            return ""
            
        section_parts = ["## Theoretical Analysis"]
        
        for evidence in sorted(theory_evidence, key=lambda x: x.confidence, reverse=True):
            section_parts.append(f"• {evidence.content}")
            
        return "\n".join(section_parts)
    
    async def _build_research_section(self, research_evidence: List[Evidence]) -> str:
        """Build research findings section."""
        if not research_evidence:
            return ""
            
        section_parts = ["## Research Findings"]
        
        for evidence in sorted(research_evidence, key=lambda x: x.confidence, reverse=True):
            section_parts.append(f"• {evidence.content}")
            
        return "\n".join(section_parts)
    
    async def _build_review_section(self, review_evidence: List[Evidence]) -> str:
        """Build peer review section."""
        if not review_evidence:
            return ""
            
        section_parts = ["## Peer Review Insights"]
        
        for evidence in review_evidence:
            section_parts.append(f"• {evidence.content}")
            
        return "\n".join(section_parts)
    
    async def _build_conflict_notes(self, conflicts: List[Conflict]) -> str:
        """Build notes about resolved conflicts."""
        if not conflicts:
            return ""
            
        resolved_count = len([c for c in conflicts if c.resolution_strategy])
        return f"Resolved {resolved_count} conflicts between agent outputs using confidence-based and temporal resolution strategies."
    
    async def _calculate_overall_confidence(self, evidence_list: List[Evidence]) -> float:
        """Calculate overall confidence in the synthesis."""
        if not evidence_list:
            return 0.0
            
        weights = await self.confidence_weighter.calculate_weights(evidence_list)
        
        if not weights:
            return np.mean([e.confidence for e in evidence_list])
            
        weighted_sum = sum(weights.values())
        return min(1.0, weighted_sum / len(weights))
    async def _process_cycle(self, *args, **kwargs):
        pass

    async def on_message_received(self, message=None, *args, **kwargs):
        pass

    async def process_task(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def get_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def run(self, *args, **kwargs):
        combined = args[0] if args else ''
        query = kwargs.get('query', args[1] if len(args) > 1 else '')
        return await self.process_request({'agent_outputs': {'research_agent': combined}, 'query': query})

    async def process_message(self, *args, **kwargs):
        return await self.process_request(*args, **kwargs)
