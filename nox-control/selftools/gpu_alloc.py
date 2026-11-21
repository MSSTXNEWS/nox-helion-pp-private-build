"""gpu_alloc: read GPUs via nvidia-smi, plan job->GPU placement by free VRAM."""
import registry as R


def query_gpus():
    r = R.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used", "--format=csv,noheader,nounits"], timeout=15)
    if r.get("missing") or r["rc"] != 0:
        return None, r
    gpus = []
    for l in r["out"].strip().splitlines():
        i, name, tot, used = [x.strip() for x in l.split(",")]
        gpus.append({"index": int(i), "name": name, "total_mb": int(tot), "free_mb": int(tot) - int(used)})
    return gpus, r


def plan(gpus, jobs, reserve_mb=512):
    free = {g["index"]: g["free_mb"] - reserve_mb for g in gpus}
    placed, unplaced = [], []
    for j in sorted(jobs, key=lambda j: -j["vram_mb"]):
        need = j["vram_mb"]
        cand = [i for i in free if free[i] >= need]
        if not cand:
            unplaced.append(j["name"])
            continue
        i = min(cand, key=lambda x: free[x])  # best fit
        free[i] -= need
        placed.append({"name": j["name"], "gpu": i, "env": {"CUDA_VISIBLE_DEVICES": str(i)}})
    return placed, unplaced, free


@R.register("gpu_alloc", "read", {"properties": {
    "jobs": {"type": "array", "description": "[{name, vram_mb}]"}, "gpus": {"type": "array", "description": "manual [{index,free_mb}] when no nvidia-smi"},
    "reserve_mb": {"type": "integer", "default": 512}}}, "GPU inventory and best-fit placement of jobs by VRAM; returns CUDA_VISIBLE_DEVICES per job.")
def gpu_alloc(a):
    gpus = a.get("gpus")
    if not gpus:
        gpus, r = query_gpus()
        if gpus is None:
            return R.blocked("nvidia-smi unavailable: %s" % (r["err"] or "rc %s" % r["rc"])[:120],
                             "run on the GPU host or pass gpus=[{index,free_mb}]")
    if not a.get("jobs"):
        return {"ok": True, "gpus": gpus}
    placed, unplaced, free = plan(gpus, a["jobs"], a["reserve_mb"])
    return {"ok": not unplaced, "gpus": gpus, "placed": placed, "unplaced": unplaced, "free_after_mb": free}
