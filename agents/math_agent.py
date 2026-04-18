import asyncio
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass
from datetime import datetime
import json

import sympy as sp
from sympy import symbols, solve, diff, integrate, simplify, expand, factor
from sympy import Matrix, tensorproduct, KroneckerProduct, Array
from sympy import Function, Eq, dsolve, pdsolve
from sympy.physics.vector import CoordinateSym, gradient, divergence, curl
from sympy.physics.quantum import Operator, Commutator, AntiCommutator
# [auto-removed unresolvable import] from sympy.tensor import tensorType, tensor, tensor
from sympy.tensor.tensor import TensMul, TensAdd
from sympy.algebras.quaternion import Quaternion
# [auto-removed unresolvable import] from sympy.geometry import Point, Line, Plane, Sphere
from sympy.diffgeom import Manifold, Patch, CoordSystem
import numpy as np

from agents.base_agent import BaseAgent
from agents.comm_bus import CommunicationBus
from physics.sympy_engine import SymPyEngine
from physics.tensors import TensorOperations
from physics.quantum import QuantumFormalism
from memory.working import WorkingMemory
from thinking.self_refine import SelfRefine
from config.logger import get_logger
from config.errors import handle_error

logger = get_logger(__name__)

@dataclass
class MathResult:
    """Result container for mathematical operations."""
    expression: Any
    simplified: Any
    latex: str
    steps: List[str]
    metadata: Dict[str, Any]

@dataclass
class DerivationContext:
    """Context for mathematical derivations."""
    variables: List[sp.Symbol]
    assumptions: List[sp.Basic]
    coordinate_system: Optional[str] = None
    manifold: Optional[str] = None
    metric: Optional[sp.Matrix] = None

class MathAgent(BaseAgent):
    """SymPy-powered symbolic math agent for physics research."""
    
    def __init__(self,       comm_bus=None, **kwargs):
        super().__init__(agent_id="math_result", name="MathResult")
        self.sympy_engine = SymPyEngine()
        self.tensor_ops = TensorOperations()
        self.quantum_ops = QuantumFormalism()
        self.working_memory = WorkingMemory()
        self.self_refine = SelfRefine()
        self.lean_proofs = []
        
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process mathematical computation requests."""
        try:
            operation = request.get("operation")
            
            if operation == "algebraic_manipulation":
                return await self.algebraic_manipulation(request)
            elif operation == "solve_ode":
                return await self.solve_ode(request)
            elif operation == "tensor_operation":
                return await self.tensor_operation(request)
            elif operation == "lie_algebra":
                return await self.lie_algebra_computation(request)
            elif operation == "symbolic_derivation":
                return await self.symbolic_derivation(request)
            elif operation == "generate_proof":
                return await self.generate_lean_proof(request)
            elif operation == "differential_geometry":
                return await self.differential_geometry(request)
            else:
                return {"error": f"Unknown operation: {operation}"}
                
        except Exception as e:
            handle_error(e)
            return {"error": str(e)}
    
    async def algebraic_manipulation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Perform algebraic manipulations on expressions."""
        expression = request.get("expression")
        operations = request.get("operations", ["simplify"])
        
        try:
            expr = sp.parse_expr(expression) if isinstance(expression, str) else expression
            results = {}
            steps = []
            
            for op in operations:
                if op == "simplify":
                    result = simplify(expr)
                    steps.append(f"Simplified: {expr} → {result}")
                elif op == "expand":
                    result = expand(expr)
                    steps.append(f"Expanded: {expr} → {result}")
                elif op == "factor":
                    result = factor(expr)
                    steps.append(f"Factored: {expr} → {result}")
                elif op == "collect":
                    var = sp.Symbol(request.get("collect_var", "x"))
                    result = sp.collect(expr, var)
                    steps.append(f"Collected terms in {var}: {expr} → {result}")
                elif op == "trigsimp":
                    result = sp.trigsimp(expr)
                    steps.append(f"Trigonometric simplification: {expr} → {result}")
                else:
                    continue
                
                results[op] = {
                    "expression": result,
                    "latex": sp.latex(result),
                    "python": str(result)
                }
                expr = result
            
            return {
                "success": True,
                "results": results,
                "steps": steps,
                "final_expression": str(expr),
                "latex": sp.latex(expr)
            }
            
        except Exception as e:
            return {"error": f"Algebraic manipulation failed: {str(e)}"}
    
    async def solve_ode(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Solve ordinary and partial differential equations."""
        equation = request.get("equation")
        function_name = request.get("function", "f")
        variable = request.get("variable", "x")
        equation_type = request.get("type", "ode")
        
        try:
            x = sp.Symbol(variable)
            f = sp.Function(function_name)
            
            if isinstance(equation, str):
                # Parse equation string
                eq_str = equation.replace(f"{function_name}({variable})", f"f({variable})")
                eq = sp.parse_expr(eq_str)
            else:
                eq = equation
            
            if equation_type == "ode":
                solution = dsolve(eq, f(x))
            elif equation_type == "pde":
                # For PDEs, we need additional variables
                y = sp.Symbol(request.get("second_variable", "y"))
                solution = pdsolve(eq, f(x, y))
            else:
                return {"error": f"Unknown equation type: {equation_type}"}
            
            # Verify solution
            verification = sp.simplify(eq.subs(f(x), solution.rhs).doit())
            
            return {
                "success": True,
                "equation": str(eq),
                "solution": str(solution),
                "latex_equation": sp.latex(eq),
                "latex_solution": sp.latex(solution),
                "verification": str(verification),
                "is_verified": verification == 0
            }
            
        except Exception as e:
            return {"error": f"ODE solving failed: {str(e)}"}
    
    async def tensor_operation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Perform tensor operations and calculations."""
        operation = request.get("tensor_operation")
        
        try:
            if operation == "create_metric":
                return await self._create_metric_tensor(request)
            elif operation == "christoffel_symbols":
                return await self._compute_christoffel_symbols(request)
            elif operation == "riemann_tensor":
                return await self._compute_riemann_tensor(request)
            elif operation == "tensor_contraction":
                return await self._tensor_contraction(request)
            elif operation == "lie_derivative":
                return await self._lie_derivative(request)
            else:
                return {"error": f"Unknown tensor operation: {operation}"}
                
        except Exception as e:
            return {"error": f"Tensor operation failed: {str(e)}"}
    
    async def _create_metric_tensor(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Create metric tensor from given components."""
        components = request.get("components")
        coordinates = request.get("coordinates", ["x", "y", "z", "t"])
        
        coord_symbols = [sp.Symbol(coord) for coord in coordinates]
        dim = len(coord_symbols)
        
        if isinstance(components, list):
            metric = sp.Matrix(components)
        else:
            # Create diagonal metric
            metric = sp.zeros(dim, dim)
            for i in range(dim):
                metric[i, i] = components.get(f"g{i}{i}", 1)
        
        # Compute inverse metric
        metric_inv = metric.inv()
        
        # Compute determinant
        det_g = metric.det()
        
        return {
            "success": True,
            "metric": str(metric),
            "inverse_metric": str(metric_inv),
            "determinant": str(det_g),
            "latex_metric": sp.latex(metric),
            "coordinates": coordinates
        }
    
    async def _compute_christoffel_symbols(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Compute Christoffel symbols from metric tensor."""
        metric = sp.Matrix(request.get("metric"))
        coordinates = request.get("coordinates", ["x", "y", "z", "t"])
        
        coord_symbols = [sp.Symbol(coord) for coord in coordinates]
        dim = len(coord_symbols)
        
        # Compute inverse metric
        metric_inv = metric.inv()
        
        # Compute Christoffel symbols
        christoffel = sp.Array.zeros(dim, dim, dim)
        
        for i in range(dim):
            for j in range(dim):
                for k in range(dim):
                    sum_term = 0
                    for l in range(dim):
                        dgjl_dxk = sp.diff(metric[j, l], coord_symbols[k])
                        dgkl_dxj = sp.diff(metric[k, l], coord_symbols[j])
                        dgjk_dxl = sp.diff(metric[j, k], coord_symbols[l])
                        sum_term += metric_inv[i, l] * (dgjl_dxk + dgkl_dxj - dgjk_dxl)
                    
                    christoffel[i, j, k] = sp.Rational(1, 2) * sum_term
        
        return {
            "success": True,
            "christoffel_symbols": str(christoffel),
            "latex": f"\\Gamma^{{\\mu}}_{{\nu\\rho}} computed",
            "coordinates": coordinates
        }
    
    async def lie_algebra_computation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Perform Lie algebra computations."""
        operation = request.get("lie_operation")
        
        try:
            if operation == "commutator":
                return await self._compute_commutator(request)
            elif operation == "lie_bracket":
                return await self._lie_bracket(request)
            elif operation == "adjoint_representation":
                return await self._adjoint_representation(request)
            elif operation == "killing_form":
                return await self._killing_form(request)
            else:
                return {"error": f"Unknown Lie algebra operation: {operation}"}
                
        except Exception as e:
            return {"error": f"Lie algebra computation failed: {str(e)}"}
    
    async def _compute_commutator(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Compute commutator of operators or matrices."""
        A = sp.Matrix(request.get("operator_A"))
        B = sp.Matrix(request.get("operator_B"))
        
        commutator = A * B - B * A
        
        return {
            "success": True,
            "commutator": str(commutator),
            "latex": sp.latex(commutator),
            "simplified": str(simplify(commutator))
        }
    
    async def symbolic_derivation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Perform step-by-step symbolic derivations."""
        goal = request.get("goal")
        starting_expression = request.get("starting_expression")
        method = request.get("method", "automated")
        
        try:
            expr = sp.parse_expr(starting_expression) if isinstance(starting_expression, str) else starting_expression
            steps = []
            current_expr = expr
            
            # Record initial expression
            steps.append({
                "step": 0,
                "description": "Starting expression",
                "expression": str(current_expr),
                "latex": sp.latex(current_expr)
            })
            
            # Apply derivation steps based on goal
            if goal == "simplify":
                simplified = simplify(current_expr)
                steps.append({
                    "step": 1,
                    "description": "Apply simplification rules",
                    "expression": str(simplified),
                    "latex": sp.latex(simplified)
                })
                current_expr = simplified
                
            elif goal == "integrate":
                variable = sp.Symbol(request.get("variable", "x"))
                integrated = integrate(current_expr, variable)
                steps.append({
                    "step": 1,
                    "description": f"Integrate with respect to {variable}",
                    "expression": str(integrated),
                    "latex": sp.latex(integrated)
                })
                current_expr = integrated
                
            elif goal == "differentiate":
                variable = sp.Symbol(request.get("variable", "x"))
                differentiated = diff(current_expr, variable)
                steps.append({
                    "step": 1,
                    "description": f"Differentiate with respect to {variable}",
                    "expression": str(differentiated),
                    "latex": sp.latex(differentiated)
                })
                current_expr = differentiated
            
            return {
                "success": True,
                "steps": steps,
                "final_expression": str(current_expr),
                "latex_final": sp.latex(current_expr)
            }
            
        except Exception as e:
            return {"error": f"Symbolic derivation failed: {str(e)}"}
    
    async def generate_lean_proof(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Lean 4 proof from symbolic computation."""
        theorem = request.get("theorem")
        hypothesis = request.get("hypothesis", [])
        proof_strategy = request.get("strategy", "direct")
        
        try:
            # Extract mathematical content
            expr = sp.parse_expr(theorem) if isinstance(theorem, str) else theorem
            
            # Generate Lean 4 proof structure
            lean_proof = self._generate_lean_structure(expr, hypothesis, proof_strategy)
            
            # Store proof for later verification
            proof_id = f"proof_{len(self.lean_proofs)}"
            self.lean_proofs.append({
                "id": proof_id,
                "theorem": str(expr),
                "proof": lean_proof,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "success": True,
                "proof_id": proof_id,
                "lean_proof": lean_proof,
                "theorem": str(expr),
                "latex_theorem": sp.latex(expr)
            }
            
        except Exception as e:
            return {"error": f"Lean proof generation failed: {str(e)}"}
    
    def _generate_lean_structure(self, expr: sp.Basic, hypothesis: List[str], strategy: str) -> str:
        """Generate Lean 4 proof structure."""
        # This is a simplified proof structure generator
        lean_code = f"""
    async def process_task(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def get_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        return None

    async def run(self, *args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        return await self.process_message({'query': query, 'type': 'comprehensive'})

    async def process_message(self, *args, **kwargs):
        return await self.process_request(*args, **kwargs)

theorem mathematical_theorem : {self._sympy_to_lean_type(expr)} := by
  -- Proof strategy: {strategy}
"""
        
        for i, hyp in enumerate(hypothesis):
            lean_code += f"  have h{i} : {hyp} := sorry\n"
        
        lean_code += "  sorry -- Complete proof here\n"
        
        return lean_code
    
    def _sympy_to_lean_type(self, expr: sp.Basic) -> str:
        """Convert SymPy expression to Lean type annotation."""
        # Simplified conversion - would need full implementation
        return str(expr).replace("**", "^").replace("*", " * ")
    
    async def differential_geometry(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Perform differential geometry computations."""
        operation = request.get("geometry_operation")
        
        try:
            if operation == "create_manifold":
                return await self._create_manifold(request)
            elif operation == "compute_curvature":
                return await self._compute_curvature(request)
            elif operation == "parallel_transport":
                return await self._parallel_transport(request)
            elif operation == "geodesics":
                return await self._compute_geodesics(request)
            else:
                return {"error": f"Unknown geometry operation: {operation}"}
                
        except Exception as e:
            return {"error": f"Differential geometry computation failed: {str(e)}"}
    
    async def _create_manifold(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Create manifold with coordinate system."""
        manifold_name = request.get("name", "M")
        dimension = request.get("dimension", 4)
        coordinates = request.get("coordinates")
        
        if not coordinates:
            coordinates = [f"x{i}" for i in range(dimension)]
        
        # Create manifold structure
        manifold_info = {
            "name": manifold_name,
            "dimension": dimension,
            "coordinates": coordinates,
            "patches": [],
            "coordinate_systems": []
        }
        
        return {
            "success": True,
            "manifold": manifold_info,
            "latex": f"M^{{{dimension}}} with coordinates ({', '.join(coordinates)})"
        }
    
    async def mathematical_insight(self, expression: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Provide mathematical insights about expressions."""
        try:
            expr = sp.parse_expr(expression)
            
            insights = {
                "expression": str(expr),
                "latex": sp.latex(expr),
                "complexity": self._analyze_complexity(expr),
                "symmetries": self._detect_symmetries(expr),
                "special_functions": self._identify_special_functions(expr),
                "asymptotic_behavior": self._analyze_asymptotics(expr),
                "dimensional_analysis": await self._dimensional_analysis(expr, context)
            }
            
            return {
                "success": True,
                "insights": insights
            }
            
        except Exception as e:
            return {"error": f"Mathematical insight failed: {str(e)}"}
    
    def _analyze_complexity(self, expr: sp.Basic) -> Dict[str, Any]:
        """Analyze mathematical complexity of expression."""
        return {
            "operation_count": sp.count_ops(expr),
            "atom_count": len(expr.atoms()),
            "free_symbols": [str(s) for s in expr.free_symbols],
            "has_transcendental": any(f in str(expr) for f in ['exp', 'log', 'sin', 'cos', 'tan'])
        }
    
    def _detect_symmetries(self, expr: sp.Basic) -> List[str]:
        """Detect mathematical symmetries in expression."""
        symmetries = []
        
        for symbol in expr.free_symbols:
            # Test for even/odd symmetry
            if expr.subs(symbol, -symbol) == expr:
                symmetries.append(f"Even in {symbol}")
            elif expr.subs(symbol, -symbol) == -expr:
                symmetries.append(f"Odd in {symbol}")
        
        return symmetries
    
    def _identify_special_functions(self, expr: sp.Basic) -> List[str]:
        """Identify special mathematical functions in expression."""
        special_funcs = []
        
        expr_str = str(expr)
        special_function_names = [
            'gamma', 'beta', 'zeta', 'erf', 'erfc', 'besselj', 'bessely',
            'hermite', 'laguerre', 'legendre', 'elliptic_e', 'elliptic_f'
        ]
        
        for func_name in special_function_names:
            if func_name in expr_str:
                special_funcs.append(func_name)
        
        return special_funcs
    
    def _analyze_asymptotics(self, expr: sp.Basic) -> Dict[str, str]:
        """Analyze asymptotic behavior of expression."""
        asymptotics = {}
        
        for symbol in expr.free_symbols:
            try:
                # Asymptotic behavior as symbol approaches infinity
                limit_inf = sp.limit(expr, symbol, sp.oo)
                asymptotics[f"{symbol}_to_inf"] = str(limit_inf)
                
                # Asymptotic behavior as symbol approaches zero
                limit_zero = sp.limit(expr, symbol, 0)
                asymptotics[f"{symbol}_to_zero"] = str(limit_zero)
                
            except Exception:
                continue
        
        return asymptotics
    
    async def _dimensional_analysis(self, expr: sp.Basic, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform dimensional analysis of expression."""
        # Simplified dimensional analysis
        dimensions = context.get("dimensions", {})
        
        dimensional_info = {
            "symbols": [str(s) for s in expr.free_symbols],
            "assumed_dimensions": dimensions,
            "consistency_check": "requires_full_implementation"
        }
        
        return dimensional_info
    
    async def export_computation(self, computation_id: str, format_type: str) -> Dict[str, Any]:
        """Export mathematical computation in various formats."""
        try:
            # Retrieve computation from working memory
            computation = await self.working_memory.get(computation_id)
            
            if not computation:
                return {"error": "Computation not found"}
            
            if format_type == "latex":
                exported = self._export_latex(computation)
            elif format_type == "mathematica":
                exported = self._export_mathematica(computation)
            elif format_type == "maple":
                exported = self._export_maple(computation)
            elif format_type == "python":
                exported = self._export_python(computation)
            else:
                return {"error": f"Unknown export format: {format_type}"}
            
            return {
                "success": True,
                "format": format_type,
                "exported_content": exported
            }
            
        except Exception as e:
            return {"error": f"Export failed: {str(e)}"}
    
    def _export_latex(self, computation: Dict[str, Any]) -> str:
        """Export computation as LaTeX document."""
        latex_doc = "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n\n"
        
        for step in computation.get("steps", []):
            latex_doc += f"\\begin{{align}}\n{step.get('latex', '')}\n\\end{{align}}\n\n"
        
        latex_doc += "\\end{document}"
        return latex_doc
    
    def _export_mathematica(self, computation: Dict[str, Any]) -> str:
        """Export computation as Mathematica code."""
        # Simplified Mathematica export
        mathematica_code = ""
        
        for step in computation.get("steps", []):
            expr_str = step.get("expression", "")
            # Convert Python/SymPy syntax to Mathematica
            mathematica_expr = expr_str.replace("**", "^").replace("*", " ")
            mathematica_code += f"{mathematica_expr};\n"
        
        return mathematica_code
    
    def _export_maple(self, computation: Dict[str, Any]) -> str:
        """Export computation as Maple code."""
        # Simplified Maple export
        maple_code = ""
        
        for step in computation.get("steps", []):
            expr_str = step.get("expression", "")
            maple_code += f"{expr_str};\n"
        
        return maple_code
    
    def _export_python(self, computation: Dict[str, Any]) -> str:
        """Export computation as Python code."""
        python_code = "import sympy as sp\nimport numpy as np\n\n"
        
        for step in computation.get("steps", []):
            expr_str = step.get("expression", "")
            python_code += f"# {step.get('description', '')}\n"
            python_code += f"expr = sp.parse_expr('{expr_str}')\n"
            python_code += f"print(expr)\n\n"
        
        return python_code
    async def _process_cycle(self, *args, **kwargs):
        pass

    async def on_message_received(self, message=None, *args, **kwargs):
        pass
