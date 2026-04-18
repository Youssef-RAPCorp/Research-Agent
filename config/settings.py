import os
from typing import Optional
from pydantic import Field, validator, field_validator, ConfigDict
from pydantic_settings import BaseSettings
from pydantic.config import ConfigDict


class KnowledgeSettings(BaseSettings):
    """Configuration for knowledge management components."""
    qdrant_host: str = Field(default="localhost", description="Qdrant vector database host")
    qdrant_port: int = Field(default=6333, description="Qdrant vector database port")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", description="Embedding model name")
    retrieval_top_k: int = Field(default=10, description="Top K results for retrieval")
    arxiv_max_results: int = Field(default=50, description="Maximum ArXiv search results")


class LLMSettings(BaseSettings):
    """Configuration for language model integrations."""
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic Claude API key")
    google_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    default_model: str = Field(default="claude-3-sonnet-20240229", description="Default LLM model")
    max_tokens: int = Field(default=4096, description="Maximum tokens per request")
    temperature: float = Field(default=0.1, description="Temperature for LLM responses")


class MemorySettings(BaseSettings):
    """Configuration for memory systems."""
    episodic_max_size: int = Field(default=1000, description="Maximum episodic memory entries")
    semantic_max_size: int = Field(default=10000, description="Maximum semantic memory entries")
    working_memory_capacity: int = Field(default=7, description="Working memory capacity")
    persistence_interval: int = Field(default=300, description="Memory persistence interval in seconds")


class ThinkingSettings(BaseSettings):
    """Configuration for thinking and reasoning systems."""
    max_refinement_steps: int = Field(default=3, description="Maximum self-refinement steps")
    reflection_depth: int = Field(default=2, description="Reflection recursion depth")
    tree_of_thoughts_width: int = Field(default=5, description="Tree of thoughts breadth")
    mcts_simulations: int = Field(default=100, description="MCTS simulation count")


class AgentSettings(BaseSettings):
    """Configuration for agent systems."""
    max_parallel_agents: int = Field(default=5, description="Maximum parallel agents")
    agent_timeout: int = Field(default=300, description="Agent task timeout in seconds")
    communication_timeout: int = Field(default=30, description="Agent communication timeout")
    orchestrator_mode: str = Field(default="collaborative", description="Orchestrator operation mode")


class PhysicsSettings(BaseSettings):
    """Configuration for physics computation systems."""
    dimensional_tolerance: float = Field(default=1e-10, description="Dimensional analysis tolerance")
    sympy_timeout: int = Field(default=60, description="SymPy computation timeout")
    theory_validation_steps: int = Field(default=5, description="Theory validation steps")
    hypothesis_confidence_threshold: float = Field(default=0.7, description="Hypothesis confidence threshold")


class DiscoverySettings(BaseSettings):
    """Configuration for discovery systems."""
    discovery_loop_interval: int = Field(default=3600, description="Discovery loop interval in seconds")
    evidence_search_depth: int = Field(default=3, description="Evidence search depth")
    hypothesis_tracking_limit: int = Field(default=100, description="Maximum tracked hypotheses")
    scheduler_max_tasks: int = Field(default=50, description="Scheduler maximum concurrent tasks")


class InterfaceSettings(BaseSettings):
    """Configuration for interface systems."""
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    cors_origins: list = Field(default=["*"], description="CORS allowed origins")
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per minute")


class FirebaseSettings(BaseSettings):
    """Configuration for Firebase integration."""
    firebase_project_id: Optional[str] = Field(default=None, description="Firebase project ID")
    firebase_credentials_path: Optional[str] = Field(default=None, description="Firebase credentials file path")
    firebase_database_url: Optional[str] = Field(default=None, description="Firebase database URL")


class SecuritySettings(BaseSettings):
    """Configuration for security settings."""
    secret_key: str = Field(default="dev-secret-key-change-in-production", description="Application secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration: int = Field(default=86400, description="JWT expiration time in seconds")
    api_key_header: str = Field(default="X-API-Key", description="API key header name")


class Settings(BaseSettings):
    """Main application settings combining all configuration sections."""
    model_config = ConfigDict(extra="ignore", env_file=".env", case_sensitive=False)
    
    # Core settings
    app_name: str = Field(default="Physics Discovery System v3.0", description="Application name")
    version: str = Field(default="3.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment (development/staging/production)")
    debug: bool = Field(default=True, description="Debug mode enabled")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # API keys (direct fields for compatibility)
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic Claude API key")
    google_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    
    # Qdrant settings (direct fields for compatibility)
    qdrant_host: str = Field(default="localhost", description="Qdrant vector database host")
    qdrant_port: int = Field(default=6333, description="Qdrant vector database port")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    
    # Common settings (direct fields for compatibility)
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", description="Embedding model name")
    retrieval_top_k: int = Field(default=10, description="Top K results for retrieval")
    firebase_project_id: Optional[str] = Field(default=None, description="Firebase project ID")
    firebase_credentials_path: Optional[str] = Field(default=None, description="Firebase credentials file path")
    secret_key: str = Field(default="dev-secret-key-change-in-production", description="Application secret key")
    arxiv_max_results: int = Field(default=50, description="Maximum ArXiv search results")
    
    # Nested configuration sections
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    thinking: ThinkingSettings = Field(default_factory=ThinkingSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    physics: PhysicsSettings = Field(default_factory=PhysicsSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    interface: InterfaceSettings = Field(default_factory=InterfaceSettings)
    firebase: FirebaseSettings = Field(default_factory=FirebaseSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @field_validator('environment')
    def validate_environment(cls, v):
        """Validate environment setting."""
        valid_envs = ['development', 'staging', 'production']
        if v not in valid_envs:
            raise ValueError(f'Environment must be one of {valid_envs}')
        return v

    @field_validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level setting."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of {valid_levels}')
        return v.upper()

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == 'production'

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == 'development'

    def get_database_url(self) -> str:
        """Get database connection URL."""
        if self.firebase.firebase_database_url:
            return self.firebase.firebase_database_url
        return f"firebase://{self.firebase.firebase_project_id}"


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment variables."""
    global _settings
    _settings = Settings()
    return _settings