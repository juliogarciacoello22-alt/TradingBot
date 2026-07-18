import ast
import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


DOMAIN_ROOT = Path(__file__).resolve().parents[1] / "core" / "domain"
DOMAIN_MODULES = (
    "common",
    "errors",
    "identifiers",
    "serialization",
    "security",
    "authorization_documents",
    "data_integrity",
    "recovery",
    "incidents",
    "audit_events",
)


def test_domain_imports_are_stdlib_or_domain_only():
    violations = []
    for path in sorted(DOMAIN_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                root = module.split(".", 1)[0]
                if module == "__future__" or module.startswith("core.domain"):
                    continue
                if root not in sys.stdlib_module_names:
                    violations.append(f"{path.name}: {module}")
    assert violations == []


def test_domain_imports_have_no_output_or_eager_application_imports():
    stdout = io.StringIO()
    stderr = io.StringIO()
    before = set(sys.modules)
    with redirect_stdout(stdout), redirect_stderr(stderr):
        for module in DOMAIN_MODULES:
            importlib.import_module(f"core.domain.{module}")
    imported = set(sys.modules) - before
    forbidden = {
        "core.feed",
        "core.runtime_guard",
        "core.pipeline_live_pro",
        "core.pipeline_backtest",
        "core.timeframe_loader",
        "core.timeframe_builder",
        "requests",
        "dotenv",
    }
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""
    assert imported.isdisjoint(forbidden)


def test_domain_init_is_minimal_and_forbidden_models_do_not_exist():
    init_source = (DOMAIN_ROOT / "__init__.py").read_text(encoding="utf-8")
    init_tree = ast.parse(init_source)
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(init_tree))
    assert not (DOMAIN_ROOT.parent / "security_models.py").exists()


def test_runtime_guard_models_are_not_duplicated():
    for module_name in DOMAIN_MODULES:
        module = importlib.import_module(f"core.domain.{module_name}")
        assert not hasattr(module, "ExecutionAuthorization")
        assert not hasattr(module, "RuntimeSafety")
