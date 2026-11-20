import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location("nox_dispatcher_advisor",Path(__file__).with_name("nox_dispatcher_advisor.py"))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def base():
    return {"stop_active":False,"onehost":{"healthy":True},
            "s03":{"readback_verified":True},
            "trainer":{"running":False},
            "gpu":{"temperature_c":55,"temperature_sensor_valid":True},
            "disk":{"free_gib":20,"checkpoint_reserve_gib":10}}

class NativeQueueAdviceTests(unittest.TestCase):
    def test_exhausted_catalog_identifies_real_next_action(self):
        x=base();x["native_queue"]={"admission_state":"NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED",
            "jobs_started":0,"workers":[{"state":"RUNNING","current_task":None} for _ in range(3)]}
        result=module.assess(x)
        self.assertIn("IDLE_NATIVE_CATALOG_EXHAUSTED",[i["code"] for i in result])
        self.assertNotIn("restart",str(result).lower())

    def test_claim_busy_and_low_memory_are_not_restart_approval(self):
        x=base();x["native_queue"]={"maintenance_busy":True,"active_claims":True,
            "resource_headroom_bytes":4096}
        codes={v["code"] for v in module.assess(x)}
        self.assertIn("NATIVE_OWNER_LEASE_BUSY",codes)
        self.assertIn("NATIVE_CGROUP_MEMORY_PRESSURE",codes)

    def test_stop_wins_over_other_optimizer_advice(self):
        x=base();x["stop_active"]=True
        x["native_queue"]={"maintenance_busy":False,"resource_headroom_bytes":0}
        self.assertEqual([z["code"] for z in module.assess(x)],["STOP_ACTIVE"])

if __name__=="__main__": unittest.main()
