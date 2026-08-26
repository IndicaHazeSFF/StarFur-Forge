"""Bounded Core-authored provenance for one untrusted adventure generation.

The value object deliberately stores identifiers and configuration labels only.
It never retains a prompt, provider response, hidden context, or chain of
thought.  It may travel with an explicitly selected candidate; it has no write
authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


_GENERATION_ID_PATTERN = re.compile(r"^TG-[0-9a-f]{32}$")
_TASK_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TRANSCRIPT_RECORD_ID_PATTERN = re.compile(r"^AT-[0-9]{6}$")
# ``TC`` identifies ordinary narrative candidates; ``TM`` identifies the
# deliberately separate typed-mutation candidate channel.  Both are opaque
# Core-assigned review handles, never model-authored authority.
_CANDIDATE_ID_PATTERN = re.compile(r"^T[CM]-[0-9]{3}$")
_MAX_LABEL_LENGTH = 160


@dataclass(frozen=True)
class AdventureTurnGenerationProvenance:
    """Small audit metadata captured by Core before a provider request."""

    generation_id: str
    task_id: str
    provider_name: str
    model_name: str | None
    origin_event_count: int
    source_record_ids: tuple[str, ...] = ()
    candidate_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.generation_id, str) or not _GENERATION_ID_PATTERN.fullmatch(self.generation_id):
            raise ValueError("generation provenance identifier is invalid")
        if not isinstance(self.task_id, str) or not _TASK_ID_PATTERN.fullmatch(self.task_id):
            raise ValueError("generation provenance task identifier is invalid")
        for field_name in ("provider_name", "model_name"):
            value = getattr(self, field_name)
            if value is None and field_name == "model_name":
                continue
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_LABEL_LENGTH:
                raise ValueError(f"generation provenance {field_name} is invalid")
            object.__setattr__(self, field_name, value.strip())
        if isinstance(self.origin_event_count, bool) or not isinstance(self.origin_event_count, int) or self.origin_event_count < 0:
            raise ValueError("generation provenance origin event count is invalid")
        if not isinstance(self.source_record_ids, tuple) or not all(
            isinstance(record_id, str) and _TRANSCRIPT_RECORD_ID_PATTERN.fullmatch(record_id)
            for record_id in self.source_record_ids
        ):
            raise ValueError("generation provenance transcript identifiers are invalid")
        if self.candidate_id is not None:
            if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID_PATTERN.fullmatch(self.candidate_id):
                raise ValueError("generation provenance candidate identifier is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "generation_id": self.generation_id,
            "task_id": self.task_id,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "origin_event_count": self.origin_event_count,
            "source_record_ids": list(self.source_record_ids),
            "candidate_id": self.candidate_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureTurnGenerationProvenance":
        fields = {
            "generation_id", "task_id", "provider_name", "model_name",
            "origin_event_count", "source_record_ids", "candidate_id",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("generation provenance fields are invalid")
        if not isinstance(value["source_record_ids"], list):
            raise ValueError("generation provenance transcript identifiers are invalid")
        return cls(
            generation_id=value["generation_id"], task_id=value["task_id"],
            provider_name=value["provider_name"], model_name=value["model_name"],
            origin_event_count=value["origin_event_count"],
            source_record_ids=tuple(value["source_record_ids"]), candidate_id=value["candidate_id"],
        )

    def for_candidate(self, candidate_id: object) -> "AdventureTurnGenerationProvenance":
        """Bind a reviewed exact candidate without changing request provenance."""
        return type(self)(
            self.generation_id, self.task_id, self.provider_name, self.model_name,
            self.origin_event_count, self.source_record_ids, candidate_id,
        )


__all__ = ["AdventureTurnGenerationProvenance"]
