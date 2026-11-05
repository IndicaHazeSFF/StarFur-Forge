"""Pure narrow config-byte/manifest equality; no I/O or locality authority.

Policy intentionally supports only the basic GGUF schema from Ollama v0.32.1.
Remote/draft and every optional extension are denied, even empty/null. This is
not full Ollama compatibility, deployment acceptance, config execution or consent.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re

from pipeline.document_job_manifest import ParsedModelManifest, ManifestBlobDescriptor, MAX_MANIFEST_BYTES


CONFIG_POLICY = "ollama-basic-gguf-config-v1"
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ModelConfigError(ValueError):
    """Content-free config schema/equality refusal."""


@dataclass(frozen=True, repr=False)
class ModelConfigMetadata:
    raw_bytes_sha256: str = field(repr=False)
    family: str = field(repr=False)
    families: tuple[str, ...] = field(repr=False)
    model_type: str = field(repr=False)
    file_type: str = field(repr=False)
    layer_digests: tuple[str, ...] = field(repr=False)

    def __post_init__(self):
        if (type(self.raw_bytes_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self.raw_bytes_sha256) is None
                or any(type(v) is not str or _LABEL.fullmatch(v) is None
                       for v in (self.family, self.model_type, self.file_type))
                or type(self.families) is not tuple or not 1 <= len(self.families) <= 16
                or any(type(v) is not str or _LABEL.fullmatch(v) is None for v in self.families)
                or len(set(self.families)) != len(self.families) or self.family not in self.families
                or type(self.layer_digests) is not tuple or not 1 <= len(self.layer_digests) <= 16
                or any(type(v) is not str or _DIGEST.fullmatch(v) is None for v in self.layer_digests)
                or len(set(self.layer_digests)) != len(self.layer_digests)):
            raise ModelConfigError("model config is invalid")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def decode_model_config(raw, manifest):
    """Validate supplied config bytes against supplied manifest descriptors only."""
    try:
        if (type(raw) is not bytes or not 2 <= len(raw) <= MAX_MANIFEST_BYTES
                or type(manifest) is not ParsedModelManifest):
            raise ValueError
        ParsedModelManifest(manifest.raw_bytes_sha256, manifest.config,
                            manifest.layers, manifest.declared_total)
        for descriptor in (manifest.config, *manifest.layers):
            ManifestBlobDescriptor(descriptor.media_type, descriptor.digest, descriptor.size)
        measured = sha256(raw).hexdigest()
        if manifest.config.size != len(raw) or manifest.config.digest != "sha256:"+measured:
            raise ValueError
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        required = {"model_format", "model_family", "model_families", "model_type",
                    "file_type", "architecture", "os", "rootfs"}
        if (type(value) is not dict or set(value) != required
                or value["model_format"] != "gguf" or value["architecture"] != "amd64"
                or value["os"] != "linux" or type(value["model_families"]) is not list):
            raise ValueError
        root = value["rootfs"]
        if (type(root) is not dict or set(root) != {"type", "diff_ids"}
                or root["type"] != "layers" or type(root["diff_ids"]) is not list
                or tuple(root["diff_ids"]) != tuple(x.digest for x in manifest.layers)):
            raise ValueError
        return ModelConfigMetadata(measured, value["model_family"], tuple(value["model_families"]),
                                   value["model_type"], value["file_type"], tuple(root["diff_ids"]))
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise ModelConfigError("model config is invalid") from None
