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
        for name in ["planning", "cleaning", "quality", "ingestion", "understanding", "analytics"]
    )
    files = list(root.rglob("*.py"))
    assert files
    for file in files:
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(forbidden), (file, module)


def test_planning_does_not_import_operation_implementations() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "planning"
    forbidden = (
        "polars",
        "duckdb",
        "dataflow.modules.ingestion",
        "dataflow.modules.quality",
        "dataflow.modules.analytics",
    )
    for file in root.rglob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(forbidden), (file, module)


def test_cleaning_compute_path_has_no_database_access() -> None:
    # El subproceso de limpieza (y lo que importa) no abre conexiones: sólo Polars y contratos.
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "cleaning"
    forbidden = (
        "sqlalchemy",
        "fastapi",
        "dataflow.bootstrap",
        "dataflow.platform.database",
        "dataflow.modules.cleaning.repository",
    )
    for name in [
        "infrastructure.py",
        "engine.py",
        "processor.py",
        "domain.py",
        "contracts.py",
        "proposal.py",
    ]:
        for module in imports(ast.parse((root / name).read_text(encoding="utf-8"))):
            assert not module.startswith(forbidden), (name, module)


def test_analytics_compute_path_has_no_database_access() -> None:
    # El subproceso de analytics.query@1 (y lo que importa) no abre conexiones.
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "analytics"
    forbidden = (
        "sqlalchemy",
        "fastapi",
        "dataflow.bootstrap",
        "dataflow.platform.database",
        "dataflow.modules.analytics.infrastructure",
    )
    for name in ["engine.py", "processor.py", "domain.py", "contracts.py"]:
        for module in imports(ast.parse((root / name).read_text(encoding="utf-8"))):
            assert not module.startswith(forbidden), (name, module)


def test_dashboards_depend_only_on_their_ports() -> None:
    # Un dashboard no calcula ni planifica: bootstrap le da planes, ejecuciones y versiones.
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "dashboards"
    files = list(root.rglob("*.py"))
    assert files
    for file in files:
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            if module.startswith("dataflow.modules.") and not module.startswith(
                "dataflow.modules.dashboards"
            ):
                assert module == "dataflow.modules.audit.public", (file, module)
            assert not module.startswith(("polars", "duckdb")), (file, module)


def test_retired_policy_pipeline_does_not_come_back() -> None:
    # Fase 13 (ADR-026): un solo recorrido automático, sin políticas, mapeos ni sesión de análisis.
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow"
    for name in ["automation", "templates", "analysis_sessions"]:
        assert not (root / "modules" / name).exists(), name
    for file in root.rglob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(
                (
                    "dataflow.modules.automation",
                    "dataflow.modules.templates",
                    "dataflow.modules.analysis_sessions",
                )
            ), (file, module)


def test_context_detection_is_pure() -> None:
    # La detección de contextos corre en el subproceso de ingesta: sin BD, Polars ni otros módulos.
    file = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "dataflow"
        / "modules"
        / "understanding"
        / "templates.py"
    )
    for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
        assert not module.startswith(("dataflow", "polars", "duckdb", "sqlalchemy")), module


def test_copilot_depends_only_on_its_ports_and_the_ai_port() -> None:
    # El copiloto no planifica, no calcula ni conoce al proveedor: bootstrap le da planes,
    # métricas y resultados, y el puerto AIProvider le da la salida estructurada.
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "copilot"
    files = list(root.rglob("*.py"))
    assert files
    for file in files:
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            if module.startswith("dataflow.modules.") and not module.startswith(
                "dataflow.modules.copilot"
            ):
                assert module == "dataflow.modules.audit.public", (file, module)
            assert not module.startswith(
                ("polars", "duckdb", "anthropic", "dataflow.integrations.ai.anthropic_provider")
            ), (file, module)


def test_ai_provider_sdk_lives_only_in_its_adapter() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "dataflow"
    adapter = src / "integrations" / "ai" / "anthropic_provider.py"
    for file in src.rglob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            if module == "anthropic" or module.startswith("anthropic."):
                assert file == adapter, (file, module)
    for file in (src / "integrations").rglob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(("dataflow.modules", "dataflow.bootstrap")), (
                file,
                module,
            )


def test_dashboards_and_reports_only_keep_their_tables() -> None:
    # Fase 13 (ADR-026): sin servicio ni HTTP; sus tablas y datos se conservan como historia.
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules"
    for name in ["dashboards", "reports"]:
        files = {file.name for file in (root / name).glob("*.py")}
        assert files <= {"__init__.py", "infrastructure.py"}, (name, files)
        source = (root / name / "infrastructure.py").read_text(encoding="utf-8")
        for module in imports(ast.parse(source)):
            assert not module.startswith("dataflow.modules."), (name, module)


def test_source_readers_run_only_in_the_isolated_ingestion_process() -> None:
    """Fase 12: cada lector de fuente se usa sólo desde el subproceso de ingesta y no toca
    la base de datos ni la red."""
    src = Path(__file__).resolve().parents[1] / "src" / "dataflow"
    processor = src / "modules" / "ingestion" / "processor.py"
    for file in src.rglob("*.py"):
        if file.is_relative_to(src / "integrations" / "sources"):
            continue
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            if module.startswith("dataflow.integrations.sources"):
                assert file == processor, (file, module)
    for file in (src / "integrations" / "sources").rglob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(
                ("sqlalchemy", "psycopg", "socket", "urllib", "http", "dataflow.modules")
            ), (file, module)


def test_delivery_only_reorders_published_results() -> None:
    """Fase 17 (ADR-034): la entrega lee contratos publicados; no calcula, no accede a la base
    de datos ni a la IA, y ReportLab sólo se usa en su renderizador."""
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "delivery"
    allowed = {
        "dataflow.modules.analytics.contracts",
        "dataflow.modules.comprehension.contracts",  # Fase 19: entendimiento del negocio
        "dataflow.modules.copilot.contracts",
        "dataflow.modules.curation.contracts",  # Fase 21: valoración de hallazgos
        "dataflow.modules.exploration.contracts",  # Fase 20: exploración guiada
        "dataflow.modules.ingestion.contracts",  # Fase 18: lectura y cambios de estructura
        "dataflow.modules.investigation.contracts",
        "dataflow.modules.quality.contracts",
    }
    for file in root.glob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(
                ("sqlalchemy", "polars", "duckdb", "anthropic", "dataflow.integrations")
            ), (file, module)
            if module.startswith("dataflow.modules.") and not module.startswith(
                "dataflow.modules.delivery"
            ):
                assert module in allowed, (file, module)
            if module.startswith("reportlab"):
                assert file.name == "pdf.py", (file, module)


def test_inspection_diagnoses_without_ai_or_database_in_its_engine() -> None:
    """Fase 22 (ADR-039): la inspección del Dataset la calcula el motor sin IA; su cálculo no
    abre la base de datos y sólo lee contratos de otros módulos."""
    root = Path(__file__).resolve().parents[1] / "src" / "dataflow" / "modules" / "inspection"
    allowed = {
        "dataflow.modules.ingestion.contracts",
        "dataflow.modules.quality.contracts",
        "dataflow.modules.understanding.contracts",
    }
    for file in root.glob("*.py"):
        for module in imports(ast.parse(file.read_text(encoding="utf-8"))):
            assert not module.startswith(("anthropic", "dataflow.integrations")), (file, module)
            if module.startswith("dataflow.modules.") and not module.startswith(
                "dataflow.modules.inspection"
            ):
                assert module in allowed, (file, module)
            if file.name in {"engine.py", "domain.py", "contracts.py"}:
                assert not module.startswith(
                    ("sqlalchemy", "fastapi", "dataflow.platform.database", "dataflow.bootstrap")
                ), (file, module)
