import ast
import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "core" / "domain" / "runtime_policy.py"
DOMAIN_INIT = ROOT / "core" / "domain" / "__init__.py"


def _imported_modules():
    tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"), filename=str(POLICY_PATH))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return modules


def test_runtime_policy_is_stdlib_only():
    violations = []
    for module in _imported_modules():
        root = module.split(".", 1)[0]
        if module == "__future__" or root in sys.stdlib_module_names:
            continue
        violations.append(module)
    assert violations == []


def test_runtime_policy_has_no_forbidden_application_imports():
    forbidden = {
        "core.runtime_guard",
        "core.api",
        "server",
        "core.feed",
        "core.pipeline_live_pro",
        "core.pipeline_backtest",
    }
    assert forbidden.isdisjoint(_imported_modules())


def test_runtime_policy_has_no_environment_or_side_effect_capabilities():
    source = POLICY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(POLICY_PATH))
    forbidden_names = {
        "open",
        "print",
        "logging",
        "requests",
        "socket",
        "environ",
        "getenv",
        "datetime",
        "time",
    }
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert forbidden_names.isdisjoint(used_names | used_attributes)


def test_import_is_silent_and_does_not_pull_application_modules():
    sys.modules.pop("core.domain.runtime_policy", None)
    before = set(sys.modules)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        importlib.import_module("core.domain.runtime_policy")
    imported = set(sys.modules) - before

    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""
    assert imported.isdisjoint(
        {
            "core.runtime_guard",
            "core.api",
            "server",
            "core.feed",
            "core.pipeline_live_pro",
            "core.pipeline_backtest",
        }
    )


def test_domain_init_does_not_eagerly_reexport_runtime_policy():
    tree = ast.parse(DOMAIN_INIT.read_text(encoding="utf-8"), filename=str(DOMAIN_INIT))
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
