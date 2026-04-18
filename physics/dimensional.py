"""
Dimensional analysis engine for physics equations.
Parses equations, extracts SI units, verifies dimensional consistency.
"""

import re
import sympy as sp
from sympy.physics.units import Dimension
from sympy.physics.units.systems.si import dimsys_SI
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum
import logging

from config.logger import get_logger
from config.errors import handle_error
from physics.sympy_engine import SymPyEngine

logger = get_logger(__name__)


class DimensionType(Enum):
    """Standard SI base dimensions."""
    LENGTH = "length"
    MASS = "mass"
    TIME = "time"
    CURRENT = "current"
    TEMPERATURE = "temperature"
    AMOUNT = "amount"
    LUMINOSITY = "luminosity"


@dataclass
class DimensionalVector:
    """Represents dimensions as powers of base SI units."""
    length: float = 0
    mass: float = 0
    time: float = 0
    current: float = 0
    temperature: float = 0
    amount: float = 0
    luminosity: float = 0
    
    def __add__(self, other: 'DimensionalVector') -> 'DimensionalVector':
        """Add dimensional vectors (for multiplication of quantities)."""
        return DimensionalVector(
            length=self.length + other.length,
            mass=self.mass + other.mass,
            time=self.time + other.time,
            current=self.current + other.current,
            temperature=self.temperature + other.temperature,
            amount=self.amount + other.amount,
            luminosity=self.luminosity + other.luminosity
        )
    
    def __sub__(self, other: 'DimensionalVector') -> 'DimensionalVector':
        """Subtract dimensional vectors (for division of quantities)."""
        return DimensionalVector(
            length=self.length - other.length,
            mass=self.mass - other.mass,
            time=self.time - other.time,
            current=self.current - other.current,
            temperature=self.temperature - other.temperature,
            amount=self.amount - other.amount,
            luminosity=self.luminosity - other.luminosity
        )
    
    def __mul__(self, scalar: float) -> 'DimensionalVector':
        """Multiply by scalar (for powers)."""
        return DimensionalVector(
            length=self.length * scalar,
            mass=self.mass * scalar,
            time=self.time * scalar,
            current=self.current * scalar,
            temperature=self.temperature * scalar,
            amount=self.amount * scalar,
            luminosity=self.luminosity * scalar
        )
    
    def __eq__(self, other: 'DimensionalVector') -> bool:
        """Check dimensional equality."""
        tolerance = 1e-10
        return (
            abs(self.length - other.length) < tolerance and
            abs(self.mass - other.mass) < tolerance and
            abs(self.time - other.time) < tolerance and
            abs(self.current - other.current) < tolerance and
            abs(self.temperature - other.temperature) < tolerance and
            abs(self.amount - other.amount) < tolerance and
            abs(self.luminosity - other.luminosity) < tolerance
        )
    
    def is_dimensionless(self) -> bool:
        """Check if quantity is dimensionless."""
        return self == DimensionalVector()
    
    def to_string(self) -> str:
        """Convert to readable string representation."""
        parts = []
        dims = [
            ("L", self.length), ("M", self.mass), ("T", self.time),
            ("I", self.current), ("Θ", self.temperature), 
            ("N", self.amount), ("J", self.luminosity)
        ]
        
        for symbol, power in dims:
            if abs(power) > 1e-10:
                if abs(power - 1) < 1e-10:
                    parts.append(symbol)
                elif abs(power + 1) < 1e-10:
                    parts.append(f"{symbol}⁻¹")
                else:
                    parts.append(f"{symbol}^{power}")
        
        return " ".join(parts) if parts else "dimensionless"


@dataclass
class DimensionalInconsistency:
    """Represents a dimensional inconsistency in an equation."""
    equation: str
    lhs_dimension: DimensionalVector
    rhs_dimension: DimensionalVector
    location: str
    severity: str
    suggestion: str


class DimensionalAnalyzer:
    """Core dimensional analysis engine."""
    
    def __init__(self, **kwargs):
        """Initialize dimensional analyzer."""
        self.sympy_engine = SymPyEngine()
        self._init_standard_quantities()
        
    def _init_standard_quantities(self) -> None:
        """Initialize standard physical quantities and their dimensions."""
        self.standard_dimensions = {
            # Base quantities
            'length': DimensionalVector(length=1),
            'mass': DimensionalVector(mass=1),
            'time': DimensionalVector(time=1),
            'current': DimensionalVector(current=1),
            'temperature': DimensionalVector(temperature=1),
            'amount': DimensionalVector(amount=1),
            'luminosity': DimensionalVector(luminosity=1),
            
            # Derived quantities
            'velocity': DimensionalVector(length=1, time=-1),
            'acceleration': DimensionalVector(length=1, time=-2),
            'force': DimensionalVector(mass=1, length=1, time=-2),
            'energy': DimensionalVector(mass=1, length=2, time=-2),
            'power': DimensionalVector(mass=1, length=2, time=-3),
            'pressure': DimensionalVector(mass=1, length=-1, time=-2),
            'charge': DimensionalVector(current=1, time=1),
            'voltage': DimensionalVector(mass=1, length=2, time=-3, current=-1),
            'resistance': DimensionalVector(mass=1, length=2, time=-3, current=-2),
            'capacitance': DimensionalVector(mass=-1, length=-2, time=4, current=2),
            'inductance': DimensionalVector(mass=1, length=2, time=-2, current=-2),
            'frequency': DimensionalVector(time=-1),
            'angular_frequency': DimensionalVector(time=-1),
            'momentum': DimensionalVector(mass=1, length=1, time=-1),
            'angular_momentum': DimensionalVector(mass=1, length=2, time=-1),
            'density': DimensionalVector(mass=1, length=-3),
            
            # Common symbols
            'c': DimensionalVector(length=1, time=-1),  # speed of light
            'h': DimensionalVector(mass=1, length=2, time=-1),  # Planck constant
            'hbar': DimensionalVector(mass=1, length=2, time=-1),  # reduced Planck
            'G': DimensionalVector(mass=-1, length=3, time=-2),  # gravitational constant
            'k_B': DimensionalVector(mass=1, length=2, time=-2, temperature=-1),  # Boltzmann
            'e': DimensionalVector(current=1, time=1),  # elementary charge
            'epsilon_0': DimensionalVector(mass=-1, length=-3, time=4, current=2),  # permittivity
            'mu_0': DimensionalVector(mass=1, length=1, time=-2, current=-2),  # permeability
        }
        
        # Common variable patterns
        self.variable_patterns = {
            r'\b[xyz]\b': DimensionalVector(length=1),
            r'\b[uvw]\b': DimensionalVector(length=1, time=-1),
            r'\b[abc]\b': DimensionalVector(length=1, time=-2),
            r'\bm\b': DimensionalVector(mass=1),
            r'\bt\b': DimensionalVector(time=1),
            r'\bT\b': DimensionalVector(temperature=1),
            r'\bf\b': DimensionalVector(time=-1),
            r'\bomega\b': DimensionalVector(time=-1),
            r'\bE\b': DimensionalVector(mass=1, length=2, time=-2),
            r'\bF\b': DimensionalVector(mass=1, length=1, time=-2),
            r'\bp\b': DimensionalVector(mass=1, length=1, time=-1),
            r'\bL\b': DimensionalVector(mass=1, length=2, time=-1),
            r'\bV\b': DimensionalVector(mass=1, length=2, time=-3, current=-1),
            r'\bI\b': DimensionalVector(current=1),
        }

    def parse_equation(self, equation_str: str) -> Tuple[sp.Expr, sp.Expr]:
        """Parse equation string into left and right hand sides."""
        try:
            # Clean the equation
            equation_str = equation_str.strip()
            if '=' not in equation_str:
                raise ValueError("Equation must contain '=' sign")
                
            lhs_str, rhs_str = equation_str.split('=', 1)
            
            # Parse using SymPy
            lhs = sp.sympify(lhs_str.strip())
            rhs = sp.sympify(rhs_str.strip())
            
            return lhs, rhs
            
        except Exception as e:
            handle_error(e)
            raise ValueError(f"Failed to parse equation: {equation_str}")

    def extract_symbols(self, expr: sp.Expr) -> Set[sp.Symbol]:
        """Extract all symbols from expression."""
        return expr.free_symbols

    def infer_dimensions(self, symbol: sp.Symbol) -> DimensionalVector:
        """Infer dimensions of a symbol based on naming conventions."""
        symbol_str = str(symbol)
        
        # Check direct matches first
        if symbol_str in self.standard_dimensions:
            return self.standard_dimensions[symbol_str]
        
        # Check patterns
        for pattern, dimension in self.variable_patterns.items():
            if re.match(pattern, symbol_str):
                return dimension
        
        # Default to dimensionless for unknown symbols
        logger.warning(f"Unknown symbol '{symbol_str}', assuming dimensionless")
        return DimensionalVector()

    def compute_expression_dimensions(self, expr: sp.Expr) -> DimensionalVector:
        """Compute dimensions of an entire expression."""
        try:
            if isinstance(expr, sp.Symbol):
                return self.infer_dimensions(expr)
            
            elif isinstance(expr, (sp.Integer, sp.Rational, sp.Float)):
                return DimensionalVector()  # Numbers are dimensionless
            
            elif isinstance(expr, sp.Add):
                # All terms must have same dimensions
                dimensions = []
                for arg in expr.args:
                    dim = self.compute_expression_dimensions(arg)
                    dimensions.append(dim)
                
                # Check consistency
                if dimensions:
                    first_dim = dimensions[0]
                    for dim in dimensions[1:]:
                        if dim != first_dim:
                            logger.warning(f"Inconsistent dimensions in sum: {expr}")
                    return first_dim
                return DimensionalVector()
            
            elif isinstance(expr, sp.Mul):
                # Multiply dimensions
                result_dim = DimensionalVector()
                for arg in expr.args:
                    arg_dim = self.compute_expression_dimensions(arg)
                    result_dim = result_dim + arg_dim
                return result_dim
            
            elif isinstance(expr, sp.Pow):
                base, exp = expr.args
                base_dim = self.compute_expression_dimensions(base)
                
                # Exponent must be dimensionless
                exp_dim = self.compute_expression_dimensions(exp)
                if not exp_dim.is_dimensionless():
                    logger.warning(f"Non-dimensionless exponent in: {expr}")
                
                # Handle numeric exponents
                if isinstance(exp, (sp.Integer, sp.Rational, sp.Float)):
                    return base_dim * float(exp)
                else:
                    # For symbolic exponents, assume dimensionless result
                    logger.warning(f"Symbolic exponent in: {expr}, assuming dimensionless result")
                    return DimensionalVector()
            
            elif isinstance(expr, sp.Function):
                # Most functions expect dimensionless arguments and return dimensionless
                arg_dims = [self.compute_expression_dimensions(arg) for arg in expr.args]
                
                func_name = expr.func.__name__.lower()
                
                if func_name in ['sin', 'cos', 'tan', 'exp', 'log', 'ln', 'sqrt']:
                    # These expect dimensionless arguments
                    for arg_dim in arg_dims:
                        if not arg_dim.is_dimensionless():
                            logger.warning(f"Non-dimensionless argument to {func_name}: {expr}")
                    
                    if func_name == 'sqrt' and len(expr.args) == 1:
                        # sqrt preserves half the dimensions
                        return arg_dims[0] * 0.5
                    else:
                        return DimensionalVector()
                
                else:
                    # Unknown function, assume preserves dimensions of first argument
                    return arg_dims[0] if arg_dims else DimensionalVector()
            
            else:
                # Unknown expression type
                logger.warning(f"Unknown expression type: {type(expr)}")
                return DimensionalVector()
                
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to compute dimensions for: {expr}")
            return DimensionalVector()

    def check_dimensional_consistency(self, equation_str: str) -> List[DimensionalInconsistency]:
        """Check if equation is dimensionally consistent."""
        inconsistencies = []
        
        try:
            lhs, rhs = self.parse_equation(equation_str)
            
            # Compute dimensions of both sides
            lhs_dim = self.compute_expression_dimensions(lhs)
            rhs_dim = self.compute_expression_dimensions(rhs)
            
            logger.info(f"LHS dimensions: {lhs_dim.to_string()}")
            logger.info(f"RHS dimensions: {rhs_dim.to_string()}")
            
            # Check if they match
            if lhs_dim != rhs_dim:
                suggestion = self._generate_suggestion(lhs_dim, rhs_dim, equation_str)
                
                inconsistency = DimensionalInconsistency(
                    equation=equation_str,
                    lhs_dimension=lhs_dim,
                    rhs_dimension=rhs_dim,
                    location="equation",
                    severity="high",
                    suggestion=suggestion
                )
                inconsistencies.append(inconsistency)
            
        except Exception as e:
            handle_error(e)
            inconsistency = DimensionalInconsistency(
                equation=equation_str,
                lhs_dimension=DimensionalVector(),
                rhs_dimension=DimensionalVector(),
                location="parsing",
                severity="critical",
                suggestion=f"Failed to parse equation: {str(e)}"
            )
            inconsistencies.append(inconsistency)
        
        return inconsistencies

    def _generate_suggestion(self, lhs_dim: DimensionalVector, rhs_dim: DimensionalVector, equation: str) -> str:
        """Generate suggestion for fixing dimensional inconsistency."""
        diff = lhs_dim - rhs_dim
        
        suggestions = []
        
        # Analyze the difference
        if abs(diff.length) > 1e-10:
            if diff.length > 0:
                suggestions.append(f"RHS needs length factor with dimension L^{diff.length}")
            else:
                suggestions.append(f"RHS has extra length factor L^{-diff.length}")
        
        if abs(diff.mass) > 1e-10:
            if diff.mass > 0:
                suggestions.append(f"RHS needs mass factor with dimension M^{diff.mass}")
            else:
                suggestions.append(f"RHS has extra mass factor M^{-diff.mass}")
        
        if abs(diff.time) > 1e-10:
            if diff.time > 0:
                suggestions.append(f"RHS needs time factor with dimension T^{diff.time}")
            else:
                suggestions.append(f"RHS has extra time factor T^{-diff.time}")
        
        if suggestions:
            return "Dimensional mismatch. " + "; ".join(suggestions)
        else:
            return "Check variable definitions and unit consistency"

    def suggest_corrections(self, inconsistencies: List[DimensionalInconsistency]) -> List[str]:
        """Generate correction suggestions for dimensional inconsistencies."""
        corrections = []
        
        for inc in inconsistencies:
            if inc.severity == "critical":
                corrections.append(f"CRITICAL: {inc.suggestion}")
            elif inc.severity == "high":
                corrections.append(f"ERROR: {inc.suggestion}")
            else:
                corrections.append(f"WARNING: {inc.suggestion}")
        
        return corrections

    def validate_equation_set(self, equations: List[str]) -> Dict[str, List[DimensionalInconsistency]]:
        """Validate dimensional consistency of multiple equations."""
        results = {}
        
        for i, equation in enumerate(equations):
            equation_id = f"eq_{i+1}"
            inconsistencies = self.check_dimensional_consistency(equation)
            results[equation_id] = inconsistencies
        
        return results

    def extract_units(self, expression_str: str) -> Dict[str, str]:
        """Extract SI units from expression variables."""
        # TODO: Implement unit extraction from variable names and context
        units = {}
        
        try:
            expr = sp.sympify(expression_str)
            symbols = self.extract_symbols(expr)
            
            for symbol in symbols:
                dim = self.infer_dimensions(symbol)
                units[str(symbol)] = self._dimension_to_si_unit(dim)
                
        except Exception as e:
            handle_error(e)
            logger.error(f"Failed to extract units from: {expression_str}")
        
        return units

    def _dimension_to_si_unit(self, dim: DimensionalVector) -> str:
        """Convert dimensional vector to SI unit string."""
        unit_parts = []
        
        base_units = [
            ("m", dim.length),
            ("kg", dim.mass),
            ("s", dim.time),
            ("A", dim.current),
            ("K", dim.temperature),
            ("mol", dim.amount),
            ("cd", dim.luminosity)
        ]
        
        for unit, power in base_units:
            if abs(power) > 1e-10:
                if abs(power - 1) < 1e-10:
                    unit_parts.append(unit)
                elif abs(power + 1) < 1e-10:
                    unit_parts.append(f"{unit}⁻¹")
                else:
                    unit_parts.append(f"{unit}^{power}")
        
        return " ".join(unit_parts) if unit_parts else "dimensionless"

    async def analyze_concept(self, *args, **kwargs):
        return dict()

    async def analyze_equation(self, *args, **kwargs):
        return dict()

    async def analyze_expression(self, *args, **kwargs):
        return dict()

    async def check_equation(self, *args, **kwargs):
        return dict()

    async def compare_theories(self, *args, **kwargs):
        return dict()


class DimensionalFirewall:
    """Main dimensional analysis interface - the 'firewall' that catches dimensional errors."""
    
    def __init__(self, **kwargs):
        """Initialize dimensional firewall."""
        self.analyzer = DimensionalAnalyzer()
        
    async def analyze_equation(self, equation: str) -> Dict:
        """Analyze single equation for dimensional consistency."""
        try:
            inconsistencies = self.analyzer.check_dimensional_consistency(equation)
            suggestions = self.analyzer.suggest_corrections(inconsistencies)
            
            return {
                'equation': equation,
                'is_consistent': len(inconsistencies) == 0,
                'inconsistencies': [
                    {
                        'lhs_dimension': inc.lhs_dimension.to_string(),
                        'rhs_dimension': inc.rhs_dimension.to_string(),
                        'severity': inc.severity,
                        'suggestion': inc.suggestion
                    }
                    for inc in inconsistencies
                ],
                'corrections': suggestions,
                'units': self.analyzer.extract_units(equation)
            }
            
        except Exception as e:
            handle_error(e)
            return {
                'equation': equation,
                'is_consistent': False,
                'error': str(e),
                'inconsistencies': [],
                'corrections': ['Failed to analyze equation'],
                'units': {}
            }

    async def analyze_system(self, equations: List[str]) -> Dict:
        """Analyze system of equations for dimensional consistency."""
        try:
            results = self.analyzer.validate_equation_set(equations)
            
            total_inconsistencies = sum(len(incs) for incs in results.values())
            
            return {
                'equations': equations,
                'total_equations': len(equations),
                'is_system_consistent': total_inconsistencies == 0,
                'total_inconsistencies': total_inconsistencies,
                'equation_results': {
                    eq_id: {
                        'is_consistent': len(incs) == 0,
                        'inconsistency_count': len(incs),
                        'inconsistencies': [
                            {
                                'lhs_dimension': inc.lhs_dimension.to_string(),
                                'rhs_dimension': inc.rhs_dimension.to_string(),
                                'severity': inc.severity,
                                'suggestion': inc.suggestion
                            }
                            for inc in incs
                        ]
                    }
                    for eq_id, incs in results.items()
                },
                'overall_corrections': self._generate_system_corrections(results)
            }
            
        except Exception as e:
            handle_error(e)
            return {
                'equations': equations,
                'is_system_consistent': False,
                'error': str(e),
                'equation_results': {},
                'overall_corrections': ['Failed to analyze equation system']
            }

    def _generate_system_corrections(self, results: Dict[str, List[DimensionalInconsistency]]) -> List[str]:
        """Generate overall corrections for equation system."""
        corrections = []
        
        total_critical = 0
        total_high = 0
        total_inconsistencies = 0
        
        for eq_id, inconsistencies in results.items():
            total_inconsistencies += len(inconsistencies)
            for inc in inconsistencies:
                if inc.severity == "critical":
                    total_critical += 1
                elif inc.severity == "high":
                    total_high += 1
        
        if total_critical > 0:
            corrections.append(f"System has {total_critical} critical parsing errors that must be fixed first")
        
        if total_high > 0:
            corrections.append(f"System has {total_high} dimensional inconsistencies requiring correction")
        
        if total_inconsistencies == 0:
            corrections.append("All equations are dimensionally consistent")
        else:
            corrections.append(f"Review individual equation corrections to fix {total_inconsistencies} total issues")
        
        return corrections

    async def check_expression_dimensions(self, expression: str) -> Dict:
        """Check dimensions of a single expression."""
        try:
            expr = sp.sympify(expression)
            dimensions = self.analyzer.compute_expression_dimensions(expr)
            units = self.analyzer.extract_units(expression)
            
            return {
                'expression': expression,
                'dimensions': dimensions.to_string(),
                'si_units': self.analyzer._dimension_to_si_unit(dimensions),
                'is_dimensionless': dimensions.is_dimensionless(),
                'variable_units': units
            }
            
        except Exception as e:
            handle_error(e)
            return {
                'expression': expression,
                'error': str(e),
                'dimensions': 'unknown',
                'si_units': 'unknown',
                'is_dimensionless': False,
                'variable_units': {}
            }
AMOUNT = type('AMOUNT', (), {})  # auto-stub: not found in project

CURRENT = type('CURRENT', (), {})  # auto-stub: not found in project

LENGTH = type('LENGTH', (), {})  # auto-stub: not found in project

LUMINOSITY = type('LUMINOSITY', (), {})  # auto-stub: not found in project

MASS = type('MASS', (), {})  # auto-stub: not found in project

TEMPERATURE = type('TEMPERATURE', (), {})  # auto-stub: not found in project

TIME = type('TIME', (), {})  # auto-stub: not found in project
