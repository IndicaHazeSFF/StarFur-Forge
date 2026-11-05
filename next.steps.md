# Rotating development handoff

Updated 2026-11-04 after verified scoped commit/push.

## Last verified backup checkpoint

- WSL main and GitHub refs/heads/main: fc6f5f20a53eafa1d7fe54e6ea7904f069f92997.
- Subject: Give Murr's artifact paws bounded reads and tidy exits.
- Previous: bd9f181b73f9792460ad11e4943fb7fc7e9fe082.
- Fifteen exact accumulated files hash-verified before staging; unrelated dirty WSL paths, bytecode, docs/COMMANDS.md, runtime state and quota trials excluded.
- Push independently verified with git ls-remote. Windows Git remains separate/stale; it was not reset.
- Ten new required gates passed this sprint. Two prior gates plus ten = twelve since last backup. Threshold crossed during final slice; its required subsystem/full verification completed before backup. Carry **2/10** into the next cadence (do not discard or count reruns).
- No recursive commit for this post-push rotation. Only next.steps.md and session.files.md become new-cycle unbacked records.

## Completed scope / evidence

M2a cleanup/adversarial hardening: both owned-handle closes attempted, content-free cleanup failure, interruption preserved; replacement/FIFO/post-read-timeout fixtures. Focused 9, subsystem 186, full 1,369 tests OK.

M2b whole-set measurement: aggregate byte preflight, one monotonic deadline, ordered hashes and earlier-member/root revalidation. Focused 6, subsystem 192, full 1,375 tests OK.

M2c explicit-basename POSIX manifest-file acquisition and synthetic disk-to-blob integration. Reader 6, integration 1, subsystem 199, full 1,382 tests OK.

All use .venv/bin/python -B -W error::ResourceWarning from the WSL root; full/subsystem had one expected platform skip. Ten distinct required suites/fences total, no optional quota-filling reruns. Full commands, copy baselines/hashes and fifteen-path allowlist: 2026-11-01.annotation-worker-design.sprint.md. Git CRLF-only whitespace preflight issue understood and resolved with command-local cr-at-eol plus ordinary whitespace checks; no persistent Git config changed.

Source/tests are backed up. No installed model, live provider, private job/source, production database, service, firewall or network-enforcement configuration was touched. Measurements are bounded trusted-host observations, not deployment acceptance or permission.

## Next dependency

COMPLETED M2f / WSL-VERIFIED (2026-11-05): config-file binding passed 6 reader,
4 integration, 224 subsystem and 1,407 full tests (one expected skip in subsystem/
full), ResourceWarning as error. Twelve gates since backup; scoped backup due
after final required verification, carry two forward. Fifteen accumulated exact
paths recorded in sprint; existing artifact_tree modified, legacy path unchanged.
No installed model/private source/provider/service/egress change. STOP for targeted
Astra review of worker-only OS egress isolation and authenticated Core transport:
network namespaces change loopback reachability, while cgroup/UID filtering needs
actual WSL capability/enforcement and narrowly authorized setup. Do not select a
privileged launcher/proxy, broaden literal-loopback policy or silently expose the
shared daemon. No broad audit or actual setup authorized. Other deployment evidence/
consent gates remain incomplete; no new operator/live smoke required.

COMPLETED M2e / WSL-VERIFIED on Medium: source-grounded pure basic-GGUF config
codec passed 6 focused, 214 subsystem and 1,397 full tests (one expected skip in
subsystem/full), ResourceWarning as error. Current counter 8/10; no commit/push
due yet. New accumulated paths pipeline/document_job_config.py and
tests/test_document_job_config.py bring unbacked scope to twelve (prior ten plus
these two). PAUSED for Sol High before measured-config filesystem acquisition/
binding into M2d. No live/manual smoke required or private processing enabled.
Completion record copies verified separately; pending queue belongs to session.files.
Night quota instruction remains: stop near 10% five-hour remaining. Last measured
72% five-hour / 96% weekly remaining, not a guarantee for the next slice.

COMPLETED M2d / WSL-VERIFIED (High): anchored tree/explicit model selection and
synthetic race fixtures passed 9 focused, 208 subsystem and 1,391 full tests
(one expected skip in subsystem/full), ResourceWarning as error. Counter 5/10.
Adds pipeline/document_job_artifact_tree.py and tests/test_document_job_artifact_tree.py
to accumulated unbacked scope; AGENTS/context ownership records also changed.
PAUSED for Roger to lower effort to Medium for source-grounded pure config-contract
work. Actual config schema still needs review before coding; do not select new
filesystem/authority work on Medium by inference. Night sprint remains authorized
until 10% five-hour remaining or earlier safety/user/model gate. No service change.

1. Anchored mapping M2d is complete under an explicit trusted caller-opened anchor; safe actual deployment-anchor acquisition/acceptance remains separate, with no discovery/default-root policy.
2. Define and implement bounded config/remote-reference validation from reviewed supported schemas. Config bytes currently get hashed but NOT interpreted as local-only evidence.
3. Only later: actual executable/dependency/runner/listener observations, explicit deployment acceptance, exact-attempt consent and sealed dispatch.
4. Mandatory OS outbound-network blocking must cover the worker AND inference processes, proven by native WSL tests before private dispatch. Restricting a caller of unrestricted shared Ollama is insufficient. Backend selection/setup and service/firewall changes remain separately gated.
5. Preserve Focus Mode, shared physical-resource capacity, no initial private retry/fallback, fixed original 24h retention, restart/unknown-outcome fencing and no provider-stop claim.

Full M2, deployment verification, consent and public processing remain INCOMPLETE. Existing default-session runtime and injected-annotator test seam are not private-runtime shortcuts. Sol High appropriate for filesystem/authority work; ask Astra only for unresolved security/design ambiguity. Do not silently switch/delegate.

## Operator acceptance / stop status

Requested ten-gate sprint COMPLETE; PAUSED, not blocked. Roger reported WORKFLOW PASS with test-owned cleanup and all 22 focused artifact tests passing on 2026-11-04 at fc6f5f2. Disposable CLI workflow operator acceptance is PASS. No extra required-development gate counted: counter remains 2/10. Preserve user.smokes.md optional pending checks; visual/audio/game checks remain user-owned. Private-processing readiness is not established.

## Current copy / test / commit / push status

- Application verification: PASS as above.
- Fifteen-path scoped commit: COMPLETE, fc6f5f20a53eafa1d7fe54e6ea7904f069f92997.
- GitHub push: VERIFIED.
- Post-push rotation copies: next.steps.md and session.files.md synchronized and SHA-256 verified; pending queue closed. Final receipt closure uses their verified rotation hashes.
- Accumulated NEW unbacked allowlist: next.steps.md, session.files.md, user.smokes.md, CHANGELOG.md, ROADMAP.md, 2026-11-01.annotation-worker-design.sprint.md, AGENTS.md, starfur.context.md, pipeline/document_job_artifact_tree.py, tests/test_document_job_artifact_tree.py. Ten exact paths; M2d source is verified but not backed up. Commit/push not due at 5/10. Exact copy evidence is in the sprint.
- Pre-copy WSL baselines: next.steps.md bfaa126cfadc137a1bb4af5deecb6321e6918bc51a63cb62560ba29f23f5ac1e; session.files.md 0d8e866029cb854c15f2bf3af2011092a7b61f923a9aea9c6d099a3722a4c4c3.
- Initial verified rotation hashes: next.steps.md 8393c8839700aa54b286fd32b9c0badd1b4fa965796586e8e9f0cf6c518e3eb5; session.files.md 7a2a066be1edf5a10a72fc5684c668aa08394b9d528071ad1f3e0fa07b9cf919. Final closure hashes returned by copy verification, not recursively embedded.
- Source of truth for pending copies is session.files.md; copy success never implies later GitHub backup.
- Current counter 8/10. Check actual quota before any new slice. Last measured 72% five-hour / 96% weekly remaining in M2e closeout, not a future guarantee. Roger's active five-hour threshold is 10% remaining.

## Continuing workflow

Read AGENTS.md, starfur.context.md and this handoff. Windows edits -> exact queued WSL copies -> required provider-free gates -> scoped GitHub backup every ten required gates. Stop on copy/hash/path/permission/independent changes or uncertain security/runtime effects. Never mirror/reset or include unrelated dirty files.
