import hashlib
import json
from typing import Dict, List, Optional, Union, Any
import numpy as np
from sentence_transformers import SentenceTransformer
import openai
from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error

logger = get_logger(__name__)
settings = get_settings()

class EmbeddingCache:
    """Simple in-memory cache for embeddings."""
    
    def __init__(self,  max_size: int = 10000, **kwargs):
        self.cache: Dict[str, np.ndarray] = {}
        self.max_size = max_size
    
    def _hash_text(self, text: str) -> str:
        """Generate hash for text."""
        return hashlib.md5(text.encode()).hexdigest()
    
    def get(self, text: str) -> Optional[np.ndarray]:
        """Get cached embedding if exists."""
        key = self._hash_text(text)
        return self.cache.get(key)
    
    def set(self, text: str, embedding: np.ndarray) -> None:
        """Cache embedding with LRU eviction."""
        if len(self.cache) >= self.max_size:
            # Simple FIFO eviction
            first_key = next(iter(self.cache))
            del self.cache[first_key]
        
        key = self._hash_text(text)
        self.cache[key] = embedding

class EmbeddingProvider:
    """Abstract base for embedding providers."""
    
    def __init__(self, **kwargs):
        self.cache = EmbeddingCache()
    
    async def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text."""
        raise NotImplementedError
    
    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for batch of texts."""
        embeddings = []
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
        return embeddings

class SentenceTransformerProvider(EmbeddingProvider):
    """Sentence transformer based embedding provider."""
    
    def __init__(self,  model_name: str = None, **kwargs):
        super().__init__()
        self.model_name = model_name or settings.embedding_model
        self.model = None
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the sentence transformer model."""
        try:
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded embedding model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            handle_error(e)
            # Fallback to default model
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    async def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for single text."""
        if not text or not text.strip():
            return np.zeros(self.model.get_sentence_embedding_dimension())
        
        # Check cache first
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            self.cache.set(text, embedding)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            handle_error(e)
            return np.zeros(self.model.get_sentence_embedding_dimension())
    
    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for batch of texts efficiently."""
        if not texts:
            return []
        
        # Filter out cached embeddings
        uncached_texts = []
        uncached_indices = []
        results = [None] * len(texts)
        
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = np.zeros(self.model.get_sentence_embedding_dimension())
                continue
            
            cached = self.cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                embeddings = self.model.encode(uncached_texts, convert_to_numpy=True)
                
                for i, embedding in enumerate(embeddings):
                    text_idx = uncached_indices[i]
                    text = texts[text_idx]
                    results[text_idx] = embedding
                    self.cache.set(text, embedding)
                    
            except Exception as e:
                logger.error(f"Failed to generate batch embeddings: {e}")
                handle_error(e)
                # Fill remaining with zeros
                dim = self.model.get_sentence_embedding_dimension()
                for idx in uncached_indices:
                    if results[idx] is None:
                        results[idx] = np.zeros(dim)
        
        return results

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI based embedding provider."""
    
    def __init__(self,  model_name: str = "text-embedding-ada-002", **kwargs):
        super().__init__()
        self.model_name = model_name
        # TODO: Set OpenAI API key from settings
        openai.api_key = getattr(settings, 'openai_api_key', None)
    
    async def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for single text using OpenAI."""
        if not text or not text.strip():
            return np.zeros(1536)  # OpenAI embedding dimension
        
        # Check cache first
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        
        try:
            response = openai.Embedding.create(
                model=self.model_name,
                input=text
            )
            embedding = np.array(response['data'][0]['embedding'])
            self.cache.set(text, embedding)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate OpenAI embedding: {e}")
            handle_error(e)
            return np.zeros(1536)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    if a.size == 0 or b.size == 0:
        return 0.0
    
    try:
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    except Exception as e:
        logger.error(f"Failed to calculate cosine similarity: {e}")
        return 0.0

def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate Euclidean distance between two vectors."""
    if a.size == 0 or b.size == 0:
        return float('inf')
    
    try:
        return np.linalg.norm(a - b)
    except Exception as e:
        logger.error(f"Failed to calculate Euclidean distance: {e}")
        return float('inf')

def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    """Normalize embedding to unit vector."""
    try:
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding
        return embedding / norm
    except Exception as e:
        logger.error(f"Failed to normalize embedding: {e}")
        return embedding

class EmbeddingUtils:
    """Utility class for embedding operations."""
    
    @staticmethod
    def find_most_similar(query_embedding: np.ndarray, 
                         embeddings: List[np.ndarray], 
                         top_k: int = 5) -> List[int]:
        """Find indices of most similar embeddings."""
        if not embeddings or query_embedding.size == 0:
            return []
        
        similarities = []
        for i, embedding in enumerate(embeddings):
            sim = cosine_similarity(query_embedding, embedding)
            similarities.append((sim, i))
        
        # Sort by similarity descending
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        return [idx for _, idx in similarities[:top_k]]
    
    @staticmethod
    def cluster_embeddings(embeddings: List[np.ndarray], 
                          n_clusters: int = 5) -> Dict[int, List[int]]:
        """Simple k-means clustering of embeddings."""
        if not embeddings or len(embeddings) < n_clusters:
            return {0: list(range(len(embeddings)))}
        
        try:
            from sklearn.cluster import KMeans
            
            embeddings_matrix = np.vstack(embeddings)
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            labels = kmeans.fit_predict(embeddings_matrix)
            
            clusters = {}
            for i, label in enumerate(labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(i)
            
            return clusters
            
        except ImportError:
            logger.warning("sklearn not available, returning single cluster")
            return {0: list(range(len(embeddings)))}
        except Exception as e:
            logger.error(f"Failed to cluster embeddings: {e}")
            handle_error(e)
            return {0: list(range(len(embeddings)))}
    
    @staticmethod
    def reduce_dimensionality(embeddings: List[np.ndarray], 
                            n_components: int = 50) -> List[np.ndarray]:
        """Reduce embedding dimensionality using PCA."""
        if not embeddings:
            return []
        
        try:
            from sklearn.decomposition import PCA
            
            embeddings_matrix = np.vstack(embeddings)
            pca = PCA(n_components=min(n_components, embeddings_matrix.shape[1]))
            reduced_matrix = pca.fit_transform(embeddings_matrix)
            
            return [reduced_matrix[i] for i in range(len(embeddings))]
            
        except ImportError:
            logger.warning("sklearn not available, returning original embeddings")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to reduce dimensionality: {e}")
            handle_error(e)
            return embeddings

# Global embedding provider instance
_embedding_provider: Optional[EmbeddingProvider] = None

def get_embedding_provider() -> EmbeddingProvider:
    """Get global embedding provider instance."""
    global _embedding_provider
    
    if _embedding_provider is None:
        try:
            _embedding_provider = SentenceTransformerProvider()
        except Exception as e:
            logger.error(f"Failed to initialize embedding provider: {e}")
            handle_error(e)
            # Fallback to a minimal provider
            _embedding_provider = SentenceTransformerProvider()
    
    return _embedding_provider

async def embed_text(text: str) -> np.ndarray:
    """Convenience function to embed single text."""
    provider = get_embedding_provider()
    return await provider.embed_text(text)

async def embed_texts(texts: List[str]) -> List[np.ndarray]:
    """Convenience function to embed multiple texts."""
    provider = get_embedding_provider()
    return await provider.embed_batch(texts)

def similarity_search(query_embedding: np.ndarray,
                     candidate_embeddings: List[np.ndarray],
                     top_k: int = None) -> List[tuple[int, float]]:
    """Perform similarity search and return ranked results."""
    if top_k is None:
        top_k = getattr(settings, 'retrieval_top_k', 10)
    
    similarities = []
    for i, embedding in enumerate(candidate_embeddings):
        sim = cosine_similarity(query_embedding, embedding)
        similarities.append((i, sim))
    
    # Sort by similarity descending
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    return similarities[:top_k]

def EmbeddingService(*args, **kwargs):
    raise NotImplementedError('EmbeddingService not yet implemented')
