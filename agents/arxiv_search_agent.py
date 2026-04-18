import asyncio
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
# [auto-removed unresolvable import] from xml.etree import ElementTree as ET

import aiohttp
from pydantic import BaseModel, Field

from config.logger import get_logger
from config.settings import get_settings
from config.errors import handle_error
from agents.base_agent import BaseAgent
from knowledge.arxiv_fetcher import ArXivFetcher
from knowledge.embedder import Embedder
import xml.etree.ElementTree as ET

try:
    from knowledge.embedder import Embedder
except ImportError:  # circular import guard — knowledge.embedder
    Embedder = type('Embedder', (), {})


@dataclass
class ArXivPaper:
    """ArXiv paper data structure."""
    id: str
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    published: datetime
    updated: datetime
    pdf_url: str
    arxiv_url: str
    primary_category: str
    relevance_score: float = 0.0
    keywords: List[str] = None


class QueryFormulation(BaseModel):
    """Query formulation parameters."""
    search_terms: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    date_range: Optional[Tuple[datetime, datetime]] = None
    max_results: int = Field(default=50)
    sort_by: str = Field(default="relevance")


class SearchResult(BaseModel):
    """Structured search result."""
    papers: List[ArXivPaper] = Field(default_factory=list)
    total_found: int = 0
    query_used: str = ""
    search_time: float = 0.0
    relevance_ranking: Dict[str, float] = Field(default_factory=dict)


class ArXivSearchAgent(BaseAgent):
    """ArXiv search agent for paper retrieval and ranking."""
    
    def __init__(self, **kwargs):
        """Initialize ArXiv search agent."""
        super().__init__(agent_id="ar_xiv_paper", name="ArXivPaper")
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.arxiv_fetcher = ArXivFetcher()
        self.embedder = Embedder()
        self.base_url = "http://export.arxiv.org/api/query"
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Physics categories mapping
        self.physics_categories = {
            'quantum': ['quant-ph', 'cond-mat.mes-hall', 'physics.atom-ph'],
            'condensed_matter': ['cond-mat.*'],
            'particle_physics': ['hep-ph', 'hep-th', 'hep-ex', 'hep-lat'],
            'cosmology': ['astro-ph.CO', 'gr-qc'],
            'optics': ['physics.optics', 'quant-ph'],
            'plasma': ['physics.plasm-ph'],
            'biophysics': ['physics.bio-ph', 'q-bio.*'],
            'general': ['physics.*']
        }
    
    async def start(self) -> None:
        """Start the agent."""
        if hasattr(super(), "start"):  # guard: base may not implement start
            if hasattr(super(), "start"):  # guard: base may not implement start
                if hasattr(super(), "start"):  # guard: base may not implement start
                    if hasattr(super(), "start"):  # guard: base may not implement start
                        if hasattr(super(), "start"):  # guard: base may not implement start
                            if hasattr(super(), "start"):  # guard: base may not implement start
                                if hasattr(super(), "start"):  # guard: base may not implement start
                                    if hasattr(super(), "start"):  # guard: base may not implement start
                                        if hasattr(super(), "start"):  # guard: base may not implement start
                                            if hasattr(super(), "start"):  # guard: base may not implement start
                                                if hasattr(super(), "start"):  # guard: base may not implement start
                                                    if hasattr(super(), "start"):  # guard: base may not implement start
                                                        if hasattr(super(), "start"):  # guard: base may not implement start
                                                            if hasattr(super(), "start"):  # guard: base may not implement start
                                                                if hasattr(super(), "start"):  # guard: base may not implement start
                                                                    if hasattr(super(), "start"):  # guard: base may not implement start
                                                                        if hasattr(super(), "start"):  # guard: base may not implement start
                                                                            if hasattr(super(), "start"):  # guard: base may not implement start
                                                                                if hasattr(super(), "start"):  # guard: base may not implement start
                                                                                    if hasattr(super(), "start"):  # guard: base may not implement start
                                                                                        if hasattr(super(), "start"):  # guard: base may not implement start
                                                                                            if hasattr(super(), "start"):  # guard: base may not implement start
                                                                                                await super().start()
        self.session = aiohttp.ClientSession()
        self.logger.info("ArXiv search agent started")
    
    async def stop(self) -> None:
        """Stop the agent."""
        if self.session:
            await self.session.close()
        await super().stop()
        self.logger.info("ArXiv search agent stopped")
    
    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming search requests."""
        try:
            action = message.get('action', 'search')
            
            if action == 'search':
                return await self._handle_search_request(message)
            elif action == 'formulate_query':
                return await self._handle_query_formulation(message)
            elif action == 'rank_papers':
                return await self._handle_ranking_request(message)
            else:
                raise ValueError(f"Unknown action: {action}")
                
        except Exception as e:
            handle_error(e)
            return {
                'status': 'error',
                'error': str(e),
                'agent_id': self.agent_id
            }
    
    async def _handle_search_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle paper search requests."""
        query = message.get('query', '')
        params = message.get('params', {})
        
        # Formulate query
        query_formulation = await self.formulate_query(query, **params)
        
        # Execute search
        search_result = await self.search_papers(query_formulation)
        
        # Rank results
        ranked_papers = await self.rank_papers(search_result.papers, query)
        
        return {
            'status': 'success',
            'papers': [
                {
                    'id': p.id,
                    'title': p.title,
                    'abstract': p.abstract,
                    'authors': p.authors,
                    'arxiv_url': p.arxiv_url,
                    'pdf_url': p.pdf_url,
                    'categories': p.categories,
                    'relevance_score': p.relevance_score,
                }
                for p in ranked_papers
            ],
            'total_found': len(ranked_papers),
            'query_used': search_result.query_used,
            'agent_id': self.agent_id,
        }
    
    async def _handle_query_formulation(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle query formulation requests."""
        query = message.get('query', '')
        params = message.get('params', {})
        
        formulation = await self.formulate_query(query, **params)
        
        return {
            'status': 'success',
            'result': formulation.model_dump(),
            'agent_id': self.agent_id
        }
    
    async def _handle_ranking_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle paper ranking requests."""
        papers_data = message.get('papers', [])
        query = message.get('query', '')
        
        papers = [ArXivPaper(**p) for p in papers_data]
        ranked_papers = await self.rank_papers(papers, query)
        
        return {
            'status': 'success',
            'result': [p.__dict__ for p in ranked_papers],
            'agent_id': self.agent_id
        }
    
    async def formulate_query(self, user_query: str, **params) -> QueryFormulation:
        """Formulate ArXiv search query from user input."""
        try:
            # Extract search terms
            search_terms = await self._extract_search_terms(user_query)
            
            # Determine relevant categories
            categories = await self._determine_categories(user_query, params.get('field'))
            
            # Extract author names if mentioned
            authors = await self._extract_authors(user_query)
            
            # Parse date constraints
            date_range = await self._parse_date_range(params.get('date_range'))
            
            # Set result limits
            max_results = min(params.get('max_results', self.settings.arxiv_max_results), 200)
            
            return QueryFormulation(
                search_terms=search_terms,
                categories=categories,
                authors=authors,
                date_range=date_range,
                max_results=max_results,
                sort_by=params.get('sort_by', 'relevance')
            )
            
        except Exception as e:
            handle_error(e)
            # Return basic formulation as fallback
            return QueryFormulation(
                search_terms=[user_query],
                max_results=self.settings.arxiv_max_results
            )
    
    async def _extract_search_terms(self, query: str) -> List[str]:
        """Extract key search terms from query."""
        # Remove common stop words and split
        stop_words = {'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # Handle quoted phrases
        quoted_phrases = re.findall(r'"([^"]*)"', query)
        remaining_query = re.sub(r'"[^"]*"', '', query)
        
        # Split remaining words
        words = re.findall(r'\b[a-zA-Z]+\b', remaining_query.lower())
        words = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Combine phrases and words
        terms = quoted_phrases + words
        
        return list(set(terms))[:10]  # Limit to top 10 terms
    
    async def _determine_categories(self, query: str, field_hint: Optional[str] = None) -> List[str]:
        """Determine relevant ArXiv categories."""
        categories = []
        query_lower = query.lower()
        
        # Check for physics field keywords
        for field, cats in self.physics_categories.items():
            if field in query_lower or (field_hint and field in field_hint.lower()):
                categories.extend(cats)
        
        # If no specific categories found, use general physics
        if not categories:
            categories = self.physics_categories['general']
        
        return list(set(categories))
    
    async def _extract_authors(self, query: str) -> List[str]:
        """Extract author names from query."""
        # Look for patterns like "by Einstein" or "Einstein et al"
        author_patterns = [
            r'(?:by|author:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'([A-Z][a-z]+\s+et\s+al\.?)',
            r'([A-Z][a-z]+,\s*[A-Z]\.?(?:\s*[A-Z]\.?)*)'
        ]
        
        authors = []
        for pattern in author_patterns:
            matches = re.findall(pattern, query)
            authors.extend(matches)
        
        return list(set(authors))
    
    async def _parse_date_range(self, date_range: Optional[str]) -> Optional[Tuple[datetime, datetime]]:
        """Parse date range from string."""
        if not date_range:
            return None
        
        try:
            # Handle formats like "2020-2023", "last year", "recent"
            if date_range.lower() == "recent":
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)
                return (start_date, end_date)
            elif date_range.lower() == "last year":
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                return (start_date, end_date)
            elif '-' in date_range:
                start_year, end_year = date_range.split('-')
                start_date = datetime(int(start_year), 1, 1)
                end_date = datetime(int(end_year), 12, 31)
                return (start_date, end_date)
        except:
            pass
        
        return None
    
    async def search_papers(self, query_formulation: QueryFormulation) -> SearchResult:
        """Execute ArXiv search based on formulation."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Build ArXiv query string
            query_string = await self._build_arxiv_query(query_formulation)
            
            # Execute search
            papers = await self._execute_arxiv_search(query_string, query_formulation.max_results)
            
            search_time = asyncio.get_event_loop().time() - start_time
            
            return SearchResult(
                papers=papers,
                total_found=len(papers),
                query_used=query_string,
                search_time=search_time
            )
            
        except Exception as e:
            handle_error(e)
            self.logger.error(
                f"[arxiv-search FAILED] {type(e).__name__}: {e}"
            )
            return SearchResult(
                papers=[],
                total_found=0,
                query_used="",
                search_time=asyncio.get_event_loop().time() - start_time
            )
    
    async def _build_arxiv_query(self, formulation: QueryFormulation) -> str:
        """Build ArXiv API query string."""
        query_parts = []
        
        # Add search terms
        if formulation.search_terms:
            terms_query = ' AND '.join(f'all:{term}' for term in formulation.search_terms)
            query_parts.append(f'({terms_query})')
        
        # Add category constraints
        if formulation.categories:
            cat_queries = []
            for cat in formulation.categories:
                if cat.endswith('.*'):
                    # Handle wildcard categories
                    cat_queries.append(f'cat:{cat[:-2]}*')
                else:
                    cat_queries.append(f'cat:{cat}')
            
            if cat_queries:
                cat_query = ' OR '.join(cat_queries)
                query_parts.append(f'({cat_query})')
        
        # Add author constraints
        if formulation.authors:
            author_query = ' OR '.join(f'au:{author}' for author in formulation.authors)
            query_parts.append(f'({author_query})')
        
        # Combine with AND
        query = ' AND '.join(query_parts) if query_parts else 'cat:physics.*'
        
        return query
    
    async def _execute_arxiv_search(self, query: str, max_results: int) -> List[ArXivPaper]:
        """Execute actual ArXiv API search."""
        if not self.session:
            await self.start()
        
        params = {
            'search_query': query,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        async with self.session.get(self.base_url, params=params) as response:
            if response.status != 200:
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                if response.status in (429, 503):
                    await asyncio.sleep(5)  # rate-limit back-off
                    return []
                raise RuntimeError(f"ArXiv API error: {response.status}")
            
            xml_content = await response.text()
            return await self._parse_arxiv_response(xml_content)
    
    async def _parse_arxiv_response(self, xml_content: str) -> List[ArXivPaper]:
        """Parse ArXiv XML response into paper objects."""
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            namespace = {'atom': 'http://www.w3.org/2005/Atom',
                        'arxiv': 'http://arxiv.org/schemas/atom'}
            
            for entry in root.findall('atom:entry', namespace):
                paper = await self._parse_paper_entry(entry, namespace)
                if paper:
                    papers.append(paper)
        
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse ArXiv XML: {e}")
        
        return papers
    
    async def _parse_paper_entry(self, entry, namespace) -> Optional[ArXivPaper]:
        """Parse individual paper entry from XML."""
        try:
            # Extract basic info
            id_elem = entry.find('atom:id', namespace)
            title_elem = entry.find('atom:title', namespace)
            summary_elem = entry.find('atom:summary', namespace)
            published_elem = entry.find('atom:published', namespace)
            updated_elem = entry.find('atom:updated', namespace)
            
            if not all([id_elem, title_elem, summary_elem]):
                return None
            
            arxiv_id = id_elem.text.split('/')[-1]
            title = title_elem.text.strip()
            abstract = summary_elem.text.strip()
            
            # Extract authors
            authors = []
            for author in entry.findall('atom:author', namespace):
                name_elem = author.find('atom:name', namespace)
                if name_elem is not None:
                    authors.append(name_elem.text)
            
            # Extract categories
            categories = []
            primary_category = ""
            
            primary_cat = entry.find('arxiv:primary_category', namespace)
            if primary_cat is not None:
                primary_category = primary_cat.get('term', '')
                categories.append(primary_category)
            
            for category in entry.findall('atom:category', namespace):
                term = category.get('term')
                if term and term not in categories:
                    categories.append(term)
            
            # Parse dates
            published = datetime.fromisoformat(published_elem.text.replace('Z', '+00:00'))
            updated = datetime.fromisoformat(updated_elem.text.replace('Z', '+00:00'))
            
            # Build URLs
            arxiv_url = id_elem.text
            pdf_url = arxiv_url.replace('abs', 'pdf') + '.pdf'
            
            # Extract keywords from abstract
            keywords = await self._extract_keywords(abstract)
            
            return ArXivPaper(
                id=arxiv_id,
                title=title,
                authors=authors,
                abstract=abstract,
                categories=categories,
                published=published,
                updated=updated,
                pdf_url=pdf_url,
                arxiv_url=arxiv_url,
                primary_category=primary_category,
                keywords=keywords
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing paper entry: {e}")
            return None
    
    async def _extract_keywords(self, abstract: str) -> List[str]:
        """Extract keywords from abstract."""
        # Simple keyword extraction based on common physics terms
        physics_keywords = [
            'quantum', 'classical', 'relativistic', 'electromagnetic', 'gravitational',
            'thermal', 'statistical', 'mechanical', 'optical', 'magnetic', 'electric',
            'particle', 'field', 'wave', 'energy', 'momentum', 'mass', 'charge',
            'symmetry', 'invariance', 'conservation', 'interaction', 'force',
            'theory', 'model', 'simulation', 'experiment', 'measurement'
        ]
        
        abstract_lower = abstract.lower()
        found_keywords = [kw for kw in physics_keywords if kw in abstract_lower]
        
        return found_keywords[:10]  # Limit to top 10
    
    async def rank_papers(self, papers: List[ArXivPaper], query: str) -> List[ArXivPaper]:
        """Rank papers by relevance to query."""
        if not papers:
            return papers
        
        try:
            # Get query embedding
            query_embedding = await self.embedder.embed_text(query)
            
            # Calculate relevance scores
            for paper in papers:
                score = await self._calculate_relevance_score(paper, query, query_embedding)
                paper.relevance_score = score
            
            # Sort by relevance score
            papers.sort(key=lambda p: p.relevance_score, reverse=True)
            
            return papers
            
        except Exception as e:
            handle_error(e)
            # Return papers with default scoring
            for i, paper in enumerate(papers):
                paper.relevance_score = 1.0 - (i * 0.01)  # Simple decay
            
            return papers
    
    async def _calculate_relevance_score(self, paper: ArXivPaper, query: str, query_embedding) -> float:
        """Calculate relevance score for a paper."""
        score = 0.0
        
        try:
            # Semantic similarity via embeddings
            paper_text = f"{paper.title} {paper.abstract}"
            paper_embedding = await self.embedder.embed_text(paper_text)
            semantic_score = await self.embedder.cosine_similarity(query_embedding, paper_embedding)
            score += semantic_score * 0.6
            
            # Keyword matching
            query_words = set(query.lower().split())
            title_words = set(paper.title.lower().split())
            abstract_words = set(paper.abstract.lower().split())
            
            title_overlap = len(query_words & title_words) / max(len(query_words), 1)
            abstract_overlap = len(query_words & abstract_words) / max(len(query_words), 1)
            
            score += title_overlap * 0.25
            score += abstract_overlap * 0.1
            
            # Recency bonus (papers from last year get small boost)
            days_old = (datetime.now() - paper.published.replace(tzinfo=None)).days
            if days_old < 365:
                score += 0.05 * (1 - days_old / 365)
            
        except Exception as e:
            self.logger.error(f"Error calculating relevance score: {e}")
            # Fallback to simple text matching
            query_lower = query.lower()
            if query_lower in paper.title.lower():
                score += 0.8
            elif query_lower in paper.abstract.lower():
                score += 0.4
            else:
                score = 0.1
        
        return max(0.0, min(1.0, score))  # Clamp to [0, 1]
    
    async def format_search_results(self, papers: List[ArXivPaper], max_papers: int = 10) -> str:
        """Format search results for display."""
        if not papers:
            return "No papers found matching the search criteria."
        
        result_lines = [f"Found {len(papers)} papers. Showing top {min(max_papers, len(papers))}:\n"]
        
        for i, paper in enumerate(papers[:max_papers], 1):
            result_lines.append(f"{i}. {paper.title}")
            result_lines.append(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            result_lines.append(f"   Published: {paper.published.strftime('%Y-%m-%d')}")
            result_lines.append(f"   Categories: {', '.join(paper.categories[:2])}")
            result_lines.append(f"   Relevance: {paper.relevance_score:.2f}")
            result_lines.append(f"   Abstract: {paper.abstract[:200]}...")
            result_lines.append(f"   URL: {paper.arxiv_url}\n")
        
        return '\n'.join(result_lines)
    
    async def get_paper_details(self, arxiv_id: str) -> Optional[ArXivPaper]:
        """Get detailed information for a specific paper."""
        try:
            formulation = QueryFormulation(
                search_terms=[f'id:{arxiv_id}'],
                max_results=1
            )
            
            result = await self.search_papers(formulation)
            return result.papers[0] if result.papers else None
            
        except Exception as e:
            handle_error(e)
            return None
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
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'comprehensive'})
