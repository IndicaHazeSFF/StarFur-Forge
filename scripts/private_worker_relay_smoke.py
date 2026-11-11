"""Opt-in N2a: disposable rootless pathname socket/descriptor smoke only.

No real service, Windows path/executable, model or network connection. The sole
mount target is a new fixture directory on WSL /tmp inside a private namespace.
This is not a production launcher or interop/confinement proof.
"""
from array import array
import errno
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

ENV = {"PATH": "/usr/bin:/usr/sbin", "LANG": "C"}
PY = (sys.executable, "-I", "-B", "-S", str(Path(__file__).resolve()))
NS = ("user", "net", "pid", "mnt")
LIMIT = 16
INT_SIZE = array("i").itemsize


class Refusal(RuntimeError):
    pass


def need(condition, label):
    if not condition:
        raise Refusal(label)


def namespaces():
    return {key: os.readlink(f"/proc/self/ns/{key}") for key in NS}


def identity(info):
    return [info.st_dev, info.st_ino]


def fd_ids():
    result = []
    for name in os.listdir("/proc/self/fd"):
        try:
            result.append(identity(os.fstat(int(name))))
        except OSError as error:
            if error.errno != errno.EBADF:
                raise
    return sorted(result)


def fixture(cfg):
    root = Path(cfg["root"])
    need(root.parent == Path("/tmp") and re.fullmatch(r"sf-worker-relay-[a-z0-9_]+", root.name)
         and root.resolve() == root, "fixture_path_refused")
    for path in (root, root / "canary", root / "empty"):
        info = path.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
             and stat.S_IMODE(info.st_mode) == 0o700 and info.st_dev == root.stat().st_dev,
             "fixture_identity_refused")
    need(identity(root.stat()) == cfg["root_id"], "fixture_changed")
    return root


def mount_view():
    return Path("/proc/self/mountinfo").read_text().splitlines()


def verify_isolated(cfg):
    current = namespaces()
    need(all(current[key] != cfg["outside"][key] for key in NS), "namespace_not_distinct")
    uid_map = Path("/proc/self/uid_map").read_text().split()
    need(uid_map == ["0", str(cfg["uid"]), "1"] and cfg["uid"] > 0, "uid_mapping_refused")
    return current


def verify_unprivileged():
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    need(all(int(status[key], 16) == 0 for key in ("CapEff", "CapPrm", "CapBnd"))
         and status["NoNewPrivs"].strip() == "1", "privilege_drop_unverified")


def setup(cfg, fd):
    verify_isolated(cfg)
    need(os.getpid() == 1, "not_namespace_init")
    root = fixture(cfg)
    mounts = mount_view()
    need(all(not any(field.startswith(("shared:", "master:", "propagate_from:"))
                     for field in line.split(" - ", 1)[0].split()[6:]) for line in mounts),
         "mount_propagation_not_private")
    source, target = root / "empty", root / "canary"
    need(identity(source.stat()) == cfg["empty_id"]
         and identity(target.stat()) == cfg["canary_id"]
         and source.resolve() == source and target.resolve() == target
         and list(source.iterdir()) == [] and {p.name for p in target.iterdir()} == {"relay.sock"},
         "mount_fixture_changed")
    if cfg["masked"]:
        subprocess.run(("/usr/bin/mount", "-i", "-n", "--bind", "--", str(source), str(target)),
                       env=ENV, check=True, timeout=2, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        need(identity(target.stat()) == cfg["empty_id"]
             and any(line.split()[4] == str(target) for line in mount_view()), "mask_not_verified")
    os.execve("/usr/bin/setpriv", ("setpriv", "--bounding-set=-all", "--inh-caps=-all",
              "--ambient-caps=-all", "--no-new-privs", *PY, "--worker", json.dumps(cfg), str(fd)), ENV)


def probe(cfg):
    root = fixture(cfg)
    need(identity((root / "canary").stat()) == cfg["empty_id" if cfg["masked"] else "canary_id"],
         "unexpected_canary_view")
    path = root / "canary" / "relay.sock"
    if cfg["masked"]:
        need(list(path.parent.iterdir()) == [], "masked_directory_not_empty")
    else:
        info = path.lstat()
        need(stat.S_ISSOCK(info.st_mode) and identity(info) == cfg["socket_id"], "canary_socket_changed")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(0.5)
        result = conn.connect_ex(str(path))
    need(result == (errno.ENOENT if cfg["masked"] else 0), "unexpected_canary_reachability")


def receive(control):
    # No ancillary data is valid. Even a rejected packet can have installed
    # descriptors; close delivered rights, including on a truncated message.
    data, ancillary, flags, _ = control.recvmsg(
        LIMIT, socket.CMSG_SPACE(4 * INT_SIZE), socket.MSG_CMSG_CLOEXEC)
    for level, kind, raw in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            delivered = array("i")
            delivered.frombytes(raw[:len(raw) - len(raw) % INT_SIZE])
            for handle in delivered:
                os.close(handle)
    return None if ancillary or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) else data


def descendant(cfg, expected):
    need(namespaces() == expected, "descendant_namespace_changed")
    verify_unprivileged()
    handles = fd_ids()
    need(cfg["control_id"] not in handles and cfg["sentinel_id"] not in handles,
         "descendant_descriptor_leak")
    probe(cfg)
    os.write(1, b"1")
    signal.pause()


def worker(cfg, fd):
    current = verify_isolated(cfg)
    need(os.getpid() == 1, "not_namespace_init")
    verify_unprivileged()
    with socket.socket(fileno=fd) as control:
        control.set_inheritable(False)
        control.settimeout(4)
        cfg["control_id"] = identity(os.fstat(fd))
        need(cfg["sentinel_id"] not in fd_ids(), "sentinel_inherited")
        need(receive(control) == b"go", "control_start_refused")
        probe(cfg)
        before = fd_ids()
        need(receive(control) is None and fd_ids() == before, "rights_refusal_failed")
        need(receive(control) is None and fd_ids() == before, "truncation_refusal_failed")
        child = subprocess.Popen((*PY, "--descendant", json.dumps(cfg), json.dumps(current)),
                                 env=ENV, close_fds=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            need(bool(select.select([child.stdout], [], [], 2)[0])
                 and child.stdout.read(1) == b"1", "descendant_not_ready")
            control.sendall(b"ready")
            need(receive(control) == b"never", "unexpected_control_exit")
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=1)
            child.stdout.close()


def only_child(pid):
    values = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    need(len(values) == 1 and values[0].isdigit(), "child_identity_unverified")
    return int(values[0])


def supervised(cfg, sentinel):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    pidfds = []
    with parent, child:
        parent.settimeout(8)
        command = ("/usr/bin/unshare", "--user", "--map-root-user", "--mount",
                   "--propagation", "private", "--pid", "--fork", "--kill-child",
                   "--mount-proc", "--net", "--", *PY, "--setup", json.dumps(cfg),
                   str(child.fileno()))
        process = subprocess.Popen(command, env=ENV, close_fds=True, pass_fds=(child.fileno(),),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        try:
            child.close()
            parent.sendall(b"go")
            parent.sendmsg([b"rights"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array("i", [sentinel]))])
            parent.sendall(b"x" * (LIMIT + 1))
            need(receive(parent) == b"ready", "fixture_not_ready")
            init = only_child(process.pid)
            for pid in (init, only_child(init)):
                pidfds.append(os.pidfd_open(pid))
            need(not select.select(pidfds, [], [], 0)[0], "fixture_exited_before_cleanup")
        finally:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
                for handle in pidfds:
                    need(bool(select.select([handle], [], [], 1)[0]), "cleanup_unverified")
            finally:
                for handle in pidfds:
                    os.close(handle)


def positive(listener, path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(0.5)
        conn.connect(str(path))
        accepted, _ = listener.accept()
        accepted.close()


def main():
    need(sys.platform == "linux" and os.geteuid() != 0 and hasattr(os, "pidfd_open"),
         "unprivileged_linux_pidfd_required")
    need(Path("/tmp").resolve() == Path("/tmp"), "temporary_path_refused")
    fs = subprocess.check_output(("/usr/bin/findmnt", "-n", "-o", "FSTYPE", "-T", "/tmp"),
                                 env=ENV, timeout=2)
    need(fs.strip() in {b"tmpfs", b"ext4"}, "non_linux_temp_mount_refused")
    root = Path(tempfile.mkdtemp(prefix="sf-worker-relay-", dir="/tmp"))
    canary, empty = root / "canary", root / "empty"
    path = canary / "relay.sock"
    try:
        canary.mkdir(mode=0o700)
        empty.mkdir(mode=0o700)
        initial_mounts = mount_view()
        initial_namespaces = namespaces()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.settimeout(1)
            listener.bind(str(path))
            listener.listen(4)
            socket_id = identity(path.lstat())
            positive(listener, path)
            read_fd, write_fd = os.pipe()
            try:
                os.set_inheritable(read_fd, True)
                cfg = dict(root=str(root), root_id=identity(root.stat()),
                           canary_id=identity(canary.stat()), empty_id=identity(empty.stat()),
                           socket_id=socket_id,
                           outside=initial_namespaces, uid=os.getuid(),
                           sentinel_id=identity(os.fstat(read_fd)))
                for masked in (False, True):
                    supervised(dict(cfg, masked=masked), read_fd)
                    need(namespaces() == initial_namespaces and mount_view() == initial_mounts
                         and identity(path.lstat()) == socket_id
                         and identity(canary.stat()) == cfg["canary_id"], "parent_mount_changed")
                    if not masked:
                        # Exactly one connection from worker and one from child.
                        for _ in range(2):
                            accepted, _ = listener.accept()
                            accepted.close()
                    need(not select.select([listener], [], [], 0)[0], "unexpected_canary_connection")
                    positive(listener, path)
                    print("PASS masked denial" if masked else "PASS unmasked positive control", flush=True)
            finally:
                os.close(read_fd)
                os.close(write_fd)
        fixture(cfg)
        need(stat.S_ISSOCK(path.lstat().st_mode) and identity(path.lstat()) == socket_id,
             "cleanup_target_changed")
        path.unlink()
        canary.rmdir()
        empty.rmdir()
        root.rmdir()
    except BaseException:
        # No broad cleanup on an uncertain boundary or process outcome.
        print(f"STOP retained test-owned fixture for inspection: {root}", file=sys.stderr)
        raise
    print("PASS N2a pathname/descriptor/private-mount controls and cleanup; deployment unverified")


def interrupted(_signal, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if len(sys.argv) == 1:
            main()
        elif len(sys.argv) == 4 and sys.argv[1] in ("--setup", "--worker"):
            (setup if sys.argv[1] == "--setup" else worker)(json.loads(sys.argv[2]), int(sys.argv[3]))
        elif len(sys.argv) == 4 and sys.argv[1] == "--descendant":
            descendant(json.loads(sys.argv[2]), json.loads(sys.argv[3]))
        else:
            raise Refusal("invalid_arguments")
    except Refusal as error:
        print(f"STOP {error}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print(f"STOP native smoke did not complete: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
