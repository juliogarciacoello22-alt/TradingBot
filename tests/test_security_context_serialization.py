import json
import hashlib
from dataclasses import replace

import pytest

from core.domain.security_context import (
    EvidenceReference,
    SecurityContextSerializationError,
    SecurityContextSnapshot,
    SecurityContextValidationError,
    SecurityEvidenceKind,
    UnsupportedSecurityContextVersionError,
)
from tests.test_security_context_domain import HASH_A, HASH_B, make_valid_snapshot


def test_canonical_round_trip_is_byte_and_hash_stable():
    snapshot = make_valid_snapshot()
    assert snapshot.schema_version == 1
    serialized = snapshot.to_json()
    restored = SecurityContextSnapshot.from_json(serialized)
    assert restored == snapshot
    assert restored.to_json() == serialized
    assert restored.context_hash == snapshot.context_hash
    assert snapshot.to_json().encode("utf-8") == snapshot.to_json().encode("utf-8")


def test_reference_input_order_does_not_change_serialization_or_hash():
    references = (
        EvidenceReference(SecurityEvidenceKind.RECOVERY, HASH_B),
        EvidenceReference(SecurityEvidenceKind.AUTHORITY, HASH_A),
    )
    first = make_valid_snapshot(evidence_references=references)
    second = make_valid_snapshot(evidence_references=tuple(reversed(references)))
    assert first.to_json() == second.to_json()
    assert first.context_hash == second.context_hash


def test_content_change_changes_context_hash():
    snapshot = make_valid_snapshot()
    changed = replace(snapshot, generation=snapshot.generation + 1)
    assert changed.context_hash != snapshot.context_hash


@pytest.mark.parametrize("value", (True, "1", 1.0, None))
def test_from_dict_rejects_non_integer_schema_version_with_exact_validation_error(value):
    data = make_valid_snapshot().to_dict()
    data["schema_version"] = value
    with pytest.raises(SecurityContextValidationError) as error:
        SecurityContextSnapshot.from_dict(data)
    assert type(error.value) is SecurityContextValidationError


@pytest.mark.parametrize("value", (0, 2))
def test_from_dict_rejects_unsupported_integer_schema_version_with_exact_error(value):
    data = make_valid_snapshot().to_dict()
    data["schema_version"] = value
    with pytest.raises(UnsupportedSecurityContextVersionError) as error:
        SecurityContextSnapshot.from_dict(data)
    assert type(error.value) is UnsupportedSecurityContextVersionError


@pytest.mark.parametrize("value", (True, "1", 1.0, None))
def test_from_json_rejects_non_integer_schema_version_with_exact_validation_error(value):
    data = make_valid_snapshot().to_dict()
    data["schema_version"] = value
    with pytest.raises(SecurityContextValidationError) as error:
        SecurityContextSnapshot.from_json(json.dumps(data))
    assert type(error.value) is SecurityContextValidationError


@pytest.mark.parametrize("value", (0, 2))
def test_from_json_rejects_unsupported_integer_schema_version_with_exact_error(value):
    data = make_valid_snapshot().to_dict()
    data["schema_version"] = value
    with pytest.raises(UnsupportedSecurityContextVersionError) as error:
        SecurityContextSnapshot.from_json(json.dumps(data))
    assert type(error.value) is UnsupportedSecurityContextVersionError


def test_incorrect_hash_is_rejected_without_repair():
    data = make_valid_snapshot().to_dict()
    data["context_hash"] = "f" * 64
    with pytest.raises(SecurityContextSerializationError, match="hash mismatch"):
        SecurityContextSnapshot.from_dict(data)


def test_unknown_fields_and_duplicate_json_keys_are_rejected():
    data = make_valid_snapshot().to_dict()
    data["unexpected"] = True
    with pytest.raises(SecurityContextSerializationError):
        SecurityContextSnapshot.from_dict(data)
    with pytest.raises(SecurityContextSerializationError):
        SecurityContextSnapshot.from_json('{"schema_version":1,"schema_version":1}')


def test_canonical_json_contains_no_implicit_or_non_json_values():
    payload = json.loads(make_valid_snapshot().to_json())
    assert payload["context_id"] == "context-1"
    assert payload["fencing_token"] == 7
    assert payload["source_identity"]["source_id"] == "source-1"
    assert payload["boot_identity"]["boot_id"] == "boot-1"
    assert payload["boot_identity"]["source_id"] == "source-1"
    assert payload["heartbeat"]["event_id"] == "heartbeat-1"
    assert payload["heartbeat"]["source_id"] == "source-1"
    assert payload["heartbeat"]["boot_id"] == "boot-1"
    assert payload["heartbeat"]["fencing_token"] == 7
    assert payload["lease"]["lease_id"] == "lease-1"
    assert payload["lease"]["fencing_token"] == 7
    assert payload["overall_verification"] == "VERIFIED"
    assert payload["clock"]["observed_at_utc"].endswith("Z")


def test_legacy_identifier_and_fencing_wrappers_are_not_accepted():
    context_data = make_valid_snapshot().to_dict()
    context_data["context_id"] = {"value": "context-1"}
    old_payload = dict(context_data)
    old_payload.pop("context_hash")
    context_data["context_hash"] = hashlib.sha256(
        json.dumps(
            old_payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(SecurityContextSerializationError):
        SecurityContextSnapshot.from_dict(context_data)

    fencing_data = make_valid_snapshot().to_dict()
    fencing_data["fencing_token"] = {"value": 7}
    with pytest.raises(SecurityContextSerializationError):
        SecurityContextSnapshot.from_dict(fencing_data)
