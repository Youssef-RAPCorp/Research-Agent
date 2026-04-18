import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Union, AsyncGenerator
from abc import ABC

import aiofiles
import aiohttp

logger = logging.getLogger(__name__)

@dataclass
class Document:
    """Represents an indexed document with metadata."""
    id: str
    content: str
    source: str
    url: Optional[str]
    title: Optional[str]
    authors: List[str]
    keywords: List[str]
    abstract: Optional[str]
    sha256: str
    timestamp: datetime
    metadata: Dict[str, Any]

@dataclass
class IndexingProgress:
    """Tracks indexing progress for checkpointing."""
    total_documents: int
    processed_documents: int
    failed_documents: int
    current_source: str
    start_time: datetime
    last_checkpoint: datetime
    processed_hashes: Set[str]

class DocumentSource(ABC):
    """Abstract base class for document sources."""
    
    async def fetch_documents(self) -> AsyncGenerator[Document, None]:
        """Fetch documents from the source."""
        pass
    
    def get_source_name(self) -> str:
        """Get the name of this source."""
        pass

class ArxivSource(DocumentSource):
    """Fetches documents from arXiv API."""
    
    def __init__(self,       query: str = "physics",       max_results: int = 1000, **kwargs):
        self.query = query
        self.max_results = max_results
        self.base_url = "http://export.arxiv.org/api/query"
    
    async def fetch_documents(self) -> AsyncGenerator[Document, None]:
        """Fetch documents from arXiv."""
        start = 0
        batch_size = 100
        
        async with aiohttp.ClientSession() as session:
            while start < self.max_results:
                params = {
                    'search_query': f'cat:{self.query}',
                    'start': start,
                    'max_results': min(batch_size, self.max_results - start),
                    'sortBy': 'submittedDate',
                    'sortOrder': 'descending'
                }
                
                try:
                    async with session.get(self.base_url, params=params) as response:
                        if response.status == 200:
                            content = await response.text()
                            documents = self._parse_arxiv_response(content)
                            for doc in documents:
                                yield doc
                        else:
                            logger.error(f"ArXiv API error: {response.status}")
                            break
                            
                except Exception as e:
                    logger.error(f"Error fetching from arXiv: {e}")
                    break
                
                start += batch_size
                await asyncio.sleep(1)  # Rate limiting
    
    def _parse_arxiv_response(self, xml_content: str) -> List[Document]:
        """Parse arXiv XML response into Document objects."""
        # TODO: Implement proper XML parsing for arXiv feed format
        # For now, return empty list as placeholder
        return []
    
    def get_source_name(self) -> str:
        return "arxiv"

class PDFSource(DocumentSource):
    """Processes local PDF files."""
    
    def __init__(self,       pdf_directory=None, **kwargs):
        self.pdf_directory = Path(pdf_directory)
    
    async def fetch_documents(self) -> AsyncGenerator[Document, None]:
        """Process PDF files from directory."""
        pdf_files = list(self.pdf_directory.glob("**/*.pdf"))
        
        for pdf_path in pdf_files:
            try:
                content = await self._extract_pdf_content(pdf_path)
                if content:
                    doc = Document(
                        id=str(pdf_path),
                        content=content,
                        source="pdf",
                        url=None,
                        title=pdf_path.stem,
                        authors=[],
                        keywords=[],
                        abstract=None,
                        sha256=self._calculate_sha256(content),
                        timestamp=datetime.now(),
                        metadata={"file_path": str(pdf_path)}
                    )
                    yield doc
            except Exception as e:
                logger.error(f"Error processing PDF {pdf_path}: {e}")
    
    async def _extract_pdf_content(self, pdf_path: Path) -> Optional[str]:
        """Extract text content from PDF file."""
        # TODO: Implement PDF text extraction using PyPDF2 or similar
        # For now, return placeholder content
        return f"Content from {pdf_path.name}"
    
    def _calculate_sha256(self, content: str) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def get_source_name(self) -> str:
        return "pdf"

class WebSource(DocumentSource):
    """Scrapes documents from web URLs."""
    
    def __init__(self,       urls=None, **kwargs):
        self.urls = urls
    
    async def fetch_documents(self) -> AsyncGenerator[Document, None]:
        """Fetch documents from web URLs."""
        async with aiohttp.ClientSession() as session:
            for url in self.urls:
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            content = await response.text()
                            # TODO: Implement proper HTML parsing and text extraction
                            cleaned_content = self._extract_text_content(content)
                            
                            doc = Document(
                                id=url,
                                content=cleaned_content,
                                source="web",
                                url=url,
                                title=self._extract_title(content),
                                authors=[],
                                keywords=[],
                                abstract=None,
                                sha256=hashlib.sha256(cleaned_content.encode('utf-8')).hexdigest(),
                                timestamp=datetime.now(),
                                metadata={"url": url, "status_code": response.status}
                            )
                            yield doc
                except Exception as e:
                    logger.error(f"Error fetching URL {url}: {e}")
                
                await asyncio.sleep(1)  # Rate limiting
    
    def _extract_text_content(self, html: str) -> str:
        """Extract text content from HTML."""
        # TODO: Implement proper HTML text extraction using BeautifulSoup
        return html[:1000]  # Placeholder
    
    def _extract_title(self, html: str) -> Optional[str]:
        """Extract title from HTML."""
        # TODO: Implement proper title extraction
        return "Web Document"
    
    def get_source_name(self) -> str:
        return "web"

class KnowledgeIndexer:
    """Multi-source knowledge indexing pipeline with deduplication and checkpointing."""
    
    def __init__(self,       
                 index_directory=None,      
                 checkpoint_interval: int = 100, **kwargs):
        """Initialize the knowledge indexer.
        
        Args:
            index_directory: Directory to store index files and checkpoints
            checkpoint_interval: Number of documents to process between checkpoints
        """
        self.index_directory = Path(index_directory)
        self.index_directory.mkdir(parents=True, exist_ok=True)
        self.checkpoint_interval = checkpoint_interval
        
        self.documents: Dict[str, Document] = {}
        self.hash_to_id: Dict[str, str] = {}
        self.progress: Optional[IndexingProgress] = None
        
        self.index_file = self.index_directory / "documents.json"
        self.hash_file = self.index_directory / "hashes.json"
        self.checkpoint_file = self.index_directory / "checkpoint.json"
    
    async def load_existing_index(self) -> None:
        """Load existing index and hash mappings from disk."""
        try:
            if self.index_file.exists():
                async with aiofiles.open(self.index_file, 'r') as f:
                    data = json.loads(await f.read())
                    self.documents = {
                        doc_id: Document(**doc_data) 
                        for doc_id, doc_data in data.items()
                    }
                    # Convert timestamp strings back to datetime objects
                    for doc in self.documents.values():
                        doc.timestamp = datetime.fromisoformat(doc.timestamp)
                
                logger.info(f"Loaded {len(self.documents)} existing documents")
            
            if self.hash_file.exists():
                async with aiofiles.open(self.hash_file, 'r') as f:
                    self.hash_to_id = json.loads(await f.read())
                
                logger.info(f"Loaded {len(self.hash_to_id)} hash mappings")
                
        except Exception as e:
            logger.error(f"Error loading existing index: {e}")
    
    async def save_index(self) -> None:
        """Save index and hash mappings to disk."""
        try:
            # Prepare documents for JSON serialization
            serializable_docs = {}
            for doc_id, doc in self.documents.items():
                doc_dict = asdict(doc)
                doc_dict['timestamp'] = doc.timestamp.isoformat()
                serializable_docs[doc_id] = doc_dict
            
            async with aiofiles.open(self.index_file, 'w') as f:
                await f.write(json.dumps(serializable_docs, indent=2))
            
            async with aiofiles.open(self.hash_file, 'w') as f:
                await f.write(json.dumps(self.hash_to_id, indent=2))
            
            logger.info(f"Saved index with {len(self.documents)} documents")
            
        except Exception as e:
            logger.error(f"Error saving index: {e}")
    
    async def save_checkpoint(self) -> None:
        """Save current progress checkpoint."""
        if self.progress:
            try:
                checkpoint_data = {
                    'total_documents': self.progress.total_documents,
                    'processed_documents': self.progress.processed_documents,
                    'failed_documents': self.progress.failed_documents,
                    'current_source': self.progress.current_source,
                    'start_time': self.progress.start_time.isoformat(),
                    'last_checkpoint': datetime.now().isoformat(),
                    'processed_hashes': list(self.progress.processed_hashes)
                }
                
                async with aiofiles.open(self.checkpoint_file, 'w') as f:
                    await f.write(json.dumps(checkpoint_data, indent=2))
                
                logger.info(f"Checkpoint saved: {self.progress.processed_documents}/{self.progress.total_documents} processed")
                
            except Exception as e:
                logger.error(f"Error saving checkpoint: {e}")
    
    async def load_checkpoint(self) -> Optional[IndexingProgress]:
        """Load existing progress checkpoint."""
        try:
            if self.checkpoint_file.exists():
                async with aiofiles.open(self.checkpoint_file, 'r') as f:
                    data = json.loads(await f.read())
                
                progress = IndexingProgress(
                    total_documents=data['total_documents'],
                    processed_documents=data['processed_documents'],
                    failed_documents=data['failed_documents'],
                    current_source=data['current_source'],
                    start_time=datetime.fromisoformat(data['start_time']),
                    last_checkpoint=datetime.fromisoformat(data['last_checkpoint']),
                    processed_hashes=set(data['processed_hashes'])
                )
                
                logger.info(f"Loaded checkpoint: {progress.processed_documents}/{progress.total_documents} processed")
                return progress
                
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
        
        return None
    
    def is_duplicate(self, document: Document) -> bool:
        """Check if document is a duplicate based on SHA256 hash."""
        return document.sha256 in self.hash_to_id
    
    async def add_document(self, document: Document) -> bool:
        """Add document to index if not duplicate.
        
        Returns:
            True if document was added, False if duplicate
        """
        if self.is_duplicate(document):
            logger.debug(f"Skipping duplicate document: {document.id}")
            return False
        
        self.documents[document.id] = document
        self.hash_to_id[document.sha256] = document.id
        
        logger.debug(f"Added document: {document.id}")
        return True
    
    async def index_source(self, source: DocumentSource) -> Dict[str, int]:
        """Index all documents from a source.
        
        Returns:
            Statistics dict with counts
        """
        stats = {
            'total': 0,
            'added': 0,
            'duplicates': 0,
            'errors': 0
        }
        
        source_name = source.get_source_name()
        logger.info(f"Starting indexing from source: {source_name}")
        
        if self.progress:
            self.progress.current_source = source_name
        
        async for document in source.fetch_documents():
            stats['total'] += 1
            
            try:
                if await self.add_document(document):
                    stats['added'] += 1
                else:
                    stats['duplicates'] += 1
                
                if self.progress:
                    self.progress.processed_documents += 1
                    self.progress.processed_hashes.add(document.sha256)
                    
                    # Save checkpoint periodically
                    if stats['total'] % self.checkpoint_interval == 0:
                        await self.save_checkpoint()
                        await self.save_index()
                
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing document {document.id}: {e}")
                
                if self.progress:
                    self.progress.failed_documents += 1
        
        logger.info(f"Completed indexing {source_name}: {stats}")
        return stats
    
    async def index_all_sources(self, sources: List[DocumentSource]) -> Dict[str, Any]:
        """Index documents from multiple sources with progress tracking.
        
        Args:
            sources: List of document sources to index
            
        Returns:
            Overall indexing statistics
        """
        await self.load_existing_index()
        
        # Initialize or load progress
        self.progress = await self.load_checkpoint()
        if not self.progress:
            self.progress = IndexingProgress(
                total_documents=0,
                processed_documents=0,
                failed_documents=0,
                current_source="",
                start_time=datetime.now(),
                last_checkpoint=datetime.now(),
                processed_hashes=set()
            )
        
        overall_stats = {
            'sources': {},
            'total_added': 0,
            'total_duplicates': 0,
            'total_errors': 0,
            'start_time': self.progress.start_time.isoformat(),
            'end_time': None,
            'duration_seconds': 0
        }
        
        try:
            for source in sources:
                source_name = source.get_source_name()
                logger.info(f"Processing source: {source_name}")
                
                source_stats = await self.index_source(source)
                overall_stats['sources'][source_name] = source_stats
                overall_stats['total_added'] += source_stats['added']
                overall_stats['total_duplicates'] += source_stats['duplicates']
                overall_stats['total_errors'] += source_stats['errors']
            
            # Final save
            await self.save_index()
            await self.save_checkpoint()
            
        except Exception as e:
            logger.error(f"Error during indexing: {e}")
            await self.save_checkpoint()  # Save progress even on error
            raise
        
        finally:
            end_time = datetime.now()
            overall_stats['end_time'] = end_time.isoformat()
            overall_stats['duration_seconds'] = (end_time - self.progress.start_time).total_seconds()
        
        logger.info(f"Indexing completed: {overall_stats}")
        return overall_stats
    
    async def search_documents(self, query: str, limit: int = 10) -> List[Document]:
        """Search indexed documents by content.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of matching documents
        """
        # TODO: Implement proper search with vector embeddings or full-text search
        # For now, simple keyword matching
        query_lower = query.lower()
        matching_docs = []
        
        for document in self.documents.values():
            if (query_lower in document.content.lower() or 
                query_lower in document.title.lower() if document.title else False or
                any(query_lower in keyword.lower() for keyword in document.keywords)):
                matching_docs.append(document)
                
                if len(matching_docs) >= limit:
                    break
        
        return matching_docs
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get indexing statistics.
        
        Returns:
            Dictionary with various statistics
        """
        source_counts = {}
        for document in self.documents.values():
            source = document.source
            source_counts[source] = source_counts.get(source, 0) + 1
        
        return {
            'total_documents': len(self.documents),
            'total_unique_hashes': len(self.hash_to_id),
            'sources': source_counts,
            'index_size_mb': self._calculate_index_size(),
            'last_updated': max([doc.timestamp for doc in self.documents.values()]).isoformat() if self.documents else None
        }
    
    def _calculate_index_size(self) -> float:
        """Calculate approximate index size in MB."""
        total_content_size = sum(len(doc.content.encode('utf-8')) for doc in self.documents.values())
        return total_content_size / (1024 * 1024)
    
    async def cleanup_checkpoint(self) -> None:
        """Clean up checkpoint file after successful completion."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.info("Checkpoint file cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up checkpoint: {e}")

async def main():
    """Example usage of the KnowledgeIndexer."""
    indexer = KnowledgeIndexer(Path("./physics_index"))
    
    # Define sources
    sources = [
        ArxivSource(query="physics.gen-ph", max_results=100),
        PDFSource(Path("./papers")),
        WebSource(["https://example.com/physics-paper"])
    ]
    
    try:
        # Run indexing
        stats = await indexer.index_all_sources(sources)
        print(f"Indexing completed: {stats}")
        
        # Example search
        results = await indexer.search_documents("quantum mechanics")
        print(f"Found {len(results)} documents matching 'quantum mechanics'")
        
        # Show statistics
        stats = indexer.get_statistics()
        print(f"Index statistics: {stats}")
        
        # Cleanup
        await indexer.cleanup_checkpoint()
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())