"""Shared memory-domain identifiers and validation."""
import re

DEFAULT_PROJECT_DOMAIN = "project:crown-of-claws"
PERSONAL_DOMAIN = "personal"

_DOMAIN_RE = re.compile(r"^(?:personal|project:[a-z0-9][a-z0-9_-]*)$")


def normalize_domain(domain=None):
    value = DEFAULT_PROJECT_DOMAIN if domain is None else str(domain).strip().casefold()
    if not _DOMAIN_RE.fullmatch(value):
        raise ValueError("Invalid memory domain; use personal or project:<slug>.")
    return value
