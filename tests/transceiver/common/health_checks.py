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

# Valid failure actions per phase. The first entry in each tuple is the default.
PRE_TEST_ACTIONS = ("skip", "warn", "fail")
POST_TEST_ACTIONS = ("exit", "warn", "fail")

PRE_TEST_MARKER = "xcvr_pre_test_failure_action"
POST_TEST_MARKER = "xcvr_post_test_failure_action"
PRE_TEST_OPTION = "--xcvr_pre_test_failure_action"
POST_TEST_OPTION = "--xcvr_post_test_failure_action"


def _resolve_action(request, marker_name, option_name, valid_actions):
    """Resolve the failure action for the current test.

    Per-test marker (if present and valid) takes precedence over the CLI option,
    which is always present and validated by argparse ``choices=`` at parse time.
    """
    marker = request.node.get_closest_marker(marker_name)
    if marker is not None and marker.args:
        action = str(marker.args[0]).lower()
        if action in valid_actions:
            return action
        logger.warning(
            "Ignoring invalid %s marker value %r; valid: %s",
            marker_name, marker.args[0], valid_actions,
        )
    return request.config.getoption(option_name)


def run_pre_check(request, checks, events):
    """Evaluate pre-test checks; act on failures per resolved action.

    Action resolution order: per-test marker ``xcvr_pre_test_failure_action`` >
    CLI option ``--xcvr_pre_test_failure_action`` > default ``skip``.

    Actions:
        skip - call ``pytest.skip`` (default).
        warn - log a warning and let the test proceed.
        fail - call ``pytest.fail`` (this test fails; session continues).

    Args:
        request: pytest ``request`` fixture from the calling fixture.
        checks: iterable of ``(name, passed, detail)`` tuples.
        events: list to append failure events to (for terminal summary).
    """
    failures = [f"{name}: {detail}" for name, passed, detail in checks if not passed]
    if not failures:
        return
    detail = "; ".join(failures)
    action = _resolve_action(request, PRE_TEST_MARKER, PRE_TEST_OPTION, PRE_TEST_ACTIONS)
    events.append({
        "test": request.node.nodeid,
        "phase": "pre-test",
        "action": action,
        "details": detail,
    })
    msg = f"Pre-test health check failed for {request.node.name} -- {detail}"
    if action == "skip":
        pytest.skip(msg)
    elif action == "fail":
        pytest.fail(msg)
    else:  # warn
        logger.warning("%s (action=warn, continuing)", msg)


def run_post_check(request, checks, events):
    """Evaluate post-test checks; act on failures per resolved action.

    Action resolution order: per-test marker ``xcvr_post_test_failure_action`` >
    CLI option ``--xcvr_post_test_failure_action`` > default ``exit``.

    Actions:
        exit - call ``pytest.exit`` to abort the session (default).
        warn - log an error and let the run continue.
        fail - call ``pytest.fail`` (this test fails; session continues).

    Args:
        request: pytest ``request`` fixture from the calling fixture.
        checks: iterable of ``(name, passed, detail)`` tuples.
        events: list to append failure events to (for terminal summary).
    """
    failures = [f"{name}: {detail}" for name, passed, detail in checks if not passed]
    if not failures:
        return
    detail = "; ".join(failures)
    action = _resolve_action(request, POST_TEST_MARKER, POST_TEST_OPTION, POST_TEST_ACTIONS)
    events.append({
        "test": request.node.nodeid,
        "phase": "post-test",
        "action": action,
        "details": detail,
    })
    msg = f"Post-test health check failed for {request.node.name} -- {detail}"
    if action == "exit":
        pytest.exit(f"Aborting: environment unhealthy after {request.node.name} -- {detail}",
                    returncode=1)
    elif action == "fail":
        pytest.fail(msg)
    else:  # warn
        logger.warning("%s (action=warn, continuing)", msg)
