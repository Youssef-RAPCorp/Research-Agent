import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pdfplumber
from pdfplumber.page import Page


logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """Single text chunk with metadata."""
    content: str
    page_number: int
    chunk_id: str
    bbox: Optional[Tuple[float, float, float, float]] = None
    chunk_type: str = "text"
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class Figure:
    """Detected figure with metadata."""
    page_number: int
    bbox: Tuple[float, float, float, float]
    caption: Optional[str] = None
    figure_id: Optional[str] = None
    image_data: Optional[bytes] = None


@dataclass
class Table:
    """Extracted table with metadata."""
    page_number: int
    data: List[List[str]]
    bbox: Tuple[float, float, float, float]
    caption: Optional[str] = None
    table_id: Optional[str] = None


@dataclass
class DocumentMetadata:
    """PDF document metadata."""
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[datetime] = None
    modification_date: Optional[datetime] = None
    page_count: int = 0
    file_size: int = 0
    language: Optional[str] = None


class PDFIngester:
    """PDF text extraction and processing with pdfplumber."""

    def __init__(
        self,     
        chunk_size: int = 1000,     
        chunk_overlap: int = 200,     
        min_chunk_size: int = 100,     
        figure_threshold: float = 10000,     
        table_threshold: float = 0.5
    , **kwargs):
        """Initialize PDF ingester with configuration parameters."""
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.figure_threshold = figure_threshold
        self.table_threshold = table_threshold
        
    async def process_pdf(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Process PDF file and extract all components."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
            
        result = {
            "metadata": None,
            "text_chunks": [],
            "figures": [],
            "tables": [],
            "raw_text": "",
            "processing_info": {
                "processed_at": datetime.utcnow(),
                "file_path": str(file_path),
                "success": False,
                "error": None
            }
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract metadata
                result["metadata"] = await self._extract_metadata(pdf, file_path)
                
                # Extract content from all pages
                all_text = []
                figures = []
                tables = []
                
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = await self._extract_page_text(page)
                    if page_text.strip():
                        all_text.append(page_text)
                    
                    # Extract figures
                    page_figures = await self._extract_figures(page, page_num)
                    figures.extend(page_figures)
                    
                    # Extract tables
                    page_tables = await self._extract_tables(page, page_num)
                    tables.extend(page_tables)
                
                # Combine all text and create chunks
                full_text = "\n\n".join(all_text)
                result["raw_text"] = full_text
                result["text_chunks"] = await self._create_text_chunks(full_text)
                result["figures"] = figures
                result["tables"] = tables
                result["processing_info"]["success"] = True
                
        except Exception as e:
            logger.error(f"Error processing PDF {file_path}: {str(e)}")
            result["processing_info"]["error"] = str(e)
            
        return result
    
    async def _extract_metadata(self, pdf: pdfplumber.PDF, file_path: Path) -> DocumentMetadata:
        """Extract document metadata from PDF."""
        metadata = DocumentMetadata()
        
        # Basic file info
        metadata.page_count = len(pdf.pages)
        metadata.file_size = file_path.stat().st_size
        
        # PDF metadata
        if pdf.metadata:
            metadata.title = pdf.metadata.get("Title")
            metadata.author = pdf.metadata.get("Author")
            metadata.subject = pdf.metadata.get("Subject")
            metadata.creator = pdf.metadata.get("Creator")
            metadata.producer = pdf.metadata.get("Producer")
            
            # Parse dates
            creation_date = pdf.metadata.get("CreationDate")
            if creation_date:
                metadata.creation_date = self._parse_pdf_date(creation_date)
                
            mod_date = pdf.metadata.get("ModDate")
            if mod_date:
                metadata.modification_date = self._parse_pdf_date(mod_date)
        
        return metadata
    
    def _parse_pdf_date(self, date_str: str) -> Optional[datetime]:
        """Parse PDF date string to datetime."""
        try:
            # PDF date format: D:YYYYMMDDHHmmSSOHH'mm'
            if date_str.startswith("D:"):
                date_str = date_str[2:]
            
            # Extract date components
            if len(date_str) >= 14:
                year = int(date_str[0:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                hour = int(date_str[8:10]) if len(date_str) >= 10 else 0
                minute = int(date_str[10:12]) if len(date_str) >= 12 else 0
                second = int(date_str[12:14]) if len(date_str) >= 14 else 0
                
                return datetime(year, month, day, hour, minute, second)
        except (ValueError, IndexError):
            pass
        
        return None
    
    async def _extract_page_text(self, page: Page) -> str:
        """Extract clean text from a PDF page."""
        try:
            text = page.extract_text()
            if text:
                # Clean up text
                text = re.sub(r'\s+', ' ', text)
                text = text.strip()
            return text or ""
        except Exception as e:
            logger.warning(f"Failed to extract text from page: {str(e)}")
            return ""
    
    async def _extract_figures(self, page: Page, page_num: int) -> List[Figure]:
        """Detect and extract figures from page."""
        figures = []
        
        try:
            # Look for images
            if hasattr(page, 'images'):
                for img in page.images:
                    bbox = (img['x0'], img['y0'], img['x1'], img['y1'])
                    area = (img['x1'] - img['x0']) * (img['y1'] - img['y0'])
                    
                    if area > self.figure_threshold:
                        figure = Figure(
                            page_number=page_num,
                            bbox=bbox,
                            figure_id=f"fig_{page_num}_{len(figures) + 1}"
                        )
                        
                        # Try to find caption nearby
                        caption = await self._find_figure_caption(page, bbox)
                        if caption:
                            figure.caption = caption
                            
                        figures.append(figure)
        
        except Exception as e:
            logger.warning(f"Failed to extract figures from page {page_num}: {str(e)}")
        
        return figures
    
    async def _find_figure_caption(self, page: Page, figure_bbox: Tuple[float, float, float, float]) -> Optional[str]:
        """Find caption text near a figure."""
        try:
            # Look for text below the figure
            x0, y0, x1, y1 = figure_bbox
            search_area = (x0, y1, x1, y1 + 50)  # 50 points below figure
            
            chars = page.within_bbox(search_area).chars
            if chars:
                text = "".join(char['text'] for char in chars)
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Look for figure patterns
                if re.search(r'fig(?:ure)?\s*\d+', text.lower()):
                    return text
                    
        except Exception:
            pass
        
        return None
    
    async def _extract_tables(self, page: Page, page_num: int) -> List[Table]:
        """Extract tables from page using pdfplumber."""
        tables = []
        
        try:
            page_tables = page.find_tables()
            
            for i, table in enumerate(page_tables):
                try:
                    data = table.extract()
                    if data and len(data) > 1:  # At least header + one row
                        # Clean table data
                        cleaned_data = []
                        for row in data:
                            if row:
                                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                                cleaned_data.append(cleaned_row)
                        
                        if cleaned_data:
                            table_obj = Table(
                                page_number=page_num,
                                data=cleaned_data,
                                bbox=table.bbox,
                                table_id=f"table_{page_num}_{i + 1}"
                            )
                            
                            # Try to find table caption
                            caption = await self._find_table_caption(page, table.bbox)
                            if caption:
                                table_obj.caption = caption
                                
                            tables.append(table_obj)
                            
                except Exception as e:
                    logger.warning(f"Failed to extract table {i} from page {page_num}: {str(e)}")
                    
        except Exception as e:
            logger.warning(f"Failed to find tables on page {page_num}: {str(e)}")
        
        return tables
    
    async def _find_table_caption(self, page: Page, table_bbox: Tuple[float, float, float, float]) -> Optional[str]:
        """Find caption text near a table."""
        try:
            # Look for text above the table
            x0, y0, x1, y1 = table_bbox
            search_area = (x0, y0 - 50, x1, y0)  # 50 points above table
            
            chars = page.within_bbox(search_area).chars
            if chars:
                text = "".join(char['text'] for char in chars)
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Look for table patterns
                if re.search(r'table\s*\d+', text.lower()):
                    return text
                    
        except Exception:
            pass
        
        return None
    
    async def _create_text_chunks(self, text: str) -> List[TextChunk]:
        """Create overlapping text chunks from full text."""
        if not text.strip():
            return []
        
        chunks = []
        sentences = self._split_into_sentences(text)
        
        current_chunk = ""
        chunk_sentences = []
        chunk_id = 0
        
        for sentence in sentences:
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            
            if len(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
                chunk_sentences.append(sentence)
            else:
                # Finalize current chunk
                if current_chunk and len(current_chunk) >= self.min_chunk_size:
                    chunk = TextChunk(
                        content=current_chunk.strip(),
                        page_number=1,  # TODO: Track actual page numbers during chunking
                        chunk_id=f"chunk_{chunk_id}",
                        metadata={"sentence_count": len(chunk_sentences)}
                    )
                    chunks.append(chunk)
                    chunk_id += 1
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0 and chunk_sentences:
                    overlap_text = self._create_overlap_text(chunk_sentences)
                    current_chunk = overlap_text + " " + sentence
                    chunk_sentences = [sentence]
                else:
                    current_chunk = sentence
                    chunk_sentences = [sentence]
        
        # Add final chunk
        if current_chunk and len(current_chunk) >= self.min_chunk_size:
            chunk = TextChunk(
                content=current_chunk.strip(),
                page_number=1,
                chunk_id=f"chunk_{chunk_id}",
                metadata={"sentence_count": len(chunk_sentences)}
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting - could be improved with nltk/spacy
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
    
    def _create_overlap_text(self, sentences: List[str]) -> str:
        """Create overlap text from recent sentences."""
        if not sentences:
            return ""
        
        overlap_text = ""
        for sentence in reversed(sentences):
            test_text = sentence + " " + overlap_text if overlap_text else sentence
            if len(test_text) <= self.chunk_overlap:
                overlap_text = test_text
            else:
                break
        
        return overlap_text
    
    async def extract_text_only(self, file_path: Union[str, Path]) -> str:
        """Extract only text content from PDF."""
        file_path = Path(file_path)
        
        try:
            with pdfplumber.open(file_path) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = await self._extract_page_text(page)
                    if page_text:
                        text_parts.append(page_text)
                
                return "\n\n".join(text_parts)
        
        except Exception as e:
            logger.error(f"Failed to extract text from {file_path}: {str(e)}")
            return ""
    
    async def get_page_count(self, file_path: Union[str, Path]) -> int:
        """Get number of pages in PDF."""
        try:
            with pdfplumber.open(file_path) as pdf:
                return len(pdf.pages)
        except Exception as e:
            logger.error(f"Failed to get page count from {file_path}: {str(e)}")
            return 0
FileNotFoundError = type('FileNotFoundError', (), {})  # auto-stub: not found in project

IndexError = type('IndexError', (), {})  # auto-stub: not found in project
