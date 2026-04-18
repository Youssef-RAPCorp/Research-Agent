"""
utils/config — compatibility shim
AI-generated modules sometimes import from utils.config instead of config.settings.
This re-exports everything from the canonical module so those imports don't break.
"""
from config.settings import *  # noqa: F401,F403
try:
    from config.settings import get_settings, Settings
except ImportError:
    pass
