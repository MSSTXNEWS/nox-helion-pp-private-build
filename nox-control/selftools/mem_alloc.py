"""mem_alloc: RAM/cgroup budget check for planned components."""
import os
import registry as R


def meminfo():
    d = {}
    for l in open("/proc/meminfo"):
        k, v = l.split(":")
        d[k] = int(v.split()[0]) // 1024
    return d


def cgroup_limit_mb():
    for p in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = open(p).read().strip()
            if v.isdigit() and int(v) < 1 << 50:
                return int(v) >> 20
        except OSError:
            pass
    return None


@R.register("mem_alloc", "read", {"properties": {
    "components": {"type": "array", "description": "[{name, mb}]"}, "reserve_mb": {"type": "integer", "default": 1024},
    "available_mb": {"type": "integer", "description": "override (for planning other hosts)"}}},
    "RAM snapshot (+cgroup limit) and whether components fit with a reserve.")
def mem_alloc(a):
    try:
        mi = meminfo()
    except OSError:
        return R.blocked("/proc/meminfo unreadable", "run on Linux")
    avail = a.get("available_mb") or mi.get("MemAvailable", 0)
    cg = cgroup_limit_mb()
    if cg and not a.get("available_mb"):
        avail = min(avail, cg)
    res = {"ok": True, "total_mb": mi.get("MemTotal"), "available_mb": avail, "cgroup_limit_mb": cg,
           "swap_free_mb": mi.get("SwapFree")}
    comps = a.get("components")
    if comps:
        need = sum(c["mb"] for c in comps)
        res.update(need_mb=need, reserve_mb=a["reserve_mb"], fits=need + a["reserve_mb"] <= avail,
                   headroom_mb=avail - a["reserve_mb"] - need)
        res["ok"] = res["fits"]
    return res
