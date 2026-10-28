"""Explicit local-operator submission/maintenance for a private annotation store.

Not a chat/model/API control, worker, or authentication service. Opening the
store fences unfinished intent and sweeps expired records, even for inspection;
the operator must acknowledge those effects before the store is constructed.
"""

from __future__ import annotations

import argparse
import json
import sys

from pipeline.document_intake import DEFAULT_MAX_DOCUMENT_BYTES, prepare_document_text
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError, JOB_ID_RE
from pipeline.document_job_inspection import (
    DEFAULT_INSPECTION_LIMIT, AnnotationJobInspectionError,
    build_annotation_result_page, validate_inspection_range,
)


class AnnotationJobControlError(ValueError):
    """Content-free invalid/unavailable local-control refusal."""


def read_annotation_job_input(stream):
    """Read at most the unchanged intake ceiling plus one overflow byte.

    Binary stdin is explicit operator-supplied data, not a path selector,
    command channel, provider disclosure or permission to read another file.
    """
    try:
        raw = stream.read(DEFAULT_MAX_DOCUMENT_BYTES + 1)
        if type(raw) is not bytes or len(raw) > DEFAULT_MAX_DOCUMENT_BYTES or b"\x00" in raw:
            raise ValueError
        content = raw.decode("utf-8")
        if not content.strip():
            raise ValueError
        return content
    except (OSError, ValueError, AttributeError):
        raise AnnotationJobControlError("bounded UTF-8 document input is required") from None


def control_annotation_jobs(root, action, *, job_id=None, confirm_delete=None,
                            acknowledge_maintenance=False, clock=None, content=None,
                            filename=None, domain=None, profile=None, confirm_store=False,
                            confirm_inspect=None, offset=None, limit=None):
    """Trusted local OS operator only. No implicit directory or provider setup.

    The private owner-only root is the entire local operator's scope. IDs and
    confirmation text are not remote credentials. Resume changes only intent;
    no processor is started, and a later owner will fence queued intent again.
    """
    if acknowledge_maintenance is not True:
        raise AnnotationJobControlError("explicit store-maintenance acknowledgement is required")
    if not isinstance(action, str) or action not in {"list", "status", "resume", "delete", "submit", "inspect-result"}:
        raise AnnotationJobControlError("unsupported annotation job control")
    if action == "inspect-result":
        if not isinstance(job_id, str) or confirm_inspect != job_id:
            raise AnnotationJobControlError("private result inspection requires the exact job identifier twice")
        offset = 0 if offset is None else offset
        limit = DEFAULT_INSPECTION_LIMIT if limit is None else limit
        try:
            validate_inspection_range(offset, limit)
        except AnnotationJobInspectionError:
            raise AnnotationJobControlError("annotation result page range is invalid") from None
    elif confirm_inspect is not None or offset is not None or limit is not None:
        raise AnnotationJobControlError("inspection fields are not valid for this control")
    document = None
    if action == "submit":
        if confirm_store is not True or job_id is not None or confirm_delete is not None:
            raise AnnotationJobControlError("explicit private document storage confirmation is required")
        try:
            document = prepare_document_text(
                content, filename, domain="personal" if domain is None else domain,
                profile="assistant_note" if profile is None else profile,
            )
            if not document.chunks or len(document.source_name) > 255 or len(document.domain) > 128:
                raise ValueError
        except (ValueError, TypeError, UnicodeError):
            raise AnnotationJobControlError("document submission is invalid") from None
    elif (content is not None or filename is not None or domain is not None or profile is not None
          or confirm_store is not False):
        raise AnnotationJobControlError("submission fields are not valid for this control")
    if action == "list":
        if job_id is not None or confirm_delete is not None:
            raise AnnotationJobControlError("annotation job control arguments are invalid")
    elif action != "submit" and (not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None):
        raise AnnotationJobControlError("exact annotation job identifier is required")
    if action == "delete":
        if not isinstance(confirm_delete, str) or confirm_delete != job_id:
            raise AnnotationJobControlError("deletion requires the exact job identifier twice")
    elif confirm_delete is not None:
        raise AnnotationJobControlError("deletion confirmation is not valid for this control")
    # All input/confirmation checks precede even lock-file creation/recovery.
    with AnnotationJobStore(root, clock=clock) as store:
        result = {"object": "starfur.annotation_job.control", "schema_version": 1,
                  "action": action, "maintenance_on_open": True}
        if action == "list":
            result["jobs"] = [item.to_public_dict() for item in store.list_progress()]
        elif action == "submit":
            job = store.submit(content, document.source_name, domain=document.domain, profile=document.profile)
            result["job"] = store.progress(job.job_id).to_public_dict()
        elif action == "delete":
            store.delete(job_id)
            result.update(job_id=job_id, deleted=True)
        elif action == "inspect-result":
            # Each store read revalidates source/results and retention. No
            # durable result is installed into an ephemeral review store.
            document = store.read_source(job_id)
            saved_result = store.read_result(job_id)
            try:
                page = build_annotation_result_page(document, saved_result, offset=offset, limit=limit)
            except AnnotationJobInspectionError:
                raise AnnotationJobControlError("annotation result inspection is unavailable") from None
            # Rendering may take time; expiry is checked again before returning
            # any candidate prose. A failed check produces no partial page.
            store.progress(job_id)
            result.update(job_id=job_id, inspection=page)
        else:
            if action == "resume":
                store.resume(job_id)
            result["job"] = store.progress(job_id).to_public_dict()
        return result


def configure_annotation_job_parser(parser):
    parser.add_argument("--root", required=True, help="Existing owner-only private job directory (POSIX/WSL)")
    parser.add_argument("--acknowledge-maintenance", action="store_true",
                        help="Allow startup fencing of unfinished intent and deletion of expired job records")
    actions = parser.add_subparsers(dest="job_action", required=True)
    actions.add_parser("list", help="List content-free progress after startup maintenance")
    submission = actions.add_parser("submit", help="Store bounded UTF-8 stdin privately; no processing")
    submission.add_argument("--filename", required=True, help="Document display filename, not a path")
    submission.add_argument("--domain", default=None, help="Explicit memory domain label; defaults to personal")
    submission.add_argument("--profile", default=None, help="Structural profile; defaults to assistant_note")
    submission.add_argument("--confirm-store", action="store_true",
                            help="Confirm private plaintext storage for 24 hours from submission")
    inspection = actions.add_parser("inspect-result", help="Explicitly display one private untrusted candidate page")
    inspection.add_argument("job_id")
    inspection.add_argument("--confirm-inspect", help="Repeat the exact job ID to disclose candidate prose locally")
    inspection.add_argument("--offset", type=int, default=None)
    inspection.add_argument("--limit", type=int, default=None, help="Candidates per page (1-10; default 5)")
    for action in ("status", "resume", "delete"):
        command = actions.add_parser(action)
        command.add_argument("job_id")
        if action == "delete":
            command.add_argument("--confirm-delete", help="Repeat the exact job ID to confirm logical deletion")


def run_annotation_job_command(args):
    """No exception/input echo or partial output on failure.

    Only separately confirmed inspect-result may print private candidate prose.
    """
    try:
        submission = {}
        if args.job_action == "submit":
            if args.acknowledge_maintenance is not True or args.confirm_store is not True:
                raise AnnotationJobControlError("explicit private storage and maintenance consent are required")
            submission = {
                "content": read_annotation_job_input(getattr(sys.stdin, "buffer", None)),
                "filename": args.filename, "domain": args.domain, "profile": args.profile,
                "confirm_store": args.confirm_store,
            }
        result = control_annotation_jobs(
            args.root, args.job_action, job_id=getattr(args, "job_id", None),
            confirm_delete=getattr(args, "confirm_delete", None),
            acknowledge_maintenance=args.acknowledge_maintenance,
            confirm_inspect=getattr(args, "confirm_inspect", None),
            offset=getattr(args, "offset", None), limit=getattr(args, "limit", None),
            **submission,
        )
    except (AnnotationJobControlError, AnnotationJobStoreError):
        print("Annotation job control refused safely. Check exact arguments, maintenance acknowledgement, "
              "storage/deletion/inspection confirmation, bounded input/page limits, private-root permissions and exclusive ownership. "
              "No provider or processing was started. Inspect local state before retrying.")
        return 2
    except KeyboardInterrupt:
        print("Annotation job control interrupted; storage completion may be uncertain. "
              "Inspect local state before retrying. No provider or processing was started.")
        return 130
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local private annotation-job submission/maintenance; no processing")
    configure_annotation_job_parser(parser)
    return run_annotation_job_command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
