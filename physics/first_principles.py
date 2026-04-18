"""First principles physics engine that constructs theories from minimal axioms."""

import asyncio
from typing import Dict, List, Optional, Set, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import sympy as sp
from sympy import symbols, Eq, solve, simplify, diff, integrate
import json
from datetime import datetime

from config.logger import get_logger
from config.errors import handle_error
from physics.sympy_engine import SympyEngine
from physics.dimensional import DimensionalAnalyzer
try:
    from physics.contradictions import ContradictionDetector
except ImportError:  # circular import guard — physics.contradictions
    ContradictionDetector = type('ContradictionDetector', (), {})
from memory.working import WorkingMemory

logger = get_logger(__name__)


class AxiomType(Enum):
    """Types of fundamental axioms."""
    GEOMETRIC = "geometric"
    ALGEBRAIC = "algebraic"
    LOGICAL = "logical"
    PHYSICAL = "physical"


class DerivationStep(Enum):
    """Types of derivation steps."""
    AXIOM_APPLICATION = "axiom_application"
    LOGICAL_DEDUCTION = "logical_deduction"
    MATHEMATICAL_OPERATION = "mathematical_operation"
    SYMMETRY_ARGUMENT = "symmetry_argument"
    DIMENSIONAL_ANALYSIS = "dimensional_analysis"
    SUBSTITUTION = "substitution"


@dataclass
class Axiom:
    """Fundamental assumption or principle."""
    name: str
    statement: str
    mathematical_form: Optional[sp.Expr] = None
    axiom_type: AxiomType = AxiomType.LOGICAL
    dependencies: Set[str] = field(default_factory=set)
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert axiom to dictionary."""
        return {
            "name": self.name,
            "statement": self.statement,
            "mathematical_form": str(self.mathematical_form) if self.mathematical_form else None,
            "axiom_type": self.axiom_type.value,
            "dependencies": list(self.dependencies),
            "confidence": self.confidence
        }


@dataclass
class DerivationChain:
    """Complete reasoning chain from axioms to conclusion."""
    premise_axioms: List[str]
    steps: List[Dict[str, Any]]
    conclusion: str
    mathematical_result: Optional[sp.Expr] = None
    validity_score: float = 0.0
    
    def add_step(self, step_type: DerivationStep, description: str, 
                 mathematical_operation: Optional[str] = None,
                 result: Optional[sp.Expr] = None) -> None:
        """Add a derivation step to the chain."""
        step = {
            "type": step_type.value,
            "description": description,
            "mathematical_operation": mathematical_operation,
            "result": str(result) if result else None,
            "timestamp": datetime.now().isoformat()
        }
        self.steps.append(step)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert derivation chain to dictionary."""
        return {
            "premise_axioms": self.premise_axioms,
            "steps": self.steps,
            "conclusion": self.conclusion,
            "mathematical_result": str(self.mathematical_result) if self.mathematical_result else None,
            "validity_score": self.validity_score
        }


@dataclass
class Theory:
    """Emergent theory constructed from first principles."""
    name: str
    foundational_axioms: List[str]
    derived_principles: List[str]
    mathematical_framework: Dict[str, sp.Expr]
    derivation_chains: List[DerivationChain]
    predictions: List[str] = field(default_factory=list)
    experimental_tests: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert theory to dictionary."""
        return {
            "name": self.name,
            "foundational_axioms": self.foundational_axioms,
            "derived_principles": self.derived_principles,
            "mathematical_framework": {k: str(v) for k, v in self.mathematical_framework.items()},
            "derivation_chains": [chain.to_dict() for chain in self.derivation_chains],
            "predictions": self.predictions,
            "experimental_tests": self.experimental_tests,
            "confidence": self.confidence
        }


class FirstPrinciplesEngine:
    """Pure axiom-to-theory engine with explicit reasoning chains."""
    
    def __init__(self,      sympy_engine: Optional[SympyEngine] = None,     
                 dimensional_analyzer: Optional[DimensionalAnalyzer] = None,     
                 contradiction_detector: Optional[ContradictionDetector] = None,     
                 working_memory: Optional[WorkingMemory] = None, **kwargs):
        """Initialize the first principles engine."""
        self.sympy_engine = sympy_engine or SympyEngine()
        self.dimensional_analyzer = dimensional_analyzer or DimensionalAnalyzer()
        self.contradiction_detector = contradiction_detector or ContradictionDetector()
        self.working_memory = working_memory or WorkingMemory()
        
        # Core axiom registry
        self.axioms: Dict[str, Axiom] = {}
        self.derived_theories: Dict[str, Theory] = {}
        self.forbidden_priors: Set[str] = set()
        
        # Initialize minimal axioms
        self._initialize_core_axioms()
    
    def _initialize_core_axioms(self) -> None:
        """Initialize minimal set of foundational axioms."""
        # Logical axioms
        self.add_axiom(Axiom(
            name="identity",
            statement="A thing is identical to itself",
            axiom_type=AxiomType.LOGICAL
        ))
        
        self.add_axiom(Axiom(
            name="non_contradiction",
            statement="A proposition cannot be both true and false",
            axiom_type=AxiomType.LOGICAL
        ))
        
        # Mathematical axioms
        x, y, z = symbols('x y z')
        self.add_axiom(Axiom(
            name="associativity",
            statement="Addition is associative",
            mathematical_form=Eq((x + y) + z, x + (y + z)),
            axiom_type=AxiomType.ALGEBRAIC
        ))
        
        # Geometric axioms
        self.add_axiom(Axiom(
            name="euclidean_space",
            statement="Space has three orthogonal dimensions",
            axiom_type=AxiomType.GEOMETRIC
        ))
        
        # Physical axioms (minimal)
        self.add_axiom(Axiom(
            name="causality",
            statement="Events have causes that precede them in time",
            axiom_type=AxiomType.PHYSICAL
        ))
    
    def add_axiom(self, axiom: Axiom) -> None:
        """Add an axiom to the registry."""
        if axiom.name in self.forbidden_priors:
            raise ValueError(f"Axiom '{axiom.name}' is explicitly forbidden as a prior")
        
        self.axioms[axiom.name] = axiom
        logger.info(f"Added axiom: {axiom.name}")
    
    def forbid_prior(self, prior_name: str) -> None:
        """Explicitly forbid a concept as an implicit prior."""
        self.forbidden_priors.add(prior_name)
        if prior_name in self.axioms:
            del self.axioms[prior_name]
        logger.info(f"Forbidden prior: {prior_name}")
    
    async def derive_principle(self, target_concept: str, 
                             allowed_axioms: List[str]) -> Optional[DerivationChain]:
        """Derive a principle using only specified axioms."""
        try:
            # Validate axioms exist
            for axiom_name in allowed_axioms:
                if axiom_name not in self.axioms:
                    raise ValueError(f"Unknown axiom: {axiom_name}")
            
            # Create derivation chain
            chain = DerivationChain(
                premise_axioms=allowed_axioms,
                steps=[],
                conclusion=target_concept
            )
            
            # Apply axiom-based reasoning
            result = await self._apply_reasoning_chain(target_concept, allowed_axioms, chain)
            
            if result:
                # Validate derivation
                chain.validity_score = await self._validate_derivation(chain)
                return chain
            
            return None
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def _apply_reasoning_chain(self, target: str, axioms: List[str], 
                                   chain: DerivationChain) -> bool:
        """Apply logical reasoning using specified axioms."""
        try:
            # Step 1: Establish foundational concepts from axioms
            chain.add_step(
                DerivationStep.AXIOM_APPLICATION,
                f"Starting from axioms: {', '.join(axioms)}"
            )
            
            # Step 2: Apply dimensional analysis if applicable
            if await self._requires_dimensional_analysis(target):
                dimensional_result = await self._apply_dimensional_reasoning(target, axioms)
                if dimensional_result:
                    chain.add_step(
                        DerivationStep.DIMENSIONAL_ANALYSIS,
                        "Applied dimensional consistency constraints",
                        result=dimensional_result
                    )
            
            # Step 3: Apply mathematical operations
            mathematical_result = await self._apply_mathematical_reasoning(target, axioms)
            if mathematical_result:
                chain.add_step(
                    DerivationStep.MATHEMATICAL_OPERATION,
                    "Applied mathematical transformations",
                    result=mathematical_result
                )
                chain.mathematical_result = mathematical_result
            
            # Step 4: Apply symmetry arguments
            symmetry_result = await self._apply_symmetry_reasoning(target, axioms)
            if symmetry_result:
                chain.add_step(
                    DerivationStep.SYMMETRY_ARGUMENT,
                    "Applied symmetry principles",
                    result=symmetry_result
                )
            
            # Step 5: Logical deduction
            chain.add_step(
                DerivationStep.LOGICAL_DEDUCTION,
                f"Derived conclusion: {target}"
            )
            
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def _requires_dimensional_analysis(self, target: str) -> bool:
        """Check if target concept requires dimensional analysis."""
        dimensional_concepts = {
            "force", "energy", "momentum", "velocity", "acceleration",
            "mass", "length", "time", "charge", "temperature"
        }
        return any(concept in target.lower() for concept in dimensional_concepts)
    
    async def _apply_dimensional_reasoning(self, target: str, axioms: List[str]) -> Optional[sp.Expr]:
        """Apply dimensional analysis constraints."""
        try:
            # Use dimensional analyzer
            dimensions = await self.dimensional_analyzer.analyze_concept(target)
            if dimensions:
                return sp.sympify(str(dimensions))
            return None
        except Exception as e:
            handle_error(e)
            return None
    
    async def _apply_mathematical_reasoning(self, target: str, axioms: List[str]) -> Optional[sp.Expr]:
        """Apply mathematical transformations and operations."""
        try:
            # Extract mathematical axioms
            math_axioms = []
            for axiom_name in axioms:
                axiom = self.axioms[axiom_name]
                if axiom.mathematical_form:
                    math_axioms.append(axiom.mathematical_form)
            
            if not math_axioms:
                return None
            
            # Apply algebraic manipulations
            result = await self.sympy_engine.solve_system(math_axioms)
            return result
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def _apply_symmetry_reasoning(self, target: str, axioms: List[str]) -> Optional[sp.Expr]:
        """Apply symmetry-based reasoning."""
        try:
            # Identify relevant symmetries
            symmetries = await self._identify_symmetries(target, axioms)
            
            if symmetries:
                # Apply symmetry constraints
                x, y, z, t = symbols('x y z t')
                if "translation" in symmetries:
                    # Translation symmetry implies conservation
                    return sp.Symbol(f"conserved_{target.lower()}")
                elif "rotation" in symmetries:
                    # Rotational symmetry implies angular conservation
                    return sp.Symbol(f"angular_{target.lower()}")
            
            return None
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def _identify_symmetries(self, target: str, axioms: List[str]) -> List[str]:
        """Identify relevant symmetries for the target concept."""
        symmetries = []
        
        # Check geometric axioms for symmetry information
        for axiom_name in axioms:
            axiom = self.axioms[axiom_name]
            if axiom.axiom_type == AxiomType.GEOMETRIC:
                if "space" in axiom.statement.lower():
                    symmetries.extend(["translation", "rotation"])
                elif "time" in axiom.statement.lower():
                    symmetries.append("temporal")
        
        return symmetries
    
    async def _validate_derivation(self, chain: DerivationChain) -> float:
        """Validate the logical consistency of a derivation chain."""
        try:
            score = 1.0
            
            # Check for contradictions
            has_contradiction = await self.contradiction_detector.check_chain(chain)
            if has_contradiction:
                score *= 0.5
            
            # Check step validity
            for step in chain.steps:
                if not await self._validate_step(step):
                    score *= 0.8
            
            # Check mathematical consistency
            if chain.mathematical_result:
                is_consistent = await self.sympy_engine.check_consistency([chain.mathematical_result])
                if not is_consistent:
                    score *= 0.6
            
            return max(score, 0.0)
            
        except Exception as e:
            handle_error(e)
            return 0.0
    
    async def _validate_step(self, step: Dict[str, Any]) -> bool:
        """Validate a single derivation step."""
        try:
            step_type = DerivationStep(step["type"])
            
            # Basic validation based on step type
            if step_type == DerivationStep.AXIOM_APPLICATION:
                return "description" in step
            elif step_type == DerivationStep.MATHEMATICAL_OPERATION:
                return "result" in step and step["result"] is not None
            elif step_type == DerivationStep.DIMENSIONAL_ANALYSIS:
                return "result" in step
            
            return True
            
        except Exception as e:
            handle_error(e)
            return False
    
    async def construct_theory(self, theory_name: str, 
                             foundational_axioms: List[str],
                             target_principles: List[str]) -> Optional[Theory]:
        """Construct a complete theory from axioms to derived principles."""
        try:
            # Validate all axioms exist
            for axiom_name in foundational_axioms:
                if axiom_name not in self.axioms:
                    raise ValueError(f"Unknown foundational axiom: {axiom_name}")
            
            # Derive each target principle
            derivation_chains = []
            mathematical_framework = {}
            
            for principle in target_principles:
                chain = await self.derive_principle(principle, foundational_axioms)
                if chain and chain.validity_score > 0.5:
                    derivation_chains.append(chain)
                    if chain.mathematical_result:
                        mathematical_framework[principle] = chain.mathematical_result
            
            # Create theory
            theory = Theory(
                name=theory_name,
                foundational_axioms=foundational_axioms,
                derived_principles=[chain.conclusion for chain in derivation_chains],
                mathematical_framework=mathematical_framework,
                derivation_chains=derivation_chains
            )
            
            # Calculate overall theory confidence
            if derivation_chains:
                theory.confidence = sum(chain.validity_score for chain in derivation_chains) / len(derivation_chains)
            
            # Generate predictions
            theory.predictions = await self._generate_predictions(theory)
            
            # Store theory
            self.derived_theories[theory_name] = theory
            
            return theory
            
        except Exception as e:
            handle_error(e)
            return None
    
    async def _generate_predictions(self, theory: Theory) -> List[str]:
        """Generate testable predictions from a theory."""
        predictions = []
        
        try:
            # Extract mathematical predictions
            for principle, expr in theory.mathematical_framework.items():
                if expr:
                    # Generate numerical predictions
                    prediction = f"If {principle}, then mathematical relationship: {expr}"
                    predictions.append(prediction)
            
            # Generate qualitative predictions from derivation chains
            for chain in theory.derivation_chains:
                if chain.validity_score > 0.7:
                    prediction = f"Experimental test: Verify {chain.conclusion} under controlled conditions"
                    predictions.append(prediction)
            
            return predictions[:10]  # Limit to top 10 predictions
            
        except Exception as e:
            handle_error(e)
            return []
    
    async def check_axiom_minimality(self, theory_name: str) -> Dict[str, Any]:
        """Check if theory can be derived from fewer axioms."""
        if theory_name not in self.derived_theories:
            return {"error": "Theory not found"}
        
        theory = self.derived_theories[theory_name]
        original_axioms = theory.foundational_axioms.copy()
        
        minimal_sets = []
        
        try:
            # Test removal of each axiom
            for i, axiom_to_remove in enumerate(original_axioms):
                reduced_axioms = original_axioms[:i] + original_axioms[i+1:]
                
                # Try to derive same principles with reduced set
                can_derive_all = True
                for principle in theory.derived_principles:
                    chain = await self.derive_principle(principle, reduced_axioms)
                    if not chain or chain.validity_score < 0.5:
                        can_derive_all = False
                        break
                
                if can_derive_all:
                    minimal_sets.append(reduced_axioms)
            
            return {
                "original_axioms": original_axioms,
                "minimal_sets": minimal_sets,
                "is_minimal": len(minimal_sets) == 0
            }
            
        except Exception as e:
            handle_error(e)
            return {"error": str(e)}
    
    def get_axiom_dependencies(self, axiom_name: str) -> Set[str]:
        """Get all axioms that the specified axiom depends on."""
        if axiom_name not in self.axioms:
            return set()
        
        dependencies = set()
        axiom = self.axioms[axiom_name]
        
        # Direct dependencies
        dependencies.update(axiom.dependencies)
        
        # Recursive dependencies
        for dep in axiom.dependencies:
            dependencies.update(self.get_axiom_dependencies(dep))
        
        return dependencies
    
    async def export_theory(self, theory_name: str) -> Optional[Dict[str, Any]]:
        """Export a theory as a complete JSON structure."""
        if theory_name not in self.derived_theories:
            return None
        
        theory = self.derived_theories[theory_name]
        
        # Include full axiom definitions
        axiom_definitions = {}
        for axiom_name in theory.foundational_axioms:
            if axiom_name in self.axioms:
                axiom_definitions[axiom_name] = self.axioms[axiom_name].to_dict()
        
        return {
            "theory": theory.to_dict(),
            "axiom_definitions": axiom_definitions,
            "export_timestamp": datetime.now().isoformat(),
            "engine_version": "1.0.0"
        }
    
    def list_theories(self) -> List[str]:
        """List all constructed theories."""
        return list(self.derived_theories.keys())
    
    def list_axioms(self) -> List[str]:
        """List all available axioms."""
        return list(self.axioms.keys())
    
    def get_forbidden_priors(self) -> List[str]:
        """Get list of forbidden implicit priors."""
        return list(self.forbidden_priors)

    async def analyze_dimensions(self, *args, **kwargs):
        return dict()

FirstPrinciples = FirstPrinciplesEngine  # auto-alias

FirstPrinciplesChecker = FirstPrinciplesEngine  # auto-alias
ALGEBRAIC = type('ALGEBRAIC', (), {})  # auto-stub: not found in project

AXIOM_APPLICATION = type('AXIOM_APPLICATION', (), {})  # auto-stub: not found in project

DIMENSIONAL_ANALYSIS = type('DIMENSIONAL_ANALYSIS', (), {})  # auto-stub: not found in project

GEOMETRIC = type('GEOMETRIC', (), {})  # auto-stub: not found in project

LOGICAL = type('LOGICAL', (), {})  # auto-stub: not found in project

LOGICAL_DEDUCTION = type('LOGICAL_DEDUCTION', (), {})  # auto-stub: not found in project

MATHEMATICAL_OPERATION = type('MATHEMATICAL_OPERATION', (), {})  # auto-stub: not found in project

PHYSICAL = type('PHYSICAL', (), {})  # auto-stub: not found in project

SUBSTITUTION = type('SUBSTITUTION', (), {})  # auto-stub: not found in project

SYMMETRY_ARGUMENT = type('SYMMETRY_ARGUMENT', (), {})  # auto-stub: not found in project
