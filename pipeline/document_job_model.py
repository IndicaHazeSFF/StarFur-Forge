"""Pure bounded inspection of an Ollama local-model listing.

This module parses an already-obtained ``/api/tags`` response for one exact
configured model.  It does not fetch the listing, read a model directory,
hash model bytes, inspect a running service, or turn server declarations into
execution/consent authority.  In particular, a digest returned by the server
is a declared identity to bind later evidence, not independently verified
local-artifact proof.
"""

from dataclasses import dataclass, field
import json
import re


MAX_LOCAL_MODEL_LISTING_BYTES = 128 * 1024
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_DETAIL_FIELDS = {"format", "parent_model", "family", "families", "parameter_size", "quantization_level",
                  "context_length", "embedding_length"}


def _details_valid(details):
    if type(details) is not dict or set(details) - _DETAIL_FIELDS or details.get("format") != "gguf":
        return False
    for key, value in details.items():
        if key in {"context_length", "embedding_length"}:
            if type(value) is not int or not 0 <= value <= (1 << 31) - 1:
                return False
        elif key == "families":
            if (type(value) is not list or len(value) > 16
                    or any(type(item) is not str or not item.isascii() or len(item) > 128 for item in value)):
                return False
        elif type(value) is not str or not value.isascii() or len(value) > 128:
            return False
    return True


class LocalModelInspectionError(ValueError):
    """Content-free refusal of an untrusted or nonmatching listing."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError


@dataclass(frozen=True, repr=False)
class DeclaredLocalModel:
    """Bounded server-declared identity; never a local-byte attestation."""

    model: str = field(repr=False)
    digest: str = field(repr=False)
    byte_size: int = field(repr=False)
    format: str = field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.model, str) or _MODEL_NAME.fullmatch(self.model) is None
                or not isinstance(self.digest, str) or _DIGEST.fullmatch(self.digest) is None
                or type(self.byte_size) is not int or not 1 <= self.byte_size <= (1 << 63) - 1
                or self.format != "gguf"):
            raise LocalModelInspectionError("local model declaration is invalid")


def inspect_ollama_local_model_listing(raw_listing, selected_model):
    """Return one exact server-declared GGUF model from bounded JSON bytes.

    All entries are validated before selection, avoiding a malformed unrelated
    record silently changing the meaning of a trusted listing.  The caller must
    separately establish direct transport, server cloud-disablement, actual
    local execution, and any private-data authorization.
    """
    if not isinstance(selected_model, str) or _MODEL_NAME.fullmatch(selected_model) is None:
        raise LocalModelInspectionError("configured local model is invalid")
    if isinstance(raw_listing, str):
        if len(raw_listing) > MAX_LOCAL_MODEL_LISTING_BYTES:
            raise LocalModelInspectionError("local model listing is invalid")
        try:
            encoded = raw_listing.encode("utf-8")
        except UnicodeEncodeError:
            raise LocalModelInspectionError("local model listing is invalid") from None
    elif isinstance(raw_listing, bytes):
        encoded = raw_listing
    else:
        raise LocalModelInspectionError("local model listing is invalid")
    if not 2 <= len(encoded) <= MAX_LOCAL_MODEL_LISTING_BYTES:
        raise LocalModelInspectionError("local model listing is invalid")
    try:
        listing = json.loads(encoded.decode("utf-8"), object_pairs_hook=_pairs,
                             parse_constant=_invalid_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise LocalModelInspectionError("local model listing is invalid") from None
    if type(listing) is not dict or set(listing) != {"models"} or type(listing["models"]) is not list:
        raise LocalModelInspectionError("local model listing is invalid")
    if not 1 <= len(listing["models"]) <= 128:
        raise LocalModelInspectionError("local model listing is invalid")
    matches = []
    for item in listing["models"]:
        required = {"name", "model", "digest", "size", "details"}
        if (type(item) is not dict or not required <= set(item)
                or set(item) - required - {"modified_at", "capabilities"}):
            raise LocalModelInspectionError("local model listing is invalid")
        # Advisory server metadata is bounded and discarded, never authority
        # or a change to the selected identity/runtime configuration.
        if "capabilities" in item:
            labels = item["capabilities"]
            if (type(labels) is not list or len(labels) > 16
                    or any(type(label) is not str or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label) is None
                           for label in labels)):
                raise LocalModelInspectionError("local model listing is invalid")
        if "modified_at" in item and (type(item["modified_at"]) is not str
                or not item["modified_at"].isascii() or not 1 <= len(item["modified_at"]) <= 64):
            raise LocalModelInspectionError("local model listing is invalid")
        if (not isinstance(item["name"], str) or _MODEL_NAME.fullmatch(item["name"]) is None
                or not isinstance(item["model"], str) or _MODEL_NAME.fullmatch(item["model"]) is None
                or not isinstance(item["digest"], str) or _DIGEST.fullmatch(item["digest"]) is None
                or type(item["size"]) is not int or not 1 <= item["size"] <= (1 << 63) - 1
                or not _details_valid(item["details"])):
            raise LocalModelInspectionError("local model listing is invalid")
        # Alias/name expansion must not become an unreviewed model selection.
        if item["name"] == selected_model and item["model"] == selected_model:
            matches.append(DeclaredLocalModel(item["model"], item["digest"], item["size"], item["details"]["format"]))
    if len(matches) != 1:
        raise LocalModelInspectionError("configured local model is unavailable")
    return matches[0]
