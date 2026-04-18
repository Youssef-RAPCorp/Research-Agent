from typing import Dict, List, Optional, Set, Any, Union
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import asyncio
from collections import defaultdict
import json

from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error
from physics.hypothesis import Hypothesis

logger = get_logger(__name__)

class HypothesisStatus(Enum):
    """Status of hypothesis in the discovery process."""
    PROPOSED = "proposed"
    TESTING = "testing"
    VALIDATED = "validated"
    REFUTED = "refuted"
    EVOLVED = "evolved"
    ABANDONED = "abandoned"

@dataclass
class HypothesisNode:
    """Node representing a hypothesis in the genealogy tree."""
    id: str
    hypothesis: Hypothesis
    status: HypothesisStatus
    confidence: float
    created_at: datetime
    updated_at: datetime
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    evolution_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for serialization."""
        return {
            "id": self.id,
            "hypothesis": self.hypothesis.to_dict(),
            "status": self.status.value,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "evidence_ids": self.evidence_ids,
            "evolution_reason": self.evolution_reason,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HypothesisNode':
        """Create node from dictionary."""
        return cls(
            id=data["id"],
            hypothesis=Hypothesis.from_dict(data["hypothesis"]),
            status=HypothesisStatus(data["status"]),
            confidence=data["confidence"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            parent_ids=data.get("parent_ids", []),
            child_ids=data.get("child_ids", []),
            evidence_ids=data.get("evidence_ids", []),
            evolution_reason=data.get("evolution_reason"),
            metadata=data.get("metadata", {})
        )

@dataclass
class EvolutionPath:
    """Path showing hypothesis evolution through generations."""
    path_id: str
    hypothesis_ids: List[str]
    confidence_progression: List[float]
    evolution_reasons: List[str]
    created_at: datetime

class HypothesisTracker:
    """Tracks hypothesis genealogy and evolution with confidence propagation."""
    
    def __init__(self, **kwargs):
        self.nodes: Dict[str, HypothesisNode] = {}
        self.root_nodes: Set[str] = set()
        self.active_hypotheses: Set[str] = set()
        self.evolution_paths: Dict[str, EvolutionPath] = {}
        self._confidence_threshold = 0.3
        self._max_generations = 10
    
    async def add_hypothesis(
        self, 
        hypothesis: Hypothesis, 
        parent_ids: Optional[List[str]] = None,
        evolution_reason: Optional[str] = None
    ) -> str:
        """Add new hypothesis to tracking system."""
        try:
            node_id = str(uuid.uuid4())
            now = datetime.now()
            
            # Calculate initial confidence based on parents
            initial_confidence = self._calculate_initial_confidence(parent_ids)
            
            node = HypothesisNode(
                id=node_id,
                hypothesis=hypothesis,
                status=HypothesisStatus.PROPOSED,
                confidence=initial_confidence,
                created_at=now,
                updated_at=now,
                parent_ids=parent_ids or [],
                evolution_reason=evolution_reason
            )
            
            self.nodes[node_id] = node
            self.active_hypotheses.add(node_id)
            
            # Update parent-child relationships
            if parent_ids:
                for parent_id in parent_ids:
                    if parent_id in self.nodes:
                        self.nodes[parent_id].child_ids.append(node_id)
                        self.nodes[parent_id].updated_at = now
            else:
                self.root_nodes.add(node_id)
            
            # Create evolution path if this is an evolution
            if parent_ids:
                await self._update_evolution_paths(node_id, parent_ids)
            
            logger.info(f"Added hypothesis {node_id} with confidence {initial_confidence}")
            return node_id
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def update_hypothesis_status(
        self, 
        hypothesis_id: str, 
        status: HypothesisStatus,
        confidence: Optional[float] = None
    ) -> bool:
        """Update hypothesis status and propagate confidence changes."""
        try:
            if hypothesis_id not in self.nodes:
                logger.warning(f"Hypothesis {hypothesis_id} not found")
                return False
            
            node = self.nodes[hypothesis_id]
            old_confidence = node.confidence
            
            node.status = status
            node.updated_at = datetime.now()
            
            if confidence is not None:
                node.confidence = confidence
            
            # Update active set based on status
            if status in [HypothesisStatus.REFUTED, HypothesisStatus.ABANDONED]:
                self.active_hypotheses.discard(hypothesis_id)
            elif status == HypothesisStatus.EVOLVED:
                self.active_hypotheses.discard(hypothesis_id)
            else:
                self.active_hypotheses.add(hypothesis_id)
            
            # Propagate confidence changes
            if confidence is not None and abs(confidence - old_confidence) > 0.1:
                await self._propagate_confidence(hypothesis_id, confidence - old_confidence)
            
            logger.info(f"Updated hypothesis {hypothesis_id} status to {status.value}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def evolve_hypothesis(
        self, 
        parent_id: str, 
        new_hypothesis: Hypothesis,
        evolution_reason: str
    ) -> str:
        """Create evolved version of hypothesis."""
        try:
            if parent_id not in self.nodes:
                raise ValueError(f"Parent hypothesis {parent_id} not found")
            
            # Mark parent as evolved
            await self.update_hypothesis_status(parent_id, HypothesisStatus.EVOLVED)
            
            # Create child hypothesis
            child_id = await self.add_hypothesis(
                new_hypothesis, 
                parent_ids=[parent_id],
                evolution_reason=evolution_reason
            )
            
            logger.info(f"Evolved hypothesis {parent_id} to {child_id}: {evolution_reason}")
            return child_id
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def merge_hypotheses(
        self, 
        parent_ids: List[str], 
        merged_hypothesis: Hypothesis,
        merge_reason: str
    ) -> str:
        """Merge multiple hypotheses into a new one."""
        try:
            # Validate all parents exist
            for parent_id in parent_ids:
                if parent_id not in self.nodes:
                    raise ValueError(f"Parent hypothesis {parent_id} not found")
            
            # Mark all parents as evolved
            for parent_id in parent_ids:
                await self.update_hypothesis_status(parent_id, HypothesisStatus.EVOLVED)
            
            # Create merged hypothesis
            merged_id = await self.add_hypothesis(
                merged_hypothesis,
                parent_ids=parent_ids,
                evolution_reason=f"Merged: {merge_reason}"
            )
            
            logger.info(f"Merged hypotheses {parent_ids} into {merged_id}")
            return merged_id
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def add_evidence(self, hypothesis_id: str, evidence_id: str) -> bool:
        """Link evidence to hypothesis."""
        try:
            if hypothesis_id not in self.nodes:
                return False
            
            node = self.nodes[hypothesis_id]
            if evidence_id not in node.evidence_ids:
                node.evidence_ids.append(evidence_id)
                node.updated_at = datetime.now()
            
            logger.debug(f"Added evidence {evidence_id} to hypothesis {hypothesis_id}")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    def get_hypothesis_lineage(self, hypothesis_id: str) -> List[str]:
        """Get complete lineage from root to specified hypothesis."""
        if hypothesis_id not in self.nodes:
            return []
        
        lineage = []
        current = self.nodes[hypothesis_id]
        
        # Traverse back to root
        while current.parent_ids:
            lineage.insert(0, current.id)
            # Take first parent for primary lineage
            parent_id = current.parent_ids[0]
            if parent_id in self.nodes:
                current = self.nodes[parent_id]
            else:
                break
        
        # Add root
        lineage.insert(0, current.id)
        return lineage
    
    def get_hypothesis_descendants(self, hypothesis_id: str) -> List[str]:
        """Get all descendants of hypothesis."""
        if hypothesis_id not in self.nodes:
            return []
        
        descendants = []
        queue = [hypothesis_id]
        visited = set()
        
        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            
            if current_id != hypothesis_id:
                descendants.append(current_id)
            
            if current_id in self.nodes:
                queue.extend(self.nodes[current_id].child_ids)
        
        return descendants
    
    def get_active_hypotheses(self) -> List[HypothesisNode]:
        """Get all currently active hypotheses."""
        return [self.nodes[h_id] for h_id in self.active_hypotheses if h_id in self.nodes]
    
    def get_generation_depth(self, hypothesis_id: str) -> int:
        """Get generation depth of hypothesis (0 for root)."""
        if hypothesis_id not in self.nodes:
            return -1
        
        if hypothesis_id in self.root_nodes:
            return 0
        
        depth = 0
        current = self.nodes[hypothesis_id]
        
        while current.parent_ids:
            depth += 1
            parent_id = current.parent_ids[0]
            if parent_id in self.nodes:
                current = self.nodes[parent_id]
            else:
                break
        
        return depth
    
    def get_confidence_statistics(self) -> Dict[str, float]:
        """Get confidence statistics across all hypotheses."""
        if not self.nodes:
            return {"min": 0.0, "max": 0.0, "avg": 0.0, "active_avg": 0.0}
        
        all_confidences = [node.confidence for node in self.nodes.values()]
        active_confidences = [
            self.nodes[h_id].confidence 
            for h_id in self.active_hypotheses 
            if h_id in self.nodes
        ]
        
        return {
            "min": min(all_confidences),
            "max": max(all_confidences),
            "avg": sum(all_confidences) / len(all_confidences),
            "active_avg": sum(active_confidences) / len(active_confidences) if active_confidences else 0.0
        }
    
    def prune_low_confidence_branches(self, threshold: Optional[float] = None) -> int:
        """Prune branches with consistently low confidence."""
        threshold = threshold or self._confidence_threshold
        pruned_count = 0
        
        # Find leaf nodes with low confidence
        to_prune = []
        for node_id, node in self.nodes.items():
            if (not node.child_ids and 
                node.confidence < threshold and 
                node.status == HypothesisStatus.PROPOSED):
                to_prune.append(node_id)
        
        # Mark for abandonment
        for node_id in to_prune:
            asyncio.create_task(
                self.update_hypothesis_status(node_id, HypothesisStatus.ABANDONED)
            )
            pruned_count += 1
        
        logger.info(f"Pruned {pruned_count} low-confidence branches")
        return pruned_count
    
    def export_genealogy(self) -> Dict[str, Any]:
        """Export complete genealogy tree."""
        return {
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "root_nodes": list(self.root_nodes),
            "active_hypotheses": list(self.active_hypotheses),
            "evolution_paths": {
                path_id: {
                    "path_id": path.path_id,
                    "hypothesis_ids": path.hypothesis_ids,
                    "confidence_progression": path.confidence_progression,
                    "evolution_reasons": path.evolution_reasons,
                    "created_at": path.created_at.isoformat()
                }
                for path_id, path in self.evolution_paths.items()
            },
            "statistics": self.get_confidence_statistics()
        }
    
    def import_genealogy(self, data: Dict[str, Any]) -> bool:
        """Import genealogy tree from exported data."""
        try:
            self.nodes = {
                node_id: HypothesisNode.from_dict(node_data)
                for node_id, node_data in data["nodes"].items()
            }
            self.root_nodes = set(data["root_nodes"])
            self.active_hypotheses = set(data["active_hypotheses"])
            
            # Import evolution paths
            for path_id, path_data in data.get("evolution_paths", {}).items():
                self.evolution_paths[path_id] = EvolutionPath(
                    path_id=path_data["path_id"],
                    hypothesis_ids=path_data["hypothesis_ids"],
                    confidence_progression=path_data["confidence_progression"],
                    evolution_reasons=path_data["evolution_reasons"],
                    created_at=datetime.fromisoformat(path_data["created_at"])
                )
            
            logger.info(f"Imported genealogy with {len(self.nodes)} hypotheses")
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    def _calculate_initial_confidence(self, parent_ids: Optional[List[str]]) -> float:
        """Calculate initial confidence based on parent hypotheses."""
        if not parent_ids:
            return 0.5  # Default for root hypotheses
        
        parent_confidences = []
        for parent_id in parent_ids:
            if parent_id in self.nodes:
                parent_confidences.append(self.nodes[parent_id].confidence)
        
        if not parent_confidences:
            return 0.5
        
        # Average of parent confidences with slight boost for evolution
        base_confidence = sum(parent_confidences) / len(parent_confidences)
        return min(0.95, base_confidence + 0.1)  # Slight evolutionary boost
    
    async def _propagate_confidence(self, hypothesis_id: str, confidence_delta: float) -> None:
        """Propagate confidence changes to related hypotheses."""
        try:
            node = self.nodes[hypothesis_id]
            propagation_factor = 0.3  # How much to propagate
            
            # Propagate to children (reduced)
            for child_id in node.child_ids:
                if child_id in self.nodes:
                    child_node = self.nodes[child_id]
                    new_confidence = child_node.confidence + (confidence_delta * propagation_factor)
                    child_node.confidence = max(0.0, min(1.0, new_confidence))
                    child_node.updated_at = datetime.now()
            
            # Propagate to parents (very reduced)
            for parent_id in node.parent_ids:
                if parent_id in self.nodes:
                    parent_node = self.nodes[parent_id]
                    new_confidence = parent_node.confidence + (confidence_delta * propagation_factor * 0.5)
                    parent_node.confidence = max(0.0, min(1.0, new_confidence))
                    parent_node.updated_at = datetime.now()
            
        except Exception as e:
            handle_error(e)
    
    async def _update_evolution_paths(self, hypothesis_id: str, parent_ids: List[str]) -> None:
        """Update evolution paths when new hypothesis is added."""
        try:
            for parent_id in parent_ids:
                if parent_id not in self.nodes:
                    continue
                
                # Find existing paths containing parent
                parent_paths = [
                    path for path in self.evolution_paths.values()
                    if parent_id in path.hypothesis_ids
                ]
                
                if parent_paths:
                    # Extend existing path
                    for path in parent_paths:
                        path.hypothesis_ids.append(hypothesis_id)
                        path.confidence_progression.append(self.nodes[hypothesis_id].confidence)
                        if self.nodes[hypothesis_id].evolution_reason:
                            path.evolution_reasons.append(self.nodes[hypothesis_id].evolution_reason)
                else:
                    # Create new path
                    path_id = str(uuid.uuid4())
                    lineage = self.get_hypothesis_lineage(hypothesis_id)
                    
                    confidences = [self.nodes[h_id].confidence for h_id in lineage if h_id in self.nodes]
                    reasons = [
                        self.nodes[h_id].evolution_reason or "Initial"
                        for h_id in lineage if h_id in self.nodes
                    ]
                    
                    self.evolution_paths[path_id] = EvolutionPath(
                        path_id=path_id,
                        hypothesis_ids=lineage,
                        confidence_progression=confidences,
                        evolution_reasons=reasons,
                        created_at=datetime.now()
                    )
            
        except Exception as e:
            handle_error(e)

    async def get_recent_hypotheses(self, *args, **kwargs):
        return dict()

    async def get_top_hypotheses(self, *args, **kwargs):
        return dict()

    async def update_hypothesis_score(self, *args, **kwargs):
        return dict()
ABANDONED = type('ABANDONED', (), {})  # auto-stub: not found in project

EVOLVED = type('EVOLVED', (), {})  # auto-stub: not found in project

PROPOSED = type('PROPOSED', (), {})  # auto-stub: not found in project

REFUTED = type('REFUTED', (), {})  # auto-stub: not found in project

TESTING = type('TESTING', (), {})  # auto-stub: not found in project

VALIDATED = type('VALIDATED', (), {})  # auto-stub: not found in project
