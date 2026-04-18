import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from config.logger import get_logger
from config.errors import handle_error
from agents.base_agent import BaseAgent
from agents.comm_bus import CommunicationBus
from agents.vector_search_agent import VectorSearchAgent
from agents.arxiv_search_agent import ArXivSearchAgent
from agents.synthesis_agent import SynthesisAgent
from knowledge.retrieval import KnowledgeRetriever
from memory.working import WorkingMemory
from physics.hypothesis import HypothesisGenerator

logger = get_logger(__name__)

class ResearchAgent(BaseAgent):
    """Orchestrates 13-agent knowledge swarm for physics research."""
    
    def __init__(
        self,     
        agent_id: str = "research_agent",     
        comm_bus: Optional[CommunicationBus] = None,     
        retriever: Optional[KnowledgeRetriever] = None,     
        working_memory: Optional[WorkingMemory] = None
    , **kwargs):
        super().__init__(agent_id="research_agent", name="ResearchAgent")
        self.retriever = retriever or KnowledgeRetriever()
        self.working_memory = working_memory or WorkingMemory()
        self.hypothesis_generator = HypothesisGenerator()
        
        # Initialize sub-agents
        self.vector_search_agent = VectorSearchAgent(comm_bus=comm_bus)
        self.arxiv_search_agent = ArXivSearchAgent(comm_bus=comm_bus)
        self.synthesis_agent = SynthesisAgent(comm_bus=comm_bus)
        
        # Agent swarm configuration
        self.swarm_agents = [
            self.vector_search_agent,
            self.arxiv_search_agent,
            self.synthesis_agent
        ]
        
        self.search_strategies = [
            "semantic_similarity",
            "keyword_expansion", 
            "citation_network",
            "temporal_relevance",
            "cross_domain"
        ]
    
    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming research requests."""
        try:
            query = message.get("query", "")
            research_type = message.get("type", "comprehensive")
            
            if research_type == "comprehensive":
                return await self.comprehensive_research(query)
            elif research_type == "targeted":
                return await self.targeted_search(query, message.get("domains", []))
            elif research_type == "hypothesis":
                return await self.hypothesis_driven_research(query)
            else:
                return {"error": f"Unknown research type: {research_type}"}
                
        except Exception as e:
            handle_error(e)
            return {"error": str(e)}
    
    async def comprehensive_research(self, query: str) -> Dict[str, Any]:
        """Execute comprehensive multi-strategy knowledge gathering."""
        logger.info(f"Starting comprehensive research for: {query}")
        
        # Dispatch parallel searches across the swarm
        search_tasks = []
        
        # Vector similarity searches with different strategies
        for strategy in self.search_strategies:
            task = self.vector_search_agent.process_message({
                "query": query,
                "strategy": strategy,
                "top_k": 20
            })
            search_tasks.append(task)
        
        # ArXiv searches with temporal and domain variations
        arxiv_queries = self._generate_arxiv_queries(query)
        for arxiv_query in arxiv_queries:
            task = self.arxiv_search_agent.process_message({
                "query": arxiv_query,
                "max_results": 50,
                "sort_by": "relevance"
            })
            search_tasks.append(task)
        
        # Execute all searches in parallel
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Filter successful results
        valid_results = [r for r in search_results if not isinstance(r, Exception)]
        for _i, _sr in enumerate(search_results):
            _np = len(_sr.get("papers", [])) if isinstance(_sr, dict) else "ERR"
            logger.info(f"[gather #{_i}] type={type(_sr).__name__} papers={_np} keys={list(_sr.keys()) if isinstance(_sr, dict) else _sr}")
        for _i, _sr in enumerate(search_results):
            _np = len(_sr.get("papers", [])) if isinstance(_sr, dict) else "ERR"
            _qu = _sr.get("query_used", "") if isinstance(_sr, dict) else ""
            logger.info(f"[gather #{_i}] type={type(_sr).__name__} papers={_np} query_used={_qu!r} keys={list(_sr.keys()) if isinstance(_sr, dict) else _sr}")
        
        # Synthesize knowledge
        synthesis_result = await self.synthesis_agent.process_message({
            "results": valid_results,
            "query": query,
            "synthesis_type": "comprehensive"
        })
        
        # Generate structured insights
        _combined_papers = []
        for _vr in valid_results:
            if not isinstance(_vr, dict):
                continue
            _got = False
            for _lk in ("papers","result","results","articles","items","entries","data"):
                _plist = _vr.get(_lk)
                if isinstance(_plist, dict):
                    _plist = _plist.get("papers", [])
                if isinstance(_plist, list):
                    for _p in _plist:
                        if isinstance(_p, dict):
                            _t = _p.get("title","")
                            _a = _p.get("abstract",_p.get("summary",_p.get("content",_p.get("text",""))))
                            if _a:
                                _combined_papers.append("Title: "+_t+"\nAbstract: "+_a)
                                _got = True
                        elif isinstance(_p, str) and _p:
                            _combined_papers.append(_p)
                            _got = True
                if _got:
                    break
            if not _got:
                for _ck in ("content","text","summary","abstract"):
                    _cv = _vr.get(_ck,"")
                    if isinstance(_cv,str) and _cv:
                        _combined_papers.append(_cv)
                        break
        if _combined_papers and not (isinstance(synthesis_result,dict) and synthesis_result.get("success")):
            _secs = ["## Research Findings"] + ["• " + _p for _p in _combined_papers]
            synthesis_result = {"content": "\n".join(_secs), "confidence": 0.7, "success": True}
        insights = await self._generate_insights(synthesis_result, query)
        
        # Store in working memory
        await self.working_memory.store_context({
            "query": query,
            "insights": insights,
            "timestamp": datetime.now().isoformat(),
            "search_count": len(valid_results)
        })
        
        return {
            "query": query,
            "insights": insights,
            "knowledge_sources": len(valid_results),
            "synthesis": synthesis_result,
            "timestamp": datetime.now().isoformat()
        }
    
    async def targeted_search(self, query: str, domains: List[str]) -> Dict[str, Any]:
        """Execute domain-specific targeted research."""
        logger.info(f"Targeted search in domains {domains} for: {query}")
        
        search_tasks = []
        
        # Domain-specific vector searches
        for domain in domains:
            domain_query = f"{query} {domain}"
            task = self.vector_search_agent.process_message({
                "query": domain_query,
                "strategy": "semantic_similarity",
                "domain_filter": domain,
                "top_k": 15
            })
            search_tasks.append(task)
        
        # Domain-specific ArXiv searches
        for domain in domains:
            task = self.arxiv_search_agent.process_message({
                "query": query,
                "categories": self._domain_to_arxiv_categories(domain),
                "max_results": 30
            })
            search_tasks.append(task)
        
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        valid_results = [r for r in search_results if not isinstance(r, Exception)]
        
        # Domain-focused synthesis
        synthesis_result = await self.synthesis_agent.process_message({
            "results": valid_results,
            "query": query,
            "synthesis_type": "domain_focused",
            "domains": domains
        })
        
        _combined_papers = []
        for _vr in valid_results:
            if not isinstance(_vr, dict):
                continue
            _got = False
            for _lk in ("papers","result","results","articles","items","entries","data"):
                _plist = _vr.get(_lk)
                if isinstance(_plist, dict):
                    _plist = _plist.get("papers", [])
                if isinstance(_plist, list):
                    for _p in _plist:
                        if isinstance(_p, dict):
                            _t = _p.get("title","")
                            _a = _p.get("abstract",_p.get("summary",_p.get("content",_p.get("text",""))))
                            if _a:
                                _combined_papers.append("Title: "+_t+"\nAbstract: "+_a)
                                _got = True
                        elif isinstance(_p, str) and _p:
                            _combined_papers.append(_p)
                            _got = True
                if _got:
                    break
            if not _got:
                for _ck in ("content","text","summary","abstract"):
                    _cv = _vr.get(_ck,"")
                    if isinstance(_cv,str) and _cv:
                        _combined_papers.append(_cv)
                        break
        if _combined_papers and not (isinstance(synthesis_result,dict) and synthesis_result.get("success")):
            _secs = ["## Research Findings"] + ["• " + _p for _p in _combined_papers]
            synthesis_result = {"content": "\n".join(_secs), "confidence": 0.7, "success": True}
        insights = await self._generate_insights(synthesis_result, query, domains)
        
        return {
            "query": query,
            "domains": domains,
            "insights": insights,
            "synthesis": synthesis_result,
            "sources_found": len(valid_results)
        }
    
    async def hypothesis_driven_research(self, query: str) -> Dict[str, Any]:
        """Research driven by hypothesis generation and testing."""
        logger.info(f"Hypothesis-driven research for: {query}")
        
        # Generate initial hypotheses
        hypotheses = await self.hypothesis_generator.generate_hypotheses(query)
        
        research_results = []
        
        for hypothesis in hypotheses:
            # Research each hypothesis
            hypothesis_query = f"{query} {hypothesis.statement}"
            
            # Focused search for evidence
            evidence_task = self.vector_search_agent.process_message({
                "query": hypothesis_query,
                "strategy": "evidence_seeking",
                "top_k": 10
            })
            
            contradictions_task = self.vector_search_agent.process_message({
                "query": f"contradictions {hypothesis_query}",
                "strategy": "semantic_similarity", 
                "top_k": 5
            })
            
            evidence_results, contradiction_results = await asyncio.gather(
                evidence_task, contradictions_task, return_exceptions=True
            )
            
            if not isinstance(evidence_results, Exception):
                research_results.append({
                    "hypothesis": hypothesis.statement,
                    "evidence": evidence_results,
                    "contradictions": contradiction_results if not isinstance(contradiction_results, Exception) else None
                })
        
        # Synthesize hypothesis evaluation
        synthesis_result = await self.synthesis_agent.process_message({
            "results": research_results,
            "query": query,
            "synthesis_type": "hypothesis_evaluation"
        })
        
        return {
            "query": query,
            "hypotheses_tested": len(hypotheses),
            "research_results": research_results,
            "synthesis": synthesis_result,
            "hypothesis_rankings": synthesis_result.get("hypothesis_rankings", [])
        }
    
    async def _generate_insights(
        self, 
        synthesis_result: Dict[str, Any], 
        query: str, 
        domains: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate structured insights from synthesis results."""
        insights = {
            "key_findings": [],
            "knowledge_gaps": [],
            "research_directions": [],
            "methodology_insights": [],
            "theoretical_implications": []
        }
        
        synthesis_content = synthesis_result.get("synthesis", {})
        if not synthesis_content:
            synthesis_content = synthesis_result
        
        # Extract key findings
        if "findings" in synthesis_content:
            insights["key_findings"] = synthesis_content["findings"]
        
        # Identify knowledge gaps
        if "gaps" in synthesis_content:
            insights["knowledge_gaps"] = synthesis_content["gaps"]
        
        # Suggest research directions
        if "directions" in synthesis_content:
            insights["research_directions"] = synthesis_content["directions"]
        
        # Add metadata
        insights["confidence_score"] = synthesis_content.get("confidence", 0.5)
        insights["source_diversity"] = synthesis_content.get("source_diversity", 0.0)
        if not insights["key_findings"]:
            for _cl in synthesis_content.get("content", "").splitlines():
                _cs = _cl.strip()
                if _cs and _cs[0] in ("•", "-"):
                    insights["key_findings"].append(_cs[1:].strip())
        
        return insights
    
    def _generate_arxiv_queries(self, base_query: str) -> List[str]:
        """Generate diverse ArXiv search queries."""
        variations = [
            base_query,
            f"{base_query} theory",
            f"{base_query} experimental",
            f"{base_query} computational",
            f"{base_query} review",
            f"{base_query} recent advances"
        ]
        return variations
    
    def _domain_to_arxiv_categories(self, domain: str) -> List[str]:
        """Map research domains to ArXiv categories."""
        domain_mapping = {
            "quantum": ["quant-ph", "cond-mat.mes-hall"],
            "cosmology": ["astro-ph.CO", "gr-qc"],
            "particle": ["hep-ph", "hep-ex", "hep-th"],
            "condensed_matter": ["cond-mat.str-el", "cond-mat.stat-mech"],
            "optics": ["physics.optics", "quant-ph"],
            "plasma": ["physics.plasm-ph"],
            "nuclear": ["nucl-th", "nucl-ex"]
        }
        return domain_mapping.get(domain.lower(), ["physics"])
    
    async def get_research_status(self) -> Dict[str, Any]:
        """Get current research status and statistics."""
        context = self.working_memory.get_current_context()
        
        return {
            "active_queries": len(context.get("queries", [])),
            "knowledge_sources": context.get("total_sources", 0),
            "recent_insights": context.get("recent_insights", []),
            "swarm_status": {
                agent.agent_id: "active" for agent in self.swarm_agents
            }
        }
    async def _process_cycle(self, *args, **kwargs):
        pass

    async def on_message_received(self, message=None, *args, **kwargs):
        pass

    async def process_task(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def get_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def run(self, *args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'comprehensive'})
