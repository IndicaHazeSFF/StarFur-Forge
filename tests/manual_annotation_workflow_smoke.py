"""Operator-invoked disposable CLI workflow; never accepts a store path.

Run from the repository root: python -m tests.manual_annotation_workflow_smoke
This is a fixture workflow, not live model/deployment or extraction-quality proof.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def main():
    if os.name != "posix" or len(sys.argv) != 1:
        print("Run in WSL without arguments; this helper uses only its own temporary store.")
        return 2
    repo = Path(__file__).resolve().parents[1]
    phase = "temporary setup"
    try:
        with tempfile.TemporaryDirectory(prefix="starfur-user-smoke-") as temporary:
            root = Path(temporary) / "jobs"
            root.mkdir(mode=0o700)

            def invoke(label, arguments, *, expected=0, source=None):
                nonlocal phase
                phase = label
                run = subprocess.run(
                    [sys.executable, "starfur.py", "annotation-jobs", "--root", str(root),
                     "--acknowledge-maintenance", *arguments],
                    input=source, capture_output=True, text=True, cwd=repo, timeout=20,
                )
                if run.returncode != expected or run.stderr.strip():
                    raise ValueError("CLI exit or stderr mismatch")
                if expected:
                    if "refused safely" not in run.stdout.lower():
                        raise ValueError("missing refusal")
                    return None
                result = json.loads(run.stdout)
                if result.get("object") != "starfur.annotation_job.control":
                    raise ValueError("unexpected CLI envelope")
                return result

            def check(condition):
                if not condition:
                    raise ValueError("workflow assertion failed")

            submitted = invoke("confirmed synthetic submission",
                               ["submit", "--filename", "synthetic.md", "--confirm-store"],
                               source="Synthetic smoke subject prefers tea.\n")
            job = submitted["job"]["job_id"]
            check(re.fullmatch(r"AJ-[0-9a-f]{32}", job) is not None)
            check(submitted["job"]["state"] == "queued")
            check("Synthetic smoke subject" not in json.dumps(submitted))
            record = root / (job + ".json")
            check(record.is_file() and not record.is_symlink())
            print("PASS: confirmed submission returns queued, content-free progress.")

            state = invoke("restart fencing", ["status", job])["job"]
            check(state["state"] == "interrupted")
            deadline = state["expires_at"]
            print("PASS: a later CLI owner fences queued intent as interrupted.")

            resumed = invoke("explicit resume intent", ["resume", job])["job"]
            check(resumed["state"] == "queued" and resumed["expires_at"] == deadline)
            again = invoke("resume does not start worker", ["status", job])["job"]
            check(again["state"] == "interrupted" and again["expires_at"] == deadline)
            print("PASS: resume records intent only and preserves retention; no worker starts.")

            before = hashlib.sha256(record.read_bytes()).digest()
            invoke("inspection consent refusal", ["inspect-result", job], expected=2)
            check(hashlib.sha256(record.read_bytes()).digest() == before)
            invoke("unprocessed result refusal",
                   ["inspect-result", job, "--confirm-inspect", job], expected=2)
            check(hashlib.sha256(record.read_bytes()).digest() == before)
            print("PASS: missing consent and unavailable results disclose no candidate page.")

            invoke("deletion confirmation refusal",
                   ["delete", job, "--confirm-delete", job[:-1] + ("0" if job[-1] != "0" else "1")], expected=2)
            check(record.exists() and hashlib.sha256(record.read_bytes()).digest() == before)
            removed = invoke("confirmed deletion", ["delete", job, "--confirm-delete", job])
            check(removed["deleted"] is True and not record.exists())
            check(invoke("empty listing", ["list"])["jobs"] == [])
            print("PASS: wrong deletion confirmation refuses; exact confirmation deletes only the fixture job.")
        print("WORKFLOW PASS. Test-owned temporary state cleaned up. Operator acceptance still requires your review.")
        return 0
    except KeyboardInterrupt:
        print("WORKFLOW INTERRUPTED at " + phase + ". Inspect before retrying; no provider-stop claim.")
        return 130
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("WORKFLOW FAIL at " + phase + ". Stop and report this phase; no automatic retry.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
