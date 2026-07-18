import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = (
    ROOT / "core/domain/security_context.py",
    ROOT / "core/domain/security_policy.py",
    ROOT / "core/security_context_provider.py",
    ROOT / "core/runtime_security_adapter.py",
)
DOMAIN_FILES = PRODUCTION_FILES[:2]


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def test_domain_imports_only_stdlib_and_sibling_domain_contracts():
    for path in DOMAIN_FILES:
        for module in imported_modules(path):
            assert module.split(".")[0] in {
                "__future__",
                "dataclasses",
                "datetime",
                "enum",
                "hmac",
                "json",
                "re",
                "typing",
                "core",
            }
            if module.startswith("core"):
                assert module.startswith("core.domain")


def test_import_direction_is_unidirectional_and_has_no_operational_modules():
    forbidden = {
        "core.api",
        "server",
        "core.feed",
        "core.pipeline_live_pro",
        "core.pipeline_backtest",
        "tools.sim101_preflight",
    }
    for path in PRODUCTION_FILES:
        modules = imported_modules(path)
        assert forbidden.isdisjoint(modules)
    for path in DOMAIN_FILES:
        assert "core.runtime_guard" not in imported_modules(path)


def test_modules_have_no_environment_network_file_logging_or_implicit_clock_calls():
    forbidden_import_roots = {
        "os",
        "dotenv",
        "requests",
        "http",
        "urllib",
        "socket",
        "pathlib",
        "logging",
        "uuid",
        "time",
    }
    forbidden_call_names = {
        "open",
        "print",
        "uuid4",
        "now",
        "utcnow",
        "time",
        "monotonic",
        "dispatch",
        "send_order",
        "place_order",
    }
    for path in PRODUCTION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert forbidden_import_roots.isdisjoint(
            module.split(".")[0] for module in imported_modules(path)
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue
            assert name not in forbidden_call_names


def test_imports_emit_no_stdout_or_stderr():
    statement = (
        "import core.domain.security_context; "
        "import core.domain.security_policy; "
        "import core.security_context_provider; "
        "import core.runtime_security_adapter"
    )
    completed = subprocess.run(
        [sys.executable, "-c", statement],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_no_prohibited_local_evidence_sources_appear_in_production():
    prohibited = (
        "live_trading_approved",
        "enable_trading",
        "trading_account",
        "account_name",
        "load_dotenv",
        "os.environ",
    )
    for path in PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8").lower()
        assert all(item not in source for item in prohibited)
