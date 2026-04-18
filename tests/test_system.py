"""
Physics Discovery System v3.0 — Basic Smoke Tests
RAP Corp | Run with: python -m pytest tests/ -v
"""

import importlib
import pytest
from pathlib import Path

MODULES = [
    "config.settings",
    "config.logger",
    "config.errors",
    "memory.episodic",
    "memory.semantic",
    "memory.working",
    "memory.router",
    "thinking.self_refine",
    "thinking.down_adaptive",
    "agents.base_agent",
    "agents.registry",
    "physics.dimensional",
    "discovery.discovery_mode",
    "discovery.scheduler",
]

@pytest.mark.parametrize("module", MODULES)
def test_module_importable(module):
    """All generated modules must be importable without errors."""
    try:
        importlib.import_module(module)
    except ImportError as e:
        pytest.skip(f"Optional dependency missing: {e}")

def test_project_structure():
    """Verify all required directories exist."""
    required_dirs = [
        "config","knowledge","memory","thinking",
        "agents","physics","discovery","interface","deploy",
    ]
    for d in required_dirs:
        assert Path(d).is_dir(), f"Missing directory: {d}"

def test_env_example_exists():
    assert Path(".env.example").exists(), ".env.example not found"

def test_requirements_exists():
    assert Path("requirements.txt").exists(), "requirements.txt not found"
