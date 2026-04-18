import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import redis.asyncio as redis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn

# Models
class HealthStatus(BaseModel):
    status: str
    timestamp: str
    version: str
    uptime_seconds: float

class StreamRequest(BaseModel):
    physics_query: str
    parameters: Dict[str, Any] = {}
    stream_id: Optional[str] = None

class TokenData(BaseModel):
    user_id: str
    role: str
    exp: datetime

class WebSocketMessage(BaseModel):
    type: str
    data: Dict[str, Any]
    timestamp: str

# Configuration
JWT_SECRET = "physics-discovery-secret-key"  # TODO: Move to environment variables
JWT_ALGORITHM = "HS256"
REDIS_URL = "redis://localhost:6379"  # TODO: Configure from environment
API_VERSION = "3.0.0"

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

# Redis connection manager
class RedisManager:
    def __init__(self, **kwargs):
        self.redis: Optional[redis.Redis] = None
    
    async def connect(self):
        """Initialize Redis connection."""
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()

redis_manager = RedisManager()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self, **kwargs):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept WebSocket connection and store client."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
    
    def disconnect(self, client_id: str):
        """Remove client connection."""
        self.active_connections.pop(client_id, None)
    
    async def send_personal_message(self, message: str, client_id: str):
        """Send message to specific client."""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
            except Exception:
                self.disconnect(client_id)
    
    async def broadcast(self, message: str):
        """Send message to all connected clients."""
        disconnected = []
        for client_id, connection in self.active_connections.items():
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(client_id)
        
        for client_id in disconnected:
            self.disconnect(client_id)

manager = ConnectionManager()

# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    start_time = time.time()
    app.state.start_time = start_time
    
    await redis_manager.connect()
    logging.info("FastAPI server started")
    
    yield
    
    await redis_manager.disconnect()
    logging.info("FastAPI server stopped")

# FastAPI app initialization
app = FastAPI(
    title="Physics Discovery System API",
    description="RAP Corp Physics Discovery System v3.0",
    version=API_VERSION,
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Verify JWT token and return user data."""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        token_data = TokenData(
            user_id=payload.get("user_id"),
            role=payload.get("role"),
            exp=datetime.fromtimestamp(payload.get("exp"))
        )
        if token_data.exp < datetime.utcnow():
            raise HTTPException(status_code=401, detail="Token expired")
        return token_data
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Physics simulation mock functions
async def simulate_physics_stream(query: str, parameters: Dict[str, Any]):
    """Generate physics simulation data stream."""
    for i in range(100):
        data = {
            "iteration": i,
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
            "energy": 100.0 + i * 0.5,
            "momentum": [i * 0.1, i * 0.2, i * 0.3],
            "field_strength": 50.0 - i * 0.1,
            "parameters": parameters
        }
        yield f"data: {json.dumps(data)}\n\n"
        await asyncio.sleep(0.1)

# Routes
@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Health check endpoint."""
    uptime = time.time() - app.state.start_time
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version=API_VERSION,
        uptime_seconds=uptime
    )

@app.post("/auth/token")
@limiter.limit("5/minute")
async def create_token(request: Request, user_id: str, role: str = "researcher"):
    """Create JWT token for authentication."""
    exp = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": exp.timestamp()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat()}

@app.post("/physics/stream")
@limiter.limit("10/minute")
async def start_physics_stream(
    request: Request,
    stream_request: StreamRequest,
    token_data: TokenData = Depends(verify_token)
):
    """Start Server-Sent Events physics simulation stream."""
    async def event_generator():
        yield "event: stream_start\n"
        yield f"data: {json.dumps({'message': 'Physics simulation started', 'query': stream_request.physics_query})}\n\n"
        
        async for data in simulate_physics_stream(stream_request.physics_query, stream_request.parameters):
            yield data
        
        yield "event: stream_end\n"
        yield f"data: {json.dumps({'message': 'Physics simulation completed'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time physics data."""
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "physics_request":
                # Start physics simulation
                response = WebSocketMessage(
                    type="physics_response",
                    data={"status": "simulation_started", "query": message_data.get("query", "")},
                    timestamp=datetime.utcnow().isoformat()
                )
                await manager.send_personal_message(response.model_dump_json(), client_id)
                
                # Simulate physics data
                for i in range(20):
                    physics_data = {
                        "iteration": i,
                        "energy": 100.0 + i * 2.0,
                        "temperature": 273.15 + i * 10,
                        "pressure": 101325 + i * 1000
                    }
                    response = WebSocketMessage(
                        type="physics_data",
                        data=physics_data,
                        timestamp=datetime.utcnow().isoformat()
                    )
                    await manager.send_personal_message(response.model_dump_json(), client_id)
                    await asyncio.sleep(0.5)
            
            elif message_data.get("type") == "broadcast":
                message = WebSocketMessage(
                    type="broadcast",
                    data={"message": message_data.get("message"), "from": client_id},
                    timestamp=datetime.utcnow().isoformat()
                )
                await manager.broadcast(message.model_dump_json())
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)

@app.get("/physics/experiments")
@limiter.limit("30/minute")
async def list_experiments(
    request: Request,
    token_data: TokenData = Depends(verify_token)
):
    """List available physics experiments."""
    experiments = [
        {
            "id": "quantum_entanglement",
            "name": "Quantum Entanglement Simulation",
            "description": "Study quantum entanglement properties",
            "parameters": ["particle_count", "interaction_strength"]
        },
        {
            "id": "electromagnetic_field",
            "name": "Electromagnetic Field Analysis",
            "description": "Analyze electromagnetic field interactions",
            "parameters": ["field_strength", "frequency", "polarization"]
        },
        {
            "id": "thermodynamics",
            "name": "Thermodynamic Process Modeling",
            "description": "Model thermodynamic processes and phase transitions",
            "parameters": ["temperature", "pressure", "volume"]
        }
    ]
    return {"experiments": experiments}

@app.post("/physics/experiments/{experiment_id}/run")
@limiter.limit("5/minute")
async def run_experiment(
    request: Request,
    experiment_id: str,
    parameters: Dict[str, Any],
    token_data: TokenData = Depends(verify_token)
):
    """Run a specific physics experiment with parameters."""
    # Store experiment in Redis
    if redis_manager.redis:
        experiment_data = {
            "experiment_id": experiment_id,
            "user_id": token_data.user_id,
            "parameters": parameters,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "running"
        }
        await redis_manager.redis.setex(
            f"experiment:{experiment_id}:{token_data.user_id}",
            3600,
            json.dumps(experiment_data)
        )
    
    return {
        "experiment_id": experiment_id,
        "status": "started",
        "estimated_duration": "30 seconds",
        "parameters": parameters
    }

@app.get("/metrics")
@limiter.limit("60/minute")
async def get_metrics(request: Request, token_data: TokenData = Depends(verify_token)):
    """Get system metrics and statistics."""
    metrics = {
        "active_connections": len(manager.active_connections),
        "uptime_seconds": time.time() - app.state.start_time,
        "memory_usage": "TODO: Implement memory monitoring",  # TODO: Add memory monitoring
        "api_version": API_VERSION,
        "timestamp": datetime.utcnow().isoformat()
    }
    return metrics

if __name__ == "__main__":
    uvicorn.run(
        "interface.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )