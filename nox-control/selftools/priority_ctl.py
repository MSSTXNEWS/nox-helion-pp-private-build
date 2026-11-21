"""priority_ctl: nice / ionice / oom_score_adj for a pid."""
import os
import registry as R


@R.register("priority_ctl", "write", {"properties": {
    "pid": {"type": "integer"}, "nice": {"type": "integer"}, "ionice_class": {"type": "integer", "description": "1 rt,2 be,3 idle"},
    "ionice_level": {"type": "integer"}, "oom_score_adj": {"type": "integer"}}, "required": ["pid"]},
    "Set nice, ionice class/level, oom_score_adj (-1000..1000) of a pid; no args = read current.")
def priority_ctl(a):
    pid = a["pid"]
    if pid <= 1:
        raise R.Denied("refusing pid <= 1")
    if not os.path.exists("/proc/%d" % pid):
        return R.fail("no such pid")
    cur = {"nice": os.getpriority(os.PRIO_PROCESS, pid)}
    try:
        cur["oom_score_adj"] = int(open("/proc/%d/oom_score_adj" % pid).read())
    except OSError:
        pass
    want = {k: a[k] for k in ("nice", "ionice_class", "ionice_level", "oom_score_adj") if k in a}
    if not want:
        return {"ok": True, "current": cur}
    if "nice" in want and not -20 <= want["nice"] <= 19 or "oom_score_adj" in want and not -1000 <= want["oom_score_adj"] <= 1000:
        return R.fail("value out of range")
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "current": cur, "would_set": want}
    done, errs = {}, {}
    if "nice" in want:
        try:
            os.setpriority(os.PRIO_PROCESS, pid, want["nice"])
            done["nice"] = want["nice"]
        except OSError as e:
            errs["nice"] = str(e)
    if "oom_score_adj" in want:
        try:
            open("/proc/%d/oom_score_adj" % pid, "w").write(str(want["oom_score_adj"]))
            done["oom_score_adj"] = want["oom_score_adj"]
        except OSError as e:
            errs["oom_score_adj"] = str(e)
    if "ionice_class" in want:
        cmd = ["ionice", "-c", str(want["ionice_class"])] + (["-n", str(want["ionice_level"])] if "ionice_level" in want else []) + ["-p", str(pid)]
        r = R.run(cmd)
        if r["rc"] == 0:
            done["ionice_class"] = want["ionice_class"]
        else:
            errs["ionice"] = r["err"].strip() or "ionice failed"
    return {"ok": not errs, "dry_run": False, "set": done, "errors": errs, "previous": cur}
