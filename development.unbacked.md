# Exact accumulated remote-unbacked allowlist

Copied from the pre-distillation handoff without dropping or reordering its 55
paths; three new handoff artifacts appended. Includes paths already present
in local-only WSL commits. This is neither a WSL copy queue nor instructions
to stage everything again. Before any authorized backup, derive and verify
the exact remaining staging set; unrelated dirt is out of scope. GitHub is
held; see [next.steps.md](next.steps.md) for the current verified checkpoints
and counter. Never clear this ledger merely because a recap rolls or a copy
queue is empty.

Recorded local-only WSL checkpoints, newest first:
`2ecaf347a50797b7ed5c8cf8d24bea9cddd2e409` (accepted pin/native outcome),
`4fd221da1906c0e04ebbe77f08fd601a688fba93` (preparation/blocker), and
`d6e1bdbd89074a6f36c0b04b734d8c01cc513d29` (earlier local work).
Last independently verified remote: `ce83a759a0b14517347051ff14d1938de971b2f2`.
Its parent `4e8f48d69990df7200d8a4be7117d2d48150007f` is the former remote
checkpoint. The remote-only commit added exactly
`docs/StarFur-handoff-before-distillation-2026-11-26.rar`; none of the 58
paths below was published by that push. The original WSL branch was left
untouched. Check ancestry and reconcile the remote archive before a later
authorized push; no force and no unrelated work.

- AGENTS.md
- CHANGELOG.md
- ROADMAP.md
- next.steps.md
- session.files.md
- 2026-11-01.annotation-worker-design.sprint.md
- docs/private_annotation_verification.plan.md
- user.smokes.md
- pipeline/document_job_worker_member_binding.py
- tests/test_document_job_worker_member_binding.py
- pipeline/document_job_worker_search_form.py
- tests/test_document_job_worker_search_form.py
- pipeline/document_job_worker_launch_profile.py
- tests/test_document_job_worker_launch_profile.py
- pipeline/document_job_worker_lookup_requirements.py
- tests/test_document_job_worker_lookup_requirements.py
- scripts/private_worker_loader_smoke.py
- tests/test_private_worker_loader_smoke.py
- scripts/private_worker_lookup_fixture.py
- tests/test_private_worker_lookup_fixture.py
- scripts/private_worker_mapping_observer.py
- tests/test_private_worker_mapping_observer.py
- scripts/private_worker_hold_lifecycle.py
- tests/test_private_worker_hold_lifecycle.py
- scripts/private_worker_cooperative_review.py
- tests/test_private_worker_cooperative_review.py
- scripts/private_worker_cooperative_fds.py
- tests/test_private_worker_cooperative_fds.py
- scripts/private_worker_cooperative_fd_read.py
- tests/test_private_worker_cooperative_fd_read.py
- scripts/private_worker_cooperative_maps.py
- tests/test_private_worker_cooperative_maps.py
- scripts/private_worker_cooperative_exchange.py
- tests/test_private_worker_cooperative_exchange.py
- scripts/private_worker_cooperative_channels.py
- tests/test_private_worker_cooperative_channels.py
- scripts/private_worker_cooperative_exec.py
- tests/test_private_worker_cooperative_exec.py
- scripts/private_worker_cooperative_reap.py
- tests/test_private_worker_cooperative_reap.py
- scripts/private_worker_cooperative_startup.py
- tests/test_private_worker_cooperative_startup.py
- scripts/private_worker_cooperative_charge.py
- tests/test_private_worker_cooperative_charge.py
- scripts/private_worker_cooperative_charge_scope.py
- tests/test_private_worker_cooperative_charge_scope.py
- starfur.context.md
- scripts/private_worker_cooperative_launch_plan.py
- tests/test_private_worker_cooperative_launch_plan.py
- scripts/private_worker_cooperative_exit_abi.py
- tests/test_private_worker_cooperative_exit_abi.py
- scripts/private_worker_cooperative_exit_read.py
- tests/test_private_worker_cooperative_exit_read.py
- scripts/private_worker_cooperative_supervisor.py
- tests/test_private_worker_cooperative_supervisor.py
- docs/AGENTS.history-2026-11-26.reference-only.md
- development.unbacked.md
- 2026-11-26.handoff-distillation.sprint.md
- pipeline/resident_action.py
- pipeline/resident_snapshot.py
- tests/test_resident_snapshot.py
- pipeline/resident_presentation.py
- tests/test_resident_presentation.py
