"""Opt-in WSL synthetic network/PID namespace smoke, NOT deployment proof.

Run as ordinary roger from the repo root; no sudo, models, host service calls,
GPU, external DNS or persisted namespace. Only one test listener, outside the
namespace, with a positive control before starting the isolated fixtures.
"""
import errno
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys

ENV = {"PATH": "/usr/bin:/usr/sbin", "LANG": "C"}
SCRIPT = str(Path(__file__).resolve())
PYTHON = (sys.executable, "-I", "-B", "-S", SCRIPT)
BLOCKED = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL}


class SmokeError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise SmokeError(code)


def netns():
    return os.readlink("/proc/self/ns/net")


def ip(*args):
    data = subprocess.check_output(
        ["/usr/sbin/ip", *args], env=ENV, timeout=2,
        stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    require(len(data) <= 8192, "ip_output_bound")
    return data


def verify_network(outside):
    require(netns() != outside, "not_isolated")
    links = json.loads(ip("-j", "link", "show"))
    require([link["ifname"] for link in links] == ["lo"], "unexpected_interface")
    for family in ("-4", "-6"):
        for route in json.loads(ip("-j", family, "route", "show", "table", "all")):
            require(route.get("dev") == "lo" and route.get("dst") != "default"
                    and "gateway" not in route and "multipath" not in route,
                    "unexpected_route")


def connect_code(family, destination):
    with socket.socket(family, socket.SOCK_STREAM) as conn:
        conn.settimeout(0.5)
        return conn.connect_ex(destination)


def probe(outside, host_port):
    verify_network(outside)
    # Literal addresses only; do not consult any DNS or service configuration.
    require(connect_code(socket.AF_INET, ("127.0.0.1", host_port)) == errno.ECONNREFUSED,
            "host_canary_reachable_or_unproven")
    for family, target in ((socket.AF_INET, "192.0.2.1"),
                           (socket.AF_INET6, "2001:db8::1")):
        require(connect_code(family, (target, 9)) in BLOCKED, "egress_not_proven_blocked")
    links = json.loads(ip("-j", "link", "show", "dev", "lo"))
    require(len(links) == 1 and "UP" in links[0]["flags"], "private_loopback_not_up")


def stage(role, outside, fd, host_port):
    require(os.getpid() == 1 and netns() != outside, "namespace_start_refused")
    if role == "--setup":
        # CAP_NET_ADMIN is only in this newly created user/network namespace.
        # No interface command runs unless the network view is proven separate.
        verify_network(outside)
        ip("link", "set", "dev", "lo", "up")
        os.execve("/usr/bin/setpriv", (
            "setpriv", "--bounding-set=-all", "--inh-caps=-all",
            "--ambient-caps=-all", "--no-new-privs",
            *PYTHON, "--worker", outside, str(fd), str(host_port),
        ), ENV)
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    require(all(int(status[key], 16) == 0 for key in ("CapEff", "CapPrm", "CapBnd"))
            and status["NoNewPrivs"].strip() == "1", "privilege_drop_unverified")
    with socket.socket(fileno=fd) as control:
        control.set_inheritable(False)
        control.settimeout(4)
        require(control.recv(16) == b"challenge", "control_challenge_invalid")
        probe(outside, host_port)
        read_fd, write_fd = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                control.close()
                os.close(read_fd)
                probe(outside, host_port)
                os.write(write_fd, b"1")
                os.close(write_fd)
                # Remain live until PID-namespace shutdown; no background I/O.
                signal.pause()
            finally:
                os._exit(1)
        os.close(write_fd)
        try:
            require(os.read(read_fd, 1) == b"1", "descendant_probe_failed")
        finally:
            os.close(read_fd)
        control.sendall(b"ready")
        # The supervisor proves the sleeper dies, rather than asking it to exit.
        require(control.recv(16) == b"never", "unexpected_control_exit")


def only_child(pid):
    children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    require(len(children) == 1 and children[0].isdigit(), "child_identity_unverified")
    return int(children[0])


def supervised_case(listener, mode):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    pidfds = []
    with parent, child:
        parent.settimeout(8)
        command = (
            "/usr/bin/unshare", "--user", "--map-root-user", "--mount",
            "--propagation", "private", "--pid", "--fork", "--kill-child",
            "--mount-proc", "--net", "--", *PYTHON, "--setup", netns(),
            str(child.fileno()), str(listener.getsockname()[1]),
        )
        process = subprocess.Popen(command, env=ENV, pass_fds=(child.fileno(),),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            child.close()
            parent.sendall(b"challenge")
            require(parent.recv(16) == b"ready", "isolated_fixture_not_ready")
            namespace_init = only_child(process.pid)
            sleeper = only_child(namespace_init)
            for pid in (namespace_init, sleeper):
                pidfds.append(os.pidfd_open(pid))
            require(not select.select(pidfds, [], [], 0)[0], "fixture_exited_before_cleanup")
            if mode == "timeout":
                parent.settimeout(0.2)
                try:
                    parent.recv(16)
                except TimeoutError:
                    pass
                else:
                    raise SmokeError("timeout_fixture_did_not_wait")
            require(not select.select([listener], [], [], 0)[0], "host_canary_received_connection")
        finally:
            try:
                # Popen owns this exact wrapper; its --kill-child SIGKILL cascades
                # through the PID namespace. Never signal a PID found by name.
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
                for handle in pidfds:
                    require(bool(select.select([handle], [], [], 1)[0]), "cleanup_unverified")
            finally:
                for handle in pidfds:
                    os.close(handle)


def main():
    require(sys.platform == "linux" and os.geteuid() != 0, "unprivileged_linux_required")
    require(hasattr(os, "pidfd_open"), "pidfd_required")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.5)
        require(connect_code(socket.AF_INET, listener.getsockname()) == 0, "host_positive_control_failed")
        conn, _ = listener.accept()
        conn.close()
        for mode in ("cancel", "timeout"):
            supervised_case(listener, mode)
            print(f"PASS {mode}: network, descendant, IPC and cleanup", flush=True)
    print("PASS synthetic WSL network/PID smoke; deployment still unverified")


def interrupted(_signal, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if len(sys.argv) == 1:
            main()
        elif len(sys.argv) == 5 and sys.argv[1] in ("--setup", "--worker"):
            stage(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        else:
            raise SmokeError("invalid_arguments")
    except SmokeError as error:
        print(f"STOP {error}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt):
        print("STOP unsupported, interrupted or unverified native smoke", file=sys.stderr)
        sys.exit(1)
