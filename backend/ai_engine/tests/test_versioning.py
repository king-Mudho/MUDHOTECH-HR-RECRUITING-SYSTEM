import pytest
from pydantic import ValidationError

from ai_engine.contracts import EvidenceStatus, SourceRef
from ai_engine.versioning import ENGINE_VERSION, input_hash


def test_input_hash_is_order_independent() -> None:
    assert input_hash({"a": 1, "b": [1, 2]}) == input_hash({"b": [1, 2], "a": 1})
    assert input_hash({"a": 1}) != input_hash({"a": 2})


def test_engine_version_semver() -> None:
    assert len(ENGINE_VERSION.split(".")) == 3


def test_contracts_are_strict_and_frozen() -> None:
    ref = SourceRef(document_id="d1", page=2, snippet=" Python ")
    assert ref.snippet == "Python"
    with pytest.raises(ValidationError):
        SourceRef(unknown="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ref.page = 3  # type: ignore[misc]
    assert EvidenceStatus.MISSING == "missing"
