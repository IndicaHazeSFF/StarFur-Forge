from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def canonical_source(path) -> str:
    """
    Convert a source path into StarFur's canonical source identifier.

    All database source references use project-relative POSIX paths.

    Example:
        /home/roger/StarFur-Forge/canon/manuscript/chapter-prologue.md

    becomes:
        canon/manuscript/chapter-prologue.md
    """
    path = Path(path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()

    try:
        relative = path.relative_to(
            PROJECT_ROOT
        )

    except ValueError:
        raise ValueError(
            f"Source is outside StarFur Forge: {path}"
        )

    return relative.as_posix()
