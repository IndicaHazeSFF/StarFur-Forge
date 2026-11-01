"""Pure narrow manifest descriptor codec; no file access or attestation."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re

MANIFEST_POLICY = "ollama-schema2-descriptors-v1"
MAX_MANIFEST_BYTES = 65536
MAX_BLOB_BYTES = 64 * 1024 ** 3
MAX_TOTAL_BYTES = 128 * 1024 ** 3
CONFIG_MEDIA = "application/vnd.docker.container.image.v1+json"
MODEL_MEDIA = "application/vnd.ollama.image.model"
ROOT_MEDIA = "application/vnd.docker.distribution.manifest.v2+json"
LAYER_MEDIA = frozenset("application/vnd.ollama.image." + name for name in ("model", "template", "params", "license"))


class ManifestDecodeError(ValueError):
    """Content-free invalid descriptor data."""


def _deny():
    raise ManifestDecodeError("model manifest is invalid")


@dataclass(frozen=True, repr=False)
class ManifestBlobDescriptor:
    media_type: str = field(repr=False)
    digest: str = field(repr=False)
    size: int = field(repr=False)

    def __post_init__(self):
        if (type(self.media_type) is not str or self.media_type not in LAYER_MEDIA | {CONFIG_MEDIA}
                or type(self.digest) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest) is None
                or type(self.size) is not int or not 1 <= self.size <= MAX_BLOB_BYTES
                or (self.media_type == CONFIG_MEDIA and self.size > MAX_MANIFEST_BYTES)):
            _deny()


@dataclass(frozen=True, repr=False)
class ParsedModelManifest:
    """Hash is of supplied bytes, not a server digest or actual disk proof."""
    raw_bytes_sha256: str = field(repr=False)
    config: ManifestBlobDescriptor = field(repr=False)
    layers: tuple[ManifestBlobDescriptor, ...] = field(repr=False)
    declared_total: int = field(repr=False)

    def __post_init__(self):
        if (type(self.raw_bytes_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.raw_bytes_sha256) is None
                or type(self.config) is not ManifestBlobDescriptor or self.config.media_type != CONFIG_MEDIA
                or type(self.layers) is not tuple or not 1 <= len(self.layers) <= 16
                or any(type(x) is not ManifestBlobDescriptor or x.media_type not in LAYER_MEDIA for x in self.layers)
                or sum(x.media_type == MODEL_MEDIA for x in self.layers) != 1
                or type(self.declared_total) is not int):
            _deny()
        entries = (self.config, *self.layers)
        if (len({x.digest for x in entries}) != len(entries)
                or self.declared_total != sum(x.size for x in entries)
                or not 1 <= self.declared_total <= MAX_TOTAL_BYTES):
            _deny()


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _deny()
        value[key] = item
    return value


def _blob(value):
    if type(value) is not dict or set(value) != {"mediaType", "digest", "size"}:
        _deny()
    return ManifestBlobDescriptor(value["mediaType"], value["digest"], value["size"])


def decode_model_manifest(raw):
    """Parse bounded supplied bytes only; never inspect layer contents or I/O."""
    try:
        if type(raw) is not bytes or not 2 <= len(raw) <= MAX_MANIFEST_BYTES:
            _deny()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda _: _deny())
        if (type(value) is not dict or set(value) != {"schemaVersion", "mediaType", "config", "layers"}
                or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 2
                or value["mediaType"] != ROOT_MEDIA or type(value["layers"]) is not list
                or not 1 <= len(value["layers"]) <= 16):
            _deny()
        config = _blob(value["config"])
        layers = tuple(_blob(x) for x in value["layers"])
        return ParsedModelManifest(sha256(raw).hexdigest(), config, layers, config.size + sum(x.size for x in layers))
    except (ValueError, TypeError, RecursionError):
        raise ManifestDecodeError("model manifest is invalid") from None
