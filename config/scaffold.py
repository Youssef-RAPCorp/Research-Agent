import os
from pathlib import Path
from typing import Dict, Any, Optional
import tomli_w
import numpy as np


def create_project_structure(base_path: Optional[Path] = None) -> None:
    """Create the complete project directory structure."""
    if base_path is None:
        base_path = Path.cwd()
    
    directories = [
        "config",
        "knowledge",
        "memory", 
        "thinking",
        "agents",
        "physics",
        "discovery",
        "interface",
        "data",
        "data/cache",
        "data/papers",
        "data/embeddings",
        "logs",
        "tests",
        "tests/unit",
        "tests/integration",
        "docs"
    ]
    
    for directory in directories:
        dir_path = base_path / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py for Python packages
        if not directory.startswith(("data", "logs", "tests", "docs")):
            (dir_path / "__init__.py").touch()


def generate_env_template() -> str:
    """Generate a .env template with all required environment variables."""
    template = """# Physics Discovery System v3.0 Environment Configuration

# API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here

# Vector Database (Qdrant)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=your_qdrant_api_key_here

# Embedding Configuration
EMBEDDING_MODEL=text-embedding-ada-002
RETRIEVAL_TOP_K=10

# Firebase Configuration
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_CREDENTIALS_PATH=path/to/firebase/credentials.json

# Application Security
SECRET_KEY=your_secret_key_here

# ArXiv Configuration
ARXIV_MAX_RESULTS=50

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/physics_discovery.log

# Development Settings
DEBUG=false
ENVIRONMENT=production
"""
    return template


def write_env_template(base_path: Optional[Path] = None) -> None:
    """Write the .env template to the project root."""
    if base_path is None:
        base_path = Path.cwd()
    
    env_path = base_path / ".env.template"
    env_path.write_text(generate_env_template())


def generate_pyproject_toml() -> Dict[str, Any]:
    """Generate pyproject.toml configuration."""
    return {
        "build-system": {
            "requires": ["setuptools>=61.0", "wheel"],
            "build-backend": "setuptools.build_meta"
        },
        "project": {
            "name": "physics-discovery-system",
            "version": "3.0.0",
            "description": "AI multi-agent system for automated physics discovery",
            "authors": [{"name": "RAP Corp", "email": "research@rapcorp.com"}],
            "license": {"text": "MIT"},
            "readme": "README.md",
            "requires-python": ">=3.11",
            "classifiers": [
                "Development Status :: 3 - Alpha",
                "Intended Audience :: Science/Research",
                "License :: OSI Approved :: MIT License",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3.11",
                "Topic :: Scientific/Engineering :: Physics"
            ],
            "dependencies": [
                "anthropic>=0.7.0",
                "qdrant-client>=1.7.0",
                "openai>=1.0.0",
                "tiktoken>=0.5.0",
                "arxiv>=2.0.0",
                "PyPDF2>=3.0.0",
                "numpy>=1.24.0",
                "sympy>=1.12",
                "scipy>=1.11.0",
                "pydantic>=2.0.0",
                "pydantic-settings>=2.0.0",
                "fastapi>=0.104.0",
                "uvicorn>=0.24.0",
                "python-multipart>=0.0.6",
                "firebase-admin>=6.0.0",
                "python-dotenv>=1.0.0",
                "aiofiles>=23.0.0",
                "httpx>=0.25.0",
                "tenacity>=8.0.0",
                "rich>=13.0.0",
                "typer>=0.9.0",
                "pytest>=7.0.0",
                "pytest-asyncio>=0.21.0",
                "black>=23.0.0",
                "isort>=5.12.0",
                "flake8>=6.0.0",
                "mypy>=1.6.0",
                "pre-commit>=3.0.0"
            ]
        },
        "tool": {
            "setuptools": {
                "packages": ["config", "knowledge", "memory", "thinking", "agents", "physics", "discovery", "interface"]
            },
            "black": {
                "line-length": 88,
                "target-version": ["py311"],
                "include": "\\.pyi?$"
            },
            "isort": {
                "profile": "black",
                "multi_line_output": 3,
                "line_length": 88
            },
            "mypy": {
                "python_version": "3.11",
                "warn_return_any": True,
                "warn_unused_configs": True,
                "disallow_untyped_defs": True
            },
            "pytest": {
                "ini_options": {
                    "asyncio_mode": "auto",
                    "testpaths": ["tests"],
                    "python_files": ["test_*.py", "*_test.py"],
                    "python_classes": ["Test*"],
                    "python_functions": ["test_*"]
                }
            }
        }
    }


def write_pyproject_toml(base_path: Optional[Path] = None) -> None:
    """Write pyproject.toml to the project root."""
    if base_path is None:
        base_path = Path.cwd()
    
    pyproject_path = base_path / "pyproject.toml"
    config = generate_pyproject_toml()
    
    with open(pyproject_path, "wb") as f:
        tomli_w.dump(config, f)


def scaffold_project(base_path: Optional[Path] = None) -> None:
    """Create complete project scaffold with structure, .env template, and pyproject.toml."""
    if base_path is None:
        base_path = Path.cwd()
    
    print(f"Creating Physics Discovery System v3.0 project structure at {base_path}")
    
    create_project_structure(base_path)
    write_env_template(base_path)
    write_pyproject_toml(base_path)
    
    # Create basic README
    readme_content = """# Physics Discovery System v3.0

AI multi-agent system for automated physics discovery and research.

## Setup

1. Copy `.env.template` to `.env` and fill in your API keys
2. Install dependencies: `pip install -e .`
3. Run the system: `python -m interface.api`

## Development

- Run tests: `pytest`
- Format code: `black .`
- Type check: `mypy .`
"""
    
    (base_path / "README.md").write_text(readme_content)
    
    print("Project scaffold created successfully!")
    print("Next steps:")
    print("1. Copy .env.template to .env and configure your API keys")
    print("2. Run: pip install -e .")
    print("3. Start developing!")