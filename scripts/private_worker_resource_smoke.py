"""R0 opt-in synthetic user-unit limit/membership/timeout test, NOT isolation.

Creates exactly one transient user service, never installs/enables a service or
changes an existing unit. Worker does only fixture/proc reads, one fork and wait.
No models, GPU, Windows data, network connection or private input. Resource limits
are read from the kernel; this is not adversarial CPU/RAM/task exhaustion testing.
"""
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

PROPERTIES = {
    "CPUQuota": "100%", "CPUQuotaPeriodSec": "100ms", "MemoryMax": "268435456",
    "MemorySwapMax": "0", "TasksMax": "16", "RuntimeMaxSec": "10s",
    "TimeoutStopSec": "2s", "KillMode": "control-group", "SendSIGKILL": "yes",
    "Restart": "no", "NoNewPrivileges": "yes", "StandardInput": "null",
    "StandardOutput": "null", "StandardError": "null", "WorkingDirectory": "/",
    "UMask": "0077",
}
FIELDS = ("Id", "LoadState", "Transient", "InvocationID", "MainPID", "ControlGroup",
          "Slice", "Type", "RuntimeMaxUSec", "TimeoutStopUSec", "KillMode",
          "SendSIGKILL", "Restart", "NoNewPrivileges", "StandardInput",
          "StandardOutput", "StandardError", "CollectMode")
FIELDS += ("ActiveState", "Result", "ActiveEnterTimestampMonotonic")


class Refusal(RuntimeError):
    pass


def need(condition, label):
    if not condition:
        raise Refusal(label)


def validate_names(unit, root):
    need(type(unit) is str and re.fullmatch(r"starfur-r0-[0-9a-f]{32}\.service", unit),
         "unit_name_refused")
    token = unit[len("starfur-r0-"):-len(".service")]
    need(type(root) is str and re.fullmatch(r"/tmp/sf-worker-resource-" + token +
                                          r"-[a-z0-9_]{8}", root), "fixture_name_refused")
    return token


def unit_command(unit, root, python, script):
    validate_names(unit, root)
    need(python == "/home/roger/StarFur-Forge/.venv/bin/python" and
         script == "/home/roger/StarFur-Forge/scripts/private_worker_resource_smoke.py",
         "executable_path_refused")
    return ("/usr/bin/systemd-run", "--user", "--no-ask-password", "--quiet",
            "--collect", "--service-type=exec", "--expand-environment=no", "--slice=-.slice",
            f"--unit={unit}", "--description=StarFur R0 synthetic resource canary",
            *(f"--property={k}={v}" for k, v in PROPERTIES.items()), "--",
            "/usr/bin/env", "-i", "LANG=C.UTF-8", "PATH=/usr/bin:/bin",
            python, "-I", "-B", "-S", script, "--worker", unit, root)


def manager_environment(uid):
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "SYSTEMD_PAGER": "",
            "SYSTEMD_COLORS": "0", "XDG_RUNTIME_DIR": f"/run/user/{uid}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus"}


def command(args, uid, *, capture=True, timeout=3):
    result = subprocess.run(args, env=manager_environment(uid), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    if capture:
        need(len(result.stdout) <= 16384, "manager_output_bound")
    return result


def unit_info(unit, uid):
    result = command(("/usr/bin/systemctl", "--user", "--no-ask-password", "--no-pager",
                      "show", "--property=" + ",".join(FIELDS), "--", unit), uid)
    text = result.stdout.decode("ascii")
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        need(separator and key in FIELDS and key not in values and len(value) <= 512,
             "manager_metadata_refused")
        values[key] = value
    need(values.get("Id") == unit and
         (result.returncode == 0 or values.get("LoadState") == "not-found"),
         "manager_inspection_failed")
    return values


def parent_group(uid):
    return Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service")


def parent_snapshot(uid):
    base = parent_group(uid)
    need(base.resolve() == base and base.is_dir() and os.access(base, os.W_OK),
         "user_delegation_unavailable")
    out = []
    for path in (base, base / "app.slice"):
        need(path.resolve() == path and path.is_dir(), "parent_group_refused")
        out.append(((path / "cgroup.controllers").read_text(),
                    (path / "cgroup.subtree_control").read_text()))
    need({"cpu", "memory", "pids"} <= set(out[0][1].split()),
         "parent_controllers_not_enabled")
    return tuple(out)


def verify_limits(values):
    quota, period = values["cpu.max"].split()
    need(quota.isdigit() and period.isdigit() and 0 < int(quota) == int(period)
         and int(period) == 100000, "cpu_limit_unverified")
    need(values["memory.max"].strip() == "268435456" and
         values["memory.swap.max"].strip() == "0" and
         values["pids.max"].strip() == "16", "resource_limits_unverified")


def check_unit(info, unit, uid):
    expected = str(parent_group(uid) / unit).removeprefix("/sys/fs/cgroup")
    need(info.get("Id") == unit and info.get("Transient") == "yes" and
         info.get("LoadState") == "loaded" and info.get("Slice") == "-.slice" and
         info.get("ControlGroup") == expected and
         re.fullmatch(r"[0-9a-f]{32}", info.get("InvocationID", "")),
         "unit_identity_unverified")
    required = {"Type": "exec", "RuntimeMaxUSec": "10s", "TimeoutStopUSec": "2s",
                "KillMode": "control-group", "SendSIGKILL": "yes", "Restart": "no",
                "NoNewPrivileges": "yes", "StandardInput": "null",
                "StandardOutput": "null", "StandardError": "null",
                "CollectMode": "inactive-or-failed"}
    need(all(info.get(k) == v for k, v in required.items()), "unit_policy_unverified")
    return expected


def fixture(root):
    path = Path(root)
    info = path.lstat()
    need(path.parent == Path("/tmp") and path.resolve() == path and stat.S_ISDIR(info.st_mode)
         and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
         "fixture_identity_refused")
    return path


def publish(root, name, value):
    path = fixture(str(root))
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    need(len(raw) <= 1024 and name in {"ready", "go", "child"}, "fixture_record_refused")
    target, temporary = path / (name + ".json"), path / (name + ".tmp")
    need(not target.exists() and not target.is_symlink(), "fixture_record_exists")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
    os.rename(temporary, target)


def read_record(root, name):
    path = fixture(str(root)) / (name + ".json")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600,
             "fixture_record_unsafe")
        raw = source.read(1025)
        after = os.fstat(source.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink,
                          s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(identity(before) == identity(after) == identity(path.lstat()) and len(raw) <= 1024,
         "fixture_record_changed")
    return json.loads(raw)


def wait_record(root, name, deadline):
    while time.monotonic() < deadline:
        try:
            return read_record(root, name)
        except FileNotFoundError:
            time.sleep(0.02)
    raise Refusal("fixture_record_timeout")


def process_record(unit, role):
    cgroup = Path("/proc/self/cgroup").read_text().splitlines()
    need(len(cgroup) == 1 and cgroup[0].startswith("0::"), "unified_cgroup_required")
    return {"unit": unit, "role": role, "pid": os.getpid(), "ppid": os.getppid(),
            "uid": os.getuid(), "cgroup": cgroup[0][3:]}


def worker(unit, root):
    nonce = validate_names(unit, root)
    need(os.getuid() > 0 and dict(os.environ) == {"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
         "worker_environment_refused")
    fixture(root)
    # Exercise SIGKILL grace, not just polite main-process termination.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    publish(root, "ready", process_record(unit, "worker"))
    go = wait_record(root, "go", time.monotonic() + 8)
    need(go == {"nonce": nonce}, "worker_release_refused")
    child = os.fork()
    if child == 0:
        publish(root, "child", process_record(unit, "child"))
    while True:
        signal.pause()


def pin_record(record, *, unit, uid, role, cgroup, expected_argv, ppid=None):
    need(type(record) is dict and set(record) == {"unit", "role", "pid", "ppid", "uid", "cgroup"}
         and record["unit"] == unit and record["uid"] == uid and record["role"] == role
         and record["cgroup"] == cgroup and type(record["pid"]) is int
         and 1 < record["pid"] < 2**31 and
         (ppid is None or record["ppid"] == ppid), "process_record_refused")
    pid = record["pid"]
    before = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    handle = os.pidfd_open(pid)
    try:
        after = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        status = dict(line.split(":", 1) for line in
                      Path(f"/proc/{pid}/status").read_text().splitlines())
        need(before[19] == after[19] and int(after[1]) == record["ppid"]
             and Path(f"/proc/{pid}/cgroup").read_text() == "0::" + cgroup + "\n"
             and status["NoNewPrivs"].strip() == "1"
             and status["Uid"].split() == [str(uid)] * 4
             and Path(f"/proc/{pid}/cmdline").read_bytes() ==
             b"\0".join(os.fsencode(a) for a in expected_argv) + b"\0"
             and not select.select([handle], [], [], 0)[0], "process_binding_changed")
        return handle
    except BaseException:
        os.close(handle)
        raise


def main():
    need(sys.platform == "linux" and os.getuid() > 0 and hasattr(os, "pidfd_open"),
         "supported_user_host_required")
    uid = os.getuid()
    snapshot = parent_snapshot(uid)
    need(Path("/tmp").resolve() == Path("/tmp"), "linux_temporary_root_required")
    nonce = uuid.uuid4().hex
    unit = "starfur-r0-" + nonce + ".service"
    need(unit_info(unit, uid).get("LoadState") == "not-found", "unit_already_exists")
    root = Path(tempfile.mkdtemp(prefix="sf-worker-resource-" + nonce + "-", dir="/tmp"))
    handles, binding = [], None
    group = parent_group(uid) / unit
    try:
        args = unit_command(unit, str(root), sys.executable, str(Path(__file__).resolve()))
        result = command(args, uid, capture=False, timeout=4)
        need(result.returncode == 0, "unit_start_failed")
        ready = wait_record(root, "ready", time.monotonic() + 4)
        info = unit_info(unit, uid)
        cgroup = check_unit(info, unit, uid)
        binding = info["InvocationID"]
        need(info.get("ActiveEnterTimestampMonotonic", "").isdigit(), "runtime_clock_unverified")
        active_since = int(info["ActiveEnterTimestampMonotonic"]) / 1000000
        need(0 < active_since <= time.monotonic(), "runtime_clock_unverified")
        need(str(ready.get("pid")) == info.get("MainPID"), "main_pid_changed")
        argv = args[args.index("/usr/bin/env") + 4:]
        handles.append(pin_record(ready, unit=unit, uid=uid, role="worker", cgroup=cgroup,
                                  expected_argv=argv))
        verify_limits({n: (group / n).read_text() for n in
                       ("cpu.max", "memory.max", "memory.swap.max", "pids.max")})
        need(unit_info(unit, uid).get("InvocationID") == binding, "unit_epoch_changed")
        need(parent_snapshot(uid) == snapshot, "parent_controllers_changed")
        publish(root, "go", {"nonce": nonce})
        child = wait_record(root, "child", time.monotonic() + 2)
        handles.append(pin_record(child, unit=unit, uid=uid, role="child", cgroup=cgroup,
                                  ppid=ready["pid"], expected_argv=argv))
        need(set((group / "cgroup.procs").read_text().split()) ==
             {str(ready["pid"]), str(child["pid"])}, "group_membership_changed")
        deadline = time.monotonic() + 16
        timed_out = False
        while time.monotonic() < deadline:
            current = unit_info(unit, uid)
            if current.get("LoadState") == "loaded":
                need(current.get("InvocationID") == binding, "unit_epoch_changed")
                need(current.get("Result") in {"success", "timeout"}, "unexpected_unit_result")
                timed_out = timed_out or current["Result"] == "timeout"
            else:
                need(current.get("LoadState") == "not-found" and timed_out,
                     "runtime_cause_unverified")
            if all(select.select([handle], [], [], 0)[0] for handle in handles):
                break
            time.sleep(0.1)
        need(timed_out and time.monotonic() >= active_since + 10 and
             all(select.select([h], [], [], 0)[0] for h in handles), "group_timeout_not_verified")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and (group.exists() or
              unit_info(unit, uid).get("LoadState") != "not-found"):
            time.sleep(0.05)
        need(not group.exists() and unit_info(unit, uid).get("LoadState") == "not-found",
             "unit_collection_unverified")
        need(parent_snapshot(uid) == snapshot, "parent_controllers_changed")
        need({p.name for p in root.iterdir()} == {"ready.json", "go.json", "child.json"},
             "fixture_cleanup_refused")
        for name in ("ready", "go", "child"):
            read_record(root, name)  # no-follow/owner/link/identity check before removal
            (root / (name + ".json")).unlink()
        root.rmdir()
    except BaseException:
        # Stop ONLY our observed invocation. No name-only kill of an unknown unit.
        if binding is not None:
            current = unit_info(unit, uid)
            if current.get("LoadState") != "not-found":
                need(current.get("InvocationID") == binding, "cleanup_epoch_changed")
                need(command(("/usr/bin/systemctl", "--user", "--no-ask-password", "stop",
                              "--", unit), uid, capture=False, timeout=4).returncode == 0,
                     "unit_stop_failed")
        print(f"STOP retained R0 fixture: {root}", file=sys.stderr)
        raise
    finally:
        for handle in handles:
            os.close(handle)
    print("PASS R0 kernel limits, parent/child membership, runtime kill and exact cleanup")
    print("Synthetic resource test only; not model, isolation or exhaustion evidence")


def interrupt(_signum, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "--worker":
            worker(sys.argv[2], sys.argv[3])
        else:
            need(len(sys.argv) == 1, "arguments_refused")
            signal.signal(signal.SIGTERM, interrupt)
            main()
    except (OSError, ValueError, Refusal, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print("STOP R0: " + (str(error) if type(error) is Refusal else type(error).__name__),
              file=sys.stderr)
        sys.exit(1)
