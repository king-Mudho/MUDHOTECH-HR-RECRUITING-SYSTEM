"""Serializer helpers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class StrictFieldsMixin:
    # Reject unknown input keys instead of silently ignoring them (docs/06 §2, backend rule 5):
    # clients must never sneak ``organisation``, ``status``, ``role`` or ``score`` into a write
    # that does not explicitly accept them. (A comment, not a docstring: drf-spectacular would
    # copy an inherited docstring into every serializer's OpenAPI description.)

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, dict):
            writable = {
                name
                for name, field in self.fields.items()  # type: ignore[attr-defined]
                if not field.read_only
            }
            unknown = sorted(set(data) - writable)
            if unknown:
                raise serializers.ValidationError(
                    {key: ["This field is not allowed."] for key in unknown}
                )
        return super().to_internal_value(data)  # type: ignore[misc]


class StrictSerializer(StrictFieldsMixin, serializers.Serializer):
    pass


class StrictModelSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    pass
