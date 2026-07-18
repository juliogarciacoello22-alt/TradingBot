import inspect
from dataclasses import FrozenInstanceError

import pytest

import core.security_context_provider as provider_module
from core.security_context_provider import (
    ProviderFailure,
    ProviderFailureCode,
    SecurityContextProvider,
    SecurityContextProviderContractError,
    SecurityContextProviderResult,
    SecurityContextRequest,
)
from tests.test_security_context_domain import HASH_A, make_valid_snapshot


def test_provider_is_runtime_checkable_async_protocol_with_explicit_lifecycle():
    assert SecurityContextProvider._is_protocol is True
    assert getattr(SecurityContextProvider, "_is_runtime_protocol", False) is True
    assert inspect.iscoroutinefunction(SecurityContextProvider.get_snapshot)
    assert inspect.iscoroutinefunction(SecurityContextProvider.aclose)
    signature = inspect.signature(SecurityContextProvider.get_snapshot)
    assert tuple(signature.parameters) == ("self", "request", "timeout_seconds")
    assert signature.parameters["timeout_seconds"].kind is inspect.Parameter.KEYWORD_ONLY


def test_provider_module_contains_no_concrete_provider():
    concrete = []
    for _, candidate in inspect.getmembers(provider_module, inspect.isclass):
        if candidate.__module__ != provider_module.__name__:
            continue
        if candidate is SecurityContextProvider:
            continue
        if callable(getattr(candidate, "get_snapshot", None)):
            concrete.append(candidate)
    assert concrete == []


def test_provider_result_requires_exactly_one_atomic_outcome():
    snapshot = make_valid_snapshot()
    failure = ProviderFailure(ProviderFailureCode.TIMEOUT, "deadline", True)
    assert SecurityContextProviderResult.success(snapshot).snapshot is snapshot
    assert SecurityContextProviderResult.failed(failure).failure is failure
    with pytest.raises(SecurityContextProviderContractError):
        SecurityContextProviderResult(None, None)
    with pytest.raises(SecurityContextProviderContractError):
        SecurityContextProviderResult(snapshot, failure)
    with pytest.raises(SecurityContextProviderContractError):
        SecurityContextProviderResult("partial", None)


def test_provider_failure_is_frozen_sanitized_and_deterministic():
    failure = ProviderFailure(
        ProviderFailureCode.HASH_MISMATCH,
        "context-hash-mismatch",
        False,
        (HASH_A, HASH_A.upper()),
    )
    assert failure.evidence_hashes == (HASH_A,)
    assert set(failure.to_dict()) == {
        "code",
        "safe_detail_code",
        "retryable",
        "evidence_hashes",
    }
    with pytest.raises(FrozenInstanceError):
        failure.retryable = True


def test_request_requires_caller_supplied_identity_and_no_generated_values():
    request = SecurityContextRequest("request-external-1", None, None, 0, None)
    assert request.request_id == "request-external-1"
    with pytest.raises(Exception):
        SecurityContextRequest("", None, None, 0, None)
