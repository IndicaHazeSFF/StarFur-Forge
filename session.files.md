# Pending copy manifest

## Pipeline (21)

- `pipeline/assistant.py`
- `pipeline/application.py`
- `pipeline/command_help.py`
- `pipeline/resident_snapshot.py`
- `pipeline/sandbox_image.py`
- `pipeline/tool_broker.py`
- `pipeline/tool_audit.py`
- `pipeline/tool_contracts.py`
- `pipeline/tool_registry.py`
- `pipeline/tool_status.py`
- `pipeline/tool_web_policy.py`
- `pipeline/tool_web_response.py`
- `pipeline/tool_web_disclosure.py`
- `pipeline/tool_web_parser.py`
- `pipeline/tool_prerequisites.py`
- `pipeline/sandbox_supervisor.py`
- `pipeline/tool_grants.py`
- `pipeline/tool_execution_router.py`
- `pipeline/tool_web_preflight.py`
- `pipeline/tool_web_connector.py`
- `pipeline/tool_web_native.py`

## Presentation (1)

- `presentation/apartment.html`

## Tests (19)

- `tests/test_api.py`
- `tests/test_application.py`
- `tests/test_command_help.py`
- `tests/test_resident_snapshot.py`
- `tests/test_sandbox_image.py`
- `tests/test_tool_status.py`
- `tests/test_tool_web_policy.py`
- `tests/test_tool_web_response.py`
- `tests/test_tool_web_disclosure.py`
- `tests/test_tool_web_parser.py`
- `tests/test_tool_broker.py`
- `tests/test_tool_prerequisites.py`
- `tests/test_tool_contracts.py`
- `tests/test_tool_registry.py`
- `tests/test_sandbox_supervisor.py`
- `tests/test_tool_execution_router.py`
- `tests/test_tool_web_preflight.py`
- `tests/test_tool_web_connector.py`
- `tests/test_tool_web_native.py`

## Documentation and policy (5)

- `AGENTS.md`
- `ROADMAP.md`
- `ROADMAP.v5.md`
- `docs/COMMANDS.md`
- `docs/SANDBOX_BACKENDS.md`

S9b exposes only aggregate session-local tool lifecycle counts. B12b documents
the optional distribution boundary. B9a adds only a pure guest-image expectation
and supplied-evidence compatibility contract. S11a/S11b add pure destination,
redirect, and connect-time address decisions without resolution or sockets.
S11c bounds sanitized response metadata and decoded text ingress without HTTP,
decompression, parsing, or trust elevation. S11d permits only no-data or
Core-classified public-data metadata; private and secret disclosure stay denied.
S11e prepares only plain text/Markdown as digest-bound `untrusted_external`
source data; instruction-like prose is not treated as trusted. No request
identity, proposal content, authority record, image access, backend operation,
installation, network request, private disclosure, or execution was exposed or
enabled. Exact one-use prerequisite receipts now close the descriptive-resource
gap at broker admission and are rechecked before launch. `web.fetch` is now
registered only as an inert URL-only, confirmation-required, prerequisite-bound
contract with reference-only results. Exact executor routing now prevents
cross-tool adapter fallback. Supervisor launches carry content-free commitments
to claimed prerequisites, and fake-only web preflight/connector tests prove URL
disclosure binding, pinned peer/TLS/Host selection, response quarantine, and
reference-only results. No native adapter is configured as a network executor,
and no public fetch command exists.
Native resolver, session-only prerequisite/quarantine stores, and pinned TLS
transport adapters now exist behind explicit trusted-local injection. The local
Assistant CLI can reserve an inert `web.fetch`, grant and approve it, prepare
short-lived exact DNS/disclosure evidence, execute it once, and inspect a
bounded quarantined artifact. Shared chat/API, passive views, providers,
prompts, memory, skills, and `sandbox.run` remain disconnected from execution.
A controlled WSL public-text and denial smoke is mandatory before continuing.
