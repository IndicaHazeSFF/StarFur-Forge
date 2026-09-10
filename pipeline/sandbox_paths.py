"""Pure portable path validation for inert sandbox input trees.

These checks prevent Core from approving one logical file tree and later
materializing a different tree on a case-insensitive or Unicode-normalizing
host. They are application-level validation, not filesystem isolation.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import unicodedata
from typing import Iterable


_WINDOWS_RESERVED_STEMS = frozenset({"con", "prn", "aux", "nul"})
_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('*?"<>|:')


def validate_portable_sandbox_path(value: object, *, max_characters: int = 240) -> str:
    """Return one exact portable relative POSIX path or fail closed."""
    if not isinstance(value, str) or not value or len(value) > max_characters:
        raise ValueError("sandbox file path is invalid")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("sandbox file path is not valid UTF-8 text") from error
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("sandbox file path must use canonical Unicode")
    if "\\" in value or any(character in value for character in _WINDOWS_FORBIDDEN_CHARACTERS):
        raise ValueError("sandbox file path must use safe POSIX separators")

    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("sandbox file path must be relative and canonical without traversal")

    for part in path.parts:
        if part.endswith((".", " ")):
            raise ValueError("sandbox file path has a Windows-unsafe trailing character")
        stem = part.split(".", 1)[0].casefold()
        if stem in _WINDOWS_RESERVED_STEMS or (
            len(stem) == 4 and stem[:3] in {"com", "lpt"} and stem[3] in "123456789"
        ):
            raise ValueError("sandbox file path uses a reserved Windows name")
    return value


def portable_sandbox_path_key(value: str) -> tuple[str, ...]:
    """Return the Windows-portable comparison key for an already valid path."""
    validated = validate_portable_sandbox_path(value)
    return tuple(part.casefold() for part in PurePosixPath(validated).parts)


def validate_portable_sandbox_tree(paths: Iterable[str]) -> tuple[str, ...]:
    """Reject duplicate, case-colliding, or file/directory-colliding trees."""
    validated = tuple(validate_portable_sandbox_path(path) for path in paths)
    keys: set[tuple[str, ...]] = set()
    for path in validated:
        key = portable_sandbox_path_key(path)
        if key in keys:
            raise ValueError("sandbox file paths must be portably unique")
        for length in range(1, len(key)):
            if key[:length] in keys:
                raise ValueError("sandbox file paths contain a file/directory collision")
        if any(existing[:len(key)] == key for existing in keys):
            raise ValueError("sandbox file paths contain a file/directory collision")
        keys.add(key)
    return validated


__all__ = [
    "portable_sandbox_path_key",
    "validate_portable_sandbox_path",
    "validate_portable_sandbox_tree",
]
