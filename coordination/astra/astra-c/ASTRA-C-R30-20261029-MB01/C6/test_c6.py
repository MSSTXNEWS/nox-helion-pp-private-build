# Run after applying patch: python test_e06_lane_order.py /path/to/verify_integration.py
import importlib.util, sys
spec=importlib.util.spec_from_file_location("candidate_e06",sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def manifest(order):
    return {"run_id":"test-only","main":{"commit_sha1":"a"*40,"tree_sha1":"b"*40,"tree_truncated":False},
      "archive":{"parts":[],"bytes":0,"expected_sha256":"0"*64},
      "prs":[],"owner_map":{},"conflicts":[],"quarantine":[],"donors":[],
      "sourcelock":"HOLD","host_merge":False,"events_bridge_test":"NOT_RUN",
      "lanes":[{"owner":n,"progress":None,"accepted":False} for n in order],
      "exe_sha256":None,"e07_exe_sha256":None,"weighted_progress":None}
assert m.audit(manifest([1,2,3,4,5,6,7]))["gates"]["09_progress_ledger"]=="PASS"
assert m.audit(manifest([2,3,4,5,6,7,1]))["gates"]["09_progress_ledger"]=="HOLD"
print("E06_OWNER_ORDER_GATE_PASS")
