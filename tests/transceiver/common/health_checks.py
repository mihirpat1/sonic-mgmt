"""
Per-test health check logic for transceiver tests.

Used by the autouse function-scoped fixture in conftest.py to capture baselines
before each test and verify system health after each test.
"""
import logging

import pytest

from tests.common.helpers.dut_utils import get_program_info

logger = logging.getLogger(__name__)

# Critical processes monitored before/after every test.
# Key = process name, value = container name.
DEFAULT_MONITORED_PROCESSES = {
    "xcvrd": "pmon",
}


class HealthBaseline:
    """Snapshot of system health state captured before a test runs."""

    __slots__ = ("pid_baselines", "core_files")

    def __init__(self, pid_baselines, core_files):
        self.pid_baselines = pid_baselines        # {process: (status, pid)}
        self.core_files = core_files              # set of filenames


def capture_baseline(duthost, monitored_processes=None):
    """Capture pre-test health baseline.

    Args:
        duthost: DUT host handle.
        monitored_processes: dict of {process_name: container_name}.
            Defaults to DEFAULT_MONITORED_PROCESSES.

    Returns:
        HealthBaseline
    """
    if monitored_processes is None:
        monitored_processes = DEFAULT_MONITORED_PROCESSES

    # 1. Record PID baselines
    pid_baselines = {}
    for process, container in monitored_processes.items():
        status, pid = get_program_info(duthost, container, process)
        pid_baselines[process] = (status, pid)
        logger.debug("Baseline PID - %s (%s): status=%s pid=%s", process, container, status, pid)

    # 2. Record current core files
    core_result = duthost.shell(
        "find /var/core/ -maxdepth 1 -type f -printf '%f\n' 2>/dev/null || true",
        module_ignore_errors=True,
    )
    core_files = (
        set(core_result.get("stdout", "").splitlines())
        if core_result.get("stdout", "").strip()
        else set()
    )
    logger.debug("Baseline core files: %d", len(core_files))

    return HealthBaseline(
        pid_baselines=pid_baselines,
        core_files=core_files,
    )


def verify_health(duthost, baseline, monitored_processes=None, expect_pid_change=None):
    """Verify post-test health against a captured baseline.

    Args:
        duthost: DUT host handle.
        baseline: HealthBaseline captured before the test.
        monitored_processes: dict of {process_name: container_name}.
        expect_pid_change: set of process names where a PID change is expected
            (e.g., after an intentional service restart).

    Returns:
        dict: {'passed': bool, 'failures': [str]}
    """
    if monitored_processes is None:
        monitored_processes = DEFAULT_MONITORED_PROCESSES
    if expect_pid_change is None:
        expect_pid_change = set()

    failures = []

    # 1. Verify PIDs unchanged (unless intentionally changed)
    for process, container in monitored_processes.items():
        status, pid = get_program_info(duthost, container, process)
        if status != "RUNNING":
            failures.append(f"Process {process} ({container}) is {status}, expected RUNNING")
            continue
        baseline_pid = baseline.pid_baselines.get(process, (None, None))[1]
        if process not in expect_pid_change and baseline_pid is not None and pid != baseline_pid:
            failures.append(
                f"Process {process} PID changed: {baseline_pid} -> {pid} (unexpected restart)"
            )

    # 2. Check for new core files
    core_result = duthost.shell(
        "find /var/core/ -maxdepth 1 -type f -printf '%f\n' 2>/dev/null || true",
        module_ignore_errors=True,
    )
    current_cores = (
        set(core_result.get("stdout", "").splitlines())
        if core_result.get("stdout", "").strip()
        else set()
    )
    new_cores = current_cores - baseline.core_files
    if new_cores:
        failures.append(f"New core files detected: {', '.join(sorted(new_cores))}")

    passed = len(failures) == 0
    if not passed:
        logger.error("Health check failures: %s", "; ".join(failures))
    else:
        logger.info("Post-test health check passed")

    return {"passed": passed, "failures": failures}


# A "check" passed to run_pre_check / run_post_check is a 3-tuple:
#   (name: str, passed: bool, detail: str)


def run_pre_check(request, checks, events):
    """Evaluate pre-test checks; skip the test if any failed.

    Args:
        request: pytest ``request`` fixture from the calling fixture.
        checks: iterable of ``(name, passed, detail)`` tuples.
        events: list to append failure events to (for terminal summary).
    """
    failures = [f"{name}: {detail}" for name, passed, detail in checks if not passed]
    if not failures:
        return
    detail = "; ".join(failures)
    events.append({
        "test": request.node.nodeid,
        "phase": "pre-test",
        "details": detail,
    })
    pytest.skip(f"Pre-test health check: {request.node.name} skipped -- {detail}")


def run_post_check(request, checks, events):
    """Evaluate post-test checks; log + abort the session if any failed.

    Args:
        request: pytest ``request`` fixture from the calling fixture.
        checks: iterable of ``(name, passed, detail)`` tuples.
        events: list to append failure events to (for terminal summary).
    """
    failures = [f"{name}: {detail}" for name, passed, detail in checks if not passed]
    if not failures:
        return
    detail = "; ".join(failures)
    logger.error("Post-test health anomaly for %s: %s", request.node.name, detail)
    events.append({
        "test": request.node.nodeid,
        "phase": "post-test",
        "details": detail,
    })
    pytest.exit(
        f"Aborting: environment unhealthy after {request.node.name} -- {detail}",
        returncode=1,
    )
