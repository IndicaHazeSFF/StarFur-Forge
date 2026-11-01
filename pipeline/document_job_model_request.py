"""Inert exact metadata request identity, never locality or consent evidence."""

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re

from pipeline.document_job_locality import ANNOTATION_LOCALITY_POLICY, LocalAnnotationTarget
from pipeline.document_job_model import DeclaredLocalModel


class ModelListingRequestError(ValueError):
    """Content-free invalid metadata request."""


@dataclass(frozen=True, repr=False)
class ModelListingRequest:
    """Pure binding of one validated literal endpoint and exact configured name.

    No network, discovery, environment access or private data is involved.
    The fingerprint is equality metadata, not authentication or a capability.
    """

    target: LocalAnnotationTarget = field(repr=False)
    model: str = field(repr=False)

    def __post_init__(self):
        try:
            if type(self.target) is not LocalAnnotationTarget or type(self.model) is not str:
                raise ValueError
            DeclaredLocalModel(self.model, "0" * 64, 1, "gguf")
            if "cloud" in re.split(r"[:/@._+-]", self.model.casefold()):
                raise ValueError
        except ValueError:
            raise ModelListingRequestError("model listing request is invalid") from None

    @property
    def fingerprint(self):
        fields = ["document-job-model-listing-request-v1", ANNOTATION_LOCALITY_POLICY,
                  self.target.fingerprint, self.model]
        return sha256(json.dumps(fields, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()
