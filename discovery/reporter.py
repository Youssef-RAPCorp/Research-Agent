from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass, field
import asyncio
import json

from config.logger import get_logger
from config.errors import handle_error
from discovery.hypothesis_tracker import HypothesisTracker
from memory.persistence import MemoryPersistence
from agents.comm_bus import CommunicationBus

logger = get_logger(__name__)

@dataclass
class Discovery:
    """Represents a scientific discovery with metadata."""
    id: str
    title: str
    description: str
    confidence: float
    timestamp: datetime
    hypothesis_id: Optional[str] = None
    evidence_count: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal('0.0'))
    tags: List[str] = field(default_factory=list)

@dataclass
class ConfidenceChange:
    """Represents a change in hypothesis confidence."""
    hypothesis_id: str
    hypothesis_title: str
    old_confidence: float
    new_confidence: float
    change: float
    timestamp: datetime
    reason: str

@dataclass
class CostBreakdown:
    """Detailed cost breakdown for research activities."""
    api_calls: Decimal = field(default_factory=lambda: Decimal('0.0'))
    compute: Decimal = field(default_factory=lambda: Decimal('0.0'))
    storage: Decimal = field(default_factory=lambda: Decimal('0.0'))
    external_services: Decimal = field(default_factory=lambda: Decimal('0.0'))
    total: Decimal = field(default_factory=lambda: Decimal('0.0'))

@dataclass
class ResearchDirection:
    """Suggested research direction with priority."""
    title: str
    description: str
    priority: int  # 1-5, 5 being highest
    estimated_cost: Decimal
    expected_value: float
    dependencies: List[str] = field(default_factory=list)

@dataclass
class OvernightReport:
    """Complete overnight research report."""
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    discoveries: List[Discovery]
    confidence_changes: List[ConfidenceChange]
    top_hypotheses: List[Dict[str, Any]]
    cost_breakdown: CostBreakdown
    suggested_directions: List[ResearchDirection]
    summary: str
    total_research_hours: float

class DiscoveryReporter:
    """Generates comprehensive overnight research reports."""
    
    def __init__(
        self,     
        hypothesis_tracker=None,     
        memory_persistence=None,     
        comm_bus=None, **kwargs):
        self.hypothesis_tracker = hypothesis_tracker
        self.memory = memory_persistence
        self.comm_bus = comm_bus
        self._cost_tracking: Dict[str, Decimal] = {}
        
    async def generate_overnight_report(
        self,
        hours_back: int = 24
    ) -> OvernightReport:
        """Generate comprehensive overnight research report."""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            logger.info(f"Generating overnight report for {start_time} to {end_time}")
            
            # Gather all report components
            discoveries = await self._collect_discoveries(start_time, end_time)
            confidence_changes = await self._collect_confidence_changes(start_time, end_time)
            top_hypotheses = await self._get_top_hypotheses()
            cost_breakdown = await self._calculate_cost_breakdown(start_time, end_time)
            suggested_directions = await self._generate_research_directions()
            summary = await self._generate_summary(
                discoveries, confidence_changes, top_hypotheses, cost_breakdown
            )
            
            report = OvernightReport(
                report_id=f"report_{int(end_time.timestamp())}",
                generated_at=end_time,
                period_start=start_time,
                period_end=end_time,
                discoveries=discoveries,
                confidence_changes=confidence_changes,
                top_hypotheses=top_hypotheses,
                cost_breakdown=cost_breakdown,
                suggested_directions=suggested_directions,
                summary=summary,
                total_research_hours=hours_back
            )
            
            await self._save_report(report)
            return report
            
        except Exception as e:
            handle_error(e)
            raise
    
    async def _collect_discoveries(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Discovery]:
        """Collect discoveries made during the time period."""
        try:
            # Query memory for discovery events
            discovery_events = await self.memory.query_events(
                event_type="discovery",
                start_time=start_time,
                end_time=end_time
            )
            
            discoveries = []
            for event in discovery_events:
                discovery = Discovery(
                    id=event.get("id", f"disc_{int(event.get('timestamp', 0))}"),
                    title=event.get("title", "Untitled Discovery"),
                    description=event.get("description", ""),
                    confidence=event.get("confidence", 0.0),
                    timestamp=datetime.fromisoformat(event.get("timestamp", start_time.isoformat())),
                    hypothesis_id=event.get("hypothesis_id"),
                    evidence_count=event.get("evidence_count", 0),
                    cost=Decimal(str(event.get("cost", 0.0))),
                    tags=event.get("tags", [])
                )
                discoveries.append(discovery)
            
            # Sort by confidence and timestamp
            discoveries.sort(key=lambda x: (x.confidence, x.timestamp), reverse=True)
            return discoveries[:20]  # Top 20 discoveries
            
        except Exception as e:
            logger.error(f"Error collecting discoveries: {e}")
            return []
    
    async def _collect_confidence_changes(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[ConfidenceChange]:
        """Collect hypothesis confidence changes during the period."""
        try:
            confidence_events = await self.memory.query_events(
                event_type="confidence_change",
                start_time=start_time,
                end_time=end_time
            )
            
            changes = []
            for event in confidence_events:
                change = ConfidenceChange(
                    hypothesis_id=event.get("hypothesis_id", "unknown"),
                    hypothesis_title=event.get("hypothesis_title", "Unknown Hypothesis"),
                    old_confidence=event.get("old_confidence", 0.0),
                    new_confidence=event.get("new_confidence", 0.0),
                    change=event.get("change", 0.0),
                    timestamp=datetime.fromisoformat(event.get("timestamp", start_time.isoformat())),
                    reason=event.get("reason", "No reason provided")
                )
                changes.append(change)
            
            # Sort by absolute change magnitude
            changes.sort(key=lambda x: abs(x.change), reverse=True)
            return changes[:15]  # Top 15 changes
            
        except Exception as e:
            logger.error(f"Error collecting confidence changes: {e}")
            return []
    
    async def _get_top_hypotheses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get current top hypotheses by confidence."""
        try:
            hypotheses = await self.hypothesis_tracker.get_all_hypotheses()
            
            # Sort by confidence and filter active ones
            active_hypotheses = [
                h for h in hypotheses 
                if h.get("status", "active") == "active"
            ]
            active_hypotheses.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
            
            return active_hypotheses[:limit]
            
        except Exception as e:
            logger.error(f"Error getting top hypotheses: {e}")
            return []
    
    async def _calculate_cost_breakdown(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> CostBreakdown:
        """Calculate detailed cost breakdown for the period."""
        try:
            # Query cost tracking events
            cost_events = await self.memory.query_events(
                event_type="cost",
                start_time=start_time,
                end_time=end_time
            )
            
            breakdown = CostBreakdown()
            
            for event in cost_events:
                category = event.get("category", "external_services")
                amount = Decimal(str(event.get("amount", 0.0)))
                
                if category == "api_calls":
                    breakdown.api_calls += amount
                elif category == "compute":
                    breakdown.compute += amount
                elif category == "storage":
                    breakdown.storage += amount
                else:
                    breakdown.external_services += amount
            
            breakdown.total = (
                breakdown.api_calls + 
                breakdown.compute + 
                breakdown.storage + 
                breakdown.external_services
            )
            
            return breakdown
            
        except Exception as e:
            logger.error(f"Error calculating cost breakdown: {e}")
            return CostBreakdown()
    
    async def _generate_research_directions(self) -> List[ResearchDirection]:
        """Generate suggested research directions based on current state."""
        try:
            # Get current hypotheses and discoveries
            hypotheses = await self.hypothesis_tracker.get_all_hypotheses()
            
            directions = []
            
            # Analyze gaps and opportunities
            for hypothesis in hypotheses[:5]:  # Top 5 hypotheses
                if hypothesis.get("confidence", 0.0) < 0.7:
                    # Low confidence - suggest more evidence gathering
                    direction = ResearchDirection(
                        title=f"Strengthen Evidence for {hypothesis.get('title', 'Unknown')}",
                        description=f"Gather more experimental or theoretical evidence for hypothesis {hypothesis.get('id', '')}",
                        priority=max(1, int(hypothesis.get("confidence", 0.0) * 5)),
                        estimated_cost=Decimal("150.00"),
                        expected_value=0.8,
                        dependencies=[hypothesis.get("id", "")]
                    )
                    directions.append(direction)
            
            # Add some general research directions
            general_directions = [
                ResearchDirection(
                    title="Explore Quantum-Classical Boundary",
                    description="Investigate the transition between quantum and classical regimes",
                    priority=4,
                    estimated_cost=Decimal("300.00"),
                    expected_value=0.9,
                    dependencies=[]
                ),
                ResearchDirection(
                    title="Cross-Reference Recent ArXiv Papers",
                    description="Search for new papers that might validate or challenge current hypotheses",
                    priority=3,
                    estimated_cost=Decimal("75.00"),
                    expected_value=0.6,
                    dependencies=[]
                )
            ]
            
            directions.extend(general_directions)
            directions.sort(key=lambda x: x.priority, reverse=True)
            
            return directions[:8]  # Top 8 directions
            
        except Exception as e:
            logger.error(f"Error generating research directions: {e}")
            return []
    
    async def _generate_summary(
        self,
        discoveries: List[Discovery],
        confidence_changes: List[ConfidenceChange],
        top_hypotheses: List[Dict[str, Any]],
        cost_breakdown: CostBreakdown
    ) -> str:
        """Generate executive summary of the overnight research."""
        try:
            summary_parts = []
            
            # Discoveries summary
            if discoveries:
                summary_parts.append(
                    f"Made {len(discoveries)} new discoveries with average confidence "
                    f"{sum(d.confidence for d in discoveries) / len(discoveries):.2f}"
                )
                top_discovery = discoveries[0]
                summary_parts.append(
                    f"Top discovery: '{top_discovery.title}' (confidence: {top_discovery.confidence:.2f})"
                )
            
            # Confidence changes summary
            if confidence_changes:
                positive_changes = [c for c in confidence_changes if c.change > 0]
                negative_changes = [c for c in confidence_changes if c.change < 0]
                
                summary_parts.append(
                    f"Confidence increased for {len(positive_changes)} hypotheses, "
                    f"decreased for {len(negative_changes)} hypotheses"
                )
            
            # Top hypothesis
            if top_hypotheses:
                top_hyp = top_hypotheses[0]
                summary_parts.append(
                    f"Leading hypothesis: '{top_hyp.get('title', 'Unknown')}' "
                    f"(confidence: {top_hyp.get('confidence', 0.0):.2f})"
                )
            
            # Cost summary
            summary_parts.append(f"Total research cost: ${cost_breakdown.total:.2f}")
            
            return ". ".join(summary_parts) + "."
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Summary generation failed."
    
    async def _save_report(self, report: OvernightReport) -> None:
        """Save the report to persistent storage."""
        try:
            report_data = {
                "report_id": report.report_id,
                "generated_at": report.generated_at.isoformat(),
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "discoveries": [
                    {
                        "id": d.id,
                        "title": d.title,
                        "description": d.description,
                        "confidence": d.confidence,
                        "timestamp": d.timestamp.isoformat(),
                        "hypothesis_id": d.hypothesis_id,
                        "evidence_count": d.evidence_count,
                        "cost": str(d.cost),
                        "tags": d.tags
                    }
                    for d in report.discoveries
                ],
                "confidence_changes": [
                    {
                        "hypothesis_id": c.hypothesis_id,
                        "hypothesis_title": c.hypothesis_title,
                        "old_confidence": c.old_confidence,
                        "new_confidence": c.new_confidence,
                        "change": c.change,
                        "timestamp": c.timestamp.isoformat(),
                        "reason": c.reason
                    }
                    for c in report.confidence_changes
                ],
                "top_hypotheses": report.top_hypotheses,
                "cost_breakdown": {
                    "api_calls": str(report.cost_breakdown.api_calls),
                    "compute": str(report.cost_breakdown.compute),
                    "storage": str(report.cost_breakdown.storage),
                    "external_services": str(report.cost_breakdown.external_services),
                    "total": str(report.cost_breakdown.total)
                },
                "suggested_directions": [
                    {
                        "title": d.title,
                        "description": d.description,
                        "priority": d.priority,
                        "estimated_cost": str(d.estimated_cost),
                        "expected_value": d.expected_value,
                        "dependencies": d.dependencies
                    }
                    for d in report.suggested_directions
                ],
                "summary": report.summary,
                "total_research_hours": report.total_research_hours
            }
            
            await self.memory.store_event(
                event_type="overnight_report",
                event_data=report_data
            )
            
            logger.info(f"Saved overnight report {report.report_id}")
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")
    
    async def get_recent_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent overnight reports."""
        try:
            reports = await self.memory.query_events(
                event_type="overnight_report",
                limit=limit
            )
            return reports
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def track_cost(
        self,
        category: str,
        amount: Decimal,
        description: str = ""
    ) -> None:
        """Track a cost event for inclusion in reports."""
        try:
            cost_event = {
                "category": category,
                "amount": str(amount),
                "description": description,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.memory.store_event(
                event_type="cost",
                event_data=cost_event
            )
            
        except Exception as e:
            logger.error(f"Error tracking cost: {e}")
    
    async def export_report(
        self,
        report: OvernightReport,
        format_type: str = "json"
    ) -> str:
        """Export report in specified format."""
        try:
            if format_type == "json":
                return json.dumps({
                    "report_id": report.report_id,
                    "generated_at": report.generated_at.isoformat(),
                    "period": f"{report.period_start.isoformat()} to {report.period_end.isoformat()}",
                    "summary": report.summary,
                    "discoveries": len(report.discoveries),
                    "confidence_changes": len(report.confidence_changes),
                    "top_hypotheses": len(report.top_hypotheses),
                    "total_cost": str(report.cost_breakdown.total),
                    "suggested_directions": len(report.suggested_directions)
                }, indent=2)
            
            elif format_type == "text":
                lines = [
                    f"OVERNIGHT RESEARCH REPORT - {report.report_id}",
                    f"Generated: {report.generated_at}",
                    f"Period: {report.period_start} to {report.period_end}",
                    "",
                    "EXECUTIVE SUMMARY:",
                    report.summary,
                    "",
                    f"DISCOVERIES: {len(report.discoveries)}",
                    f"CONFIDENCE CHANGES: {len(report.confidence_changes)}",
                    f"TOP HYPOTHESES: {len(report.top_hypotheses)}",
                    f"TOTAL COST: ${report.cost_breakdown.total}",
                    f"RESEARCH DIRECTIONS: {len(report.suggested_directions)}"
                ]
                return "\n".join(lines)
            
            else:
                raise ValueError(f"Unsupported format: {format_type}")
                
        except Exception as e:
            handle_error(e)
            return f"Export failed: {e}"
    async def generate_discovery_report(self, *args, **kwargs):
        return dict()
