import asyncio
import contextvars
import functools
import inspect
import logging
import sys
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, Union

from config.logger import get_logger

logger = get_logger(__name__)

# Correlation ID context variable for tracking requests across async boundaries
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('correlation_id', default='')


class PhysicsError(Exception):
    """Base exception for all physics discovery system errors."""
    
    def __init__(self,       message=None,       error_code: str = "PHYSICS_ERROR",       context: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.correlation_id = correlation_id_var.get() or str(uuid.uuid4())
        self.timestamp = datetime.utcnow()


class ValidationError(PhysicsError):
    """Raised when validation fails."""
    
    def __init__(self,       message=None,       field: str = "",       value: Any = None, **kwargs):
        super().__init__(message, "VALIDATION_ERROR", {"field": field, "value": value})
        self.field = field
        self.value = value


class ConfigurationError(PhysicsError):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self,       message=None,       config_key: str = "", **kwargs):
        super().__init__(message, "CONFIG_ERROR", {"config_key": config_key})
        self.config_key = config_key


class APIError(PhysicsError):
    """Raised when external API calls fail."""
    
    def __init__(self,       message=None,       api_name: str = "",       status_code: Optional[int] = None, **kwargs):
        super().__init__(message, "API_ERROR", {"api_name": api_name, "status_code": status_code})
        self.api_name = api_name
        self.status_code = status_code


class AgentError(PhysicsError):
    """Raised when agent operations fail."""
    
    def __init__(self,       message=None,       agent_name: str = "",       operation: str = "", **kwargs):
        super().__init__(message, "AGENT_ERROR", {"agent_name": agent_name, "operation": operation})
        self.agent_name = agent_name
        self.operation = operation


class KnowledgeError(PhysicsError):
    """Raised when knowledge operations fail."""
    
    def __init__(self,       message=None,       knowledge_type: str = "",       operation: str = "", **kwargs):
        super().__init__(message, "KNOWLEDGE_ERROR", {"knowledge_type": knowledge_type, "operation": operation})
        self.knowledge_type = knowledge_type
        self.operation = operation


class MemoryError(PhysicsError):
    """Raised when memory operations fail."""
    
    def __init__(self,       message=None,       memory_type: str = "",       operation: str = "", **kwargs):
        super().__init__(message, "MEMORY_ERROR", {"memory_type": memory_type, "operation": operation})
        self.memory_type = memory_type
        self.operation = operation


class ThinkingError(PhysicsError):
    """Raised when thinking/reasoning operations fail."""
    
    def __init__(self,       message=None,       thinking_type: str = "",       operation: str = "", **kwargs):
        super().__init__(message, "THINKING_ERROR", {"thinking_type": thinking_type, "operation": operation})
        self.thinking_type = thinking_type
        self.operation = operation


class DiscoveryError(PhysicsError):
    """Raised when discovery operations fail."""
    
    def __init__(self,       message=None,       discovery_phase: str = "",       operation: str = "", **kwargs):
        super().__init__(message, "DISCOVERY_ERROR", {"discovery_phase": discovery_phase, "operation": operation})
        self.discovery_phase = discovery_phase
        self.operation = operation


class PhysicsCalculationError(PhysicsError):
    """Raised when physics calculations fail."""
    
    def __init__(self,       message=None,       calculation_type: str = "",       parameters: Optional[Dict] = None, **kwargs):
        super().__init__(message, "PHYSICS_CALC_ERROR", {"calculation_type": calculation_type, "parameters": parameters})
        self.calculation_type = calculation_type
        self.parameters = parameters or {}


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID in context."""
    if correlation_id is None:
        correlation_id = generate_correlation_id()
    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str:
    """Get current correlation ID from context."""
    return correlation_id_var.get() or ""


def with_correlation_id(func):
    """Decorator to inject correlation ID into function context."""
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            correlation_id = kwargs.pop('correlation_id', None)
            if correlation_id:
                set_correlation_id(correlation_id)
            elif not get_correlation_id():
                set_correlation_id()
            return await func(*args, **kwargs)
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            correlation_id = kwargs.pop('correlation_id', None)
            if correlation_id:
                set_correlation_id(correlation_id)
            elif not get_correlation_id():
                set_correlation_id()
            return func(*args, **kwargs)
        return sync_wrapper


def get_enriched_stack_trace(exc: Exception, max_frames: int = 20) -> List[Dict[str, Any]]:
    """Get enriched stack trace with local variables."""
    tb = exc.__traceback__
    frames = []
    
    while tb and len(frames) < max_frames:
        frame = tb.tb_frame
        code = frame.f_code
        
        # Get local variables (limit size to avoid memory issues)
        local_vars = {}
        for key, value in frame.f_locals.items():
            try:
                # Only include simple types and limit string length
                if isinstance(value, (str, int, float, bool, type(None))):
                    if isinstance(value, str) and len(value) > 200:
                        local_vars[key] = value[:200] + "..."
                    else:
                        local_vars[key] = value
                elif hasattr(value, '__name__'):
                    local_vars[key] = f"<{type(value).__name__}: {getattr(value, '__name__', 'unknown')}>"
                else:
                    local_vars[key] = f"<{type(value).__name__}>"
            except Exception:
                local_vars[key] = "<error_getting_value>"
        
        frame_info = {
            "file": code.co_filename,
            "line": tb.tb_lineno,
            "function": code.co_name,
            "locals": local_vars
        }
        
        frames.append(frame_info)
        tb = tb.tb_next
    
    return frames


def handle_error(exc: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Global error handler that enriches exceptions with context and correlation IDs."""
    correlation_id = get_correlation_id()
    if not correlation_id:
        correlation_id = generate_correlation_id()
        set_correlation_id(correlation_id)
    
    error_info = {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "context": context or {}
    }
    
    # Add physics error specific information
    if isinstance(exc, PhysicsError):
        error_info.update({
            "error_code": exc.error_code,
            "physics_context": exc.context,
            "physics_correlation_id": exc.correlation_id
        })
    
    # Get enriched stack trace
    if exc.__traceback__:
        error_info["stack_trace"] = get_enriched_stack_trace(exc)
        error_info["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
    
    # Add system information
    frame = inspect.currentframe()
    if frame and frame.f_back:
        caller_frame = frame.f_back
        error_info["caller"] = {
            "file": caller_frame.f_code.co_filename,
            "line": caller_frame.f_lineno,
            "function": caller_frame.f_code.co_name
        }
    
    # Log the error
    logger.error(
        f"Error {error_info['error_type']}: {error_info['error_message']}",
        extra={
            "correlation_id": correlation_id,
            "error_code": getattr(exc, "error_code", "UNKNOWN"),
            "context": error_info["context"]
        },
        exc_info=True
    )
    
    return error_info


def safe_execute(func, *args, **kwargs):
    """Safely execute a function with error handling."""
    try:
        if asyncio.iscoroutinefunction(func):
            return asyncio.create_task(func(*args, **kwargs))
        else:
            return func(*args, **kwargs)
    except Exception as e:
        error_info = handle_error(e, {"function": func.__name__, "args": str(args), "kwargs": str(kwargs)})
        raise PhysicsError(f"Safe execution failed: {str(e)}", "SAFE_EXEC_ERROR", error_info)


async def safe_execute_async(func, *args, **kwargs):
    """Safely execute an async function with error handling."""
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        error_info = handle_error(e, {"function": func.__name__, "args": str(args), "kwargs": str(kwargs)})
        raise PhysicsError(f"Safe async execution failed: {str(e)}", "SAFE_ASYNC_EXEC_ERROR", error_info)


def error_boundary(reraise: bool = True, default_return=None):
    """Decorator to create an error boundary around functions."""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    handle_error(e, {"function": func.__name__})
                    if reraise:
                        raise
                    return default_return
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    handle_error(e, {"function": func.__name__})
                    if reraise:
                        raise
                    return default_return
            return sync_wrapper
    return decorator


class ErrorCollector:
    """Collects and manages multiple errors during batch operations."""
    
    def __init__(self, **kwargs):
        self.errors: List[Dict[str, Any]] = []
        self.correlation_id = get_correlation_id() or generate_correlation_id()
    
    def add_error(self, exc: Exception, context: Optional[Dict[str, Any]] = None):
        """Add an error to the collection."""
        error_info = handle_error(exc, context)
        self.errors.append(error_info)
    
    def has_errors(self) -> bool:
        """Check if any errors have been collected."""
        return len(self.errors) > 0
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of collected errors."""
        return {
            "total_errors": len(self.errors),
            "correlation_id": self.correlation_id,
            "errors": self.errors,
            "error_types": list(set(error["error_type"] for error in self.errors))
        }
    
    def raise_if_errors(self):
        """Raise a PhysicsError if any errors were collected."""
        if self.has_errors():
            summary = self.get_error_summary()
            raise PhysicsError(
                f"Batch operation failed with {summary['total_errors']} errors",
                "BATCH_ERROR",
                summary
            )


# Global exception hook for uncaught exceptions
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Global handler for uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    correlation_id = get_correlation_id() or generate_correlation_id()
    set_correlation_id(correlation_id)
    
    logger.critical(
        f"Uncaught exception: {exc_type.__name__}: {exc_value}",
        extra={"correlation_id": correlation_id},
        exc_info=(exc_type, exc_value, exc_traceback)
    )
    
    # Still call the default handler to ensure proper exit
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# Install the global exception handler
sys.excepthook = global_exception_handler
KeyboardInterrupt = type('KeyboardInterrupt', (), {})  # auto-stub: not found in project
