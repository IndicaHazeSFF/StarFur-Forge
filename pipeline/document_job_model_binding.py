"""Pure declared identity equality; not artifact verification or fresh proof."""
from dataclasses import dataclass, field
import re

from pipeline.document_job_model import DeclaredLocalModel
from pipeline.document_job_model_request import ModelListingRequest


class ModelListingBindingError(ValueError):
    """Content-free declaration binding refusal."""


@dataclass(frozen=True, repr=False, init=False)
class BoundModelDeclaration:
    """Untrusted declaration bound to one exact request and expected digest.

    Trusted assembly must obtain the expected digest independently; equality
    does not verify bytes, locality, freshness, cloud policy or private consent.
    """
    request_fingerprint: str = field(repr=False)
    declaration: DeclaredLocalModel = field(repr=False)

    def __init__(self, request, declaration, expected_digest):
        if (type(request) is not ModelListingRequest or type(declaration) is not DeclaredLocalModel
                or type(expected_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
                or declaration.model != request.model or declaration.digest != expected_digest):
            raise ModelListingBindingError("model listing binding is invalid")
        object.__setattr__(self, "request_fingerprint", request.fingerprint)
        object.__setattr__(self, "declaration", declaration)
