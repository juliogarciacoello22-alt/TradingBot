import ast
import inspect
from dataclasses import fields
from pathlib import Path

import core.domain.security_context as security_context
import core.domain.security_policy as security_policy
import core.runtime_security_adapter as runtime_security_adapter
import core.security_context_provider as security_context_provider
from core.runtime_guard import ExecutionAuthorization, RuntimeSafety


ROOT = Path(__file__).resolve().parents[1]
NEW_PRODUCTION_FILES = (
    ROOT / "core/domain/security_context.py",
    ROOT / "core/domain/security_policy.py",
    ROOT / "core/security_context_provider.py",
    ROOT / "core/runtime_security_adapter.py",
)


def test_domain_does_not_import_or_redefine_legacy_runtime_models():
    assert ExecutionAuthorization.__module__ == "core.runtime_guard"
    assert RuntimeSafety.__module__ == "core.runtime_guard"
    for module in (security_context, security_policy):
        assert not hasattr(module, "ExecutionAuthorization")
        assert not hasattr(module, "RuntimeSafety")


def test_security_policy_decision_is_not_an_operational_authorization():
    field_names = {item.name for item in fields(security_policy.SecurityPolicyDecision)}
    assert "allowed" not in field_names
    assert "authorized" not in field_names
    assert not hasattr(security_policy.SecurityPolicyDecision, "dispatch")


def test_no_dispatch_order_or_authorize_functions_are_introduced():
    prohibited_fragments = ("dispatch", "send_order", "place_order", "authorize_execution")
    for module in (
        security_context,
        security_policy,
        security_context_provider,
        runtime_security_adapter,
    ):
        functions = {
            name.lower()
            for name, value in inspect.getmembers(module, inspect.isfunction)
            if value.__module__ == module.__name__
        }
        assert all(
            fragment not in name
            for name in functions
            for fragment in prohibited_fragments
        )


def test_new_modules_contain_no_calls_into_operational_routing():
    prohibited_attributes = {
        "dispatch",
        "send_order",
        "place_order",
        "evaluate_signal_permission",
        "sync_api_runtime_mode",
    }
    for path in NEW_PRODUCTION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert called.isdisjoint(prohibited_attributes)


def test_frozen_runtime_modules_do_not_import_phase1c_b_modules():
    for relative in ("core/runtime_guard.py", "core/api.py", "server.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "security_context" not in source
        assert "security_policy" not in source
        assert "runtime_security_adapter" not in source
