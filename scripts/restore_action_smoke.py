"""Offline, opt-in repair for the inspected Action Smoke registration only.

Stop StarFur writers first. This is a maintenance helper, not a Core command,
automatic workspace discovery, concurrent registry recovery, or migration.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_initiative import AdventureParticipantRoster
from pipeline.adventure_registry import AdventureRecord, AdventureRegistry
from pipeline.adventure_resources import AdventureResourceCatalog
from pipeline.adventure_transcript import AdventureTranscriptRecord, TRANSCRIPT_WRITE_LOCK_FILENAME


WORKSPACE_ID = "action-smoke-0c1a9a45ed14"
TITLE = "Action Smoke"
MAX_BYTES = 2 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON fields; repair refused")
        result[key] = value
    return result


def _json(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)


def _read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or linked maintenance input; repair refused")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("maintenance input exceeds repair bound")
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("maintenance input exceeds repair bound")
    return data


def restore(root, *, apply=False):
    """Preview by default; back up exact inputs before replacing registry only."""
    supplied_root = Path(root)
    if supplied_root.is_symlink():
        raise ValueError("linked adventure root; repair refused")
    root = supplied_root.resolve(strict=True)
    workspace = root / WORKSPACE_ID
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("Action Smoke workspace is missing or linked")
    names = {path.name for path in workspace.iterdir()}
    # The transcript writer leaves this coordination file after releasing its
    # OS-held lock. Its existence/contents are not evidence of a live writer.
    # Preserve and recheck it like every input; never remove or acquire it here.
    allowed_names = {"manifest.json", "transcript.jsonl", TRANSCRIPT_WRITE_LOCK_FILENAME}
    if "manifest.json" not in names or not names <= allowed_names:
        raise ValueError("workspace differs from inspected manifest/transcript-only case")

    inputs = {root / "registry.json": _read(root / "registry.json")}
    inputs.update({workspace / name: _read(workspace / name) for name in sorted(names)})
    manifest = _json(inputs[workspace / "manifest.json"])
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported adventure manifest")
    if manifest.get("adventure_id") != WORKSPACE_ID or manifest.get("title") != TITLE:
        raise ValueError("manifest identity differs from inspected Action Smoke")
    storage = manifest.get("storage")
    if not isinstance(storage, dict) or storage.get("event_log") != "not_created":
        raise ValueError("manifest does not describe the inspected event-free workspace")
    record = AdventureRecord(WORKSPACE_ID, TITLE, manifest.get("created_at"))
    datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
    if "participant_roster" in manifest:
        AdventureParticipantRoster.from_dict(WORKSPACE_ID, manifest["participant_roster"])
    if "resource_catalog" in manifest:
        AdventureResourceCatalog.from_dict(manifest["resource_catalog"])
    transcript = inputs.get(workspace / "transcript.jsonl", b"")
    for sequence, line in enumerate(transcript.decode("utf-8").splitlines(), 1):
        item = AdventureTranscriptRecord.from_dict(_json(line.encode("utf-8")))
        if item.sequence != sequence:
            raise ValueError("transcript sequence is invalid")

    registry_path = root / "registry.json"
    registry = _json(inputs[registry_path])
    if not isinstance(registry, dict) or type(registry.get("schema_version")) is not int or registry["schema_version"] != 1:
        raise ValueError("unsupported registry schema")
    # Use the existing record/schema validator without opening any runtime store.
    records = AdventureRegistry(root).list()
    matches = [item for item in records if item.adventure_id == WORKSPACE_ID or item.title.casefold() == TITLE.casefold()]
    if matches:
        if matches == [record]:
            return "Action Smoke is already registered; nothing changed."
        raise ValueError("conflicting registry identity; repair refused")
    if not apply:
        return "Preview passed: restore Action Smoke only; no files changed. Stop all StarFur writers before --apply."

    backup_root = root / "_registration_backups"
    if backup_root.is_symlink():
        raise ValueError("linked backup root; repair refused")
    backup_root.mkdir(mode=0o700, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="action-smoke-", dir=backup_root))
    for path, data in inputs.items():
        with (backup / path.name).open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    # Preserve existing entry payloads and any registry metadata, adding one entry.
    registry["adventures"].append(asdict(record))
    replacement = (json.dumps(registry, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".registration-", dir=root, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        if {path.name for path in workspace.iterdir()} != names or any(_read(path) != data for path, data in inputs.items()):
            raise ValueError("maintenance inputs changed; backup retained, registry not replaced")
        os.replace(temporary, registry_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return f"Restored Action Smoke registration only. Backup: {backup}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="exact adventure root; normally adventures")
    parser.add_argument("--apply", action="store_true", help="back up inputs and restore the missing entry")
    args = parser.parse_args()
    try:
        print(restore(args.root, apply=args.apply))
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(1, "Repair refused: inputs failed validation or changed. Nothing was reset; retain any backup.\n")


if __name__ == "__main__":
    main()
