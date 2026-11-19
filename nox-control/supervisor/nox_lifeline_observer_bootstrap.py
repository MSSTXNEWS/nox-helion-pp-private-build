#!/usr/bin/env python3
"""Bound the Supervisor-hosted observer before execing its pinned runtime."""
import json
import os
import resource

PYTHON = "/usr/bin/python3"
RUNTIME = "/root/nox/scripts/nox_lifeline_observer.py"
ARGS = [PYTHON, "-u", RUNTIME,
        "--policy", "/etc/nox/lifeline-observer.json",
        "--state", "/root/nox/state/lifeline-observer/state.json",
        "--observer-only"]
LIMITS = {
    resource.RLIMIT_AS: (512 * 1024**2, "address_space_bytes"),
    resource.RLIMIT_NOFILE: (128, "open_files"),
    resource.RLIMIT_CORE: (0, "core_bytes"),
    resource.RLIMIT_FSIZE: (8 * 1024**2, "file_size_bytes"),
}


def apply_limits():
    result = {}
    for kind, (requested, label) in LIMITS.items():
        _soft, hard = resource.getrlimit(kind)
        ceiling = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
        resource.setrlimit(kind, (ceiling, ceiling))
        soft_after, hard_after = resource.getrlimit(kind)
        if soft_after != ceiling or hard_after != ceiling:
            raise RuntimeError("resource limit readback mismatch")
        result[label] = ceiling
    os.nice(10)
    result["nice"] = os.getpriority(os.PRIO_PROCESS, 0)
    result["hard_cgroup_memory_limit"] = "unsupported_by_supervisor"
    result["cpu_quota"] = "unsupported_by_supervisor"
    result["cpu_scheduling"] = "nice_only_no_hard_quota"
    return result


limits = apply_limits()
os.environ.clear()
os.environ.update({
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "PYTHONUNBUFFERED": "1",
    "NOX_LIFELINE_RESOURCE_LIMITS": json.dumps(limits, sort_keys=True,
                                               separators=(",", ":")),
})
os.execv(PYTHON, ARGS)
