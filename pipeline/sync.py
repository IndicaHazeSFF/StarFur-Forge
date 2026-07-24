from pathlib import Path
import hashlib
import json
import subprocess
import sys

from pipeline.canon_writer import export_entities
from pipeline.db import get_entities
from pipeline.proposal_pipeline import analyze_document


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANON_ROOT = PROJECT_ROOT / "canon"
MANUSCRIPT_ROOT = CANON_ROOT / "manuscript"

DATA_ROOT = PROJECT_ROOT / "data"
MANIFEST_PATH = DATA_ROOT / "sync_manifest.json"

SYNC_VERSION = 1
ANNOTATOR_VERSION = 2
CHUNKER_VERSION = 2


def file_hash(path: Path) -> str:
    """
    Calculate a SHA-256 hash for a file.
    """
    hasher = hashlib.sha256()

    with path.open("rb") as file:
        while block := file.read(65536):
            hasher.update(block)

    return hasher.hexdigest()


def load_manifest():
    """
    Load previous sync state.
    """
    if not MANIFEST_PATH.exists():
        return {
            "sync_version": SYNC_VERSION,
            "annotator_version": ANNOTATOR_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "files": {},
        }

    try:
        return json.loads(
            MANIFEST_PATH.read_text(
                encoding="utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        OSError,
    ):
        print(
            "WARNING: Sync manifest is invalid. "
            "Treating all manuscript files as changed."
        )

        return {
            "sync_version": SYNC_VERSION,
            "annotator_version": ANNOTATOR_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "files": {},
        }


def save_manifest(manifest):
    """
    Persist sync state.
    """
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def relative_path(path: Path) -> str:
    return str(
        path.relative_to(PROJECT_ROOT)
    )


def find_manuscripts():
    """
    Find Markdown manuscript files only.

    Generated lore files are intentionally excluded from
    manuscript analysis.
    """
    if not MANUSCRIPT_ROOT.exists():
        return []

    return sorted(
        MANUSCRIPT_ROOT.rglob("*.md")
    )


def determine_changed_files(
    files,
    manifest,
):
    """
    Determine which manuscript files require lore analysis.
    """
    previous_files = manifest.get(
        "files",
        {},
    )

    force_reanalysis = (
        manifest.get("annotator_version")
        != ANNOTATOR_VERSION
        or manifest.get("chunker_version")
        != CHUNKER_VERSION
    )

    changed = []
    hashes = {}

    for path in files:
        rel = relative_path(path)
        digest = file_hash(path)

        hashes[rel] = digest

        previous = previous_files.get(rel)

        if force_reanalysis:
            changed.append(path)

        elif not previous:
            changed.append(path)

        elif previous.get("hash") != digest:
            changed.append(path)

    return changed, hashes, force_reanalysis


def run_ingestion():
    """
    Run the existing Chroma ingestion pipeline.
    """
    print("\n=== SEMANTIC MEMORY ===\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.ingest",
        ],
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Chroma ingestion failed."
        )


def export_canon():
    """
    Ensure every confirmed entity has a Markdown file.
    """
    print("\n=== CANON EXPORT ===\n")

    entities = get_entities()

    created = 0
    existing = 0

    for result in export_entities(entities):

        if result["created"]:
            print(
                f"CREATE   {result['name']} "
                f"-> {result['path']}"
            )
            created += 1

        else:
            existing += 1

    print(
        f"\nCanon files created: {created}"
    )
    print(
        f"Canon files existing: {existing}"
    )


def run_sync():
    print("\n" + "=" * 70)
    print("STARFUR SYNC")
    print("=" * 70)

    manifest = load_manifest()
    manuscripts = find_manuscripts()

    changed, hashes, forced = (
        determine_changed_files(
            manuscripts,
            manifest,
        )
    )

    print(
        f"\nManuscript files: {len(manuscripts)}"
    )
    print(
        f"Changed/new:      {len(changed)}"
    )
    print(
        f"Unchanged:        "
        f"{len(manuscripts) - len(changed)}"
    )

    if forced:
        print(
            "\nPipeline version changed: "
            "forcing manuscript re-analysis."
        )

    # ---------------------------------
    # CHROMA
    # ---------------------------------

    run_ingestion()

    # ---------------------------------
    # STRUCTURED LORE ANALYSIS
    # ---------------------------------

    print("\n=== STRUCTURED MEMORY ===\n")

    if not changed:
        print(
            "No manuscript files require lore analysis."
        )

    successful = []

    for index, path in enumerate(
        changed,
        start=1,
    ):
        rel = relative_path(path)

        print(
            f"\n[{index}/{len(changed)}] "
            f"{rel}"
        )

        try:
            analyze_document(path)

        except Exception as error:
            print(
                f"\nERROR analyzing {rel}: "
                f"{error}"
            )
            continue

        successful.append(path)

    # ---------------------------------
    # CANON EXPORT
    # ---------------------------------

    export_canon()

    # ---------------------------------
    # UPDATE MANIFEST
    # ---------------------------------

    old_files = manifest.get(
        "files",
        {},
    )

    new_files = {}

    for path in manuscripts:
        rel = relative_path(path)

        if path in successful or path not in changed:
            new_files[rel] = {
                "hash": hashes[rel],
            }

        elif rel in old_files:
            # Analysis failed. Keep old state so the
            # file will be attempted again next sync.
            new_files[rel] = old_files[rel]

    new_manifest = {
        "sync_version": SYNC_VERSION,
        "annotator_version": ANNOTATOR_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "files": new_files,
    }

    save_manifest(new_manifest)

    failed = len(changed) - len(successful)

    print("\n" + "=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)

    print(
        f"Manuscripts scanned: {len(manuscripts)}"
    )
    print(
        f"Analyzed:            {len(successful)}"
    )
    print(
        f"Skipped unchanged:   "
        f"{len(manuscripts) - len(changed)}"
    )
    print(
        f"Failed:              {failed}"
    )

    if failed:
        print(
            "\nFailed documents remain dirty and "
            "will be retried next sync."
        )


if __name__ == "__main__":
    run_sync()
