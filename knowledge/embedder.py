import asyncio
import logging
import hashlib
import pickle
from typing import List, Dict, Any, Optional, Union, Tuple
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm.asyncio import tqdm
import torch

from config.logger import get_logger
from config.settings import get_settings
from config.errors import handle_error

logger = get_logger(__name__)

class Embedder:
    """Multi-model embedding pipeline with caching and batch processing."""
    
    def __init__(self,      model_name: Optional[str] = None, **kwargs):
        """Initialize embedder with specified model."""
        self.settings = get_settings()
        self.model_name = model_name or self.settings.embedding_model
        self._model = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._cache = {}
        self._cache_size = 1000
        
    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to load model {self.model_name}: {e}")
                # Fallback to a basic model
                self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(f"{self.model_name}:{text}".encode()).hexdigest()
    
    def _cache_get(self, key: str) -> Optional[np.ndarray]:
        """Get embedding from cache."""
        return self._cache.get(key)
    
    def _cache_set(self, key: str, value: np.ndarray) -> None:
        """Set embedding in cache with LRU eviction."""
        if len(self._cache) >= self._cache_size:
            # Remove oldest entry (simple FIFO for now)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = value
    
    async def embed_text(self, text: str) -> np.ndarray:
        """Embed single text with caching."""
        if not text or not text.strip():
            return np.zeros(self.model.get_sentence_embedding_dimension())
        
        cache_key = self._get_cache_key(text.strip())
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        
        try:
            # Run embedding in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                self._executor, 
                self._embed_sync, 
                text.strip()
            )
            
            self._cache_set(cache_key, embedding)
            return embedding
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to embed text: {e}")
            return np.zeros(self.model.get_sentence_embedding_dimension())
    
    def _embed_sync(self, text: str) -> np.ndarray:
        """Synchronous embedding for thread execution."""
        return self.model.encode(text, convert_to_numpy=True)
    
    async def embed_batch(self, texts: List[str], batch_size: int = 32, show_progress: bool = True) -> List[np.ndarray]:
        """Embed multiple texts with batch processing and progress tracking."""
        if not texts:
            return []
        
        # Filter out empty texts and create mapping
        non_empty_texts = [(i, text.strip()) for i, text in enumerate(texts) if text and text.strip()]
        results = [np.zeros(self.model.get_sentence_embedding_dimension())] * len(texts)
        
        if not non_empty_texts:
            return results
        
        # Check cache first
        to_embed = []
        for i, text in non_empty_texts:
            cache_key = self._get_cache_key(text)
            cached = self._cache_get(cache_key)
            if cached is not None:
                results[i] = cached
            else:
                to_embed.append((i, text, cache_key))
        
        if not to_embed:
            return results
        
        # Process in batches
        embeddings = []
        batch_texts = []
        batch_indices = []
        batch_keys = []
        
        progress_desc = f"Embedding {len(to_embed)} texts"
        pbar = tqdm(total=len(to_embed), desc=progress_desc, disable=not show_progress)
        
        try:
            for idx, (i, text, cache_key) in enumerate(to_embed):
                batch_texts.append(text)
                batch_indices.append(i)
                batch_keys.append(cache_key)
                
                if len(batch_texts) >= batch_size or idx == len(to_embed) - 1:
                    # Process batch
                    loop = asyncio.get_event_loop()
                    batch_embeddings = await loop.run_in_executor(
                        self._executor,
                        self._embed_batch_sync,
                        batch_texts
                    )
                    
                    # Store results and cache
                    for j, embedding in enumerate(batch_embeddings):
                        original_idx = batch_indices[j]
                        cache_key = batch_keys[j]
                        results[original_idx] = embedding
                        self._cache_set(cache_key, embedding)
                    
                    pbar.update(len(batch_texts))
                    
                    # Reset batch
                    batch_texts = []
                    batch_indices = []
                    batch_keys = []
            
        except Exception as e:
            handle_error(e)
            logger.error(f"Batch embedding failed: {e}")
        finally:
            pbar.close()
        
        return results
    
    def _embed_batch_sync(self, texts: List[str]) -> List[np.ndarray]:
        """Synchronous batch embedding for thread execution."""
        embeddings = self.model.encode(texts, convert_to_numpy=True, batch_size=len(texts))
        if len(texts) == 1:
            return [embeddings]
        return list(embeddings)
    
    async def embed_documents(self, documents: List[Dict[str, Any]], text_field: str = 'content') -> List[Dict[str, Any]]:
        """Embed documents and add embedding field."""
        if not documents:
            return []
        
        texts = [doc.get(text_field, '') for doc in documents]
        embeddings = await self.embed_batch(texts, show_progress=True)
        
        enriched_docs = []
        for doc, embedding in zip(documents, embeddings):
            enriched_doc = doc.copy()
            enriched_doc['embedding'] = embedding.tolist()
            enriched_doc['embedding_model'] = self.model_name
            enriched_docs.append(enriched_doc)
        
        return enriched_docs
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between embeddings."""
        if embedding1.size == 0 or embedding2.size == 0:
            return 0.0
        
        # Normalize vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return np.dot(embedding1, embedding2) / (norm1 * norm2)
    
    async def find_similar_texts(self, query: str, text_embeddings: List[Tuple[str, np.ndarray]], top_k: int = 5) -> List[Tuple[str, float]]:
        """Find most similar texts to query."""
        query_embedding = await self.embed_text(query)
        
        similarities = []
        for text, embedding in text_embeddings:
            similarity = self.compute_similarity(query_embedding, embedding)
            similarities.append((text, similarity))
        
        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings from this model."""
        return self.model.get_sentence_embedding_dimension()
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._executor:
            self._executor.shutdown(wait=True)
        self._cache.clear()
        logger.info("Embedder resources cleaned up")
    
    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cache_size': len(self._cache),
            'max_cache_size': self._cache_size,
            'model_name': self.model_name,
            'embedding_dimension': self.get_embedding_dimension()
        }
    async def cosine_similarity(self, embedding1, embedding2, *args, **kwargs) -> float:
        """Async wrapper around compute_similarity."""
        import numpy as np
        try:
            e1 = np.array(embedding1) if not isinstance(embedding1, np.ndarray) else embedding1
            e2 = np.array(embedding2) if not isinstance(embedding2, np.ndarray) else embedding2
            return float(self.compute_similarity(e1, e2))
        except Exception:
            return 0.0

    async def embed(self, *args, **kwargs):
        return dict()

    async def initialize(self, *args, **kwargs):
        return dict()
