"""Internal per-attempt annotation runtime restrictions, not provider authority.

No persistence, readiness claim, provider construction, disclosure permission,
public controls or authentication. A binding must be freshly captured by Core
on an explicit attempt; it does not attest the model bytes behind a label.
"""

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Callable

from pipeline.task_profiles import (
    TASK_DOCUMENT_ANNOTATION, TASK_DOCUMENT_ANNOTATION_FALLBACK, TaskProfile, TaskProfiles,
)
from pipeline.task_routing import normalize_provider_id


class AnnotationJobRuntimeError(ValueError):
    """Closed binding failure with no model/config/provider content."""

    def __init__(self):
        super().__init__("annotation job runtime binding is invalid or changed")


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

    def __post_init__(self):
        if not callable(self._invoke):
            raise AnnotationJobRuntimeError()

    def annotate_document_chunk(self, document, chunk_id):
        return self._invoke(document, chunk_id)
