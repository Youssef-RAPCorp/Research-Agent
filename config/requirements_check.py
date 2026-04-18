"""Runtime dependency checker for Physics Discovery System v3.0."""

import asyncio
import importlib
import pkg_resources
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
# [auto-removed unresolvable import] from packaging import version
import toml
import numpy as np


@dataclass
class DependencySpec:
    """Specification for a required dependency."""
    name: str
    min_version: Optional[str] = None
    max_version: Optional[str] = None
    extras: List[str] = field(default_factory=list)
    optional: bool = False
    conflicts_with: List[str] = field(default_factory=list)
    install_command: Optional[str] = None


@dataclass
class CheckResult:
    """Result of dependency checking."""
    package: str
    installed: bool
    version: Optional[str] = None
    satisfied: bool = False
    conflicts: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


class RequirementsChecker:
    """Runtime dependency validation and conflict detection."""
    
    def __init__(self,      config_path: Optional[Path] = None, **kwargs):
        """Initialize checker with optional configuration file."""
        self.config_path = config_path or Path("pyproject.toml")
        self.dependencies: Dict[str, DependencySpec] = {}
        self.installed_packages: Dict[str, str] = {}
        self._load_dependencies()
        
    def _load_dependencies(self) -> None:
        """Load dependency specifications from configuration."""
        if self.config_path.exists():
            config = toml.load(self.config_path)
            deps = config.get("tool", {}).get("physics_discovery", {}).get("dependencies", {})
            
            for name, spec in deps.items():
                if isinstance(spec, str):
                    self.dependencies[name] = DependencySpec(name=name, min_version=spec)
                else:
                    self.dependencies[name] = DependencySpec(
                        name=name,
                        min_version=spec.get("min_version"),
                        max_version=spec.get("max_version"),
                        extras=spec.get("extras", []),
                        optional=spec.get("optional", False),
                        conflicts_with=spec.get("conflicts_with", []),
                        install_command=spec.get("install_command")
                    )
        
        # Add critical system dependencies
        self._add_core_dependencies()
    
    def _add_core_dependencies(self) -> None:
        """Add core dependencies required by the physics discovery system."""
        core_deps = {
            "numpy": DependencySpec("numpy", "1.21.0", "2.0.0"),
            "scipy": DependencySpec("scipy", "1.7.0"),
            "matplotlib": DependencySpec("matplotlib", "3.4.0"),
            "pandas": DependencySpec("pandas", "1.3.0"),
            "sympy": DependencySpec("sympy", "1.8"),
            "torch": DependencySpec("torch", "1.11.0"),
            "transformers": DependencySpec("transformers", "4.20.0"),
            "langchain": DependencySpec("langchain", "0.1.0"),
            "asyncio": DependencySpec("asyncio", optional=True),
            "aiohttp": DependencySpec("aiohttp", "3.8.0"),
            "pydantic": DependencySpec("pydantic", "2.0.0"),
            "fastapi": DependencySpec("fastapi", "0.100.0"),
            "uvicorn": DependencySpec("uvicorn", "0.20.0"),
            "pytest": DependencySpec("pytest", "7.0.0", optional=True),
            "black": DependencySpec("black", "22.0.0", optional=True),
            "mypy": DependencySpec("mypy", "1.0.0", optional=True)
        }
        
        for name, spec in core_deps.items():
            if name not in self.dependencies:
                self.dependencies[name] = spec
    
    async def check_all_dependencies(self) -> List[CheckResult]:
        """Check all registered dependencies asynchronously."""
        await self._refresh_installed_packages()
        
        tasks = [
            self._check_single_dependency(spec)
            for spec in self.dependencies.values()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [
            result for result in results 
            if isinstance(result, CheckResult)
        ]
    
    async def _refresh_installed_packages(self) -> None:
        """Refresh cache of installed packages."""
        loop = asyncio.get_event_loop()
        
        def get_installed():
            packages = {}
            for dist in pkg_resources.working_set:
                packages[dist.project_name.lower()] = dist.version
            return packages
        
        self.installed_packages = await loop.run_in_executor(None, get_installed)
    
    async def _check_single_dependency(self, spec: DependencySpec) -> CheckResult:
        """Check a single dependency specification."""
        result = CheckResult(package=spec.name, installed=False)
        
        # Check if package is installed
        package_name = spec.name.lower()
        if package_name not in self.installed_packages:
            if not spec.optional:
                result.error_message = f"Required package '{spec.name}' not installed"
            return result
        
        result.installed = True
        result.version = self.installed_packages[package_name]
        
        # Check version constraints
        if not await self._check_version_constraints(spec, result.version):
            result.error_message = f"Version {result.version} does not satisfy constraints"
            return result
        
        # Check conflicts
        conflicts = await self._check_conflicts(spec)
        if conflicts:
            result.conflicts = conflicts
            result.error_message = f"Conflicts detected with: {', '.join(conflicts)}"
            return result
        
        result.satisfied = True
        return result
    
    async def _check_version_constraints(self, spec: DependencySpec, installed_version: str) -> bool:
        """Check if installed version satisfies constraints."""
        try:
            ver = version.parse(installed_version)
            
            if spec.min_version:
                min_ver = version.parse(spec.min_version)
                if ver < min_ver:
                    return False
            
            if spec.max_version:
                max_ver = version.parse(spec.max_version)
                if ver >= max_ver:
                    return False
            
            return True
        except Exception:
            return False
    
    async def _check_conflicts(self, spec: DependencySpec) -> List[str]:
        """Check for package conflicts."""
        conflicts = []
        
        for conflict_package in spec.conflicts_with:
            if conflict_package.lower() in self.installed_packages:
                conflicts.append(conflict_package)
        
        return conflicts
    
    async def install_missing_dependencies(self, results: List[CheckResult]) -> bool:
        """Install missing dependencies automatically."""
        missing = [
            result for result in results 
            if not result.installed and not self.dependencies[result.package].optional
        ]
        
        if not missing:
            return True
        
        for result in missing:
            spec = self.dependencies[result.package]
            success = await self._install_package(spec)
            if not success:
                return False
        
        return True
    
    async def _install_package(self, spec: DependencySpec) -> bool:
        """Install a single package."""
        loop = asyncio.get_event_loop()
        
        def install():
            try:
                cmd = spec.install_command or f"pip install {spec.name}"
                if spec.min_version:
                    cmd += f">={spec.min_version}"
                if spec.max_version:
                    cmd += f"<{spec.max_version}"
                
                result = subprocess.run(
                    cmd.split(),
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0
            except Exception:
                return False
        
        return await loop.run_in_executor(None, install)
    
    def validate_python_version(self) -> bool:
        """Validate Python version requirements."""
        current = sys.version_info
        
        if current < (3, 8):
            warnings.warn("Python 3.8+ required for full functionality")
            return False
        
        if current >= (3, 12):
            warnings.warn("Python 3.12+ not fully tested")
        
        return True
    
    def generate_requirements_file(self, output_path: Path = Path("requirements.txt")) -> None:
        """Generate requirements.txt file from specifications."""
        lines = []
        
        for spec in self.dependencies.values():
            if spec.optional:
                continue
            
            line = spec.name
            if spec.min_version and spec.max_version:
                line += f">={spec.min_version},<{spec.max_version}"
            elif spec.min_version:
                line += f">={spec.min_version}"
            elif spec.max_version:
                line += f"<{spec.max_version}"
            
            if spec.extras:
                extras = ",".join(spec.extras)
                line = line.replace(spec.name, f"{spec.name}[{extras}]")
            
            lines.append(line)
        
        output_path.write_text("\n".join(sorted(lines)) + "\n")
    
    def check_security_vulnerabilities(self) -> List[str]:
        """Check for known security vulnerabilities in dependencies."""
        # TODO: Integrate with safety or pip-audit for vulnerability scanning
        vulnerabilities = []
        
        # Basic checks for known problematic versions
        problematic = {
            "pillow": ["<8.3.2"],  # CVE-2021-34552
            "pyyaml": ["<5.4"],    # CVE-2020-14343
            "requests": ["<2.25.0"] # Various CVEs
        }
        
        for package, vulnerable_versions in problematic.items():
            if package in self.installed_packages:
                current_ver = version.parse(self.installed_packages[package])
                
                for vuln_spec in vulnerable_versions:
                    if vuln_spec.startswith("<"):
                        max_ver = version.parse(vuln_spec[1:])
                        if current_ver < max_ver:
                            vulnerabilities.append(f"{package} {current_ver} has known vulnerabilities")
        
        return vulnerabilities
    
    async def health_check(self) -> Dict[str, Union[bool, List[str]]]:
        """Comprehensive health check of all dependencies."""
        results = await self.check_all_dependencies()
        
        failed = [r for r in results if not r.satisfied]
        conflicts = [r for r in results if r.conflicts]
        vulnerabilities = self.check_security_vulnerabilities()
        
        return {
            "python_version_ok": self.validate_python_version(),
            "all_dependencies_satisfied": len(failed) == 0,
            "no_conflicts": len(conflicts) == 0,
            "no_vulnerabilities": len(vulnerabilities) == 0,
            "failed_dependencies": [r.package for r in failed],
            "conflicted_dependencies": [r.package for r in conflicts],
            "vulnerabilities": vulnerabilities
        }


async def main():
    """Main entry point for dependency checking."""
    checker = RequirementsChecker()
    
    health = await checker.health_check()
    
    if not health["all_dependencies_satisfied"]:
        print("Installing missing dependencies...")
        results = await checker.check_all_dependencies()
        await checker.install_missing_dependencies(results)
        
        # Re-check after installation
        health = await checker.health_check()
    
    if health["all_dependencies_satisfied"]:
        print("✓ All dependencies satisfied")
    else:
        print("✗ Dependency issues remain:")
        for issue in ["failed_dependencies", "conflicted_dependencies", "vulnerabilities"]:
            if health[issue]:
                print(f"  {issue}: {health[issue]}")


if __name__ == "__main__":
    asyncio.run(main())