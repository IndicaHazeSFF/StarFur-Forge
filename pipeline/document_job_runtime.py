"""Internal per-attempt annotation runtime restrictions, not provider authority.

No persistence, readiness claim, provider construction, disclosure permission,
public controls or authentication. A binding must be freshly captured by Core
on an explicit attempt; it does not attest the model bytes behind a label.
"""

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Callable

from pipeline.task_profiles import (
    TASK_DOCUMENT_ANNOTATION, TASK_DOCUMENT_ANNOTATION_FALLBACK, TaskProfile, TaskProfiles,
)
from pipeline.task_routing import normalize_provider_id


class AnnotationJobRuntimeError(ValueError):
    """Closed binding failure with no model/config/provider content."""

    def __init__(self):
        super().__init__("annotation job runtime binding is invalid or changed")


def validate_runtime_fingerprint(value):
    """Validate declared equality evidence, not its authenticity or model bytes."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AnnotationJobRuntimeError()
    return value


@dataclass(frozen=True)
class AnnotationRuntimeEvidence:
    """Internal content-free checkpoint coverage, never execution verification."""
    checkpointed_chunks: int
    bound_chunks: int
    distinct_configurations: int

    def __post_init__(self):
        if (any(type(value) is not int for value in (
                self.checkpointed_chunks, self.bound_chunks, self.distinct_configurations))
                or not 0 <= self.distinct_configurations <= self.bound_chunks <= self.checkpointed_chunks <= 100_000
                or (self.bound_chunks > 0) != (self.distinct_configurations > 0)):
            raise AnnotationJobRuntimeError()

    def to_public_dict(self):
        # Internal projection only; no CLI/API/snapshot automatically uses it.
        return {"checkpointed_chunks": self.checkpointed_chunks,
                "bound_chunks": self.bound_chunks,
                "distinct_configurations": self.distinct_configurations,
                "uniform_declared_configuration": self.bound_chunks == self.checkpointed_chunks
                and self.bound_chunks > 0 and self.distinct_configurations == 1}


def annotation_runtime_fingerprint(profiles, *, default_model, provider_id):
    """Commit to both effective annotation profiles, not unrelated task settings.

    Hashes are equality evidence only, never authorization or proof of provider
    readiness. Mutable option mappings are copied/revalidated on each capture.
    """
    try:
        if (type(profiles) is not TaskProfiles or not isinstance(default_model, str)
                or not default_model.strip() or len(default_model) > 256):
            raise ValueError
        provider_id = normalize_provider_id(provider_id)
        primary = profiles.get(TASK_DOCUMENT_ANNOTATION) or TaskProfile(TASK_DOCUMENT_ANNOTATION)
        selected = [primary]
        if primary.fallback_task is not None:
            fallback = profiles.get(TASK_DOCUMENT_ANNOTATION_FALLBACK)
            if (primary.fallback_task != TASK_DOCUMENT_ANNOTATION_FALLBACK or fallback is None
                    or fallback.fallback_task is not None):
                raise ValueError
            selected.append(fallback)
        payload = []
        for profile in selected:
            validated = TaskProfile(**profile.public_dict())
            if validated.provider is not None and normalize_provider_id(validated.provider) != provider_id:
                raise ValueError
            resolved = validated.resolved(default_model=default_model, base_options={})
            if not isinstance(resolved.model, str) or len(resolved.model) > 256:
                raise ValueError
            entry = validated.public_dict()
            entry.update(provider=provider_id, model=resolved.model)
            payload.append(entry)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > 16_384:
            raise ValueError
        return sha256(encoded).hexdigest()
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise AnnotationJobRuntimeError() from None


@dataclass(frozen=True, repr=False, eq=False)
class BoundAnnotationJobRuntime:
    """Trusted in-process adapter; only the application supplies its callback.

    Not a capability token or hostile-plugin boundary. No provider/config
    fields are public or rendered through repr, status, API or the CLI.
    """
    _invoke: Callable = field(repr=False)
    configuration_fingerprint: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if not callable(self._invoke):
            raise AnnotationJobRuntimeError()
        if self.configuration_fingerprint is not None:
            validate_runtime_fingerprint(self.configuration_fingerprint)

    def annotate_document_chunk(self, document, chunk_id):
        return self._invoke(document, chunk_id)
