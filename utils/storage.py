import os
import json
import pickle
import hashlib
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List, Union, BinaryIO
from datetime import datetime
import asyncio
import aiofiles
from dataclasses import asdict
from pydantic import BaseModel

from config.logger import get_logger
from config.errors import handle_error

logger = get_logger(__name__)


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class FileStorage:
    """Local file system storage handler."""
    
    def __init__(self,   base_path: str = "data", **kwargs):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def write(self, path: str, data: Union[str, bytes, Dict[str, Any]], encoding: str = "utf-8") -> bool:
        """Write data to file."""
        try:
            full_path = self.base_path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            if isinstance(data, dict):
                with open(full_path, 'w', encoding=encoding) as f:
                    json.dump(data, f, indent=2, default=str)
            elif isinstance(data, bytes):
                with open(full_path, 'wb') as f:
                    f.write(data)
            else:
                with open(full_path, 'w', encoding=encoding) as f:
                    f.write(str(data))
            return True
        except Exception as e:
            handle_error(e)
            return False
    
    def read(self, path: str, encoding: str = "utf-8") -> Optional[Union[str, Dict[str, Any]]]:
        """Read data from file."""
        try:
            full_path = self.base_path / path
            if not full_path.exists():
                return None
            
            if path.endswith('.json'):
                with open(full_path, 'r', encoding=encoding) as f:
                    return json.load(f)
            else:
                with open(full_path, 'r', encoding=encoding) as f:
                    return f.read()
        except Exception as e:
            handle_error(e)
            return None
    
    def read_bytes(self, path: str) -> Optional[bytes]:
        """Read binary data from file."""
        try:
            full_path = self.base_path / path
            if not full_path.exists():
                return None
            
            with open(full_path, 'rb') as f:
                return f.read()
        except Exception as e:
            handle_error(e)
            return None
    
    def exists(self, path: str) -> bool:
        """Check if file exists."""
        return (self.base_path / path).exists()
    
    def delete(self, path: str, **kwargs) -> bool:
        """Delete file or directory."""
        try:
            full_path = self.base_path / path
            if full_path.is_dir():
                shutil.rmtree(full_path)
            elif full_path.exists():
                full_path.unlink()
            return True
        except Exception as e:
            handle_error(e)
            return False
    
    def list_files(self, directory: str = "", pattern: str = "*") -> List[str]:
        """List files in directory."""
        try:
            search_path = self.base_path / directory
            if not search_path.exists():
                return []
            
            files = []
            for file_path in search_path.glob(pattern):
                if file_path.is_file():
                    relative_path = file_path.relative_to(self.base_path)
                    files.append(str(relative_path))
            return files
        except Exception as e:
            handle_error(e)
            return []


class AsyncFileStorage:
    """Async file system storage handler."""
    
    def __init__(self,   base_path: str = "data", **kwargs):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def write(self, path: str, data: Union[str, bytes, Dict[str, Any]], encoding: str = "utf-8") -> bool:
        """Write data to file asynchronously."""
        try:
            full_path = self.base_path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            if isinstance(data, dict):
                async with aiofiles.open(full_path, 'w', encoding=encoding) as f:
                    await f.write(json.dumps(data, indent=2, default=str))
            elif isinstance(data, bytes):
                async with aiofiles.open(full_path, 'wb') as f:
                    await f.write(data)
            else:
                async with aiofiles.open(full_path, 'w', encoding=encoding) as f:
                    await f.write(str(data))
            return True
        except Exception as e:
            handle_error(e)
            return False
    
    async def read(self, path: str, encoding: str = "utf-8") -> Optional[Union[str, Dict[str, Any]]]:
        """Read data from file asynchronously."""
        try:
            full_path = self.base_path / path
            if not full_path.exists():
                return None
            
            if path.endswith('.json'):
                async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
                    return await f.read()
        except Exception as e:
            handle_error(e)
            return None
    
    async def read_bytes(self, path: str) -> Optional[bytes]:
        """Read binary data from file asynchronously."""
        try:
            full_path = self.base_path / path
            if not full_path.exists():
                return None
            
            async with aiofiles.open(full_path, 'rb') as f:
                return await f.read()
        except Exception as e:
            handle_error(e)
            return None


class CacheStorage:
    """In-memory cache with optional persistence."""
    
    def __init__(self,   max_size: int = 1000,   persist_path: Optional[str] = None, **kwargs):
        self.cache: Dict[str, Any] = {}
        self.access_order: List[str] = []
        self.max_size = max_size
        self.persist_path = persist_path
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load cache from persistence file."""
        if self.persist_path and os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, 'rb') as f:
                    data = pickle.load(f)
                    self.cache = data.get('cache', {})
                    self.access_order = data.get('access_order', [])
                logger.info(f"Loaded cache with {len(self.cache)} items")
            except Exception as e:
                handle_error(e)
    
    def _save_cache(self) -> None:
        """Save cache to persistence file."""
        if self.persist_path:
            try:
                os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
                with open(self.persist_path, 'wb') as f:
                    pickle.dump({
                        'cache': self.cache,
                        'access_order': self.access_order
                    }, f)
            except Exception as e:
                handle_error(e)
    
    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if self.access_order:
            lru_key = self.access_order.pop(0)
            self.cache.pop(lru_key, None)
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        if key in self.cache:
            # Move to end (most recently used)
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set item in cache."""
        if key in self.cache:
            # Update existing
            if key in self.access_order:
                self.access_order.remove(key)
        elif len(self.cache) >= self.max_size:
            # Evict LRU
            self._evict_lru()
        
        self.cache[key] = value
        self.access_order.append(key)
        
        if self.persist_path:
            self._save_cache()
    
    def delete(self, key: str, **kwargs) -> bool:
        """Delete item from cache."""
        if key in self.cache:
            del self.cache[key]
            if key in self.access_order:
                self.access_order.remove(key)
            if self.persist_path:
                self._save_cache()
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache items."""
        self.cache.clear()
        self.access_order.clear()
        if self.persist_path:
            self._save_cache()
    
    def size(self) -> int:
        """Get cache size."""
        return len(self.cache)


class HashStorage:
    """Content-addressable storage using file hashes."""
    
    def __init__(self,   storage=None, **kwargs):
        self.storage = storage
        self.index_path = "hash_index.json"
        self._load_index()
    
    def _load_index(self) -> None:
        """Load hash index."""
        index_data = self.storage.read(self.index_path)
        self.index = index_data if isinstance(index_data, dict) else {}
    
    def _save_index(self) -> None:
        """Save hash index."""
        self.storage.write(self.index_path, self.index)
    
    def _compute_hash(self, data: Union[str, bytes]) -> str:
        """Compute SHA256 hash of data."""
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.sha256(data).hexdigest()
    
    def store(self, data: Union[str, bytes], metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store data by content hash."""
        content_hash = self._compute_hash(data)
        
        # Store content
        content_path = f"content/{content_hash[:2]}/{content_hash}"
        self.storage.write(content_path, data)
        
        # Update index
        self.index[content_hash] = {
            'path': content_path,
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat(),
            'size': len(data) if isinstance(data, bytes) else len(data.encode('utf-8'))
        }
        self._save_index()
        
        return content_hash
    
    def retrieve(self, content_hash: str, **kwargs) -> Optional[Union[str, bytes]]:
        """Retrieve data by content hash."""
        if content_hash not in self.index:
            return None
        
        path = self.index[content_hash]['path']
        return self.storage.read(path)
    
    def get_metadata(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Get metadata for content hash."""
        return self.index.get(content_hash, {}).get('metadata')
    
    def exists(self, content_hash: str) -> bool:
        """Check if content exists."""
        return content_hash in self.index
    
    def list_hashes(self) -> List[str]:
        """List all content hashes."""
        return list(self.index.keys())


class VersionedStorage:
    """Storage with versioning support."""
    
    def __init__(self,   storage=None, **kwargs):
        self.storage = storage
        self.versions_path = "versions"
    
    def store_version(self, key: str, data: Union[str, bytes, Dict[str, Any]], version: Optional[str] = None) -> str:
        """Store a new version of data."""
        if version is None:
            version = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        version_path = f"{self.versions_path}/{key}/{version}"
        self.storage.write(version_path, data)
        
        # Update latest pointer
        latest_path = f"{self.versions_path}/{key}/latest"
        self.storage.write(latest_path, version)
        
        return version
    
    def get_version(self, key: str, version: Optional[str] = None) -> Optional[Union[str, Dict[str, Any]]]:
        """Get specific version of data."""
        if version is None:
            # Get latest version
            latest_path = f"{self.versions_path}/{key}/latest"
            version = self.storage.read(latest_path)
            if not version:
                return None
        
        version_path = f"{self.versions_path}/{key}/{version}"
        return self.storage.read(version_path)
    
    def list_versions(self, key: str) -> List[str]:
        """List all versions of a key."""
        versions_dir = f"{self.versions_path}/{key}"
        versions = self.storage.list_files(versions_dir)
        # Filter out 'latest' pointer
        return [v.split('/')[-1] for v in versions if not v.endswith('latest')]
    
    def delete_version(self, key: str, version: str) -> bool:
        """Delete a specific version."""
        version_path = f"{self.versions_path}/{key}/{version}"
        return self.storage.delete(version_path)


class StorageManager:
    """Unified storage manager combining different storage backends."""
    
    def __init__(self,   base_path: str = "data", **kwargs):
        self.file_storage = FileStorage(base_path)
        self.async_storage = AsyncFileStorage(base_path)
        self.cache = CacheStorage(persist_path=f"{base_path}/cache.pkl")
        self.hash_storage = HashStorage(self.file_storage)
        self.versioned_storage = VersionedStorage(self.file_storage)
    
    def get_file_storage(self) -> FileStorage:
        """Get file storage instance."""
        return self.file_storage
    
    def get_async_storage(self) -> AsyncFileStorage:
        """Get async storage instance."""
        return self.async_storage
    
    def get_cache(self) -> CacheStorage:
        """Get cache storage instance."""
        return self.cache
    
    def get_hash_storage(self) -> HashStorage:
        """Get hash storage instance."""
        return self.hash_storage
    
    def get_versioned_storage(self) -> VersionedStorage:
        """Get versioned storage instance."""
        return self.versioned_storage


# Global storage manager instance
_storage_manager: Optional[StorageManager] = None


def get_storage_manager(base_path: str = "data") -> StorageManager:
    """Get global storage manager instance."""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager(base_path)
    return _storage_manager


def save_json(path: str, data: Dict[str, Any], storage: Optional[FileStorage] = None) -> bool:
    """Save JSON data to file."""
    if storage is None:
        storage = get_storage_manager().get_file_storage()
    return storage.write(path, data)


def load_json(path: str, storage: Optional[FileStorage] = None) -> Optional[Dict[str, Any]]:
    """Load JSON data from file."""
    if storage is None:
        storage = get_storage_manager().get_file_storage()
    data = storage.read(path)
    return data if isinstance(data, dict) else None


def save_text(path: str, text: str, storage: Optional[FileStorage] = None) -> bool:
    """Save text to file."""
    if storage is None:
        storage = get_storage_manager().get_file_storage()
    return storage.write(path, text)


def load_text(path: str, storage: Optional[FileStorage] = None) -> Optional[str]:
    """Load text from file."""
    if storage is None:
        storage = get_storage_manager().get_file_storage()
    data = storage.read(path)
    return data if isinstance(data, str) else None


async def save_json_async(path: str, data: Dict[str, Any], storage: Optional[AsyncFileStorage] = None) -> bool:
    """Save JSON data to file asynchronously."""
    if storage is None:
        storage = get_storage_manager().get_async_storage()
    return await storage.write(path, data)


async def load_json_async(path: str, storage: Optional[AsyncFileStorage] = None) -> Optional[Dict[str, Any]]:
    """Load JSON data from file asynchronously."""
    if storage is None:
        storage = get_storage_manager().get_async_storage()
    data = await storage.read(path)
    return data if isinstance(data, dict) else None


def cache_get(key: str, cache: Optional[CacheStorage] = None) -> Optional[Any]:
    """Get item from cache."""
    if cache is None:
        cache = get_storage_manager().get_cache()
    return cache.get(key)


def cache_set(key: str, value: Any, cache: Optional[CacheStorage] = None) -> None:
    """Set item in cache."""
    if cache is None:
        cache = get_storage_manager().get_cache()
    cache.set(key, value)


def ensure_directory(path: str, storage: Optional[FileStorage] = None) -> None:
    """Ensure directory exists."""
    if storage is None:
        storage = get_storage_manager().get_file_storage()
    full_path = storage.base_path / path
    full_path.mkdir(parents=True, exist_ok=True)


def cleanup_old_files(directory: str, max_age_days: int = 30, storage: Optional[FileStorage] = None) -> int:
    """Clean up old files in directory."""
    if storage is None:
        storage = get_storage_manager().get_file_storage()
    
    try:
        cleanup_path = storage.base_path / directory
        if not cleanup_path.exists():
            return 0
        
        cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
        deleted_count = 0
        
        for file_path in cleanup_path.rglob('*'):
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    handle_error(e)
        
        return deleted_count
    except Exception as e:
        handle_error(e)
        return 0

def VectorStore(*args, **kwargs):
    raise NotImplementedError('VectorStore not yet implemented')
