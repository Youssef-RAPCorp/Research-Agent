import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlencode, quote
from dataclasses import dataclass, field

import aiohttp
from pydantic import BaseModel, Field

from typing import TYPE_CHECKING  # noqa
from config.settings import get_settings
from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error


@dataclass
class ArxivPaper:
    """Data class representing an arXiv paper with metadata."""
    id: str
    title: str
    abstract: str
    authors: List[str]
    categories: List[str]
    published: datetime
    updated: datetime
    doi: Optional[str] = None
    journal_ref: Optional[str] = None
    pdf_url: Optional[str] = None
    latex_equations: List[str] = field(default_factory=list)
    citation_count: int = 0
    references: List[str] = field(default_factory=list)


class ArxivQuery(BaseModel):
    """Query parameters for arXiv API search."""
    search_query: str
    id_list: List[str] = Field(default_factory=list)
    start: int = Field(default=0)
    max_results: int = Field(default=10)
    sort_by: str = Field(default="relevance")
    sort_order: str = Field(default="descending")


class ArxivFetcher:
    """ArXiv API client for paper search and metadata retrieval."""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    def __init__(self, **kwargs):
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_delay = 3.0  # Respect arXiv API rate limits
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def search_papers(
        self, 
        query: str, 
        max_results: Optional[int] = None,
        categories: Optional[List[str]] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None
    ) -> List[ArxivPaper]:
        """Search arXiv papers with optional filters."""
        try:
            max_results = max_results or self.settings.arxiv_max_results
            
            # Build search query with categories and date filters
            search_terms = []
            
            if categories:
                cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
                search_terms.append(f"({cat_query})")
            
            # Add text search
            if query.strip():
                # Escape special characters and wrap in quotes for exact phrase matching
                escaped_query = query.replace('"', '\\"')
                search_terms.append(f'all:"{escaped_query}"')
            
            final_query = " AND ".join(search_terms) if search_terms else "all:physics"
            
            arxiv_query = ArxivQuery(
                search_query=final_query,
                max_results=max_results,
                sort_by="submittedDate",
                sort_order="descending"
            )
            
            papers = await self._fetch_papers(arxiv_query)
            
            # Apply date filtering post-fetch if specified
            if date_range:
                start_date, end_date = date_range
                papers = [
                    p for p in papers 
                    if start_date <= p.published <= end_date
                ]
            
            self.logger.info(f"Found {len(papers)} papers for query: {query}")
            return papers
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def get_paper_by_id(self, arxiv_id: str) -> Optional[ArxivPaper]:
        """Fetch a specific paper by arXiv ID."""
        try:
            # Clean the arXiv ID
            clean_id = arxiv_id.replace("arXiv:", "").replace("v", "")
            
            query = ArxivQuery(
                search_query="",
                id_list=[clean_id],
                max_results=1
            )
            
            papers = await self._fetch_papers(query)
            return papers[0] if papers else None
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def get_recent_papers(
        self, 
        categories: List[str], 
        days_back: int = 7,
        max_results: Optional[int] = None
    ) -> List[ArxivPaper]:
        """Get recent papers from specified categories."""
        try:
            max_results = max_results or self.settings.arxiv_max_results
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            # Search with category filter
            cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
            
            query = ArxivQuery(
                search_query=f"({cat_query})",
                max_results=max_results * 2,  # Fetch extra to account for date filtering
                sort_by="submittedDate",
                sort_order="descending"
            )
            
            papers = await self._fetch_papers(query)
            
            # Filter by date
            recent_papers = [
                p for p in papers 
                if p.published >= cutoff_date
            ][:max_results]
            
            self.logger.info(f"Found {len(recent_papers)} recent papers in {categories}")
            return recent_papers
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def _fetch_papers(self, query: ArxivQuery) -> List[ArxivPaper]:
        """Internal method to fetch papers from arXiv API."""
        if not self.session:
            raise RuntimeError("ArxivFetcher not properly initialized. Use as async context manager.")
        
        try:
            # Build API URL
            params = {
                "search_query": query.search_query,
                "start": query.start,
                "max_results": query.max_results,
                "sortBy": query.sort_by,
                "sortOrder": query.sort_order
            }
            
            if query.id_list:
                params["id_list"] = ",".join(query.id_list)
            
            url = f"{self.BASE_URL}?{urlencode(params)}"
            
            # Make API request with rate limiting
            await asyncio.sleep(self._rate_limit_delay)
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"ArXiv API error: {response.status}")
                    return []
                
                xml_content = await response.text()
                return self._parse_arxiv_response(xml_content)
                
        except Exception as e:
            handle_error(e)
            return []
    
    def _parse_arxiv_response(self, xml_content: str) -> List[ArxivPaper]:
        """Parse arXiv API XML response."""
        try:
            root = ET.fromstring(xml_content)
            
            # Define namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            papers = []
            
            for entry in root.findall('atom:entry', namespaces):
                try:
                    paper = self._parse_paper_entry(entry, namespaces)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    self.logger.warning(f"Failed to parse paper entry: {e}")
                    continue
            
            return papers
            
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse arXiv XML response: {e}")
            return []
    
    def _parse_paper_entry(self, entry: ET.Element, namespaces: Dict[str, str]) -> Optional[ArxivPaper]:
        """Parse individual paper entry from XML."""
        try:
            # Extract basic metadata
            title = entry.find('atom:title', namespaces)
            title_text = title.text.strip().replace('\n', ' ') if title is not None else ""
            
            summary = entry.find('atom:summary', namespaces)
            abstract_text = summary.text.strip().replace('\n', ' ') if summary is not None else ""
            
            # Extract arXiv ID
            id_elem = entry.find('atom:id', namespaces)
            arxiv_id = id_elem.text.split('/')[-1] if id_elem is not None else ""
            
            # Extract authors
            authors = []
            for author in entry.findall('atom:author', namespaces):
                name_elem = author.find('atom:name', namespaces)
                if name_elem is not None:
                    authors.append(name_elem.text)
            
            # Extract categories
            categories = []
            for category in entry.findall('atom:category', namespaces):
                term = category.get('term')
                if term:
                    categories.append(term)
            
            # Extract dates
            published_elem = entry.find('atom:published', namespaces)
            published_date = self._parse_date(published_elem.text) if published_elem is not None else datetime.now()
            
            updated_elem = entry.find('atom:updated', namespaces)
            updated_date = self._parse_date(updated_elem.text) if updated_elem is not None else published_date
            
            # Extract DOI and journal reference
            doi = None
            journal_ref = None
            
            doi_elem = entry.find('arxiv:doi', namespaces)
            if doi_elem is not None:
                doi = doi_elem.text
            
            journal_elem = entry.find('arxiv:journal_ref', namespaces)
            if journal_elem is not None:
                journal_ref = journal_elem.text
            
            # Extract PDF URL
            pdf_url = None
            for link in entry.findall('atom:link', namespaces):
                if link.get('type') == 'application/pdf':
                    pdf_url = link.get('href')
                    break
            
            # Extract LaTeX equations from abstract
            latex_equations = self.extract_latex_equations(abstract_text)
            
            return ArxivPaper(
                id=arxiv_id,
                title=title_text,
                abstract=abstract_text,
                authors=authors,
                categories=categories,
                published=published_date,
                updated=updated_date,
                doi=doi,
                journal_ref=journal_ref,
                pdf_url=pdf_url,
                latex_equations=latex_equations
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing paper entry: {e}")
            return None
    
    def _parse_date(self, date_string: str) -> datetime:
        """Parse date string from arXiv API."""
        try:
            # ArXiv dates are in ISO format
            return datetime.fromisoformat(date_string.replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception:
            return datetime.now()
    
    def extract_latex_equations(self, text: str) -> List[str]:
        """Extract LaTeX equations from text."""
        equations = []
        
        # Pattern for inline math: $...$
        inline_pattern = r'\$([^$]+)\$'
        inline_matches = re.findall(inline_pattern, text)
        equations.extend(inline_matches)
        
        # Pattern for display math: $$...$$
        display_pattern = r'\$\$([^$]+)\$\$'
        display_matches = re.findall(display_pattern, text)
        equations.extend(display_matches)
        
        # Pattern for \begin{equation}...\end{equation}
        equation_pattern = r'\\begin\{equation\}(.*?)\\end\{equation\}'
        equation_matches = re.findall(equation_pattern, text, re.DOTALL)
        equations.extend([eq.strip() for eq in equation_matches])
        
        # Pattern for \begin{align}...\end{align}
        align_pattern = r'\\begin\{align\}(.*?)\\end\{align\}'
        align_matches = re.findall(align_pattern, text, re.DOTALL)
        equations.extend([eq.strip() for eq in align_matches])
        
        # Clean and filter equations
        cleaned_equations = []
        for eq in equations:
            eq = eq.strip()
            if eq and len(eq) > 2:  # Filter out very short expressions
                cleaned_equations.append(eq)
        
        return cleaned_equations
    
    async def get_citation_info(self, arxiv_id: str) -> Dict[str, Any]:
        """Get citation information for a paper (placeholder for future implementation)."""
        # TODO: Integrate with citation databases like Semantic Scholar or CrossRef
        return {
            "citation_count": 0,
            "references": [],
            "citing_papers": []
        }
    
    async def search_by_author(self, author_name: str, max_results: Optional[int] = None) -> List[ArxivPaper]:
        """Search papers by author name."""
        try:
            max_results = max_results or self.settings.arxiv_max_results
            
            # Clean author name for search
            cleaned_name = author_name.strip().replace(' ', '_')
            search_query = f'au:"{cleaned_name}"'
            
            query = ArxivQuery(
                search_query=search_query,
                max_results=max_results,
                sort_by="submittedDate",
                sort_order="descending"
            )
            
            papers = await self._fetch_papers(query)
            self.logger.info(f"Found {len(papers)} papers by author: {author_name}")
            return papers
            
        except Exception as e:
            handle_error(e)
            return []
    
    def get_physics_categories(self) -> Dict[str, str]:
        """Get mapping of physics categories on arXiv."""
        return {
            "physics.gen-ph": "General Physics",
            "physics.class-ph": "Classical Physics", 
            "physics.comp-ph": "Computational Physics",
            "physics.data-an": "Data Analysis, Statistics and Probability",
            "physics.flu-dyn": "Fluid Dynamics",
            "physics.med-ph": "Medical Physics",
            "physics.optics": "Optics",
            "physics.ed-ph": "Physics Education",
            "physics.soc-ph": "Physics and Society",
            "physics.ao-ph": "Atmospheric and Oceanic Physics",
            "physics.atom-ph": "Atomic Physics",
            "physics.space-ph": "Space Physics",
            "physics.hist-ph": "History and Philosophy of Physics",
            "physics.ins-det": "Instrumentation and Detectors",
            "physics.plasm-ph": "Plasma Physics",
            "physics.pop-ph": "Popular Physics",
            "quant-ph": "Quantum Physics",
            "cond-mat": "Condensed Matter",
            "gr-qc": "General Relativity and Quantum Cosmology", 
            "hep-th": "High Energy Physics - Theory",
            "hep-ph": "High Energy Physics - Phenomenology",
            "hep-ex": "High Energy Physics - Experiment",
            "hep-lat": "High Energy Physics - Lattice",
            "nucl-th": "Nuclear Theory",
            "nucl-ex": "Nuclear Experiment",
            "astro-ph": "Astrophysics",
            "math-ph": "Mathematical Physics"
        }
    
    async def get_trending_topics(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Analyze trending topics in recent papers."""
        try:
            categories = list(self.get_physics_categories().keys())
            recent_papers = await self.get_recent_papers(categories, days_back, max_results=200)
            
            # Simple keyword frequency analysis
            word_freq = {}
            for paper in recent_papers:
                title_words = paper.title.lower().split()
                abstract_words = paper.abstract.lower().split()
                
                for word in title_words + abstract_words:
                    if len(word) > 4:  # Filter short words
                        word_freq[word] = word_freq.get(word, 0) + 1
            
            # Sort by frequency and return top trends
            trending = [
                {"keyword": word, "frequency": freq}
                for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]
            ]
            
            return trending
            
        except Exception as e:
            handle_error(e)
            return []


# Factory function for dependency injection
def get_arxiv_fetcher() -> ArxivFetcher:
    """Factory function to get ArxivFetcher instance."""
    return ArxivFetcher()

ArXivFetcher = ArxivFetcher  # auto-alias
BASE_URL = type('BASE_URL', (), {})  # auto-stub: not found in project

ET = type('ET', (), {})  # auto-stub: not found in project
