import numpy as np
import sympy as sp
from typing import List, Dict, Tuple, Optional, Union, Any
from dataclasses import dataclass
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config.logger import get_logger
from config.errors import handle_error

logger = get_logger(__name__)

@dataclass
class TensorIndex:
    """Tensor index with covariant/contravariant specification."""
    name: str
    is_contravariant: bool = True
    position: int = 0

class TensorOperations:
    """Ricci calculus toolkit for general relativity computations."""
    
    def __init__(self,      metric: Optional[sp.Matrix] = None,      coordinates: Optional[List[sp.Symbol]] = None, **kwargs):
        """Initialize with metric tensor and coordinate system."""
        self.metric = metric
        self.coordinates = coordinates or []
        self.christoffel_symbols = None
        self.riemann_tensor = None
        self.ricci_tensor = None
        self.ricci_scalar = None
        self.einstein_tensor = None
        self._cache = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def set_metric(self, metric: sp.Matrix, coordinates: List[sp.Symbol]) -> None:
        """Set the metric tensor and coordinate system."""
        self.metric = metric
        self.coordinates = coordinates
        self._clear_cache()
    
    def _clear_cache(self) -> None:
        """Clear all cached computations."""
        self._cache.clear()
        self.christoffel_symbols = None
        self.riemann_tensor = None
        self.ricci_tensor = None
        self.ricci_scalar = None
        self.einstein_tensor = None
    
    def metric_inverse(self) -> sp.Matrix:
        """Compute inverse metric tensor."""
        if 'metric_inverse' not in self._cache:
            try:
                self._cache['metric_inverse'] = self.metric.inv()
            except Exception as e:
                handle_error(e)
                raise ValueError(f"Cannot invert metric tensor: {e}")
        return self._cache['metric_inverse']
    
    def metric_determinant(self) -> sp.Expr:
        """Compute determinant of metric tensor."""
        if 'metric_det' not in self._cache:
            self._cache['metric_det'] = self.metric.det()
        return self._cache['metric_det']
    
    def christoffel_symbols_first_kind(self) -> sp.Array:
        """Compute Christoffel symbols of the first kind."""
        if 'christoffel_1st' not in self._cache:
            n = len(self.coordinates)
            symbols = sp.Array.zeros(n, n, n)
            
            for i in range(n):
                for j in range(n):
                    for k in range(n):
                        # Γ_{ijk} = (1/2)(∂g_{ik}/∂x^j + ∂g_{jk}/∂x^i - ∂g_{ij}/∂x^k)
                        term1 = sp.diff(self.metric[i, k], self.coordinates[j])
                        term2 = sp.diff(self.metric[j, k], self.coordinates[i])
                        term3 = sp.diff(self.metric[i, j], self.coordinates[k])
                        symbols[i, j, k] = sp.Rational(1, 2) * (term1 + term2 - term3)
            
            self._cache['christoffel_1st'] = symbols
        return self._cache['christoffel_1st']
    
    def christoffel_symbols_second_kind(self) -> sp.Array:
        """Compute Christoffel symbols of the second kind."""
        if self.christoffel_symbols is None:
            n = len(self.coordinates)
            symbols = sp.Array.zeros(n, n, n)
            g_inv = self.metric_inverse()
            christoffel_1st = self.christoffel_symbols_first_kind()
            
            for i in range(n):
                for j in range(n):
                    for k in range(n):
                        # Γ^i_{jk} = g^{il} Γ_{ljk}
                        for l in range(n):
                            symbols[i, j, k] += g_inv[i, l] * christoffel_1st[l, j, k]
            
            self.christoffel_symbols = symbols
        return self.christoffel_symbols
    
    def covariant_derivative(self, tensor: sp.Array, indices: List[TensorIndex]) -> sp.Array:
        """Compute covariant derivative of a tensor."""
        try:
            christoffel = self.christoffel_symbols_second_kind()
            n = len(self.coordinates)
            
            # Start with partial derivative
            result = self._partial_derivative_tensor(tensor, indices)
            
            # Add connection terms for each index
            for idx_pos, tensor_idx in enumerate(indices):
                connection_terms = self._compute_connection_terms(
                    tensor, indices, idx_pos, christoffel, tensor_idx.is_contravariant
                )
                result += connection_terms
            
            return result
        except Exception as e:
            handle_error(e)
            raise ValueError(f"Error computing covariant derivative: {e}")
    
    def _partial_derivative_tensor(self, tensor: sp.Array, indices: List[TensorIndex]) -> sp.Array:
        """Compute partial derivative of tensor with respect to coordinates."""
        n = len(self.coordinates)
        shape = list(tensor.shape) + [n]
        result = sp.Array.zeros(*shape)
        
        # Iterate over all tensor components
        for idx in np.ndindex(tensor.shape):
            for coord_idx in range(n):
                new_idx = idx + (coord_idx,)
                result[new_idx] = sp.diff(tensor[idx], self.coordinates[coord_idx])
        
        return result
    
    def _compute_connection_terms(self, tensor: sp.Array, indices: List[TensorIndex], 
                                 idx_pos: int, christoffel: sp.Array, is_contravariant: bool) -> sp.Array:
        """Compute connection terms for covariant derivative."""
        n = len(self.coordinates)
        shape = list(tensor.shape) + [n]
        connection_terms = sp.Array.zeros(*shape)
        
        sign = 1 if is_contravariant else -1
        
        # Add connection terms
        for idx in np.ndindex(tensor.shape):
            for coord_idx in range(n):
                for dummy_idx in range(n):
                    # Build indices for Christoffel symbol and tensor
                    christoffel_indices = self._build_christoffel_indices(
                        idx, idx_pos, dummy_idx, coord_idx, is_contravariant
                    )
                    tensor_indices = self._build_tensor_indices(idx, idx_pos, dummy_idx)
                    
                    new_idx = idx + (coord_idx,)
                    connection_terms[new_idx] += (
                        sign * christoffel[christoffel_indices] * tensor[tensor_indices]
                    )
        
        return connection_terms
    
    def _build_christoffel_indices(self, idx: Tuple, idx_pos: int, dummy_idx: int, 
                                  coord_idx: int, is_contravariant: bool) -> Tuple:
        """Build indices for Christoffel symbol access."""
        if is_contravariant:
            return (idx[idx_pos], dummy_idx, coord_idx)
        else:
            return (dummy_idx, idx[idx_pos], coord_idx)
    
    def _build_tensor_indices(self, idx: Tuple, idx_pos: int, dummy_idx: int) -> Tuple:
        """Build indices for tensor access with dummy index substitution."""
        tensor_idx = list(idx)
        tensor_idx[idx_pos] = dummy_idx
        return tuple(tensor_idx)
    
    def riemann_curvature_tensor(self) -> sp.Array:
        """Compute Riemann curvature tensor."""
        if self.riemann_tensor is None:
            n = len(self.coordinates)
            riemann = sp.Array.zeros(n, n, n, n)
            christoffel = self.christoffel_symbols_second_kind()
            
            for rho in range(n):
                for sigma in range(n):
                    for mu in range(n):
                        for nu in range(n):
                            # R^ρ_{σμν} = ∂Γ^ρ_{σν}/∂x^μ - ∂Γ^ρ_{σμ}/∂x^ν + Γ^ρ_{λμ}Γ^λ_{σν} - Γ^ρ_{λν}Γ^λ_{σμ}
                            term1 = sp.diff(christoffel[rho, sigma, nu], self.coordinates[mu])
                            term2 = sp.diff(christoffel[rho, sigma, mu], self.coordinates[nu])
                            
                            term3 = sum(
                                christoffel[rho, lam, mu] * christoffel[lam, sigma, nu]
                                for lam in range(n)
                            )
                            term4 = sum(
                                christoffel[rho, lam, nu] * christoffel[lam, sigma, mu]
                                for lam in range(n)
                            )
                            
                            riemann[rho, sigma, mu, nu] = term1 - term2 + term3 - term4
            
            self.riemann_tensor = riemann
        return self.riemann_tensor
    
    def ricci_tensor_compute(self) -> sp.Matrix:
        """Compute Ricci tensor."""
        if self.ricci_tensor is None:
            n = len(self.coordinates)
            ricci = sp.Matrix.zeros(n, n)
            riemann = self.riemann_curvature_tensor()
            
            for mu in range(n):
                for nu in range(n):
                    # R_{μν} = R^ρ_{μρν}
                    ricci[mu, nu] = sum(riemann[rho, mu, rho, nu] for rho in range(n))
            
            self.ricci_tensor = ricci
        return self.ricci_tensor
    
    def ricci_scalar_compute(self) -> sp.Expr:
        """Compute Ricci scalar."""
        if self.ricci_scalar is None:
            g_inv = self.metric_inverse()
            ricci = self.ricci_tensor_compute()
            n = len(self.coordinates)
            
            # R = g^{μν}R_{μν}
            self.ricci_scalar = sum(
                g_inv[mu, nu] * ricci[mu, nu]
                for mu in range(n) for nu in range(n)
            )
        return self.ricci_scalar
    
    def einstein_tensor_compute(self) -> sp.Matrix:
        """Compute Einstein tensor."""
        if self.einstein_tensor is None:
            ricci = self.ricci_tensor_compute()
            ricci_scalar = self.ricci_scalar_compute()
            n = len(self.coordinates)
            
            # G_{μν} = R_{μν} - (1/2)g_{μν}R
            self.einstein_tensor = sp.Matrix.zeros(n, n)
            for mu in range(n):
                for nu in range(n):
                    self.einstein_tensor[mu, nu] = (
                        ricci[mu, nu] - sp.Rational(1, 2) * self.metric[mu, nu] * ricci_scalar
                    )
        return self.einstein_tensor
    
    def einstein_field_equations(self, stress_energy_tensor: sp.Matrix, 
                                cosmological_constant: sp.Expr = 0) -> sp.Matrix:
        """Compute Einstein field equations: G_{μν} + Λg_{μν} = 8πT_{μν}."""
        einstein = self.einstein_tensor_compute()
        n = len(self.coordinates)
        
        lhs = einstein.copy()
        if cosmological_constant != 0:
            for mu in range(n):
                for nu in range(n):
                    lhs[mu, nu] += cosmological_constant * self.metric[mu, nu]
        
        rhs = 8 * sp.pi * stress_energy_tensor
        
        return lhs - rhs  # Return as equations = 0
    
    def raise_index(self, tensor: sp.Array, index_position: int) -> sp.Array:
        """Raise a tensor index using the inverse metric."""
        g_inv = self.metric_inverse()
        n = len(self.coordinates)
        
        # Create new tensor with raised index
        new_shape = list(tensor.shape)
        result = sp.Array.zeros(*new_shape)
        
        for idx in np.ndindex(tensor.shape):
            for raised_idx in range(n):
                # Multiply by inverse metric component
                old_idx = list(idx)
                old_idx[index_position] = raised_idx
                
                for contracted_idx in range(n):
                    contract_idx = list(idx)
                    contract_idx[index_position] = contracted_idx
                    result[tuple(old_idx)] += (
                        g_inv[raised_idx, contracted_idx] * tensor[tuple(contract_idx)]
                    )
        
        return result
    
    def lower_index(self, tensor: sp.Array, index_position: int) -> sp.Array:
        """Lower a tensor index using the metric."""
        n = len(self.coordinates)
        
        # Create new tensor with lowered index
        new_shape = list(tensor.shape)
        result = sp.Array.zeros(*new_shape)
        
        for idx in np.ndindex(tensor.shape):
            for lowered_idx in range(n):
                # Multiply by metric component
                old_idx = list(idx)
                old_idx[index_position] = lowered_idx
                
                for contracted_idx in range(n):
                    contract_idx = list(idx)
                    contract_idx[index_position] = contracted_idx
                    result[tuple(old_idx)] += (
                        self.metric[lowered_idx, contracted_idx] * tensor[tuple(contract_idx)]
                    )
        
        return result
    
    def tensor_contraction(self, tensor: sp.Array, index1: int, index2: int) -> sp.Array:
        """Contract two indices of a tensor."""
        n = len(self.coordinates)
        old_shape = list(tensor.shape)
        new_shape = [s for i, s in enumerate(old_shape) if i not in [index1, index2]]
        
        if not new_shape:
            # Scalar result
            result = 0
            for i in range(n):
                idx = [slice(None)] * len(old_shape)
                idx[index1] = i
                idx[index2] = i
                result += tensor[tuple(idx)]
            return result
        
        result = sp.Array.zeros(*new_shape)
        
        # Sum over contracted indices
        for contracted_val in range(n):
            for idx in np.ndindex(*new_shape):
                # Build full index with contracted indices inserted
                full_idx = list(idx)
                for pos in sorted([index1, index2]):
                    full_idx.insert(pos, contracted_val)
                
                # Map to result index
                result_idx = tuple(idx)
                result[result_idx] += tensor[tuple(full_idx)]
        
        return result
    
    def parallel_transport(self, vector: sp.Matrix, curve_param: sp.Symbol, 
                          curve_coords: List[sp.Expr]) -> sp.Matrix:
        """Parallel transport vector along curve."""
        n = len(self.coordinates)
        christoffel = self.christoffel_symbols_second_kind()
        
        # Parallel transport equation: dV^μ/dλ + Γ^μ_{νρ}(dx^ν/dλ)V^ρ = 0
        transport_eqs = []
        
        for mu in range(n):
            eq = sp.diff(vector[mu], curve_param)
            
            for nu in range(n):
                for rho in range(n):
                    curve_vel = sp.diff(curve_coords[nu], curve_param)
                    connection_term = (
                        christoffel[mu, nu, rho].subs(
                            [(coord, curve_coords[i]) for i, coord in enumerate(self.coordinates)]
                        ) * curve_vel * vector[rho]
                    )
                    eq += connection_term
            
            transport_eqs.append(eq)
        
        return sp.Matrix(transport_eqs)
    
    def geodesic_equations(self) -> List[sp.Expr]:
        """Compute geodesic equations."""
        n = len(self.coordinates)
        christoffel = self.christoffel_symbols_second_kind()
        
        # Parameter for geodesic
        tau = sp.Symbol('tau')
        
        geodesic_eqs = []
        for mu in range(n):
            # d²x^μ/dτ² + Γ^μ_{νρ}(dx^ν/dτ)(dx^ρ/dτ) = 0
            eq = sp.diff(self.coordinates[mu], tau, 2)
            
            for nu in range(n):
                for rho in range(n):
                    vel_nu = sp.diff(self.coordinates[nu], tau)
                    vel_rho = sp.diff(self.coordinates[rho], tau)
                    eq += christoffel[mu, nu, rho] * vel_nu * vel_rho
            
            geodesic_eqs.append(eq)
        
        return geodesic_eqs
    
    def weyl_tensor(self) -> sp.Array:
        """Compute Weyl conformal tensor."""
        n = len(self.coordinates)
        if n != 4:
            raise ValueError("Weyl tensor only defined for 4D spacetime")
        
        riemann = self.riemann_curvature_tensor()
        ricci = self.ricci_tensor_compute()
        ricci_scalar = self.ricci_scalar_compute()
        g_inv = self.metric_inverse()
        
        weyl = sp.Array.zeros(n, n, n, n)
        
        for a in range(n):
            for b in range(n):
                for c in range(n):
                    for d in range(n):
                        # Weyl tensor formula in 4D
                        weyl_component = riemann[a, b, c, d]
                        
                        # Subtract Ricci terms
                        weyl_component -= (
                            sp.Rational(1, 2) * (
                                self.metric[a, c] * ricci[b, d] - 
                                self.metric[a, d] * ricci[b, c] - 
                                self.metric[b, c] * ricci[a, d] + 
                                self.metric[b, d] * ricci[a, c]
                            )
                        )
                        
                        # Add scalar curvature term
                        weyl_component += (
                            sp.Rational(1, 6) * ricci_scalar * (
                                self.metric[a, c] * self.metric[b, d] - 
                                self.metric[a, d] * self.metric[b, c]
                            )
                        )
                        
                        weyl[a, b, c, d] = weyl_component
        
        return weyl
    
    async def compute_curvature_invariants(self) -> Dict[str, sp.Expr]:
        """Compute various curvature invariants."""
        def _compute_invariants():
            invariants = {}
            
            # Ricci scalar
            invariants['ricci_scalar'] = self.ricci_scalar_compute()
            
            # Kretschmann scalar: R_{abcd}R^{abcd}
            riemann = self.riemann_curvature_tensor()
            g_inv = self.metric_inverse()
            n = len(self.coordinates)
            
            kretschmann = 0
            for a in range(n):
                for b in range(n):
                    for c in range(n):
                        for d in range(n):
                            for a_up in range(n):
                                for b_up in range(n):
                                    for c_up in range(n):
                                        for d_up in range(n):
                                            kretschmann += (
                                                riemann[a, b, c, d] * 
                                                g_inv[a, a_up] * g_inv[b, b_up] * 
                                                g_inv[c, c_up] * g_inv[d, d_up] * 
                                                riemann[a_up, b_up, c_up, d_up]
                                            )
            
            invariants['kretschmann_scalar'] = kretschmann
            
            return invariants
        
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self.executor, _compute_invariants)
        except Exception as e:
            handle_error(e)
            raise
    
    def __del__(self):
        """Cleanup executor on deletion."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)