"""Mechanical checks of Regista's ports-and-adapters dependency rule."""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src/regista"

# Which Regista packages each layer may import, besides the standard library.
# Only the composition root (cli.py) and adapters may reach provider formats.
ALLOWED_REGISTA_IMPORTS = {
    "domain": ("regista.domain",),
    "pipeline": ("regista.domain", "regista.pipeline"),
    "detectors": ("regista.domain", "regista.detectors"),
    "templates.py": ("regista.domain",),
    "warehouse": ("regista.domain", "regista.warehouse", "duckdb"),
    "storage": ("regista.pipeline", "regista.storage", "boto3", "botocore", "mypy_boto3_s3"),
    "valuation": ("regista.domain", "regista.valuation", "numpy"),
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Relative imports hide which layer they reach; require absolute ones.
                modules.add("." * node.level + (node.module or ""))
            elif node.module is not None:
                modules.add(node.module)
    return modules


def _is_allowed(module: str, allowed: tuple[str, ...]) -> bool:
    if module == "__future__" or module.split(".")[0] in sys.stdlib_module_names:
        return True
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in allowed)


def _files(layer: str) -> list[Path]:
    path = PACKAGE / layer
    return [path] if path.is_file() else sorted(path.rglob("*.py"))


@pytest.mark.parametrize("layer", sorted(ALLOWED_REGISTA_IMPORTS))
def test_layer_imports_only_the_standard_library_and_allowed_packages(layer: str) -> None:
    files = _files(layer)
    assert files, f"no Python files found for layer {layer!r} under {PACKAGE}"

    violations = {
        f"{path.relative_to(PACKAGE)}: {module}"
        for path in files
        for module in _imported_modules(path)
        if not _is_allowed(module, ALLOWED_REGISTA_IMPORTS[layer])
    }

    assert not violations, f"{layer} must not import adapters or third parties: {violations}"


def test_only_the_warehouse_imports_duckdb() -> None:
    offenders = {
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if path.relative_to(PACKAGE).parts[0] != "warehouse"
        and any(module.split(".")[0] == "duckdb" for module in _imported_modules(path))
    }

    assert not offenders, f"only regista.warehouse may import duckdb: {offenders}"


def test_only_the_storage_package_imports_boto3() -> None:
    offenders = {
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if path.relative_to(PACKAGE).parts[0] != "storage"
        and any(
            module.split(".")[0] in ("boto3", "botocore", "mypy_boto3_s3")
            for module in _imported_modules(path)
        )
    }

    assert not offenders, f"only regista.storage may import boto3: {offenders}"
