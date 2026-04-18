from abc import ABC
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import uuid

from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent
from agents.registry import AgentRegistry
from agents.comm_bus import CommunicationBus
from thinking.reflection import ReflectionEngine
from thinking.tree_of_thoughts import TreeOfThoughtsEngine
from memory.router import MemoryRouter

logger = get_logger(__name__)

@runtime_checkable
class AgentInterface(Protocol):
    """Protocol defining the standard agent interface."""
    
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input data and return results."""
        ...
    
    async def collaborate(self, other_agent: "AgentInterface", task: str) -> Dict[str, Any]:
        """Collaborate with another agent on a task."""
        ...

@dataclass
class AgentCapabilities:
    """Defines capabilities of an agent."""
    
    name: str
    description: str
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)
    collaboration_modes: List[str] = field(default_factory=list)
    expertise_domains: List[str] = field(default_factory=list)

@dataclass
class Task:
    """Represents a task to be executed by agents."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    assigned_agent: Optional[str] = None
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None

class AgentManager:
    """Manages agent lifecycle and coordination."""
    
    def __init__(self, **kwargs):
        self.registry = AgentRegistry()
        self.comm_bus = CommunicationBus()
        self.memory_router = MemoryRouter()
        self.active_agents: Dict[str, BaseAgent] = {}
        self.task_queue: List[Task] = []
        
    async def register_agent(self, agent: BaseAgent) -> bool:
        """Register an agent with the system."""
        try:
            await self.registry.register(agent)
            self.active_agents[agent.agent_id] = agent
            logger.info(f"Agent {agent.agent_id} registered successfully")
            return True
        except Exception as e:
            handle_error(e)
            return False
    
    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the system."""
        try:
            await self.registry.unregister(agent_id)
            self.active_agents.pop(agent_id, None)
            logger.info(f"Agent {agent_id} unregistered successfully")
            return True
        except Exception as e:
            handle_error(e)
            return False
    
    async def assign_task(self, task: Task) -> Optional[str]:
        """Assign a task to the most suitable agent."""
        try:
            suitable_agents = await self._find_suitable_agents(task)
            if not suitable_agents:
                logger.warning(f"No suitable agents found for task {task.id}")
                return None
            
            # Select the best agent based on capabilities and workload
            selected_agent = await self._select_best_agent(suitable_agents, task)
            task.assigned_agent = selected_agent.agent_id
            task.status = "assigned"
            
            logger.info(f"Task {task.id} assigned to agent {selected_agent.agent_id}")
            return selected_agent.agent_id
        except Exception as e:
            handle_error(e)
            return None
    
    async def execute_task(self, task: Task) -> Optional[Dict[str, Any]]:
        """Execute a task using the assigned agent."""
        try:
            if not task.assigned_agent:
                logger.error(f"Task {task.id} has no assigned agent")
                return None
            
            agent = self.active_agents.get(task.assigned_agent)
            if not agent:
                logger.error(f"Assigned agent {task.assigned_agent} not found")
                return None
            
            task.status = "executing"
            result = await agent.process(task.input_data)
            task.result = result
            task.status = "completed"
            
            logger.info(f"Task {task.id} completed successfully")
            return result
        except Exception as e:
            handle_error(e)
            task.status = "failed"
            return None
    
    async def collaborate_agents(self, agent_ids: List[str], task: str) -> Dict[str, Any]:
        """Coordinate collaboration between multiple agents."""
        try:
            agents = [self.active_agents[aid] for aid in agent_ids if aid in self.active_agents]
            if len(agents) < 2:
                raise ValueError("Need at least 2 agents for collaboration")
            
            collaboration_results = []
            
            # Create collaboration pairs
            for i in range(len(agents)):
                for j in range(i + 1, len(agents)):
                    result = await agents[i].collaborate(agents[j], task)
                    collaboration_results.append(result)
            
            # Synthesize results
            synthesized = await self._synthesize_collaboration_results(collaboration_results)
            return synthesized
        except Exception as e:
            handle_error(e)
            return {"error": str(e)}
    
    async def _find_suitable_agents(self, task: Task) -> List[BaseAgent]:
        """Find agents suitable for a given task."""
        suitable = []
        for agent in self.active_agents.values():
            if await self._is_agent_suitable(agent, task):
                suitable.append(agent)
        return suitable
    
    async def _is_agent_suitable(self, agent: BaseAgent, task: Task) -> bool:
        """Check if an agent is suitable for a task."""
        try:
            capabilities = await agent.get_capabilities()
            return (
                task.type in capabilities.input_types or
                any(domain in task.description for domain in capabilities.expertise_domains)
            )
        except:
            return False
    
    async def _select_best_agent(self, agents: List[BaseAgent], task: Task) -> BaseAgent:
        """Select the best agent from a list of suitable agents."""
        if len(agents) == 1:
            return agents[0]
        
        # Score agents based on various factors
        best_agent = agents[0]
        best_score = 0
        
        for agent in agents:
            score = await self._calculate_agent_score(agent, task)
            if score > best_score:
                best_score = score
                best_agent = agent
        
        return best_agent
    
    async def _calculate_agent_score(self, agent: BaseAgent, task: Task) -> float:
        """Calculate suitability score for an agent and task."""
        score = 0.0
        
        try:
            capabilities = await agent.get_capabilities()
            
            # Expertise match
            for domain in capabilities.expertise_domains:
                if domain.lower() in task.description.lower():
                    score += 2.0
            
            # Input type compatibility
            if task.type in capabilities.input_types:
                score += 1.0
            
            # Agent availability (inverse of current workload)
            workload = await agent.get_workload()
            score += max(0, 1.0 - workload / 100.0)
            
        except:
            pass
        
        return score
    
    async def _synthesize_collaboration_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesize results from multiple collaboration sessions."""
        if not results:
            return {"error": "No collaboration results to synthesize"}
        
        synthesized = {
            "collaboration_count": len(results),
            "combined_insights": [],
            "consensus_points": [],
            "divergent_views": [],
            "synthesis_timestamp": datetime.now().isoformat()
        }
        
        # Extract insights from all results
        for result in results:
            if "insights" in result:
                synthesized["combined_insights"].extend(result["insights"])
        
        # Simple consensus detection (in practice, would use more sophisticated methods)
        insight_counts = {}
        for insight in synthesized["combined_insights"]:
            key = insight.get("topic", str(insight))
            insight_counts[key] = insight_counts.get(key, 0) + 1
        
        # Points that appear in multiple collaborations are likely consensus
        for topic, count in insight_counts.items():
            if count > 1:
                synthesized["consensus_points"].append({"topic": topic, "frequency": count})
        
        return synthesized

class AgentCoordinator:
    """Coordinates complex multi-agent workflows."""
    
    def __init__(self,   agent_manager=None, **kwargs):
        self.agent_manager = agent_manager
        self.reflection_engine = ReflectionEngine()
        self.thinking_engine = TreeOfThoughtsEngine()
        
    async def execute_workflow(self, workflow_definition: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a complex multi-agent workflow."""
        try:
            workflow_id = workflow_definition.get("id", str(uuid.uuid4()))
            steps = workflow_definition.get("steps", [])
            
            logger.info(f"Starting workflow {workflow_id} with {len(steps)} steps")
            
            workflow_results = {
                "workflow_id": workflow_id,
                "steps_completed": 0,
                "step_results": [],
                "final_result": None,
                "status": "running"
            }
            
            for i, step in enumerate(steps):
                step_result = await self._execute_workflow_step(step, workflow_results)
                workflow_results["step_results"].append(step_result)
                workflow_results["steps_completed"] = i + 1
                
                if step_result.get("status") == "failed":
                    workflow_results["status"] = "failed"
                    break
            
            if workflow_results["status"] != "failed":
                workflow_results["status"] = "completed"
                workflow_results["final_result"] = await self._synthesize_workflow_results(
                    workflow_results["step_results"]
                )
            
            logger.info(f"Workflow {workflow_id} completed with status: {workflow_results['status']}")
            return workflow_results
            
        except Exception as e:
            handle_error(e)
            return {"status": "error", "error": str(e)}
    
    async def _execute_workflow_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single workflow step."""
        try:
            step_type = step.get("type")
            step_name = step.get("name", f"step_{len(context['step_results']) + 1}")
            
            if step_type == "single_agent":
                return await self._execute_single_agent_step(step, context)
            elif step_type == "collaboration":
                return await self._execute_collaboration_step(step, context)
            elif step_type == "reflection":
                return await self._execute_reflection_step(step, context)
            else:
                raise ValueError(f"Unknown step type: {step_type}")
                
        except Exception as e:
            handle_error(e)
            return {"name": step_name, "status": "failed", "error": str(e)}
    
    async def _execute_single_agent_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single agent step."""
        agent_type = step.get("agent_type")
        task_data = step.get("task_data", {})
        
        # Find suitable agent
        suitable_agents = []
        for agent in self.agent_manager.active_agents.values():
            capabilities = await agent.get_capabilities()
            if agent_type in capabilities.expertise_domains:
                suitable_agents.append(agent)
        
        if not suitable_agents:
            return {"status": "failed", "error": f"No agent found for type {agent_type}"}
        
        agent = suitable_agents[0]
        result = await agent.process(task_data)
        
        return {
            "name": step.get("name", "single_agent_step"),
            "status": "completed",
            "agent_id": agent.agent_id,
            "result": result
        }
    
    async def _execute_collaboration_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a collaboration step."""
        agent_types = step.get("agent_types", [])
        task = step.get("task", "")
        
        # Find agents for each type
        agent_ids = []
        for agent_type in agent_types:
            for agent in self.agent_manager.active_agents.values():
                capabilities = await agent.get_capabilities()
                if agent_type in capabilities.expertise_domains:
                    agent_ids.append(agent.agent_id)
                    break
        
        if len(agent_ids) < 2:
            return {"status": "failed", "error": "Need at least 2 agents for collaboration"}
        
        result = await self.agent_manager.collaborate_agents(agent_ids, task)
        
        return {
            "name": step.get("name", "collaboration_step"),
            "status": "completed",
            "participating_agents": agent_ids,
            "result": result
        }
    
    async def _execute_reflection_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a reflection step."""
        reflection_input = {
            "previous_results": context.get("step_results", []),
            "reflection_prompt": step.get("prompt", "Reflect on the previous steps")
        }
        
        reflection_result = await self.reflection_engine.reflect(reflection_input)
        
        return {
            "name": step.get("name", "reflection_step"),
            "status": "completed",
            "result": reflection_result
        }
    
    async def _synthesize_workflow_results(self, step_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesize results from all workflow steps."""
        synthesis = {
            "total_steps": len(step_results),
            "successful_steps": len([r for r in step_results if r.get("status") == "completed"]),
            "key_insights": [],
            "recommendations": [],
            "synthesis_timestamp": datetime.now().isoformat()
        }
        
        # Extract insights from all steps
        for step_result in step_results:
            if step_result.get("status") == "completed":
                result = step_result.get("result", {})
                if "insights" in result:
                    synthesis["key_insights"].extend(result["insights"])
                if "recommendations" in result:
                    synthesis["recommendations"].extend(result["recommendations"])
        
        return synthesis

async def create_agent_system() -> AgentManager:
    """Factory function to create a complete agent system."""
    manager = AgentManager()
    
    # TODO: Initialize and register default agents
    # This would typically load agent configurations and instantiate them
    
    logger.info("Agent system created successfully")
    return manager