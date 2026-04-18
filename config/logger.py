import logging
import logging.handlers
import os
import re
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import sys

from config.settings import get_settings


@dataclass
class LogAnalysis:
    """Analysis of previous log file."""
    error_count: int = 0
    memory_warnings: int = 0
    crash_indicators: int = 0
    last_startup: Optional[datetime] = None
    failure_patterns: List[str] = None
    recovery_suggestions: List[str] = None
    
    def __post_init__(self):
        if self.failure_patterns is None:
            self.failure_patterns = []
        if self.recovery_suggestions is None:
            self.recovery_suggestions = []


@dataclass
class RetryStrategy:
    """Adaptive retry strategy based on log analysis."""
    max_retries: int = 3
    base_delay: float = 1.0
    backoff_multiplier: float = 2.0
    circuit_breaker_threshold: int = 5
    memory_limit_mb: int = 1024
    
    def adjust_for_analysis(self, analysis: LogAnalysis) -> None:
        """Adjust strategy based on log analysis."""
        if analysis.memory_warnings > 0:
            self.memory_limit_mb = min(512, self.memory_limit_mb)
        
        if analysis.error_count > 10:
            self.max_retries = min(2, self.max_retries)
            self.base_delay = min(0.5, self.base_delay)
        
        if analysis.crash_indicators > 0:
            self.circuit_breaker_threshold = 3


class SelfAwareFormatter(logging.Formatter):
    """Custom formatter that adds context about system state."""
    
    def format(self, record):
        # Add memory usage info
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            record.memory_mb = f"{memory_mb:.1f}"
        except:
            record.memory_mb = "unknown"
        
        # Add custom fields
        if not hasattr(record, 'component'):
            record.component = getattr(record, 'name', 'unknown').split('.')[-1]
        
        return super().format(record)


class SelfAwareLogger:
    """Self-aware logger that analyzes its own logs for adaptive behavior."""
    
    def __init__(self,      name: str = "physics_discovery", **kwargs):
        self.settings = get_settings()
        self.name = name
        self.log_dir = Path("logs")
        self.log_file = self.log_dir / f"{name}.log"
        self.analysis_file = self.log_dir / f"{name}_analysis.json"
        
        # Create logs directory
        self.log_dir.mkdir(exist_ok=True)
        
        # Analyze previous logs on startup
        self.analysis = self._analyze_previous_logs()
        self.retry_strategy = RetryStrategy()
        self.retry_strategy.adjust_for_analysis(self.analysis)
        
        # Setup logger
        self._setup_logger()
        
        # Log startup analysis
        self._log_startup_analysis()
    
    def _setup_logger(self) -> None:
        """Setup the logger with appropriate handlers and formatters."""
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Custom formatter
        formatter = SelfAwareFormatter(
            fmt='%(asctime)s | %(levelname)8s | %(component)15s | %(memory_mb)6sMB | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    def _analyze_previous_logs(self) -> LogAnalysis:
        """Analyze previous log files for patterns and issues."""
        analysis = LogAnalysis()
        
        if not self.log_file.exists():
            return analysis
        
        try:
            # Read the last 1000 lines for efficiency
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-1000:]
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Parse timestamp and check for recent startup
                timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if timestamp_match:
                    try:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if 'Physics Discovery System starting' in line:
                            analysis.last_startup = log_time
                    except:
                        pass
                
                # Count errors and warnings
                if 'ERROR' in line:
                    analysis.error_count += 1
                    
                    # Identify specific failure patterns
                    if 'ConnectionError' in line or 'TimeoutError' in line:
                        analysis.failure_patterns.append('network_issues')
                    elif 'MemoryError' in line or 'out of memory' in line.lower():
                        analysis.failure_patterns.append('memory_exhaustion')
                        analysis.memory_warnings += 1
                    elif 'KeyError' in line or 'AttributeError' in line:
                        analysis.failure_patterns.append('data_structure_issues')
                    elif 'API' in line and ('rate limit' in line.lower() or 'quota' in line.lower()):
                        analysis.failure_patterns.append('api_rate_limits')
                
                # Memory warnings
                if 'memory' in line.lower() and ('warning' in line.lower() or 'high' in line.lower()):
                    analysis.memory_warnings += 1
                
                # Crash indicators
                if any(indicator in line.lower() for indicator in [
                    'segmentation fault', 'core dumped', 'fatal error',
                    'killed', 'terminated unexpectedly', 'system exit'
                ]):
                    analysis.crash_indicators += 1
            
            # Generate recovery suggestions
            analysis.recovery_suggestions = self._generate_recovery_suggestions(analysis)
            
            # Save analysis
            self._save_analysis(analysis)
            
        except Exception as e:
            # Fallback analysis if log reading fails
            analysis.recovery_suggestions.append(f"Log analysis failed: {str(e)}")
        
        return analysis
    
    def _generate_recovery_suggestions(self, analysis: LogAnalysis) -> List[str]:
        """Generate recovery suggestions based on analysis."""
        suggestions = []
        
        if 'network_issues' in analysis.failure_patterns:
            suggestions.append("Implement exponential backoff for network requests")
            suggestions.append("Add circuit breaker pattern for external APIs")
        
        if 'memory_exhaustion' in analysis.failure_patterns:
            suggestions.append("Reduce batch sizes and implement streaming")
            suggestions.append("Add memory monitoring and cleanup")
        
        if 'api_rate_limits' in analysis.failure_patterns:
            suggestions.append("Implement request throttling and queuing")
            suggestions.append("Add API key rotation if available")
        
        if analysis.error_count > 20:
            suggestions.append("Consider graceful degradation modes")
            suggestions.append("Implement health checks and auto-recovery")
        
        if analysis.crash_indicators > 0:
            suggestions.append("Add process monitoring and auto-restart")
            suggestions.append("Implement checkpoint/recovery mechanism")
        
        return suggestions
    
    def _save_analysis(self, analysis: LogAnalysis) -> None:
        """Save analysis to JSON file."""
        try:
            analysis_data = asdict(analysis)
            # Convert datetime to string
            if analysis_data['last_startup']:
                analysis_data['last_startup'] = analysis_data['last_startup'].isoformat()
            
            with open(self.analysis_file, 'w') as f:
                json.dump(analysis_data, f, indent=2)
        except Exception:
            pass  # Fail silently
    
    def _log_startup_analysis(self) -> None:
        """Log the startup analysis results."""
        self.logger.info("=" * 80)
        self.logger.info("Physics Discovery System starting - Self-Aware Logger Analysis")
        self.logger.info("=" * 80)
        
        if self.analysis.last_startup:
            time_since = datetime.now() - self.analysis.last_startup
            self.logger.info(f"Last startup: {self.analysis.last_startup} ({time_since} ago)")
        else:
            self.logger.info("No previous startup detected - fresh install")
        
        if self.analysis.error_count > 0:
            self.logger.warning(f"Previous session had {self.analysis.error_count} errors")
        
        if self.analysis.memory_warnings > 0:
            self.logger.warning(f"Previous session had {self.analysis.memory_warnings} memory warnings")
        
        if self.analysis.crash_indicators > 0:
            self.logger.error(f"Previous session had {self.analysis.crash_indicators} crash indicators")
        
        if self.analysis.failure_patterns:
            self.logger.info(f"Detected failure patterns: {', '.join(set(self.analysis.failure_patterns))}")
        
        if self.analysis.recovery_suggestions:
            self.logger.info("Recovery suggestions:")
            for suggestion in self.analysis.recovery_suggestions[:3]:  # Show top 3
                self.logger.info(f"  • {suggestion}")
        
        # Log adjusted retry strategy
        self.logger.info(f"Retry strategy: max_retries={self.retry_strategy.max_retries}, "
                        f"base_delay={self.retry_strategy.base_delay}s, "
                        f"memory_limit={self.retry_strategy.memory_limit_mb}MB")
        
        self.logger.info("=" * 80)
    
    def get_retry_strategy(self) -> RetryStrategy:
        """Get the current retry strategy."""
        return self.retry_strategy
    
    def log_memory_usage(self) -> None:
        """Log current memory usage."""
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            if memory_mb > self.retry_strategy.memory_limit_mb:
                self.logger.warning(f"High memory usage: {memory_mb:.1f}MB > {self.retry_strategy.memory_limit_mb}MB limit")
            else:
                self.logger.debug(f"Memory usage: {memory_mb:.1f}MB")
                
        except Exception as e:
            self.logger.debug(f"Could not get memory usage: {e}")
    
    def log_operation_start(self, operation: str, **context) -> str:
        """Log the start of an operation with context."""
        operation_id = f"{operation}_{datetime.now().strftime('%H%M%S')}"
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        self.logger.info(f"Starting {operation} [ID: {operation_id}] | {context_str}")
        return operation_id
    
    def log_operation_end(self, operation_id: str, success: bool = True, **results) -> None:
        """Log the end of an operation with results."""
        status = "SUCCESS" if success else "FAILED"
        results_str = ", ".join(f"{k}={v}" for k, v in results.items())
        self.logger.info(f"Completed {operation_id} | {status} | {results_str}")
    
    def log_adaptive_action(self, action: str, reason: str) -> None:
        """Log an adaptive action taken based on analysis."""
        self.logger.info(f"ADAPTIVE ACTION: {action} | Reason: {reason}")
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if an operation should be retried based on analysis."""
        if attempt >= self.retry_strategy.max_retries:
            return False
        
        error_type = type(error).__name__
        error_msg = str(error).lower()
        
        # Don't retry certain types of errors
        non_retryable = [
            'authenticationerror', 'permissionerror', 'notfound',
            'valueerror', 'typeerror'
        ]
        
        if error_type.lower() in non_retryable:
            self.logger.info(f"Not retrying {error_type} (non-retryable)")
            return False
        
        # Retry network and temporary errors
        retryable_patterns = ['timeout', 'connection', 'rate limit', 'service unavailable']
        if any(pattern in error_msg for pattern in retryable_patterns):
            self.logger.info(f"Retrying {error_type} (attempt {attempt + 1}/{self.retry_strategy.max_retries})")
            return True
        
        # Default retry for unknown errors
        self.logger.info(f"Retrying unknown error {error_type} (attempt {attempt + 1}/{self.retry_strategy.max_retries})")
        return True
    
    def get_retry_delay(self, attempt: int) -> float:
        """Get the delay for a retry attempt."""
        delay = self.retry_strategy.base_delay * (self.retry_strategy.backoff_multiplier ** attempt)
        return min(delay, 60.0)  # Cap at 1 minute


# Global logger instance
_logger_instance: Optional[SelfAwareLogger] = None


def get_logger(name: str = None) -> logging.Logger:
    """Factory function to get a logger instance."""
    global _logger_instance
    
    if _logger_instance is None:
        _logger_instance = SelfAwareLogger(name or "physics_discovery")
    
    if name and name != _logger_instance.name:
        # Return a child logger for different components
        return _logger_instance.logger.getChild(name.split('.')[-1])
    
    return _logger_instance.logger


def get_self_aware_logger() -> SelfAwareLogger:
    """Get the self-aware logger instance."""
    global _logger_instance
    
    if _logger_instance is None:
        _logger_instance = SelfAwareLogger()
    
    return _logger_instance