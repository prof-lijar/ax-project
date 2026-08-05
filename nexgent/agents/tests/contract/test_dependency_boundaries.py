"""Static checks for the repository's inward dependency direction."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _forbidden_imports(source_root: Path, forbidden_roots: set[str]) -> list[str]:
    violations: list[str] = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", maxsplit=1)[0] in forbidden_roots:
                    relative_path = path.relative_to(ROOT)
                    violations.append(f"{relative_path}:{node.lineno} imports {name}")
    return violations


def test_shared_packages_do_not_depend_on_apps_or_workflows() -> None:
    assert _forbidden_imports(ROOT / "packages", {"apps", "workflows"}) == []


def test_workflows_do_not_depend_on_apps() -> None:
    assert _forbidden_imports(ROOT / "workflows", {"apps"}) == []
