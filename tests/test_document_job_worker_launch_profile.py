"""Synthetic supplied-byte launch declarations; never execute the argv."""
from dataclasses import FrozenInstanceError, replace
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import _inspect_metadata
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_image import WorkerImageInventory, WorkerImageMember
from pipeline.document_job_worker_launch_profile import ARGV, UNRESOLVED, WorkerLaunchProfileError, propose_worker_launch_profile
from pipeline.document_job_worker_search_form import review_worker_search_form
from tests.test_document_job_worker_elf_search import search_fixture


def inputs():
    specs = ((('worker', 'llama-server'), 'entrypoint', '$ORIGIN'),
             (('worker', 'libggml-cpu-x64.so'), 'plugin', '$ORIGIN:/build/llama-server-cpu/bin:'),
             (('lib64', 'ld-linux-x86-64.so.2'), 'interpreter', None),
             (('worker', 'liba.so'), 'library', None))
    members, forms = [], []
    for i, (target, role, text) in enumerate(specs):
        entries = ((29, text),) if text is not None else ()
        raw = bytearray(search_fixture(entries, needed=False)); raw[-1] = i
        if role == 'entrypoint': struct.pack_into('<H', raw, 16, 2)
        else: struct.pack_into('<I', raw, 120, 0)
        raw = bytes(raw); metadata, _ = _inspect_metadata(raw, review_search=True)
        members.append(WorkerImageMember(target, len(raw), role, metadata, review_worker_elf_search(raw)))
        forms.append((target, review_worker_search_form(raw)))
    return WorkerImageInventory(tuple(members)), tuple(forms)


class WorkerLaunchProfileTests(unittest.TestCase):
    def test_inert_fixed_initial_profile_redacted_immutable_and_unresolved(self):
        inventory, forms = inputs()
        with patch('builtins.open', side_effect=AssertionError), patch('subprocess.Popen', side_effect=AssertionError):
            a = propose_worker_launch_profile(inventory, forms)
            b = propose_worker_launch_profile(WorkerImageInventory(inventory.members[::-1]), forms[::-1])
        self.assertEqual(a.fingerprint, b.fingerprint); self.assertEqual(a.argv, ARGV)
        self.assertEqual(a.argv[5], ''); self.assertEqual(a.status, 'proposal_only')
        self.assertEqual(a.unresolved, UNRESOLVED); self.assertIn('descendant_exec_enforcement', a.unresolved)
        self.assertFalse(hasattr(a, 'eligible_to_execute')); self.assertNotIn('/worker', repr(a))
        with self.assertRaises(FrozenInstanceError): a.argv = ()

    def test_forged_search_hash_or_raw_digest_refuses(self):
        inv, forms = inputs(); target, value = forms[0]
        for kw in (dict(raw_sha256='f'*64), dict(search_fingerprint='f'*64), dict(form='unsupported')):
            with self.assertRaises(WorkerLaunchProfileError):
                propose_worker_launch_profile(inv, ((target, replace(value, **kw)), *forms[1:]))

    def test_missing_extra_duplicate_forms_refuse(self):
        inv, forms = inputs()
        for bad in (forms[:-1], forms+forms[:1], list(forms), ((('build','x'), forms[0][1]),), (None,)):
            with self.assertRaises(WorkerLaunchProfileError): propose_worker_launch_profile(inv, bad)

    def test_unsupported_target_role_interpreter_and_duplicate_bytes_refuse(self):
        inv, forms = inputs()
        for role in ('entrypoint', 'plugin', 'interpreter', 'library'):
            member = next(m for m in inv.members if m.role == role)
            target = ('outside', member.target[-1])
            changed = WorkerImageInventory(tuple(replace(m, target=target) if m is member else m for m in inv.members))
            moved = tuple((target if p == member.target else p, v) for p, v in forms)
            with self.assertRaises(WorkerLaunchProfileError): propose_worker_launch_profile(changed, moved)

    def test_constructed_profile_cannot_clear_requirements_or_change_options(self):
        inv, forms = inputs(); value = propose_worker_launch_profile(inv, forms)
        for kw in (dict(policy='future'), dict(argv=ARGV+('--audit','x')), dict(argv=list(ARGV)),
                   dict(environment=(('LD_LIBRARY_PATH','/tmp'),)), dict(unresolved=()), dict(status='ready')):
            with self.assertRaises(WorkerLaunchProfileError): replace(value, **kw)

    def test_missing_required_plugin_refuses(self):
        inv, forms = inputs(); keep = tuple(m for m in inv.members if m.role != 'plugin')
        with self.assertRaises(WorkerLaunchProfileError):
            propose_worker_launch_profile(WorkerImageInventory(keep), tuple((p,v) for p,v in forms if p in {m.target for m in keep}))
