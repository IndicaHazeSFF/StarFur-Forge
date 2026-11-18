"""C4/C5/C8 explicit single-unit synthetic prerequisites, NOT worker deployment.

No discovery/startup call. Fixed fixtures + one measured Linux interpreter only.
One bounded transient user unit; no installs/config/shared-service/model changes.
Use only under the corresponding fresh native approval. Failures retain fixture.
"""
import ctypes
import errno
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parent
resource = _load("c4_resource", HERE / "private_worker_resource_smoke.py")
root_test = _load("c4_root", HERE / "private_worker_root_smoke.py")
fixture_bytes = _load("c4_fixture", HERE / "private_worker_loader_fixture.py")
cwd_policy = _load("c5_cwd", HERE / "private_worker_cwd_policy.py")
lookup_fixtures = _load("c8_lookup", HERE / "private_worker_lookup_fixture.py")
elf = _load("c4_elf", HERE.parent / "pipeline/document_job_worker_elf.py")
Refusal = resource.Refusal
need = resource.need
PYTHON = "/home/roger/StarFur-Forge/.venv/bin/python"
SCRIPT = "/home/roger/StarFur-Forge/scripts/private_worker_loader_smoke.py"
LOADER_COMPONENTS = ("usr", "lib", "x86_64-linux-gnu", "ld-linux-x86-64.so.2")
MAX_LOADER = 2 * 1024 * 1024


def failure_label(error):
    value = str(error) if isinstance(error, (Refusal, root_test.Refusal)) else type(error).__name__
    return value if re.fullmatch(r"[A-Za-z0-9_:]{1,192}", value) else "native_error"


def names(unit, directory):
    need(type(unit) is str and re.fullmatch(r"starfur-c[458]-[0-9a-f]{32}\.service", unit), "unit_refused")
    token = unit[len("starfur-c4-"):-len(".service")]
    need(type(directory) is str and re.fullmatch(r"/tmp/sf-worker-loader-" + token + r"-[a-z0-9_]{8}", directory), "fixture_refused")
    return token


def unit_command(unit, directory, python, script):
    names(unit, directory)
    need(python == PYTHON and script == SCRIPT, "executable_refused")
    return ("/usr/bin/systemd-run", "--user", "--no-ask-password", "--quiet", "--collect",
            "--service-type=exec", "--expand-environment=no", "--slice=-.slice",
            "--unit=" + unit, "--description=StarFur synthetic loader prerequisite",
            *(f"--property={k}={v}" for k, v in resource.PROPERTIES.items()), "--",
            "/usr/bin/env", "-i", "LANG=C.UTF-8", "PATH=/usr/bin:/bin",
            python, "-I", "-B", "-S", script, "--worker", unit, directory)


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def cases(lookup=False):
    need(type(lookup) is bool, "mode_refused")
    return (("positive", 42), ("decoy", 13), ("negative", 127), ("transitive", 127)) if lookup else (("positive", 42), ("negative", 127))


def canary_command(label, lookup):
    need(label in dict(cases(lookup)), "case_refused")
    path = "/" + label + "/main"
    return (("/lib64/ld-linux-x86-64.so.2", "--inhibit-cache", "--library-path", "/" + label,
             "--glibc-hwcaps-mask", "", path) if lookup else (path,))


def success_record(digest, lookup):
    return dict(ok=True, **dict(cases(lookup)), pinned=6 if lookup else 4, loader_hash=digest)


def acquire_loader():
    """One fixed anchored regular root-owned file, bounded reads, metadata only.

    Returns bytes for this synthetic copy only, not accepted deployment evidence.
    Time fences acceptance; cannot cancel a blocked kernel read.
    """
    directory = handle = None
    deadline = time.monotonic() + 2
    try:
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        device = os.fstat(directory).st_dev
        for part in LOADER_COMPONENTS[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = child
            s = os.fstat(directory)
            need(s.st_uid == 0 and s.st_dev == device and not s.st_mode & 0o022, "loader_directory_refused")
        before_dir = identity(os.fstat(directory))
        name = LOADER_COMPONENTS[-1]
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == 0
             and before.st_dev == device and not before.st_mode & 0o7022
             and 64 <= before.st_size <= MAX_LOADER, "loader_file_refused")
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        need(identity(os.fstat(handle)) == identity(before), "loader_identity_changed")
        data, total = [], 0
        while True:
            need(time.monotonic() < deadline, "loader_deadline")
            chunk = os.read(handle, min(65536, before.st_size + 1 - total))
            if not chunk:
                break
            total += len(chunk); need(total <= before.st_size, "loader_byte_limit")
            data.append(chunk)
        raw = b"".join(data)
        observed = elf.inspect_worker_elf(raw)
        need(total == before.st_size and observed.object_kind == "shared_object"
             and observed.interpreter is None and observed.needed == (), "loader_metadata_refused")
        need(identity(os.fstat(handle)) == identity(before) ==
             identity(os.stat(name, dir_fd=directory, follow_symlinks=False))
             and identity(os.fstat(directory)) == before_dir and time.monotonic() < deadline,
             "loader_identity_changed")
        return raw, sha256(raw).hexdigest()
    finally:
        for fd in (handle, directory):
            if fd is not None:
                os.close(fd)


def write_new(path, raw, mode):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_LOADER, "fixture_bytes_refused")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)


def read_loader_copy(directory, digest, size):
    need(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest)
         and type(size) is int and 64 <= size <= MAX_LOADER, "loader_binding_refused")
    path = directory / "loader.bin"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o400
             and before.st_size == size, "loader_copy_refused")
        raw = source.read(size + 1)
        need(identity(os.fstat(source.fileno())) == identity(before) == identity(path.lstat())
             and len(raw) == size and sha256(raw).hexdigest() == digest, "loader_copy_changed")
    return raw


def child_record(pid, unit, cgroup, uid, parent):
    return dict(unit=unit, role="child", pid=pid, ppid=parent, uid=uid, cgroup=cgroup)


def pinned_child(parent, cfg, argv):
    pid = root_test.only_child(parent)
    handle = resource.pin_record(child_record(pid, cfg["unit"], cfg["cgroup"], cfg["uid"], parent),
                                 unit=cfg["unit"], uid=cfg["uid"], role="child", cgroup=cfg["cgroup"],
                                 expected_argv=argv, ppid=parent)
    return pid, handle


def probe_cwd_locked():
    """Valid-directory probes, not invalid-pointer/EBADF false positives."""
    before = identity(os.stat("."))
    need(os.getcwd() == "/cwd" and not list(Path("/cwd").iterdir()), "cwd_initial_refused")
    directory = os.open("/decoy", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for operation in (lambda: os.chdir("/decoy"), lambda: os.fchdir(directory)):
            try: operation()
            except OSError as error: need(error.errno == errno.EPERM, "cwd_errno_refused")
            else: raise Refusal("cwd_change_allowed")
        need(identity(os.stat(".")) == before and os.getcwd() == "/cwd", "cwd_changed")
    finally:
        os.close(directory)


def keep_private_decoy_fd():
    directory = os.open("/decoy", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    if directory != 3:
        os.dup2(directory, 3, inheritable=True); os.close(directory)
    else: os.set_inheritable(3, True)
    need(stat.S_ISDIR(os.fstat(3).st_mode) and
         root_test.identity(os.fstat(3)) == root_test.identity(os.stat("/decoy")) and
         os.get_inheritable(3), "private_directory_fd_refused")
    root_test.close_except({3})  # only an internal sealed-root directory, never an outside fd


def stage(cfg, fd):
    """Trusted synthetic namespace-init only; no supplied code/path selection."""
    control = socket.socket(fileno=fd); phase = "boot"
    try:
        control.settimeout(4)
        control.sendall(b"boot"); need(control.recv(32) == b"go", "stage_release_refused")
        names(cfg["unit"], cfg["root"])
        lookup = cfg["unit"].startswith("starfur-c8-")
        cwd = lookup or cfg["unit"].startswith("starfur-c5-")
        need(os.getpid() == 1 and all(root_test.namespaces()[n] != cfg["outside"][n] for n in root_test.NS), "namespace_unverified")
        need(Path("/proc/self/uid_map").read_text().split() == ["0", str(cfg["uid"]), "1"], "uid_map_refused")
        directory = Path(cfg["root"])
        need(directory.resolve() == directory and root_test.identity(directory.lstat()) == cfg["root_id"]
             and directory.stat().st_uid == os.getuid() and stat.S_IMODE(directory.stat().st_mode) == 0o700, "fixture_changed")
        new = directory / "root"
        need(new.resolve() == new and root_test.identity(new.lstat()) == cfg["new_id"]
             and not list(new.iterdir()), "candidate_root_changed")
        loader = read_loader_copy(directory, cfg["loader_hash"], cfg["loader_size"])
        need(all(not any(f.startswith(("shared:", "master:", "propagate_from:"))
                         for f in line.split(" - ", 1)[0].split()[6:]) for line in root_test.mounts()), "propagation_unverified")
        lib = ctypes.CDLL(None, use_errno=True)
        lib.mount.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p)
        lib.umount2.argtypes = (ctypes.c_char_p, ctypes.c_int); lib.syscall.restype = ctypes.c_long
        root_test.syscall_policy.verify_abi()
        if cwd: cwd_policy.verify_abi()
        phase = "root"
        root_test.checked(lib.mount(b"tmpfs", os.fsencode(new), b"tmpfs", 6, b"size=4m,mode=0700"), "tmpfs_refused")
        for name in ("proc", "formats", "old-root", "lib64", "positive", "negative", "decoy", "cwd", "transitive"):
            (new / name).mkdir(mode=0o700)
        (new / "marker").write_bytes(root_test.MARKER)
        root_test.checked(lib.mount(b"proc", os.fsencode(new / "proc"), b"proc", 14, None), "proc_refused")
        root_test.checked(lib.mount(b"binfmt_misc", os.fsencode(new / "formats"), b"binfmt_misc", 15, None), "registry_refused")
        root_test.require_empty_registry(new / "formats", cfg["registry_device"])
        write_new(new / "lib64/ld-linux-x86-64.so.2", loader, 0o500)
        if lookup:
            for name, _ in cases(True):
                write_new(new / name / "main", lookup_fixtures.main_bytes(), 0o500)
            for name in ("positive", "decoy", "transitive"):
                write_new(new / name / "libfixture.so", lookup_fixtures.library_bytes(decoy=name == "decoy"), 0o400)
            for name in ("positive", "decoy"):
                write_new(new / name / "libfixture-leaf.so", lookup_fixtures.leaf_bytes(), 0o400)
        else:
            for name in ("positive", "negative"):
                write_new(new / name / "main", fixture_bytes.cwd_canary_bytes() if cwd else fixture_bytes.canary_bytes(), 0o500)
            write_new(new / "positive/libfixture.so", fixture_bytes.library_bytes(), 0o400)
            write_new(new / "decoy/libfixture.so", fixture_bytes.library_bytes(decoy=True), 0o400)
        need(sha256((new / "lib64/ld-linux-x86-64.so.2").read_bytes()).hexdigest() == cfg["loader_hash"], "image_loader_changed")
        new_id = root_test.identity(new.stat())
        root_test.checked(lib.syscall(ctypes.c_long(155), ctypes.c_char_p(os.fsencode(new)),
                                    ctypes.c_char_p(os.fsencode(new / "old-root"))), "pivot_refused")
        os.chdir("/"); root_test.checked(lib.umount2(b"/old-root", 2 | 8), "old_root_detach_refused")
        os.rmdir("/old-root")
        root_test.checked(lib.mount(None, b"/", None, 32 | 1 | 2 | 4, None), "seal_refused")
        root_test.close_except({fd}); root_test.drop_privileges(lib)
        if cwd:
            need(len(list(Path("/proc/self/task").iterdir())) == 1, "single_thread_required")
            # Explicitly sever any prior FS-struct sharing before installing guards/forking.
            root_test.checked(lib.syscall(ctypes.c_long(272), ctypes.c_long(cwd_policy.CLONE_FS)), "fs_unshare_refused")
        root_test.syscall_policy.install(lib)
        probe_cfg = dict(root=cfg["root"], binfmt=True, syscalls=True, registry_device=cfg["registry_device"])
        root_test.probe(probe_cfg, new_id, {fd}); root_test.probe_syscall_guard(lib)
        if cwd:
            os.chdir("/cwd"); cwd_policy.install(lib); probe_cwd_locked()
        for label, expected in cases(lookup):
            phase = label
            read_fd, write_fd = os.pipe()
            child = os.fork()
            if child == 0:
                try:
                    control.close(); os.close(write_fd)
                    root_test.close_except({read_fd})
                    need(os.read(read_fd, 1) == b"1", "child_release_refused")
                    os.close(read_fd)
                    if cwd:
                        probe_cwd_locked(); keep_private_decoy_fd()
                    else:
                        os.chdir("/decoy"); root_test.close_except(set())
                    argv = canary_command(label, lookup)
                    os.execve(argv[0], argv, {"LANG": "C"})
                finally:
                    os._exit(111)
            os.close(read_fd)
            try:
                control.sendall(label.encode("ascii"))
                need(control.recv(32) == ("go-" + label).encode("ascii"), "child_release_refused")
                os.write(write_fd, b"1")
            finally:
                os.close(write_fd)
            waited, status = os.waitpid(child, 0)
            need(waited == child and os.waitstatus_to_exitcode(status) == expected, label + "_result_refused")
        control.sendall(b"passed"); need(control.recv(32) == b"finish", "finish_refused")
    except BaseException as error:
        try:
            label = str(error) if isinstance(error, (Refusal, root_test.Refusal)) else type(error).__name__
            if re.fullmatch(r"[A-Za-z0-9_]{1,64}", label) is None: label = "native_error"
            control.sendall(("STOP:" + phase + ":" + label).encode("ascii"))
        except OSError:
            pass
        raise
    finally:
        control.close()


def supervise(cfg):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    handles = []
    with parent, child:
        parent.settimeout(5)
        argv = (PYTHON, "-I", "-B", "-S", SCRIPT, "--stage", json.dumps(cfg, sort_keys=True), str(child.fileno()))
        command = ("/usr/bin/unshare", "--user", "--map-root-user", "--mount", "--propagation", "private",
                   "--pid", "--fork", "--kill-child", "--mount-proc", "--net", "--", *argv)
        process = subprocess.Popen(command, env=root_test.ENV, close_fds=True, pass_fds=(child.fileno(),),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            handles.append(os.pidfd_open(process.pid)); child.close()
            root_test.receive_phase(parent, b"boot")
            init, handle = pinned_child(process.pid, cfg, argv); handles.append(handle)
            parent.sendall(b"go")
            lookup = cfg["unit"].startswith("starfur-c8-")
            for text, _ in cases(lookup):
                label = text.encode("ascii")
                root_test.receive_phase(parent, label)
                _, handle = pinned_child(init, cfg, argv); handles.append(handle)
                parent.sendall(b"go-" + label)
            root_test.receive_phase(parent, b"passed"); parent.sendall(b"finish")
            need(process.wait(timeout=2) == 0, "stage_exit_refused")
            need(len(handles) == (6 if lookup else 4) and all(select.select([h], [], [], 1)[0] for h in handles), "descendant_exit_unverified")
        finally:
            try:
                if process.poll() is None:
                    if handles:
                        signal.pidfd_send_signal(handles[0], signal.SIGKILL)
                    else:
                        process.kill()  # owned Popen only; stage has not received go
                process.wait(timeout=2)
                need(all(select.select([h], [], [], 2)[0] for h in handles), "descendant_cleanup_unverified")
            finally:
                for handle in handles: os.close(handle)


def worker(unit, directory):
    token = names(unit, directory)
    need(dict(os.environ) == {"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"}, "worker_environment_refused")
    root = resource.fixture(directory)
    resource.publish(root, "ready", resource.process_record(unit, "worker"))
    go = resource.wait_record(root, "go", time.monotonic() + 6)
    need(set(go) == {"nonce", "loader_hash", "loader_size"} and go["nonce"] == token, "release_refused")
    registry = root_test.registry_snapshot()
    cfg = dict(unit=unit, root=directory, uid=os.getuid(), outside=root_test.namespaces(),
               root_id=root_test.identity(root.stat()), new_id=root_test.identity((root / "root").stat()),
               loader_hash=go["loader_hash"], loader_size=go["loader_size"], registry_device=registry[0],
               cgroup=resource.process_record(unit, "worker")["cgroup"])
    try:
        supervise(cfg)
        need(root_test.registry_snapshot() == registry, "parent_registry_changed")
        resource.publish(root, "child", success_record(go["loader_hash"], unit.startswith("starfur-c8-")))
    except BaseException as error:
        resource.publish(root, "child", dict(ok=False, failure=failure_label(error)))
        raise
    while True: signal.pause()


def main(expected_digest, *, cwd=False, lookup=False):
    need(type(cwd) is bool and type(lookup) is bool and not (cwd and lookup), "mode_refused")
    need(type(expected_digest) is str and re.fullmatch(r"[0-9a-f]{64}", expected_digest), "expected_loader_digest_refused")
    need(sys.platform == "linux" and os.getuid() == 1000 and os.uname().machine == "x86_64"
         and hasattr(signal, "pidfd_send_signal"), "supported_host_required")
    uid = os.getuid(); snapshot = resource.parent_snapshot(uid); registry = root_test.registry_snapshot()
    raw, digest = acquire_loader()
    need(digest == expected_digest, "reviewed_loader_changed")
    token = uuid.uuid4().hex; unit = ("starfur-c8-" if lookup else "starfur-c5-" if cwd else "starfur-c4-") + token + ".service"
    need(resource.unit_info(unit, uid).get("LoadState") == "not-found", "unit_exists")
    root = Path(tempfile.mkdtemp(prefix="sf-worker-loader-" + token + "-", dir="/tmp"))
    binding = None; handle = None; group = resource.parent_group(uid) / unit
    try:
        (root / "root").mkdir(mode=0o700); write_new(root / "loader.bin", raw, 0o400)
        args = unit_command(unit, str(root), sys.executable, str(Path(__file__).resolve()))
        need(resource.command(args, uid, capture=False, timeout=4).returncode == 0, "unit_start_refused")
        started = resource.unit_info(unit, uid)
        resource.check_unit(started, unit, uid); binding = started["InvocationID"]
        ready = resource.wait_record(root, "ready", time.monotonic() + 4)
        info = resource.unit_info(unit, uid); cgroup = resource.check_unit(info, unit, uid)
        need(info["InvocationID"] == binding, "startup_epoch_changed")
        need(str(ready.get("pid")) == info.get("MainPID"), "main_pid_changed")
        argv = args[args.index("/usr/bin/env") + 4:]
        handle = resource.pin_record(ready, unit=unit, uid=uid, role="worker", cgroup=cgroup, expected_argv=argv)
        resource.verify_limits({n: (group / n).read_text() for n in
                                ("cpu.max", "memory.max", "memory.swap.max", "pids.max")})
        need(resource.unit_info(unit, uid).get("InvocationID") == binding
             and resource.parent_snapshot(uid) == snapshot, "unit_binding_changed")
        resource.publish(root, "go", dict(nonce=token, loader_hash=digest, loader_size=len(raw)))
        result = resource.wait_record(root, "child", time.monotonic() + 7)
        if (type(result) is dict and set(result) == {"ok", "failure"} and result["ok"] is False
                and type(result["failure"]) is str and re.fullmatch(r"[A-Za-z0-9_:]{1,192}", result["failure"])):
            raise Refusal(result["failure"])
        need(result == success_record(digest, lookup), "loader_gate_failed")
        need(resource.unit_info(unit, uid).get("InvocationID") == binding, "cleanup_epoch_changed")
        need(resource.command(("/usr/bin/systemctl", "--user", "--no-ask-password", "stop", "--", unit),
                              uid, capture=False, timeout=4).returncode == 0, "unit_stop_refused")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and (group.exists() or resource.unit_info(unit, uid).get("LoadState") != "not-found"):
            time.sleep(0.05)
        need(select.select([handle], [], [], 0)[0] and not group.exists()
             and resource.unit_info(unit, uid).get("LoadState") == "not-found", "unit_cleanup_unverified")
        need(resource.parent_snapshot(uid) == snapshot and root_test.registry_snapshot() == registry, "parent_state_changed")
        need({p.name for p in root.iterdir()} == {"root", "loader.bin", "ready.json", "go.json", "child.json"}
             and (root / "root").resolve() == root / "root" and not list((root / "root").iterdir()), "fixture_cleanup_refused")
        read_loader_copy(root, digest, len(raw))
        for name in ("ready", "go", "child"):
            resource.read_record(root, name); (root / (name + ".json")).unlink()
        (root / "loader.bin").unlink(); (root / "root").rmdir(); root.rmdir()
    except BaseException:
        if binding is not None:
            current = resource.unit_info(unit, uid)
            if current.get("LoadState") != "not-found":
                need(current.get("InvocationID") == binding, "cleanup_epoch_changed")
                need(resource.command(("/usr/bin/systemctl", "--user", "--no-ask-password", "stop", "--", unit),
                                      uid, capture=False, timeout=4).returncode == 0, "unit_stop_failed")
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and (group.exists() or resource.unit_info(unit, uid).get("LoadState") != "not-found"):
                time.sleep(0.05)
            need(not group.exists() and resource.unit_info(unit, uid).get("LoadState") == "not-found"
                 and (handle is None or select.select([handle], [], [], 0)[0]), "failure_cleanup_unverified")
        print("STOP retained synthetic loader fixture: " + str(root), file=sys.stderr)
        raise
    finally:
        if handle is not None: os.close(handle)
    print("PASS " + ("C8 direct loader intended42/decoy13/missing127/transitive-missing127" if lookup else "C5 cwd parent/fork/exec denied, mixed intended42/missing127" if cwd else "C4 intended42/missing127") +
          " with decoy13, exact bindings/limits and complete cleanup")
    print("Synthetic loader prerequisite only; not real-worker/dlopen/CPU/security readiness")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "--worker":
            worker(sys.argv[2], sys.argv[3])
        elif len(sys.argv) == 4 and sys.argv[1] == "--stage":
            stage(json.loads(sys.argv[2]), int(sys.argv[3]))
        else:
            need(len(sys.argv) in (3, 4) and sys.argv[1] == "--expect-loader" and
                 (len(sys.argv) == 3 or sys.argv[3] in ("--cwd-prerequisite", "--lookup-prerequisite")), "arguments_refused")
            signal.signal(signal.SIGTERM, resource.interrupt)
            main(sys.argv[2], cwd=len(sys.argv) == 4 and sys.argv[3] == "--cwd-prerequisite",
                 lookup=len(sys.argv) == 4 and sys.argv[3] == "--lookup-prerequisite")
    except BaseException as error:
        label = failure_label(error)
        print("STOP loader prerequisite: " + label, file=sys.stderr); sys.exit(1)
