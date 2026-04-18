"""Citation Tracker - Reference graph builder and impact analysis system."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import quote

import aiohttp
import networkx as nx
from pydantic import BaseModel, Field

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error


@dataclass
class Citation:
    """Single citation record."""
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    cited_by_count: int = 0
    references: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Normalize identifiers."""
        if self.doi:
            self.doi = self.doi.lower().strip()
        if self.arxiv_id:
            self.arxiv_id = self.arxiv_id.strip()


@dataclass
class Author:
    """Author profile and metrics."""
    name: str
    orcid: Optional[str] = None
    affiliations: List[str] = field(default_factory=list)
    h_index: int = 0
    citation_count: int = 0
    paper_count: int = 0
    coauthors: Set[str] = field(default_factory=set)
    fields: List[str] = field(default_factory=list)


class CitationMetrics(BaseModel):
    """Citation network metrics."""
    total_papers: int = 0
    total_citations: int = 0
    h_index: int = 0
    average_citations: float = 0.0
    collaboration_index: float = 0.0
    recent_impact: float = 0.0


class CitationManager:
    """Reference graph builder with DOI resolution and impact tracking."""
    
    def __init__(self, **kwargs):
        """Initialize citation manager."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.citation_graph = nx.DiGraph()
        self.citations: Dict[str, Citation] = {}
        self.authors: Dict[str, Author] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            
    async def resolve_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Resolve DOI to citation metadata."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'RAP-Physics-Discovery/3.0'
            }
            
            # Clean DOI
            clean_doi = doi.strip().lower()
            if clean_doi.startswith('doi:'):
                clean_doi = clean_doi[4:]
            if clean_doi.startswith('http'):
                clean_doi = clean_doi.split('doi.org/')[-1]
                
            url = f"https://api.crossref.org/works/{quote(clean_doi)}"
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.model_dump_json()
                    return self._parse_crossref_data(data.get('message', {}))
                else:
                    self.logger.warning(f"DOI resolution failed: {response.status}")
                    return None
                    
        except Exception as e:
            handle_error(e)
            return None
            
    def _parse_crossref_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse CrossRef API response."""
        try:
            # Extract basic metadata
            result = {
                'doi': data.get('DOI', '').lower(),
                'title': '',
                'authors': [],
                'year': None,
                'journal': '',
                'references': [],
                'cited_by_count': data.get('is-referenced-by-count', 0)
            }
            
            # Title
            titles = data.get('title', [])
            if titles:
                result['title'] = titles[0]
                
            # Authors
            authors = data.get('author', [])
            for author in authors:
                given = author.get('given', '')
                family = author.get('family', '')
                if family:
                    full_name = f"{given} {family}".strip()
                    result['authors'].append(full_name)
                    
            # Publication year
            published = data.get('published-print') or data.get('published-online')
            if published and 'date-parts' in published:
                date_parts = published['date-parts'][0]
                if date_parts:
                    result['year'] = date_parts[0]
                    
            # Journal
            container = data.get('container-title', [])
            if container:
                result['journal'] = container[0]
                
            # References
            references = data.get('reference', [])
            for ref in references:
                if 'DOI' in ref:
                    result['references'].append(ref['DOI'].lower())
                    
            return result
            
        except Exception as e:
            handle_error(e)
            return {}
            
    async def fetch_semantic_scholar_data(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Fetch data from Semantic Scholar API."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            # TODO: Add Semantic Scholar API key to settings
            headers = {
                'User-Agent': 'RAP-Physics-Discovery/3.0',
                'Accept': 'application/json'
            }
            
            # Determine identifier type
            if identifier.startswith('10.'):
                url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{identifier}"
            elif 'arxiv' in identifier.lower() or identifier.count('.') >= 1:
                url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{identifier}"
            else:
                url = f"https://api.semanticscholar.org/graph/v1/paper/{identifier}"
                
            # Request fields
            fields = "title,authors,year,journal,citationCount,referenceCount,references,citations"
            url += f"?fields={fields}"
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.model_dump_json()
                else:
                    self.logger.warning(f"Semantic Scholar API failed: {response.status}")
                    return None
                    
        except Exception as e:
            handle_error(e)
            return None
            
    async def add_citation(self, identifier: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[Citation]:
        """Add citation to the graph."""
        try:
            # Check if already exists
            if identifier in self.citations:
                return self.citations[identifier]
                
            # Resolve metadata if not provided
            if not metadata:
                if identifier.startswith('10.'):
                    metadata = await self.resolve_doi(identifier)
                else:
                    metadata = await self.fetch_semantic_scholar_data(identifier)
                    
            if not metadata:
                self.logger.warning(f"Could not resolve metadata for {identifier}")
                return None
                
            # Create citation object
            citation = Citation(
                doi=metadata.get('doi') if identifier.startswith('10.') else None,
                arxiv_id=identifier if not identifier.startswith('10.') else None,
                title=metadata.get('title', ''),
                authors=metadata.get('authors', []),
                year=metadata.get('year'),
                journal=metadata.get('journal', ''),
                cited_by_count=metadata.get('cited_by_count', 0),
                references=metadata.get('references', [])
            )
            
            # Store citation
            self.citations[identifier] = citation
            
            # Add to graph
            self.citation_graph.add_node(identifier, **metadata)
            
            # Add reference edges
            for ref_id in citation.references:
                if ref_id != identifier:  # Avoid self-loops
                    self.citation_graph.add_edge(identifier, ref_id)
                    
            # Update author profiles
            await self._update_author_profiles(citation)
            
            return citation
            
        except Exception as e:
            handle_error(e)
            return None
            
    async def _update_author_profiles(self, citation: Citation) -> None:
        """Update author profiles with citation data."""
        try:
            for author_name in citation.authors:
                if author_name not in self.authors:
                    self.authors[author_name] = Author(name=author_name)
                    
                author = self.authors[author_name]
                author.paper_count += 1
                author.citation_count += citation.cited_by_count
                
                # Add coauthors
                for coauthor in citation.authors:
                    if coauthor != author_name:
                        author.coauthors.add(coauthor)
                        
                # Infer field from journal or title
                if citation.journal:
                    field = self._infer_research_field(citation.journal, citation.title)
                    if field and field not in author.fields:
                        author.fields.append(field)
                        
        except Exception as e:
            handle_error(e)
            
    def _infer_research_field(self, journal: str, title: str) -> Optional[str]:
        """Infer research field from journal and title."""
        text = f"{journal} {title}".lower()
        
        field_keywords = {
            'quantum': ['quantum', 'qubit', 'entanglement', 'decoherence'],
            'cosmology': ['cosmic', 'universe', 'dark matter', 'dark energy', 'big bang'],
            'particle': ['particle', 'hadron', 'lepton', 'boson', 'fermion'],
            'condensed_matter': ['condensed matter', 'solid state', 'superconductor'],
            'astrophysics': ['astrophys', 'stellar', 'galactic', 'extragalactic'],
            'optics': ['optical', 'photon', 'laser', 'spectroscopy'],
            'nuclear': ['nuclear', 'radioactive', 'fission', 'fusion']
        }
        
        for field, keywords in field_keywords.items():
            if any(keyword in text for keyword in keywords):
                return field
                
        return None
        
    async def build_citation_network(self, seed_papers: List[str], depth: int = 2) -> None:
        """Build citation network starting from seed papers."""
        try:
            queue = [(paper_id, 0) for paper_id in seed_papers]
            processed = set()
            
            while queue:
                paper_id, current_depth = queue.pop(0)
                
                if paper_id in processed or current_depth >= depth:
                    continue
                    
                processed.add(paper_id)
                citation = await self.add_citation(paper_id)
                
                if citation:
                    # Add references to queue
                    for ref_id in citation.references:
                        if ref_id not in processed:
                            queue.append((ref_id, current_depth + 1))
                            
                # Rate limiting
                await asyncio.sleep(0.1)
                
            self.logger.info(f"Built citation network: {len(self.citations)} papers")
            
        except Exception as e:
            handle_error(e)
            
    def calculate_h_index(self, author_name: str) -> int:
        """Calculate h-index for an author."""
        try:
            if author_name not in self.authors:
                return 0
                
            # Get citations for author's papers
            author_papers = []
            for paper_id, citation in self.citations.items():
                if author_name in citation.authors:
                    author_papers.append(citation.cited_by_count)
                    
            if not author_papers:
                return 0
                
            # Calculate h-index
            author_papers.sort(reverse=True)
            h_index = 0
            
            for i, citations in enumerate(author_papers):
                if citations >= i + 1:
                    h_index = i + 1
                else:
                    break
                    
            # Update author profile
            self.authors[author_name].h_index = h_index
            return h_index
            
        except Exception as e:
            handle_error(e)
            return 0
            
    def calculate_impact_score(self, paper_id: str) -> float:
        """Calculate comprehensive impact score for a paper."""
        try:
            if paper_id not in self.citations:
                return 0.0
                
            citation = self.citations[paper_id]
            
            # Base citation count
            raw_citations = citation.cited_by_count
            
            # Age normalization
            current_year = datetime.now().year
            paper_age = current_year - (citation.year or current_year)
            age_factor = max(0.1, 1.0 / (1 + paper_age * 0.1))
            
            # Journal prestige factor (simplified)
            journal_factor = self._get_journal_factor(citation.journal)
            
            # Author reputation factor
            author_factor = self._get_author_reputation_factor(citation.authors)
            
            # Network centrality
            centrality_factor = 1.0
            if self.citation_graph.has_node(paper_id):
                try:
                    centrality = nx.betweenness_centrality(self.citation_graph).get(paper_id, 0)
                    centrality_factor = 1.0 + centrality
                except:
                    pass
                    
            # Combined score
            impact_score = (raw_citations * age_factor * journal_factor * 
                          author_factor * centrality_factor)
            
            return float(impact_score)
            
        except Exception as e:
            handle_error(e)
            return 0.0
            
    def _get_journal_factor(self, journal: str) -> float:
        """Get journal prestige factor."""
        if not journal:
            return 1.0
            
        journal = journal.lower()
        
        # High-impact physics journals
        tier1_journals = ['nature', 'science', 'physical review letters']
        tier2_journals = ['physical review', 'journal of high energy physics']
        
        if any(j in journal for j in tier1_journals):
            return 2.0
        elif any(j in journal for j in tier2_journals):
            return 1.5
        else:
            return 1.0
            
    def _get_author_reputation_factor(self, authors: List[str]) -> float:
        """Get author reputation factor."""
        if not authors:
            return 1.0
            
        total_h_index = 0
        valid_authors = 0
        
        for author_name in authors:
            if author_name in self.authors:
                total_h_index += self.authors[author_name].h_index
                valid_authors += 1
                
        if valid_authors == 0:
            return 1.0
            
        avg_h_index = total_h_index / valid_authors
        return 1.0 + (avg_h_index / 100.0)  # Normalize h-index contribution
        
    def get_citation_metrics(self, author_name: str) -> CitationMetrics:
        """Get comprehensive citation metrics for an author."""
        try:
            if author_name not in self.authors:
                return CitationMetrics()
                
            author = self.authors[author_name]
            
            # Calculate h-index
            h_index = self.calculate_h_index(author_name)
            
            # Calculate average citations
            avg_citations = 0.0
            if author.paper_count > 0:
                avg_citations = author.citation_count / author.paper_count
                
            # Calculate collaboration index
            collaboration_index = len(author.coauthors) / max(1, author.paper_count)
            
            # Calculate recent impact (papers from last 5 years)
            recent_impact = self._calculate_recent_impact(author_name)
            
            return CitationMetrics(
                total_papers=author.paper_count,
                total_citations=author.citation_count,
                h_index=h_index,
                average_citations=avg_citations,
                collaboration_index=collaboration_index,
                recent_impact=recent_impact
            )
            
        except Exception as e:
            handle_error(e)
            return CitationMetrics()
            
    def _calculate_recent_impact(self, author_name: str) -> float:
        """Calculate impact from recent papers."""
        try:
            current_year = datetime.now().year
            recent_citations = 0
            recent_papers = 0
            
            for paper_id, citation in self.citations.items():
                if (author_name in citation.authors and 
                    citation.year and 
                    current_year - citation.year <= 5):
                    recent_citations += citation.cited_by_count
                    recent_papers += 1
                    
            if recent_papers == 0:
                return 0.0
                
            return recent_citations / recent_papers
            
        except Exception as e:
            handle_error(e)
            return 0.0
            
    def find_collaboration_opportunities(self, author_name: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Find potential collaboration opportunities."""
        try:
            if author_name not in self.authors:
                return []
                
            author = self.authors[author_name]
            opportunities = []
            
            # Find authors in similar fields
            for other_name, other_author in self.authors.items():
                if other_name == author_name:
                    continue
                    
                # Check field overlap
                field_overlap = set(author.fields) & set(other_author.fields)
                if not field_overlap:
                    continue
                    
                # Calculate collaboration potential
                reputation_score = other_author.h_index
                novelty_score = 1.0 - (len(author.coauthors & other_author.coauthors) / 
                                     max(1, len(author.coauthors)))
                
                opportunities.append({
                    'author': other_name,
                    'shared_fields': list(field_overlap),
                    'reputation_score': reputation_score,
                    'novelty_score': novelty_score,
                    'total_score': reputation_score * novelty_score
                })
                
            # Sort by total score
            opportunities.sort(key=lambda x: x['total_score'], reverse=True)
            return opportunities[:max_results]
            
        except Exception as e:
            handle_error(e)
            return []
            
    def export_citation_graph(self) -> Dict[str, Any]:
        """Export citation graph data."""
        try:
            nodes = []
            edges = []
            
            for node_id in self.citation_graph.nodes():
                node_data = self.citation_graph.nodes[node_id]
                nodes.append({
                    'id': node_id,
                    'title': node_data.get('title', ''),
                    'authors': node_data.get('authors', []),
                    'year': node_data.get('year'),
                    'citations': node_data.get('cited_by_count', 0)
                })
                
            for source, target in self.citation_graph.edges():
                edges.append({'source': source, 'target': target})
                
            return {
                'nodes': nodes,
                'edges': edges,
                'metadata': {
                    'total_papers': len(self.citations),
                    'total_authors': len(self.authors),
                    'generated_at': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            handle_error(e)
            return {'nodes': [], 'edges': [], 'metadata': {}}
            
    async def refresh_citation_counts(self) -> None:
        """Refresh citation counts for all papers."""
        try:
            self.logger.info("Refreshing citation counts...")
            
            for paper_id in list(self.citations.keys()):
                # Get updated metadata
                if paper_id.startswith('10.'):
                    metadata = await self.resolve_doi(paper_id)
                else:
                    metadata = await self.fetch_semantic_scholar_data(paper_id)
                    
                if metadata and 'cited_by_count' in metadata:
                    self.citations[paper_id].cited_by_count = metadata['cited_by_count']
                    
                # Rate limiting
                await asyncio.sleep(0.2)
                
            self.logger.info("Citation count refresh completed")
            
        except Exception as e:
            handle_error(e)
    async def format_citation(self, *args, **kwargs):
        return dict()
