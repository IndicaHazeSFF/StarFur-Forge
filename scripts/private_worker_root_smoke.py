"""Opt-in synthetic root / N2b.2a binfmt prerequisite; not an interop barrier.

No Windows execution, host services, inference, installs or global changes.
Only a private namespace's tmpfs root and owned /tmp fixture are changed.
--binfmt-prerequisite adds a fresh read-only namespace-private registry and
a fixed Linux-only exit canary, never a Windows executable or registration.
"""
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile

_policy_spec = importlib.util.spec_from_file_location(
    "synthetic_worker_syscalls", Path(__file__).with_name("private_worker_syscall_policy.py"))
syscall_policy = importlib.util.module_from_spec(_policy_spec)
_policy_spec.loader.exec_module(syscall_policy)  # inert; native install is opt-in

ENV = {"PATH": "/usr/bin:/usr/sbin", "LANG": "C"}
PY = (sys.executable, "-I", "-B", "-S", str(Path(__file__).resolve()))
NS = ("user", "net", "pid", "mnt")
MARKER = b"synthetic-inside"


def linux_canary_bytes():
    """Fixed x86-64 Linux ELF: exit(42), no loader, files, sockets or input."""
    code = bytes.fromhex("b83c000000bf2a0000000f05")
    size = 64 + 56 + len(code)
    header = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                         2, 62, 1, 0x400078, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    segment = struct.pack("<IIQQQQQQ", 1, 5, 0, 0x400000, 0x400000, size, size, 4096)
    return header + segment + code


def registry_snapshot():
    """Bounded read-only parent registry observation; never write/register."""
    base = Path("/proc/sys/fs/binfmt_misc")
    names = sorted(p.name for p in base.iterdir())
    need(len(names) <= 64 and "WSLInterop" in names and "status" in names,
         "parent_registry_unavailable")
    out = []
    for name in names:
        need(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name), "registry_name_refused")
        if name == "register":
            continue  # write-only control; must never open it
        with (base / name).open("rb") as source:
            raw = source.read(4097)
        need(len(raw) <= 4096, "registry_observation_too_large")
        out.append((name, raw))
    need(dict(out)["status"] == b"enabled\n", "parent_registry_not_enabled")
    return base.stat().st_dev, tuple(out)


def require_empty_registry(path, parent_device):
    need(path.stat().st_dev != parent_device, "registry_instance_not_separate")
    need({p.name for p in path.iterdir()} == {"register", "status"},
         "registry_not_empty")
    need((path / "status").read_bytes() == b"enabled\n", "private_registry_unavailable")


def exec_linux_canary():
    # No shell, interpreter, search path, Windows magic, host path or user args.
    os.execve("/linux-canary", ("/linux-canary",), {"LANG": "C"})
    raise Refusal("canary_exec_returned")


def probe_syscall_guard(lib):
    # Socket creation only: never connect to a host, Windows endpoint or relay.
    for family in (socket.AF_UNIX, socket.AF_NETLINK, socket.AF_VSOCK):
        try:
            candidate = socket.socket(family, socket.SOCK_STREAM)
        except OSError as error:
            need(error.errno == errno.EPERM, "socket_guard_unverified")
        else:
            candidate.close()
            raise Refusal("host_socket_creation_allowed")
    for family in (socket.AF_INET, socket.AF_INET6):
        with socket.socket(family, socket.SOCK_STREAM):
            pass  # private namespace only, no bind/connect or external address
    ctypes.set_errno(0)
    result = lib.syscall(ctypes.c_long(syscall_policy.NUMBERS["unshare"]), ctypes.c_long(0))
    need(result == -1 and ctypes.get_errno() == errno.EPERM,
         "namespace_guard_unverified")  # unshare(0) is harmless if guard is broken


# CPython may import ctypes._layout when Structure fields are declared. Do
# this before namespace/root changes, not after host libraries are detached.
class CapabilityHeader(ctypes.Structure):
    _fields_ = (("version", ctypes.c_uint32), ("pid", ctypes.c_int))


class CapabilityData(ctypes.Structure):
    _fields_ = (("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32),
                ("inheritable", ctypes.c_uint32))


CapabilityDataArray = CapabilityData * 2


class Refusal(RuntimeError):
    pass


def need(condition, label):
    if not condition:
        raise Refusal(label)


def identity(value):
    return [value.st_dev, value.st_ino]


def namespaces():
    return {key: os.readlink(f"/proc/self/ns/{key}") for key in NS}


def mounts():
    return Path("/proc/self/mountinfo").read_text().splitlines()


def checked(result, label):
    need(result == 0, label)


def drop_privileges(lib):
    # Linux ABI v3. These are namespace-local caps; no host-root privilege.
    for cap in range(64):
        result = lib.prctl(24, cap, 0, 0, 0)  # PR_CAPBSET_DROP
        if result != 0:
            need(ctypes.get_errno() == errno.EINVAL and cap > 0, "capability_drop_failed")
            break
    checked(lib.prctl(47, 4, 0, 0, 0), "ambient_clear_failed")
    checked(lib.prctl(38, 1, 0, 0, 0), "no_new_privileges_failed")
    header, data = CapabilityHeader(0x20080522, 0), CapabilityDataArray()
    checked(lib.syscall(ctypes.c_long(126), ctypes.byref(header), ctypes.byref(data)), "capset_failed")
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    need(all(int(status[k], 16) == 0 for k in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb"))
         and status["NoNewPrivs"].strip() == "1", "capability_state_unverified")


def close_except(allowed):
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd not in allowed:
            try:
                os.close(fd)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise


def probe(cfg, new_id, allowed):
    need(identity(os.stat("/")) == new_id and os.getcwd() == "/", "root_or_cwd_changed")
    need(Path("/marker").read_bytes() == MARKER, "inside_marker_failed")
    expected_mounts = {"/", "/proc", "/formats"} if cfg.get("binfmt") else {"/", "/proc"}
    need({line.split()[4] for line in mounts()} == expected_mounts, "old_mount_visible")
    if cfg.get("binfmt"):
        require_empty_registry(Path("/formats"), cfg["registry_device"])
        try:
            write_fd = os.open("/write-canary", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as error:
            need(error.errno == errno.EROFS, "root_read_only_unverified")
        else:
            os.close(write_fd)
            raise Refusal("root_writable")
    need(Path("/proc/self/root").resolve() == Path("/"), "proc_root_changed")
    try:
        os.stat(cfg["root"] + "/outside")
    except FileNotFoundError:
        pass
    else:
        raise Refusal("outside_canary_visible")
    if not cfg.get("syscalls"):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(0.5)
            need(conn.connect_ex(cfg["root"] + "/canary.sock") == errno.ENOENT,
                 "outside_socket_reachable")
    close_except(allowed)
    # No directory or other inherited outside handle remains open.
    for fd in allowed:
        need(not stat.S_ISDIR(os.fstat(fd).st_mode), "outside_directory_handle")


def stage(cfg, fd):
    control = socket.socket(fileno=fd)
    phase = "initial"
    try:
        control.settimeout(5)
        # Do not start isolation work until the supervisor owns our pidfd.
        control.sendall(b"boot")
        need(control.recv(16) == b"go", "control_start_refused")
        need(os.getpid() == 1 and all(namespaces()[key] != cfg["outside"][key] for key in NS),
             "namespace_not_isolated")
        need(Path("/proc/self/uid_map").read_text().split() == ["0", str(cfg["uid"]), "1"]
             and cfg["uid"] > 0, "uid_map_refused")
        root = Path(cfg["root"])
        need(root.parent == Path("/tmp") and root.resolve() == root
             and re.fullmatch(r"sf-worker-root-[a-z0-9_]+", root.name), "fixture_path_refused")
        info = root.lstat()
        need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
             and info.st_uid == os.getuid() and identity(info) == cfg["root_id"],
             "fixture_identity_changed")
        new = root / "root"
        need(new.resolve() == new and list(new.iterdir()) == []
             and identity(new.lstat()) == cfg["new_id"], "candidate_root_changed")
        need(all(not any(f.startswith(("shared:", "master:", "propagate_from:"))
                         for f in line.split(" - ", 1)[0].split()[6:]) for line in mounts()),
             "mount_propagation_not_private")
        phase = "load_library"
        # Load all library entry points before old-root detachment.
        lib = ctypes.CDLL(None, use_errno=True)
        lib.mount.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                              ctypes.c_ulong, ctypes.c_char_p)
        lib.umount2.argtypes = (ctypes.c_char_p, ctypes.c_int)
        lib.syscall.restype = ctypes.c_long
        if cfg.get("syscalls"):
            syscall_policy.verify_abi()  # headers are read before root detachment
        phase = "private_root"
        checked(lib.mount(b"tmpfs", os.fsencode(new), b"tmpfs", 6, b"size=4m,mode=0700"),
                "private_tmpfs_failed")
        (new / "proc").mkdir(mode=0o700)
        (new / "old-root").mkdir(mode=0o700)
        (new / "marker").write_bytes(MARKER)
        checked(lib.mount(b"proc", os.fsencode(new / "proc"), b"proc", 14, None),
                "private_proc_failed")
        if cfg.get("binfmt"):
            phase = "private_registry"
            (new / "formats").mkdir(mode=0o700)
            # A fresh filesystem mount, NOT a bind of the inherited registry.
            # Read-only + nosuid/nodev/noexec; no status/register write follows.
            checked(lib.mount(b"binfmt_misc", os.fsencode(new / "formats"),
                              b"binfmt_misc", 15, None), "private_registry_mount_refused")
            require_empty_registry(new / "formats", cfg["registry_device"])
            (new / "linux-canary").write_bytes(linux_canary_bytes())
            (new / "linux-canary").chmod(0o500)
        new_id = identity(new.stat())
        phase = "pivot"
        checked(lib.syscall(ctypes.c_long(155), ctypes.c_char_p(os.fsencode(new)),
                            ctypes.c_char_p(os.fsencode(new / "old-root"))), "pivot_root_failed")
        os.chdir("/")
        checked(lib.umount2(b"/old-root", 2 | 8), "old_root_detach_failed")
        os.rmdir("/old-root")
        if cfg.get("binfmt"):
            # Seal all fixture-root bytes before executing the fixed canary.
            checked(lib.mount(None, b"/", None, 32 | 1 | 2 | 4, None),
                    "fixture_root_seal_failed")
        phase = "close_handles"
        close_except({fd})
        phase = "drop_capabilities"
        drop_privileges(lib)
        if cfg.get("syscalls"):
            phase = "syscall_guard"
            syscall_policy.install(lib)
            probe_syscall_guard(lib)
        phase = "root_probe"
        probe(cfg, new_id, {fd})
        phase = "descendant"
        read_fd, write_fd = os.pipe()
        gate_read, gate_write = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                control.close()
                os.close(read_fd)
                os.close(gate_write)
                close_except({write_fd, gate_read})
                need(os.read(gate_read, 1) == b"1", "descendant_start_refused")
                os.close(gate_read)
                close_except({write_fd})
                probe(cfg, new_id, {write_fd})
                if cfg.get("syscalls"):
                    probe_syscall_guard(lib)
                os.write(write_fd, b"1")
                os.close(write_fd)
                if cfg.get("binfmt"):
                    exec_linux_canary()
                signal.pause()
            finally:
                os._exit(1)
        os.close(write_fd)
        os.close(gate_read)
        try:
            # Child is blocked on its private gate until its pidfd is captured.
            control.sendall(b"child")
            need(control.recv(16) == b"child-go", "descendant_start_refused")
            os.write(gate_write, b"1")
            os.close(gate_write)
            gate_write = None
            need(bool(select.select([read_fd], [], [], 2)[0]) and os.read(read_fd, 1) == b"1",
                 "descendant_root_probe_failed")
        finally:
            if gate_write is not None:
                os.close(gate_write)
            os.close(read_fd)
        if cfg.get("binfmt"):
            waited, status = os.waitpid(child, 0)
            need(waited == child and os.waitstatus_to_exitcode(status) == 42,
                 "linux_canary_failed")
        control.sendall(b"ready")
        need(control.recv(16) == b"never", "unexpected_control_exit")
    except BaseException as error:
        try:
            label = str(error) if type(error) is Refusal else type(error).__name__
            if re.fullmatch(r"[A-Za-z0-9_]{1,64}", label) is None:
                label = "native_error"
            control.sendall(f"STOP:{phase}:{label}".encode("ascii"))
        except OSError:
            pass
        raise
    finally:
        control.close()


def only_child(pid):
    values = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    need(len(values) == 1 and values[0].isdigit(), "process_identity_unverified")
    return int(values[0])


def capture_child(parent_pid):
    """Pin the observed direct child before allowing its test phase to run."""
    pid = only_child(parent_pid)
    # Start time plus direct-parent membership fences a PID-reuse observation.
    before = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    handle = os.pidfd_open(pid)
    try:
        after = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        need(before == after and only_child(parent_pid) == pid
             and not select.select([handle], [], [], 0)[0], "process_identity_changed")
        return pid, handle
    except BaseException:
        os.close(handle)
        raise


def receive_phase(control, expected):
    result = control.recv(128)
    if result.startswith(b"STOP:"):
        # Worker diagnostics are closed phase/category labels, never raw errors.
        label = result.decode("ascii")
        need(re.fullmatch(r"STOP:[A-Za-z0-9_]{1,64}:[A-Za-z0-9_]{1,64}", label),
             "startup_diagnostic_invalid")
        raise Refusal(label)
    need(result == expected, "fixture_not_ready")


def supervise(cfg):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    handles = []
    with parent, child:
        parent.settimeout(8)
        cmd = ("/usr/bin/unshare", "--user", "--map-root-user", "--mount",
               "--propagation", "private", "--pid", "--fork", "--kill-child",
               "--mount-proc", "--net", "--", *PY, "--worker", json.dumps(cfg), str(child.fileno()))
        process = subprocess.Popen(cmd, env=ENV, close_fds=True, pass_fds=(child.fileno(),),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            child.close()
            receive_phase(parent, b"boot")
            init, handle = capture_child(process.pid)
            handles.append(handle)
            parent.sendall(b"go")
            receive_phase(parent, b"child")
            _, handle = capture_child(init)
            handles.append(handle)
            parent.sendall(b"child-go")
            receive_phase(parent, b"ready")
            need(not select.select([handles[0]], [], [], 0)[0], "fixture_exited_early")
            child_exited = bool(select.select([handles[1]], [], [], 0)[0])
            need(child_exited == bool(cfg.get("binfmt")), "descendant_lifetime_changed")
        finally:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
                for handle in handles:
                    need(bool(select.select([handle], [], [], 1)[0]), "process_cleanup_unverified")
            finally:
                for handle in handles:
                    os.close(handle)


def positive(listener, socket_path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(0.5)
        conn.connect(str(socket_path))
        accepted, _ = listener.accept()
        accepted.close()


def main(*, binfmt=False, syscalls=False):
    need(not syscalls or binfmt, "registry_prerequisite_required")
    need(sys.platform == "linux" and os.geteuid() != 0 and os.uname().machine == "x86_64"
         and hasattr(os, "pidfd_open"), "supported_unprivileged_host_required")
    header = Path("/usr/include/x86_64-linux-gnu/asm/unistd_64.h").read_text()
    need(all(re.search(rf"^#define __NR_{name} {number}$", header, re.M)
             for name, number in (("pivot_root", 155), ("capset", 126))), "syscall_abi_unverified")
    need(Path("/tmp").resolve() == Path("/tmp"), "temporary_path_refused")
    fs = subprocess.check_output(("/usr/bin/findmnt", "-n", "-o", "FSTYPE", "-T", "/tmp"),
                                 env=ENV, timeout=2)
    need(fs.strip() in {b"tmpfs", b"ext4"}, "non_linux_fixture_refused")
    registry = registry_snapshot() if binfmt else None
    root = Path(tempfile.mkdtemp(prefix="sf-worker-root-", dir="/tmp"))
    try:
        (root / "root").mkdir(mode=0o700)
        outside = root / "outside"
        outside.write_bytes(b"synthetic-outside")
        path = root / "canary.sock"
        original_mounts, original_namespaces = mounts(), namespaces()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.settimeout(1)
            listener.bind(str(path))
            listener.listen(1)
            original = identity(path.lstat())
            positive(listener, path)
            cfg = dict(root=str(root), uid=os.getuid(), root_id=identity(root.stat()),
                       new_id=identity((root / "root").stat()), outside=original_namespaces)
            if binfmt:
                cfg.update(binfmt=True, registry_device=registry[0])
            if syscalls:
                cfg["syscalls"] = True
            supervise(cfg)
            need(mounts() == original_mounts and namespaces() == original_namespaces
                 and identity(path.lstat()) == original and list((root / "root").iterdir()) == []
                 and outside.read_bytes() == b"synthetic-outside", "parent_state_changed")
            need(not select.select([listener], [], [], 0)[0], "unexpected_canary_connection")
            positive(listener, path)
        if binfmt:
            need(registry_snapshot() == registry, "parent_registry_changed")
        need(stat.S_ISSOCK(path.lstat().st_mode) and identity(path.lstat()) == original,
             "cleanup_socket_changed")
        path.unlink()
        outside.unlink()
        (root / "root").rmdir()
        root.rmdir()
    except BaseException:
        print(f"STOP retained test-owned fixture: {root}", file=sys.stderr)
        raise
    if syscalls:
        print("PASS N2b.2b synthetic inherited syscall/socket guard and Linux exec")
        print("Guard is not a production syscall allowlist or complete sandbox")
    elif binfmt:
        print("PASS N2b.2a private empty registry, sealed root, fixed Linux exec and cleanup")
    else:
        print("PASS N2b.1 restricted root, old-root detachment, capability drop, child and cleanup")
    print("Windows interop, real inference and deployment remain unverified")


def interrupt(_signal, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt)
    try:
        if len(sys.argv) == 1:
            main()
        elif sys.argv[1:] == ["--binfmt-prerequisite"]:
            main(binfmt=True)
        elif sys.argv[1:] == ["--syscall-prerequisite"]:
            main(binfmt=True, syscalls=True)
        elif len(sys.argv) == 4 and sys.argv[1] == "--worker":
            stage(json.loads(sys.argv[2]), int(sys.argv[3]))
        else:
            raise Refusal("invalid_arguments")
    except Refusal as error:
        print(f"STOP {error}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print(f"STOP unsupported/interrupted smoke: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
