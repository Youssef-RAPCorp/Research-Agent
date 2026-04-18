import asyncio
import json
import logging
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, Field

from config.logger import get_logger
from config.settings import get_settings
from config.errors import handle_error
from knowledge.qdrant_store import QdrantStore
from knowledge.embedder import Embedder
from memory.persistence import PersistenceManager


class Fact(BaseModel):
    """Represents a semantic fact with confidence and metadata."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "unknown"
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
    access_count: int = 0
    decay_rate: float = 0.001
    tags: Set[str] = Field(default_factory=set)
    contradictions: Set[str] = Field(default_factory=set)
    supporting_facts: Set[str] = Field(default_factory=set)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None


class BayesianUpdate(BaseModel):
    """Bayesian update parameters for fact confidence."""
    prior_confidence: float
    likelihood: float
    evidence_strength: float
    posterior_confidence: float
    timestamp: datetime = Field(default_factory=datetime.now)


class SemanticMemory:
    """Long-term fact store with confidence decay, Bayesian updates, and contradiction handling."""
    
    def __init__(self, **kwargs):
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.facts: Dict[str, Fact] = {}
        self.embedder = Embedder()
        self.qdrant = QdrantStore()
        self.persistence = PersistenceManager()
        self._decay_task: Optional[asyncio.Task] = None
        
        # Bayesian parameters
        self.confidence_threshold = 0.7
        self.contradiction_threshold = 0.8
        self.decay_interval = 3600  # 1 hour
        
    async def initialize(self) -> None:
        """Initialize the semantic memory system."""
        try:
            await self.qdrant.initialize()
            await self.embedder.initialize()
            await self._load_facts()
            self._decay_task = asyncio.create_task(self._decay_loop())
            self.logger.info("Semantic memory initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize semantic memory: {e}")
            handle_error(e)
            
    async def shutdown(self) -> None:
        """Shutdown the semantic memory system."""
        if self._decay_task:
            self._decay_task.cancel()
        await self._save_facts()
        self.logger.info("Semantic memory shutdown")
        
    async def store_fact(self, content: str, confidence: float = 0.5, 
                        source: str = "unknown", tags: Set[str] = None,
                        metadata: Dict[str, Any] = None) -> str:
        """Store a new fact in semantic memory."""
        try:
            if tags is None:
                tags = set()
            if metadata is None:
                metadata = {}
                
            # Create embedding
            embedding = await self.embedder.embed(content)
            
            # Check for existing similar facts
            similar_facts = await self._find_similar_facts(content, embedding, threshold=0.9)
            
            if similar_facts:
                # Update existing fact instead of creating duplicate
                fact_id = similar_facts[0][0]
                return await self._update_existing_fact(fact_id, confidence, source)
            
            fact = Fact(
                content=content,
                confidence=confidence,
                source=source,
                tags=tags,
                metadata=metadata,
                embedding=embedding
            )
            
            # Check for contradictions
            await self._check_contradictions(fact)
            
            self.facts[fact.id] = fact
            
            # Store in vector database
            await self.qdrant.store_vector(
                vector_id=fact.id,
                embedding=embedding,
                metadata={
                    "content": content,
                    "confidence": confidence,
                    "source": source,
                    "tags": list(tags),
                    "created_at": fact.created_at.isoformat(),
                    **metadata
                }
            )
            
            self.logger.debug(f"Stored fact {fact.id}: {content[:50]}...")
            return fact.id
            
        except Exception as e:
            self.logger.error(f"Failed to store fact: {e}")
            handle_error(e)
            return ""
            
    async def retrieve_fact(self, fact_id: str) -> Optional[Fact]:
        """Retrieve a fact by ID."""
        fact = self.facts.get(fact_id)
        if fact:
            fact.access_count += 1
            fact.last_updated = datetime.now()
            await self._apply_access_boost(fact)
        return fact
        
    async def search_facts(self, query: str, top_k: int = 10, 
                          min_confidence: float = 0.3) -> List[Tuple[Fact, float]]:
        """Search for facts using semantic similarity."""
        try:
            query_embedding = await self.embedder.embed(query)
            
            # Search in vector database
            results = await self.qdrant.search_similar(
                query_embedding=query_embedding,
                top_k=top_k * 2  # Get more to filter by confidence
            )
            
            fact_results = []
            for vector_id, similarity in results:
                fact = self.facts.get(vector_id)
                if fact and fact.confidence >= min_confidence:
                    fact.access_count += 1
                    fact.last_updated = datetime.now()
                    await self._apply_access_boost(fact)
                    fact_results.append((fact, similarity))
                    
            # Sort by combined score (similarity * confidence)
            fact_results.sort(key=lambda x: x[1] * x[0].confidence, reverse=True)
            return fact_results[:top_k]
            
        except Exception as e:
            self.logger.error(f"Failed to search facts: {e}")
            handle_error(e)
            return []
            
    async def update_confidence(self, fact_id: str, new_evidence: Dict[str, Any], 
                               likelihood: float) -> bool:
        """Update fact confidence using Bayesian inference."""
        try:
            fact = self.facts.get(fact_id)
            if not fact:
                return False
                
            # Bayesian update
            prior = fact.confidence
            evidence_strength = new_evidence.get("strength", 1.0)
            
            # Calculate posterior using Bayes' theorem
            posterior = self._bayesian_update(prior, likelihood, evidence_strength)
            
            # Store update history
            update = BayesianUpdate(
                prior_confidence=prior,
                likelihood=likelihood,
                evidence_strength=evidence_strength,
                posterior_confidence=posterior
            )
            
            if "updates" not in fact.metadata:
                fact.metadata["updates"] = []
            fact.metadata["updates"].append(update.model_dump())
            
            fact.confidence = posterior
            fact.last_updated = datetime.now()
            
            # Update vector database
            await self._update_vector_metadata(fact)
            
            self.logger.debug(f"Updated fact {fact_id} confidence: {prior:.3f} -> {posterior:.3f}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update confidence: {e}")
            handle_error(e)
            return False
            
    async def add_contradiction(self, fact1_id: str, fact2_id: str, 
                               explanation: str = "") -> bool:
        """Mark two facts as contradictory."""
        try:
            fact1 = self.facts.get(fact1_id)
            fact2 = self.facts.get(fact2_id)
            
            if not fact1 or not fact2:
                return False
                
            fact1.contradictions.add(fact2_id)
            fact2.contradictions.add(fact1_id)
            
            # Store contradiction metadata
            contradiction_data = {
                "explanation": explanation,
                "timestamp": datetime.now().isoformat(),
                "confidence_at_time": {"fact1": fact1.confidence, "fact2": fact2.confidence}
            }
            
            if "contradictions_data" not in fact1.metadata:
                fact1.metadata["contradictions_data"] = {}
            if "contradictions_data" not in fact2.metadata:
                fact2.metadata["contradictions_data"] = {}
                
            fact1.metadata["contradictions_data"][fact2_id] = contradiction_data
            fact2.metadata["contradictions_data"][fact1_id] = contradiction_data
            
            # Reduce confidence for contradicting facts
            await self._handle_contradiction_confidence(fact1, fact2)
            
            self.logger.info(f"Added contradiction between {fact1_id} and {fact2_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add contradiction: {e}")
            handle_error(e)
            return False
            
    async def resolve_contradiction(self, fact1_id: str, fact2_id: str, 
                                  winner_id: str) -> bool:
        """Resolve a contradiction by choosing the winning fact."""
        try:
            fact1 = self.facts.get(fact1_id)
            fact2 = self.facts.get(fact2_id)
            
            if not fact1 or not fact2:
                return False
                
            winner = self.facts.get(winner_id)
            loser = fact2 if winner_id == fact1_id else fact1
            
            if not winner:
                return False
                
            # Boost winner confidence
            winner.confidence = min(0.95, winner.confidence + 0.2)
            
            # Significantly reduce loser confidence
            loser.confidence = max(0.05, loser.confidence - 0.3)
            
            # Remove contradiction links
            fact1.contradictions.discard(fact2_id)
            fact2.contradictions.discard(fact1_id)
            
            # Update metadata
            resolution_data = {
                "resolved_at": datetime.now().isoformat(),
                "winner": winner_id,
                "resolution_method": "manual"
            }
            
            winner.metadata.setdefault("resolutions", []).append(resolution_data)
            loser.metadata.setdefault("resolutions", []).append(resolution_data)
            
            await self._update_vector_metadata(winner)
            await self._update_vector_metadata(loser)
            
            self.logger.info(f"Resolved contradiction: {winner_id} wins over {loser.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to resolve contradiction: {e}")
            handle_error(e)
            return False
            
    async def get_contradictions(self, fact_id: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Get all contradictions for a fact."""
        fact = self.facts.get(fact_id)
        if not fact:
            return []
            
        contradictions = []
        for contradicting_id in fact.contradictions:
            contradiction_data = fact.metadata.get("contradictions_data", {}).get(contradicting_id, {})
            contradictions.append((contradicting_id, contradiction_data))
            
        return contradictions
        
    async def prune_low_confidence(self, threshold: float = 0.1) -> int:
        """Remove facts below confidence threshold."""
        try:
            to_remove = []
            for fact_id, fact in self.facts.items():
                if fact.confidence < threshold:
                    to_remove.append(fact_id)
                    
            for fact_id in to_remove:
                await self._remove_fact(fact_id)
                
            self.logger.info(f"Pruned {len(to_remove)} low-confidence facts")
            return len(to_remove)
            
        except Exception as e:
            self.logger.error(f"Failed to prune facts: {e}")
            handle_error(e)
            return 0
            
    async def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        if not self.facts:
            return {"total_facts": 0}
            
        confidences = [f.confidence for f in self.facts.values()]
        access_counts = [f.access_count for f in self.facts.values()]
        
        total_contradictions = sum(len(f.contradictions) for f in self.facts.values()) // 2
        
        return {
            "total_facts": len(self.facts),
            "avg_confidence": np.mean(confidences),
            "confidence_std": np.std(confidences),
            "high_confidence_facts": sum(1 for c in confidences if c > 0.8),
            "low_confidence_facts": sum(1 for c in confidences if c < 0.3),
            "total_contradictions": total_contradictions,
            "avg_access_count": np.mean(access_counts),
            "most_accessed": max(access_counts) if access_counts else 0
        }
        
    def _bayesian_update(self, prior: float, likelihood: float, 
                        evidence_strength: float) -> float:
        """Perform Bayesian update on confidence."""
        # Convert to log-odds for numerical stability
        prior_odds = prior / (1 - prior + 1e-10)
        
        # Likelihood ratio based on evidence strength
        likelihood_ratio = likelihood * evidence_strength + (1 - evidence_strength)
        
        # Update odds
        posterior_odds = prior_odds * likelihood_ratio
        
        # Convert back to probability
        posterior = posterior_odds / (1 + posterior_odds)
        
        return max(0.01, min(0.99, posterior))
        
    async def _find_similar_facts(self, content: str, embedding: List[float], 
                                 threshold: float = 0.9) -> List[Tuple[str, float]]:
        """Find facts similar to the given content."""
        try:
            results = await self.qdrant.search_similar(
                query_embedding=embedding,
                top_k=5
            )
            
            similar = []
            for vector_id, similarity in results:
                if similarity >= threshold:
                    similar.append((vector_id, similarity))
                    
            return similar
            
        except Exception as e:
            self.logger.error(f"Failed to find similar facts: {e}")
            return []
            
    async def _update_existing_fact(self, fact_id: str, confidence: float, 
                                  source: str) -> str:
        """Update an existing similar fact."""
        fact = self.facts.get(fact_id)
        if fact:
            # Merge confidence using weighted average
            weight = 0.3  # Weight for new evidence
            fact.confidence = (1 - weight) * fact.confidence + weight * confidence
            
            # Update source if different
            if source != "unknown" and source not in fact.metadata.get("sources", []):
                fact.metadata.setdefault("sources", []).append(source)
                
            fact.last_updated = datetime.now()
            await self._update_vector_metadata(fact)
            
        return fact_id
        
    async def _check_contradictions(self, new_fact: Fact) -> None:
        """Check for contradictions with existing facts."""
        try:
            # Find semantically similar facts
            similar_facts = await self._find_similar_facts(
                new_fact.content, 
                new_fact.embedding, 
                threshold=0.7
            )
            
            for fact_id, similarity in similar_facts:
                existing_fact = self.facts.get(fact_id)
                if existing_fact:
                    # Simple contradiction detection based on negation keywords
                    if self._detect_contradiction(new_fact.content, existing_fact.content):
                        await self.add_contradiction(
                            new_fact.id, 
                            fact_id, 
                            "Semantic contradiction detected"
                        )
                        
        except Exception as e:
            self.logger.error(f"Failed to check contradictions: {e}")
            
    def _detect_contradiction(self, content1: str, content2: str) -> bool:
        """Simple contradiction detection using keyword patterns."""
        negation_patterns = [
            ("is", "is not"), ("are", "are not"), ("has", "does not have"),
            ("can", "cannot"), ("will", "will not"), ("true", "false"),
            ("exists", "does not exist"), ("possible", "impossible")
        ]
        
        content1_lower = content1.lower()
        content2_lower = content2.lower()
        
        for pos, neg in negation_patterns:
            if (pos in content1_lower and neg in content2_lower) or \
               (neg in content1_lower and pos in content2_lower):
                return True
                
        return False
        
    async def _handle_contradiction_confidence(self, fact1: Fact, fact2: Fact) -> None:
        """Adjust confidence when facts contradict."""
        # Reduce confidence for both facts
        confidence_penalty = 0.1
        
        fact1.confidence = max(0.1, fact1.confidence - confidence_penalty)
        fact2.confidence = max(0.1, fact2.confidence - confidence_penalty)
        
        await self._update_vector_metadata(fact1)
        await self._update_vector_metadata(fact2)
        
    async def _apply_access_boost(self, fact: Fact) -> None:
        """Apply confidence boost based on access frequency."""
        # Small boost for frequently accessed facts
        if fact.access_count % 10 == 0:  # Every 10 accesses
            boost = 0.01 * math.log(1 + fact.access_count / 10)
            fact.confidence = min(0.95, fact.confidence + boost)
            
    async def _update_vector_metadata(self, fact: Fact) -> None:
        """Update vector database metadata."""
        try:
            await self.qdrant.update_metadata(
                vector_id=fact.id,
                metadata={
                    "confidence": fact.confidence,
                    "access_count": fact.access_count,
                    "last_updated": fact.last_updated.isoformat(),
                    "tags": list(fact.tags),
                    **fact.metadata
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to update vector metadata: {e}")
            
    async def _remove_fact(self, fact_id: str) -> None:
        """Remove a fact from memory and vector store."""
        try:
            if fact_id in self.facts:
                del self.facts[fact_id]
                
            await self.qdrant.delete_vector(fact_id)
            
        except Exception as e:
            self.logger.error(f"Failed to remove fact {fact_id}: {e}")
            
    async def _decay_loop(self) -> None:
        """Background task for confidence decay."""
        while True:
            try:
                await asyncio.sleep(self.decay_interval)
                await self._apply_confidence_decay()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in decay loop: {e}")
                
    async def _apply_confidence_decay(self) -> None:
        """Apply time-based confidence decay to all facts."""
        current_time = datetime.now()
        
        for fact in self.facts.values():
            time_diff = (current_time - fact.last_updated).total_seconds()
            
            # Exponential decay
            decay_factor = math.exp(-fact.decay_rate * time_diff)
            fact.confidence *= decay_factor
            
            # Minimum confidence threshold
            fact.confidence = max(0.01, fact.confidence)
            
        self.logger.debug("Applied confidence decay to all facts")
        
    async def _load_facts(self) -> None:
        """Load facts from persistent storage."""
        try:
            data = await self.persistence.load("semantic_facts")
            if data:
                for fact_data in data:
                    fact = Fact(**fact_data)
                    self.facts[fact.id] = fact
                    
                self.logger.info(f"Loaded {len(self.facts)} facts from storage")
                
        except Exception as e:
            self.logger.error(f"Failed to load facts: {e}")
            
    async def _save_facts(self) -> None:
        """Save facts to persistent storage."""
        try:
            facts_data = []
            for fact in self.facts.values():
                fact_dict = fact.model_dump()
                fact_dict["tags"] = list(fact.tags)
                fact_dict["contradictions"] = list(fact.contradictions)
                fact_dict["supporting_facts"] = list(fact.supporting_facts)
                facts_data.append(fact_dict)
                
            await self.persistence.save("semantic_facts", facts_data)
            self.logger.info(f"Saved {len(facts_data)} facts to storage")
            
        except Exception as e:
            self.logger.error(f"Failed to save facts: {e}")

    async def health_check(self, *args, **kwargs):
        return dict()

    async def retrieve(self, *args, **kwargs):
        return dict()

    async def search(self, *args, **kwargs):
        return dict()

    async def store(self, *args, **kwargs):
        return dict()

    async def store_context(self, *args, **kwargs):
        return dict()

SemanticMemoryManager = SemanticMemory  # auto-alias