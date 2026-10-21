"""The dependency rule: domain code depends on nothing outside the domain, and application code
depends on the domain and on ports, never on frameworks, the database or the web layer."""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

FRAMEWORKS = ("sqlalchemy", "fastapi", "starlette", "pydantic", "httpx", "alembic", "google")
OUTER = (".infrastructure", ".api", ".dev")


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def layer_files(layer: str) -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if layer in p.relative_to(APP).parts)


def _outer(name: str) -> bool:
    return name.startswith("app.") and (any(part in name for part in OUTER) or name.startswith(("app.infrastructure", "app.api")))


@pytest.mark.parametrize("path", layer_files("domain"), ids=lambda p: str(p.relative_to(APP)))
def test_domain_is_independent(path):
    bad = [n for n in imports(path)
           if n.startswith(FRAMEWORKS) or _outer(n) or ".application" in n or n == "app.core.config"]
    assert not bad, f"{path.relative_to(APP)} imports {bad}"


@pytest.mark.parametrize("path", layer_files("application"), ids=lambda p: str(p.relative_to(APP)))
def test_application_depends_only_on_domain_and_ports(path):
    bad = [n for n in imports(path) if n.startswith(FRAMEWORKS) or _outer(n)]
    assert not bad, f"{path.relative_to(APP)} imports {bad}"
