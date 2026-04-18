import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

# [auto-removed unresolvable import] # [auto-removed unresolvable import] # [auto-removed unresolvable import] from firebase_admin import credentials, firestore, auth, storage, initialize_app
import firebase_admin
# [auto-removed unresolvable import] from google.cloud import firestore as gcs_firestore
# [auto-removed unresolvable import] from google.api_core import retry
from pydantic import BaseModel, Field

from config.settings import get_settings
from config.logger import get_logger
from config.errors import handle_error


class RAPCorpUser(BaseModel):
    """RAP Corp user document schema."""
    uid: str
    email: str
    display_name: Optional[str] = None
    role: str = "researcher"
    department: str = "physics"
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: Optional[datetime] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)


class ResearchSession(BaseModel):
    """Research session document schema."""
    session_id: str
    user_uid: str
    query: str
    mode: str = "discovery"
    pattern: str = "synthesis"
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    results: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HypothesisRecord(BaseModel):
    """Physics hypothesis tracking schema."""
    hypothesis_id: str
    session_id: str
    user_uid: str
    title: str
    description: str
    mathematical_formulation: Optional[str] = None
    evidence_score: float = 0.0
    validation_status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    citations: List[str] = Field(default_factory=list)
    peer_reviews: List[Dict[str, Any]] = Field(default_factory=list)


class ExperimentResult(BaseModel):
    """Experimental result schema."""
    experiment_id: str
    hypothesis_id: str
    user_uid: str
    experiment_type: str
    parameters: Dict[str, Any]
    results: Dict[str, Any]
    statistical_significance: Optional[float] = None
    reproducibility_score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)
    validated: bool = False


class FirebaseClient:
    """Async Firebase client with RAP Corp schemas and retry logic."""
    
    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.settings = get_settings()
        self._app: Optional[firebase_admin.App] = None
        self._db: Optional[gcs_firestore.AsyncClient] = None
        self._auth: Optional[auth.Client] = None
        self._storage: Optional[storage.bucket.Bucket] = None
        self._retry_config = retry.Retry(
            initial=1.0,
            maximum=60.0,
            multiplier=2.0,
            deadline=300.0
        )
    
    async def initialize(self) -> None:
        """Initialize Firebase services."""
        try:
            if not self._app:
                # TODO: Replace with actual Firebase credentials
                if self.settings.firebase_credentials_path and Path(self.settings.firebase_credentials_path).exists():
                    cred = credentials.Certificate(self.settings.firebase_credentials_path)
                    self._app = initialize_app(cred, {
                        'projectId': self.settings.firebase_project_id,
                        'storageBucket': f"{self.settings.firebase_project_id}.appspot.com"
                    })
                else:
                    # Use default credentials for development
                    self._app = initialize_app()
                
                self._db = firestore.async_client(app=self._app)
                self._auth = auth.Client(app=self._app)
                self._storage = storage.bucket(app=self._app)
                
                await self._setup_collections()
                self.logger.info("Firebase client initialized successfully")
                
        except Exception as e:
            handle_error(e)
            raise
    
    async def _setup_collections(self) -> None:
        """Setup Firestore collections with proper indexes."""
        collections = [
            'rap_corp_users',
            'research_sessions', 
            'hypothesis_records',
            'experiment_results',
            'peer_reviews',
            'physics_theories'
        ]
        
        for collection in collections:
            try:
                await self._db.collection(collection).limit(1).get()
            except Exception:
                # Collection doesn't exist, create with sample doc
                doc_ref = self._db.collection(collection).document('_init')
                await doc_ref.set({'initialized': True, 'created_at': datetime.now()})
                await doc_ref.delete()
    
    async def create_user(self, user_data: RAPCorpUser) -> str:
        """Create a new RAP Corp user."""
        try:
            doc_ref = self._db.collection('rap_corp_users').document(user_data.uid)
            await doc_ref.set(user_data.model_dump())
            self.logger.info(f"Created user: {user_data.uid}")
            return user_data.uid
        except Exception as e:
            handle_error(e)
            raise
    
    async def get_user(self, uid: str) -> Optional[RAPCorpUser]:
        """Retrieve user by UID."""
        try:
            doc = await self._db.collection('rap_corp_users').document(uid).get()
            if doc.exists:
                return RAPCorpUser(**doc.to_dict())
            return None
        except Exception as e:
            handle_error(e)
            raise
    
    async def update_user_activity(self, uid: str) -> None:
        """Update user's last active timestamp."""
        try:
            doc_ref = self._db.collection('rap_corp_users').document(uid)
            await doc_ref.update({'last_active': datetime.now()})
        except Exception as e:
            handle_error(e)
            raise
    
    async def create_research_session(self, session: ResearchSession) -> str:
        """Create a new research session."""
        try:
            doc_ref = self._db.collection('research_sessions').document(session.session_id)
            await doc_ref.set(session.model_dump())
            self.logger.info(f"Created research session: {session.session_id}")
            return session.session_id
        except Exception as e:
            handle_error(e)
            raise
    
    async def update_session_results(self, session_id: str, results: List[Dict[str, Any]]) -> None:
        """Update research session results."""
        try:
            doc_ref = self._db.collection('research_sessions').document(session_id)
            await doc_ref.update({
                'results': results,
                'updated_at': datetime.now()
            })
        except Exception as e:
            handle_error(e)
            raise
    
    async def get_user_sessions(self, user_uid: str, limit: int = 50) -> List[ResearchSession]:
        """Get user's research sessions."""
        try:
            query = (self._db.collection('research_sessions')
                    .where('user_uid', '==', user_uid)
                    .order_by('created_at', direction=firestore.Query.DESCENDING)
                    .limit(limit))
            
            docs = await query.get()
            return [ResearchSession(**doc.to_dict()) for doc in docs]
        except Exception as e:
            handle_error(e)
            return []
    
    async def create_hypothesis(self, hypothesis: HypothesisRecord) -> str:
        """Create a new physics hypothesis record."""
        try:
            doc_ref = self._db.collection('hypothesis_records').document(hypothesis.hypothesis_id)
            await doc_ref.set(hypothesis.model_dump())
            self.logger.info(f"Created hypothesis: {hypothesis.hypothesis_id}")
            return hypothesis.hypothesis_id
        except Exception as e:
            handle_error(e)
            raise
    
    async def update_hypothesis_evidence(self, hypothesis_id: str, evidence_score: float) -> None:
        """Update hypothesis evidence score."""
        try:
            doc_ref = self._db.collection('hypothesis_records').document(hypothesis_id)
            await doc_ref.update({
                'evidence_score': evidence_score,
                'updated_at': datetime.now()
            })
        except Exception as e:
            handle_error(e)
            raise
    
    async def get_top_hypotheses(self, limit: int = 10) -> List[HypothesisRecord]:
        """Get top-rated hypotheses by evidence score."""
        try:
            query = (self._db.collection('hypothesis_records')
                    .order_by('evidence_score', direction=firestore.Query.DESCENDING)
                    .limit(limit))
            
            docs = await query.get()
            return [HypothesisRecord(**doc.to_dict()) for doc in docs]
        except Exception as e:
            handle_error(e)
            return []
    
    async def create_experiment_result(self, result: ExperimentResult) -> str:
        """Store experimental result."""
        try:
            doc_ref = self._db.collection('experiment_results').document(result.experiment_id)
            await doc_ref.set(result.model_dump())
            self.logger.info(f"Created experiment result: {result.experiment_id}")
            return result.experiment_id
        except Exception as e:
            handle_error(e)
            raise
    
    async def get_hypothesis_experiments(self, hypothesis_id: str) -> List[ExperimentResult]:
        """Get all experiments for a hypothesis."""
        try:
            query = self._db.collection('experiment_results').where('hypothesis_id', '==', hypothesis_id)
            docs = await query.get()
            return [ExperimentResult(**doc.to_dict()) for doc in docs]
        except Exception as e:
            handle_error(e)
            return []
    
    async def search_hypotheses(self, query_text: str, limit: int = 20) -> List[HypothesisRecord]:
        """Search hypotheses by text content."""
        try:
            # Simple text search - for production, use Firestore full-text search
            docs = await (self._db.collection('hypothesis_records')
                         .order_by('evidence_score', direction=firestore.Query.DESCENDING)
                         .limit(limit * 2)
                         .get())
            
            results = []
            query_lower = query_text.lower()
            
            for doc in docs:
                hypothesis = HypothesisRecord(**doc.to_dict())
                if (query_lower in hypothesis.title.lower() or 
                    query_lower in hypothesis.description.lower()):
                    results.append(hypothesis)
                    if len(results) >= limit:
                        break
            
            return results
        except Exception as e:
            handle_error(e)
            return []
    
    async def store_file(self, file_path: str, content: bytes, content_type: str = 'application/octet-stream') -> str:
        """Store file in Firebase Storage."""
        try:
            blob = self._storage.blob(file_path)
            blob.upload_from_string(content, content_type=content_type)
            
            # Make file publicly readable
            blob.make_public()
            
            self.logger.info(f"Stored file: {file_path}")
            return blob.public_url
        except Exception as e:
            handle_error(e)
            raise
    
    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file from Firebase Storage."""
        try:
            blob = self._storage.blob(file_path)
            if blob.exists():
                return blob.download_as_bytes()
            return None
        except Exception as e:
            handle_error(e)
            return None
    
    async def batch_write(self, operations: List[Dict[str, Any]]) -> None:
        """Execute batch write operations."""
        try:
            batch = self._db.batch()
            
            for op in operations:
                collection = op['collection']
                doc_id = op['doc_id']
                data = op['data']
                operation = op.get('operation', 'set')
                
                doc_ref = self._db.collection(collection).document(doc_id)
                
                if operation == 'set':
                    batch.set(doc_ref, data)
                elif operation == 'update':
                    batch.update(doc_ref, data)
                elif operation == 'delete':
                    batch.delete(doc_ref)
            
            await batch.commit()
            self.logger.info(f"Executed batch write with {len(operations)} operations")
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def close(self) -> None:
        """Clean up Firebase resources."""
        try:
            if self._db:
                self._db.close()
            self.logger.info("Firebase client closed")
        except Exception as e:
            handle_error(e)


_firebase_client: Optional[FirebaseClient] = None


async def get_firebase_client() -> FirebaseClient:
    """Factory function to get Firebase client instance."""
    global _firebase_client
    
    if _firebase_client is None:
        _firebase_client = FirebaseClient()
        await _firebase_client.initialize()
    
    return _firebase_client

def get_firebase_client(*args, **kwargs):
    pass
