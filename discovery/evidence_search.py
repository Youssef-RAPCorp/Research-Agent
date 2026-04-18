import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from typing import TYPE_CHECKING  # noqa
from config.settings import get_settings
from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error
from knowledge.retrieval import RetrievalEngine
from knowledge.arxiv_fetcher import ArxivFetcher
from knowledge.embedder import Embedder
from knowledge.validator import KnowledgeValidator

logger = get_logger(__name__)

@dataclass
class Evidence:
    """Represents a piece of evidence with metadata."""
    content: str
    source: str
    relevance_score: float
    type: str  # 'support' or 'challenge'
    confidence: float
    metadata: Dict[str, Any]
    retrieved_at: datetime

class EvidenceSearchEngine:
    """Parallel evidence search engine for hypothesis testing."""
    
    def __init__(self, **kwargs):
        self.settings = get_settings()
        self.retrieval_engine = RetrievalEngine()
        self.arxiv_fetcher = ArxivFetcher()
        self.embedder = Embedder()
        self.validator = KnowledgeValidator()
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def search_evidence(
        self, 
        hypothesis: str, 
        support_weight: float = 0.7,
        challenge_weight: float = 0.3,
        max_results: int = 20
    ) -> List[Evidence]:
        """Search for both supporting and challenging evidence in parallel."""
        try:
            # Split search between support and challenge based on weights
            support_count = int(max_results * support_weight)
            challenge_count = max_results - support_count
            
            # Run parallel searches
            support_task = self._search_supporting_evidence(hypothesis, support_count)
            challenge_task = self._search_challenging_evidence(hypothesis, challenge_count)
            
            support_evidence, challenge_evidence = await asyncio.gather(
                support_task, challenge_task, return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(support_evidence, Exception):
                logger.error(f"Support evidence search failed: {support_evidence}")
                support_evidence = []
            if isinstance(challenge_evidence, Exception):
                logger.error(f"Challenge evidence search failed: {challenge_evidence}")
                challenge_evidence = []
            
            # Combine and rank all evidence
            all_evidence = support_evidence + challenge_evidence
            ranked_evidence = await self._rank_evidence(all_evidence, hypothesis)
            
            logger.info(f"Found {len(ranked_evidence)} evidence items for hypothesis")
            return ranked_evidence
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def _search_supporting_evidence(self, hypothesis: str, max_results: int) -> List[Evidence]:
        """Search for evidence that supports the hypothesis."""
        evidence_list = []
        
        # Parallel search across multiple sources
        tasks = [
            self._search_vector_store(hypothesis, "support", max_results // 2),
            self._search_arxiv(hypothesis, "support", max_results // 2)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                evidence_list.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Supporting evidence search failed: {result}")
        
        return evidence_list
    
    async def _search_challenging_evidence(self, hypothesis: str, max_results: int) -> List[Evidence]:
        """Search for evidence that challenges the hypothesis."""
        evidence_list = []
        
        # Generate counter-queries
        counter_queries = await self._generate_counter_queries(hypothesis)
        
        # Parallel search with counter-queries
        tasks = []
        for query in counter_queries[:3]:  # Limit to 3 counter-queries
            tasks.append(self._search_vector_store(query, "challenge", max_results // 3))
            tasks.append(self._search_arxiv(query, "challenge", max_results // 3))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                evidence_list.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Challenging evidence search failed: {result}")
        
        return evidence_list
    
    async def _search_vector_store(self, query: str, evidence_type: str, max_results: int) -> List[Evidence]:
        """Search the vector store for relevant evidence."""
        try:
            # Run retrieval in thread pool
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                self.executor,
                self.retrieval_engine.search,
                query,
                max_results
            )
            
            evidence_list = []
            for result in results:
                evidence = Evidence(
                    content=result.get('content', ''),
                    source=f"vector_store:{result.get('source', 'unknown')}",
                    relevance_score=result.get('score', 0.0),
                    type=evidence_type,
                    confidence=result.get('score', 0.0),
                    metadata=result.get('metadata', {}),
                    retrieved_at=datetime.now()
                )
                evidence_list.append(evidence)
            
            return evidence_list
            
        except Exception as e:
            logger.error(f"Vector store search failed: {e}")
            return []
    
    async def _search_arxiv(self, query: str, evidence_type: str, max_results: int) -> List[Evidence]:
        """Search ArXiv for relevant papers."""
        try:
            # Run ArXiv search in thread pool
            loop = asyncio.get_event_loop()
            papers = await loop.run_in_executor(
                self.executor,
                self.arxiv_fetcher.search_papers,
                query,
                max_results
            )
            
            evidence_list = []
            for paper in papers:
                # Calculate relevance using embeddings
                relevance = await self._calculate_relevance(query, paper.get('abstract', ''))
                
                evidence = Evidence(
                    content=paper.get('abstract', ''),
                    source=f"arxiv:{paper.get('id', 'unknown')}",
                    relevance_score=relevance,
                    type=evidence_type,
                    confidence=relevance * 0.8,  # ArXiv papers are generally reliable
                    metadata={
                        'title': paper.get('title', ''),
                        'authors': paper.get('authors', []),
                        'published': paper.get('published', ''),
                        'url': paper.get('url', '')
                    },
                    retrieved_at=datetime.now()
                )
                evidence_list.append(evidence)
            
            return evidence_list
            
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            return []
    
    async def _generate_counter_queries(self, hypothesis: str) -> List[str]:
        """Generate queries to find counter-evidence."""
        counter_queries = [
            f"limitations of {hypothesis}",
            f"contradictions to {hypothesis}",
            f"alternative theories to {hypothesis}",
            f"experimental failures of {hypothesis}",
            f"criticisms of {hypothesis}"
        ]
        
        # Extract key terms from hypothesis for more specific counter-queries
        key_terms = await self._extract_key_terms(hypothesis)
        for term in key_terms[:3]:  # Limit to 3 key terms
            counter_queries.append(f"problems with {term}")
            counter_queries.append(f"{term} experimental challenges")
        
        return counter_queries
    
    async def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key physics terms from text."""
        # Simple keyword extraction - in production, use NLP models
        physics_keywords = [
            'quantum', 'relativity', 'entropy', 'energy', 'momentum', 
            'field', 'particle', 'wave', 'symmetry', 'conservation'
        ]
        
        words = text.lower().split()
        key_terms = [word for word in words if word in physics_keywords]
        return list(set(key_terms))
    
    async def _calculate_relevance(self, query: str, content: str) -> float:
        """Calculate relevance score between query and content using embeddings."""
        try:
            # Run embedding calculation in thread pool
            loop = asyncio.get_event_loop()
            similarity = await loop.run_in_executor(
                self.executor,
                self.embedder.calculate_similarity,
                query,
                content
            )
            return float(similarity)
        except Exception as e:
            logger.warning(f"Relevance calculation failed: {e}")
            return 0.5  # Default relevance
    
    async def _rank_evidence(self, evidence_list: List[Evidence], hypothesis: str) -> List[Evidence]:
        """Rank evidence by relevance and quality."""
        try:
            # Validate evidence quality
            for evidence in evidence_list:
                evidence.confidence *= await self._assess_evidence_quality(evidence)
            
            # Sort by combined relevance and confidence
            ranked = sorted(
                evidence_list,
                key=lambda e: (e.relevance_score * 0.6 + e.confidence * 0.4),
                reverse=True
            )
            
            # Remove duplicates based on content similarity
            deduplicated = await self._deduplicate_evidence(ranked)
            
            return deduplicated
            
        except Exception as e:
            logger.error(f"Evidence ranking failed: {e}")
            return evidence_list
    
    async def _assess_evidence_quality(self, evidence: Evidence) -> float:
        """Assess the quality of evidence based on various factors."""
        quality_score = 1.0
        
        # Source credibility
        if 'arxiv' in evidence.source:
            quality_score *= 0.9  # ArXiv papers are peer-reviewed
        elif 'vector_store' in evidence.source:
            quality_score *= 0.8  # Depends on vector store content quality
        
        # Content length - very short content is less reliable
        if len(evidence.content) < 100:
            quality_score *= 0.7
        elif len(evidence.content) > 1000:
            quality_score *= 0.9
        
        # Recency for ArXiv papers
        if evidence.metadata.get('published'):
            try:
                pub_date = datetime.fromisoformat(evidence.metadata['published'])
                days_old = (datetime.now() - pub_date).days
                if days_old < 365:  # Recent papers get boost
                    quality_score *= 1.1
                elif days_old > 3650:  # Very old papers get slight penalty
                    quality_score *= 0.9
            except:
                pass
        
        return min(quality_score, 1.0)
    
    async def _deduplicate_evidence(self, evidence_list: List[Evidence]) -> List[Evidence]:
        """Remove duplicate evidence based on content similarity."""
        if len(evidence_list) <= 1:
            return evidence_list
        
        deduplicated = []
        similarity_threshold = 0.85
        
        for evidence in evidence_list:
            is_duplicate = False
            
            for existing in deduplicated:
                try:
                    similarity = await self._calculate_relevance(
                        evidence.content, existing.content
                    )
                    if similarity > similarity_threshold:
                        is_duplicate = True
                        # Keep the one with higher confidence
                        if evidence.confidence > existing.confidence:
                            deduplicated.remove(existing)
                            deduplicated.append(evidence)
                        break
                except:
                    continue
            
            if not is_duplicate:
                deduplicated.append(evidence)
        
        return deduplicated
    
    async def search_targeted_evidence(
        self, 
        hypothesis: str, 
        focus_areas: List[str],
        evidence_type: str = "both"
    ) -> List[Evidence]:
        """Search for evidence in specific focus areas."""
        all_evidence = []
        
        for area in focus_areas:
            targeted_query = f"{hypothesis} {area}"
            
            if evidence_type in ["support", "both"]:
                support_evidence = await self._search_supporting_evidence(
                    targeted_query, self.settings.retrieval_top_k // len(focus_areas)
                )
                all_evidence.extend(support_evidence)
            
            if evidence_type in ["challenge", "both"]:
                challenge_evidence = await self._search_challenging_evidence(
                    targeted_query, self.settings.retrieval_top_k // len(focus_areas)
                )
                all_evidence.extend(challenge_evidence)
        
        return await self._rank_evidence(all_evidence, hypothesis)
    
    async def get_evidence_summary(self, evidence_list: List[Evidence]) -> Dict[str, Any]:
        """Generate a summary of evidence findings."""
        if not evidence_list:
            return {
                'total_evidence': 0,
                'support_count': 0,
                'challenge_count': 0,
                'avg_relevance': 0.0,
                'avg_confidence': 0.0,
                'sources': []
            }
        
        support_count = len([e for e in evidence_list if e.type == 'support'])
        challenge_count = len([e for e in evidence_list if e.type == 'challenge'])
        
        avg_relevance = sum(e.relevance_score for e in evidence_list) / len(evidence_list)
        avg_confidence = sum(e.confidence for e in evidence_list) / len(evidence_list)
        
        sources = list(set([e.source.split(':')[0] for e in evidence_list]))
        
        return {
            'total_evidence': len(evidence_list),
            'support_count': support_count,
            'challenge_count': challenge_count,
            'support_ratio': support_count / len(evidence_list),
            'avg_relevance': round(avg_relevance, 3),
            'avg_confidence': round(avg_confidence, 3),
            'sources': sources,
            'top_evidence': evidence_list[:5]  # Top 5 pieces of evidence
        }
    async def search_contradicting_evidence(self, *args, **kwargs):
        return dict()

    async def search_supporting_evidence(self, *args, **kwargs):
        return dict()
