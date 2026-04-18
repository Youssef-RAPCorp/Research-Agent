import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from pydantic import BaseModel, Field

from typing import TYPE_CHECKING  # noqa
from config.settings import get_settings
from typing import TYPE_CHECKING  # noqa
from config.logger import get_logger
from typing import TYPE_CHECKING  # noqa
from config.errors import handle_error
from typing import TYPE_CHECKING  # noqa
from config.firebase import get_firebase_client
from discovery.continuous_loop import ContinuousDiscoveryLoop
from discovery.discovery_mode import DiscoveryMode
from discovery.reporter import DiscoveryReporter


class ScheduleType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    ONE_TIME = "one_time"


class JobPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal" 
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CostLimits:
    """Cost limits for discovery jobs."""
    daily_limit: float = 50.0
    monthly_limit: float = 1000.0
    per_job_limit: float = 10.0
    warning_threshold: float = 0.8


@dataclass
class RateLimits:
    """API rate limits for discovery jobs."""
    api_calls_per_minute: int = 60
    api_calls_per_hour: int = 1000
    concurrent_jobs: int = 3
    job_timeout_seconds: int = 3600


@dataclass
class ScheduleWindow:
    """Time window for scheduled jobs."""
    start_time: time = field(default_factory=lambda: time(22, 0))  # 10 PM
    end_time: time = field(default_factory=lambda: time(6, 0))     # 6 AM
    timezone: str = "UTC"
    enabled: bool = True


class JobConfig(BaseModel):
    """Configuration for a scheduled discovery job."""
    job_id: str
    name: str
    description: str = ""
    schedule_type: ScheduleType = ScheduleType.CRON
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    discovery_mode: DiscoveryMode = DiscoveryMode.HYBRID
    query: str = ""
    pattern: str = ""
    priority: JobPriority = JobPriority.NORMAL
    enabled: bool = True
    max_retries: int = 3
    retry_delay_seconds: int = 300
    timeout_seconds: int = 3600
    cost_limit: float = 10.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class JobExecution:
    """Record of a job execution."""
    job_id: str
    execution_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "running"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cost: float = 0.0
    api_calls: int = 0
    retry_count: int = 0


class DiscoveryScheduler:
    """APScheduler-backed discovery job scheduler with cost and rate limiting."""
    
    def __init__(self, **kwargs):
        self.logger = get_logger(__name__)
        self.settings = get_settings()
        self.firebase = get_firebase_client()
        
        self.scheduler = AsyncIOScheduler()
        self.discovery_loop = ContinuousDiscoveryLoop()
        self.reporter = DiscoveryReporter()
        
        self.cost_limits = CostLimits()
        self.rate_limits = RateLimits()
        self.schedule_window = ScheduleWindow()
        
        self.jobs: Dict[str, JobConfig] = {}
        self.executions: Dict[str, JobExecution] = {}
        self.current_cost: Dict[str, float] = {"daily": 0.0, "monthly": 0.0}
        self.api_calls_count: Dict[str, int] = {"minute": 0, "hour": 0}
        self.running_jobs: Dict[str, str] = {}  # job_id -> execution_id
        
        self._setup_scheduler()
    
    def _setup_scheduler(self):
        """Setup scheduler event listeners."""
        self.scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
    
    async def start(self):
        """Start the scheduler."""
        try:
            self.scheduler.start()
            await self._load_jobs()
            await self._schedule_cost_reset()
            await self._schedule_rate_limit_reset()
            self.logger.info("Discovery scheduler started")
        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {e}")
            handle_error(e)
    
    async def stop(self):
        """Stop the scheduler."""
        try:
            self.scheduler.shutdown(wait=True)
            self.logger.info("Discovery scheduler stopped")
        except Exception as e:
            self.logger.error(f"Failed to stop scheduler: {e}")
            handle_error(e)
    
    async def add_job(self, job_config: JobConfig) -> bool:
        """Add a new discovery job."""
        try:
            if job_config.job_id in self.jobs:
                self.logger.warning(f"Job {job_config.job_id} already exists")
                return False
            
            if not self._validate_job_config(job_config):
                return False
            
            self.jobs[job_config.job_id] = job_config
            
            if job_config.enabled:
                await self._schedule_job(job_config)
            
            await self._save_job_config(job_config)
            self.logger.info(f"Added discovery job: {job_config.job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add job {job_config.job_id}: {e}")
            handle_error(e)
            return False
    
    async def remove_job(self, job_id: str) -> bool:
        """Remove a discovery job."""
        try:
            if job_id not in self.jobs:
                self.logger.warning(f"Job {job_id} not found")
                return False
            
            # Cancel if running
            if job_id in self.running_jobs:
                await self.cancel_job(job_id)
            
            # Remove from scheduler
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Remove from memory and storage
            del self.jobs[job_id]
            await self._delete_job_config(job_id)
            
            self.logger.info(f"Removed discovery job: {job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove job {job_id}: {e}")
            handle_error(e)
            return False
    
    async def update_job(self, job_config: JobConfig) -> bool:
        """Update an existing discovery job."""
        try:
            if job_config.job_id not in self.jobs:
                self.logger.warning(f"Job {job_config.job_id} not found")
                return False
            
            if not self._validate_job_config(job_config):
                return False
            
            # Remove old schedule
            if self.scheduler.get_job(job_config.job_id):
                self.scheduler.remove_job(job_config.job_id)
            
            self.jobs[job_config.job_id] = job_config
            
            # Add new schedule if enabled
            if job_config.enabled:
                await self._schedule_job(job_config)
            
            await self._save_job_config(job_config)
            self.logger.info(f"Updated discovery job: {job_config.job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update job {job_config.job_id}: {e}")
            handle_error(e)
            return False
    
    async def pause_job(self, job_id: str) -> bool:
        """Pause a discovery job."""
        try:
            if job_id not in self.jobs:
                return False
            
            if self.scheduler.get_job(job_id):
                self.scheduler.pause_job(job_id)
            
            self.jobs[job_id].enabled = False
            await self._save_job_config(self.jobs[job_id])
            
            self.logger.info(f"Paused discovery job: {job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to pause job {job_id}: {e}")
            handle_error(e)
            return False
    
    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused discovery job."""
        try:
            if job_id not in self.jobs:
                return False
            
            if self.scheduler.get_job(job_id):
                self.scheduler.resume_job(job_id)
            else:
                await self._schedule_job(self.jobs[job_id])
            
            self.jobs[job_id].enabled = True
            await self._save_job_config(self.jobs[job_id])
            
            self.logger.info(f"Resumed discovery job: {job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to resume job {job_id}: {e}")
            handle_error(e)
            return False
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running discovery job."""
        try:
            if job_id not in self.running_jobs:
                return False
            
            execution_id = self.running_jobs[job_id]
            execution = self.executions.get(execution_id)
            
            if execution:
                execution.status = "cancelled"
                execution.end_time = datetime.utcnow()
                await self._save_execution(execution)
            
            del self.running_jobs[job_id]
            self.logger.info(f"Cancelled discovery job: {job_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel job {job_id}: {e}")
            handle_error(e)
            return False
    
    async def run_job_now(self, job_id: str) -> Optional[str]:
        """Run a discovery job immediately."""
        try:
            if job_id not in self.jobs:
                self.logger.warning(f"Job {job_id} not found")
                return None
            
            if not await self._check_limits():
                self.logger.warning("Rate or cost limits exceeded")
                return None
            
            job_config = self.jobs[job_id]
            execution_id = await self._execute_job(job_config)
            return execution_id
            
        except Exception as e:
            self.logger.error(f"Failed to run job {job_id}: {e}")
            handle_error(e)
            return None
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a discovery job."""
        if job_id not in self.jobs:
            return None
        
        job_config = self.jobs[job_id]
        is_running = job_id in self.running_jobs
        
        return {
            "job_id": job_id,
            "name": job_config.name,
            "enabled": job_config.enabled,
            "is_running": is_running,
            "next_run": None,  # TODO: Get from scheduler
            "last_execution": self._get_last_execution(job_id)
        }
    
    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get status of all discovery jobs."""
        return [self.get_job_status(job_id) for job_id in self.jobs.keys()]
    
    def get_execution_history(self, job_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get execution history for a job."""
        executions = [
            exec for exec in self.executions.values() 
            if exec.job_id == job_id
        ]
        executions.sort(key=lambda x: x.start_time, reverse=True)
        
        return [
            {
                "execution_id": exec.execution_id,
                "start_time": exec.start_time,
                "end_time": exec.end_time,
                "status": exec.status,
                "cost": exec.cost,
                "api_calls": exec.api_calls,
                "error": exec.error
            }
            for exec in executions[:limit]
        ]
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost summary."""
        return {
            "current_daily": self.current_cost["daily"],
            "current_monthly": self.current_cost["monthly"],
            "daily_limit": self.cost_limits.daily_limit,
            "monthly_limit": self.cost_limits.monthly_limit,
            "daily_remaining": max(0, self.cost_limits.daily_limit - self.current_cost["daily"]),
            "monthly_remaining": max(0, self.cost_limits.monthly_limit - self.current_cost["monthly"])
        }
    
    def update_cost_limits(self, limits: CostLimits):
        """Update cost limits."""
        self.cost_limits = limits
        self.logger.info("Updated cost limits")
    
    def update_rate_limits(self, limits: RateLimits):
        """Update rate limits."""
        self.rate_limits = limits
        self.logger.info("Updated rate limits")
    
    def update_schedule_window(self, window: ScheduleWindow):
        """Update schedule window."""
        self.schedule_window = window
        self.logger.info("Updated schedule window")
    
    async def _schedule_job(self, job_config: JobConfig):
        """Schedule a job with APScheduler."""
        if job_config.schedule_type == ScheduleType.CRON and job_config.cron_expression:
            trigger = CronTrigger.from_crontab(job_config.cron_expression)
        elif job_config.schedule_type == ScheduleType.INTERVAL and job_config.interval_seconds:
            trigger = IntervalTrigger(seconds=job_config.interval_seconds)
        else:
            self.logger.error(f"Invalid schedule config for job {job_config.job_id}")
            return
        
        self.scheduler.add_job(
            func=self._execute_job_wrapper,
            trigger=trigger,
            args=[job_config],
            id=job_config.job_id,
            name=job_config.name,
            max_instances=1,
            coalesce=True,
            replace_existing=True
        )
    
    async def _execute_job_wrapper(self, job_config: JobConfig):
        """Wrapper for job execution with error handling."""
        try:
            await self._execute_job(job_config)
        except Exception as e:
            self.logger.error(f"Job execution failed for {job_config.job_id}: {e}")
            handle_error(e)
    
    async def _execute_job(self, job_config: JobConfig) -> str:
        """Execute a discovery job."""
        execution_id = f"{job_config.job_id}_{datetime.utcnow().isoformat()}"
        
        execution = JobExecution(
            job_id=job_config.job_id,
            execution_id=execution_id,
            start_time=datetime.utcnow()
        )
        
        self.executions[execution_id] = execution
        self.running_jobs[job_config.job_id] = execution_id
        
        try:
            # Check limits before execution
            if not await self._check_limits():
                execution.status = "failed"
                execution.error = "Rate or cost limits exceeded"
                execution.end_time = datetime.utcnow()
                return execution_id
            
            # Check schedule window
            if not self._is_in_schedule_window():
                execution.status = "skipped"
                execution.error = "Outside scheduled window"
                execution.end_time = datetime.utcnow()
                return execution_id
            
            self.logger.info(f"Starting discovery job: {job_config.job_id}")
            
            # Execute discovery
            result = await asyncio.wait_for(
                self.discovery_loop.run_discovery(
                    query=job_config.query,
                    mode=job_config.discovery_mode,
                    pattern=job_config.pattern
                ),
                timeout=job_config.timeout_seconds
            )
            
            execution.result = result
            execution.status = "completed"
            execution.cost = result.get("cost", 0.0) if result else 0.0
            execution.api_calls = result.get("api_calls", 0) if result else 0
            
            # Update cost tracking
            self.current_cost["daily"] += execution.cost
            self.current_cost["monthly"] += execution.cost
            
            # Generate report if configured
            if result and job_config.metadata.get("generate_report", False):
                await self.reporter.generate_discovery_report(result)
            
            self.logger.info(f"Completed discovery job: {job_config.job_id}")
            
        except asyncio.TimeoutError:
            execution.status = "timeout"
            execution.error = f"Job timed out after {job_config.timeout_seconds} seconds"
            
        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            self.logger.error(f"Job execution failed: {e}")
            
        finally:
            execution.end_time = datetime.utcnow()
            await self._save_execution(execution)
            
            if job_config.job_id in self.running_jobs:
                del self.running_jobs[job_config.job_id]
        
        return execution_id
    
    async def _check_limits(self) -> bool:
        """Check if execution is within rate and cost limits."""
        # Check cost limits
        if self.current_cost["daily"] >= self.cost_limits.daily_limit:
            return False
        if self.current_cost["monthly"] >= self.cost_limits.monthly_limit:
            return False
        
        # Check rate limits
        if self.api_calls_count["minute"] >= self.rate_limits.api_calls_per_minute:
            return False
        if self.api_calls_count["hour"] >= self.rate_limits.api_calls_per_hour:
            return False
        
        # Check concurrent jobs
        if len(self.running_jobs) >= self.rate_limits.concurrent_jobs:
            return False
        
        return True
    
    def _is_in_schedule_window(self) -> bool:
        """Check if current time is within the schedule window."""
        if not self.schedule_window.enabled:
            return True
        
        now = datetime.utcnow().time()
        start = self.schedule_window.start_time
        end = self.schedule_window.end_time
        
        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end
    
    def _validate_job_config(self, job_config: JobConfig) -> bool:
        """Validate job configuration."""
        if not job_config.job_id or not job_config.name:
            return False
        
        if job_config.schedule_type == ScheduleType.CRON:
            if not job_config.cron_expression:
                return False
        elif job_config.schedule_type == ScheduleType.INTERVAL:
            if not job_config.interval_seconds or job_config.interval_seconds <= 0:
                return False
        
        return True
    
    def _get_last_execution(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get last execution for a job."""
        executions = [
            exec for exec in self.executions.values() 
            if exec.job_id == job_id
        ]
        
        if not executions:
            return None
        
        last_exec = max(executions, key=lambda x: x.start_time)
        return {
            "execution_id": last_exec.execution_id,
            "start_time": last_exec.start_time,
            "end_time": last_exec.end_time,
            "status": last_exec.status,
            "cost": last_exec.cost
        }
    
    async def _on_job_executed(self, event):
        """Handle job execution event."""
        self.logger.debug(f"Job executed: {event.job_id}")
    
    async def _on_job_error(self, event):
        """Handle job error event."""
        self.logger.error(f"Job error: {event.job_id} - {event.exception}")
    
    async def _schedule_cost_reset(self):
        """Schedule daily and monthly cost resets."""
        # Reset daily costs at midnight
        self.scheduler.add_job(
            func=self._reset_daily_costs,
            trigger=CronTrigger(hour=0, minute=0),
            id="reset_daily_costs"
        )
        
        # Reset monthly costs on first of month
        self.scheduler.add_job(
            func=self._reset_monthly_costs,
            trigger=CronTrigger(day=1, hour=0, minute=0),
            id="reset_monthly_costs"
        )
    
    async def _schedule_rate_limit_reset(self):
        """Schedule rate limit resets."""
        # Reset per-minute counters
        self.scheduler.add_job(
            func=self._reset_minute_counters,
            trigger=IntervalTrigger(minutes=1),
            id="reset_minute_counters"
        )
        
        # Reset hourly counters
        self.scheduler.add_job(
            func=self._reset_hour_counters,
            trigger=IntervalTrigger(hours=1),
            id="reset_hour_counters"
        )
    
    async def _reset_daily_costs(self):
        """Reset daily cost counters."""
        self.current_cost["daily"] = 0.0
        self.logger.info("Reset daily cost counters")
    
    async def _reset_monthly_costs(self):
        """Reset monthly cost counters."""
        self.current_cost["monthly"] = 0.0
        self.logger.info("Reset monthly cost counters")
    
    async def _reset_minute_counters(self):
        """Reset per-minute API call counters."""
        self.api_calls_count["minute"] = 0
    
    async def _reset_hour_counters(self):
        """Reset hourly API call counters."""
        self.api_calls_count["hour"] = 0
    
    async def _load_jobs(self):
        """Load job configurations from storage."""
        try:
            # TODO: Load from Firebase
            self.logger.info("Loaded job configurations")
        except Exception as e:
            self.logger.error(f"Failed to load jobs: {e}")
            handle_error(e)
    
    async def _save_job_config(self, job_config: JobConfig):
        """Save job configuration to storage."""
        try:
            # TODO: Save to Firebase
            pass
        except Exception as e:
            self.logger.error(f"Failed to save job config: {e}")
            handle_error(e)
    
    async def _delete_job_config(self, job_id: str):
        """Delete job configuration from storage."""
        try:
            # TODO: Delete from Firebase
            pass
        except Exception as e:
            self.logger.error(f"Failed to delete job config: {e}")
            handle_error(e)
    
    async def _save_execution(self, execution: JobExecution):
        """Save execution record to storage."""
        try:
            # TODO: Save to Firebase
            pass
        except Exception as e:
            self.logger.error(f"Failed to save execution: {e}")
            handle_error(e)
CRITICAL = type('CRITICAL', (), {})  # auto-stub: not found in project

CRON = type('CRON', (), {})  # auto-stub: not found in project

HIGH = type('HIGH', (), {})  # auto-stub: not found in project

INTERVAL = type('INTERVAL', (), {})  # auto-stub: not found in project

LOW = type('LOW', (), {})  # auto-stub: not found in project

NORMAL = type('NORMAL', (), {})  # auto-stub: not found in project

ONE_TIME = type('ONE_TIME', (), {})  # auto-stub: not found in project
