#!/usr/bin/env python3
"""NOX AUTO 1B read-only admission and same-prompt A/B source guard.
No owner session, no GPU mutation, no scheduler, no native attestation.
"""
import argparse
import json
import math
import statistics
import unittest
from pathlib import Path

INSTANCE = 60509551

def issha(v):
    return isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)

def finite(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0

def admission(runtime, maya, manifest):
    reasons = []
    files = manifest.get("files", [])
    sizes = [f.get("bytes") for f in files if isinstance(f, dict)]
    names = [f.get("path") for f in files if isinstance(f, dict)]
    hashes = [f.get("sha256") for f in files if isinstance(f, dict)]
    total = manifest.get("total_unique_gguf_bytes")
    if (len(files) != 6 or len(names) != 6 or len(set(names)) != 6
            or len(sizes) != 6 or any(type(n) is not int or n <= 0 for n in sizes)
            or len(hashes) != 6 or not all(issha(h) for h in hashes)
            or type(total) is not int or total != sum(sizes)):
        reasons.append("INVALID_UNIQUE_WEIGHT_MANIFEST")
    alias = manifest.get("alias", {})
    if alias and (alias.get("path") in names or alias.get("target") not in names or alias.get("duplicate_bytes") is not False):
        reasons.append("DUPLICATE_ENGRAM_ALIAS")
    lim = runtime.get("resource_limits_observed", {})
    admission = runtime.get("admission_candidate", {})
    free, reserve = lim.get("disk_free_bytes_at_preflight"), admission.get("disk_reserve_bytes")
    if type(free) is not int or type(reserve) is not int or free < 0 or reserve < 0:
        reasons.append("DISK_READBACK_REQUIRED")
    elif type(total) is int and total > max(free - reserve, 0):
        reasons.append("LOCAL_DISK_INSUFFICIENT_FOR_MODEL")
    drive = runtime.get("drive", {})
    if not drive.get("server_auth_connected") or not drive.get("server_write_test_passed"):
        reasons.append("SERVER_DRIVE_SHA_ROUNDTRIP_MISSING")
    if maya.get("launch", {}).get("candidate_parameters", {}).get("gpu_ids") != [0, 1]:
        reasons.append("GPU_0_1_PLACEMENT_NOT_VALIDATED")
    if runtime.get("state") != "ACTIVE_VERIFIED" or not maya.get("validation", {}).get("executed_inference"):
        reasons.append("MAYA_NOT_NATIVE_INFERENCE_VERIFIED")
    return {"status": "HOLD", "native_pass": False, "native_jobs": "UNKNOWN_NOT_READ",
            "reasons": sorted(set(reasons)), "scope": "SOURCE_ONLY_NO_LIVE_WRITE"}

def compare(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {"status":"HOLD", "reason":"MISSING_PAIRED_NATIVE_AB", "native_pass":False}
    for item in (before, after):
        if item.get("instance_id") != INSTANCE or item.get("route") != "existing_resonance" or item.get("stop_latched") is not False:
            return {"status":"HOLD", "reason":"ROUTE_STOP_OR_INSTANCE_MISMATCH", "native_pass":False}
        rows = item.get("samples")
        if (not isinstance(rows, list) or len(rows) < 3 or
                any(not isinstance(x, dict) or not issha(x.get("prompt_sha256"))
                    or not finite(x.get("ttft_ms")) or not finite(x.get("decode_tps")) for x in rows)):
            return {"status":"HOLD", "reason":"MISSING_VALID_SSE_SAMPLES", "native_pass":False}
        if len({x["prompt_sha256"] for x in rows}) != len(rows):
            return {"status":"HOLD", "reason":"DUPLICATE_PROMPTS", "native_pass":False}
    for k in ("model_sha256", "route", "prompt_suite_sha256", "sampling_sha256", "context", "endpoint_revision"):
        if before.get(k) != after.get(k) or before.get(k) is None:
            return {"status":"HOLD", "reason":"AB_CHANGED_"+k.upper(), "native_pass":False}
    b = sorted(before["samples"], key=lambda x:x["prompt_sha256"])
    a = sorted(after["samples"], key=lambda x:x["prompt_sha256"])
    if [x["prompt_sha256"] for x in a] != [x["prompt_sha256"] for x in b]:
        return {"status":"HOLD", "reason":"AB_PROMPT_SET_MISMATCH", "native_pass":False}
    bt, at = (statistics.median(x["ttft_ms"] for x in rows) for rows in (b, a))
    bs, a_s = (statistics.median(x["decode_tps"] for x in rows) for rows in (b, a))
    return {"status":"SOURCE_AB_COMPUTED_NOT_NATIVE_ATTESTED", "native_pass":False,
            "ttft_before_ms":bt, "ttft_after_ms":at,
            "decode_before_tps":bs, "decode_after_tps":a_s,
            "improved_source_candidate":at < bt and a_s >= bs}

class Tests(unittest.TestCase):
    def setUp(self):
        h = "a"*64
        self.m={"files":[{"path":str(i),"bytes":2,"sha256":h} for i in range(6)],"total_unique_gguf_bytes":12}
        self.r={"resource_limits_observed":{"disk_free_bytes_at_preflight":10},
                "admission_candidate":{"disk_reserve_bytes":3},
                "drive":{"server_auth_connected":False,"server_write_test_passed":False}}
        self.y={"launch":{"candidate_parameters":{"gpu_ids":[0,1]}}}
        self.a={"instance_id":INSTANCE,"route":"existing_resonance","stop_latched":False,
                "model_sha256":h,"prompt_suite_sha256":h,"sampling_sha256":h,
                "context":512,"endpoint_revision":"one",
                "samples":[{"prompt_sha256":str(i)*64,"ttft_ms":200,"decode_tps":10} for i in (1,2,3)]}
    def test_realistic_hold(self):
        x=admission(self.r,self.y,self.m)
        self.assertIn("LOCAL_DISK_INSUFFICIENT_FOR_MODEL",x["reasons"])
        self.assertFalse(x["native_pass"])
    def test_alias(self):
        self.m["alias"]={"path":"1","target":"5","duplicate_bytes":False}
        self.assertIn("DUPLICATE_ENGRAM_ALIAS",admission(self.r,self.y,self.m)["reasons"])
    def test_manifest(self):
        self.m["files"][0]["bytes"]=-1
        self.assertIn("INVALID_UNIQUE_WEIGHT_MANIFEST",admission(self.r,self.y,self.m)["reasons"])
    def test_no_ab(self):
        self.assertEqual(compare(None,None)["status"],"HOLD")
    def test_no_fake_native_ab(self):
        x=compare(self.a,self.a)
        self.assertFalse(x["native_pass"])
    def test_ab_mismatch(self):
        x=json.loads(json.dumps(self.a)); x["model_sha256"]="b"*64
        self.assertEqual(compare(self.a,x)["reason"],"AB_CHANGED_MODEL_SHA256")
    def test_ab_nan(self):
        x=json.loads(json.dumps(self.a)); x["samples"][0]["ttft_ms"]=float("nan")
        self.assertEqual(compare(self.a,x)["status"],"HOLD")
    def test_ab_gain(self):
        x=json.loads(json.dumps(self.a))
        for row in x["samples"]: row["ttft_ms"]=150; row["decode_tps"]=12
        self.assertTrue(compare(self.a,x)["improved_source_candidate"])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    for n in ("runtime","maya","manifest","before","after"):p.add_argument("--"+n)
    args=p.parse_args()
    if args.selftest:
        result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if not all((args.runtime,args.maya,args.manifest)):p.error("runtime, maya, manifest required")
    read=lambda x:json.loads(Path(x).read_text()) if x else None
    print(json.dumps({"admission":admission(read(args.runtime),read(args.maya),read(args.manifest)),
        "ab":compare(read(args.before),read(args.after))},ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
