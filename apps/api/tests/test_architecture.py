import ast
from pathlib import Path


def imports(tree: ast.AST) -> list[str]:
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            result.append(node.module or "")
        elif isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
    return result


def test_domain_and_application_do_not_import_infrastructure() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules"
    prohibited = ("fastapi", "sqlalchemy", "duckdb", "polars", "argon2", "dataflow.bootstrap")
    for file in root.rglob("*.py"):
        relative = file.relative_to(root)
        if file.stem not in {"domain", "application"} and not {
            "domain",
            "application",
        }.intersection(relative.parts):
            continue
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for module in imports(tree):
            assert not module.startswith(prohibited), (file, module)
            assert ".infrastructure" not in module and ".presentation" not in module


def test_cross_module_imports_use_public_contracts() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules"
    for file in root.rglob("*.py"):
        own = file.relative_to(root).parts[0]
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            if module.startswith("dataflow.modules."):
                parts = module.split(".")
                if parts[2] != own:
                    assert len(parts) >= 4 and parts[3] in {"public", "contracts"}, (file, module)


def test_business_module_dependencies_are_acyclic() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules"
    graph: dict[str, set[str]] = {path.name: set() for path in root.iterdir() if path.is_dir()}
    for file in root.rglob("*.py"):
        own = file.relative_to(root).parts[0]
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            if module.startswith("dataflow.modules."):
                target = module.split(".")[2]
                if target != own:
                    graph[own].add(target)
    pending = dict(graph)
    while pending:
        leaves = {
            name for name, dependencies in pending.items() if not dependencies.intersection(pending)
        }
        assert leaves, f"Ciclo entre módulos: {pending}"
        pending = {name: deps for name, deps in pending.items() if name not in leaves}


def test_executions_depends_only_on_ports_not_on_operation_modules() -> None:
    # executions recibe el registro inyectado por bootstrap: no conoce planning ni a los
    # módulos que implementan operaciones (cleaning, quality, ingestion, understanding).
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "executions"
    forbidden = tuple(
        f"dataflow.modules.{name}"
        for name in ["planning", "cleaning", "quality", "ingestion", "understanding"]
    )
    files = list(root.rglob("*.py"))
    assert files
    for file in files:
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(forbidden), (file, module)


def test_planning_does_not_import_operation_implementations() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "planning"
    forbidden = ("polars", "duckdb", "dataflow.modules.ingestion", "dataflow.modules.quality")
    for file in root.rglob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(forbidden), (file, module)
