"""NOX V19: the original 60 logical worms MUST yield to live chat and direct orders.

Source-only policy tests. No native queue creation, CUDA training or daemon.
"""
import unittest
from nox_runpod.teacher_mesh.v47.control.dispatcher import load_matrix, plan
from nox_runpod.teacher_mesh.v47.control.worm_supervisor import recommend_background_admission


def observed(**values):
    defaults={
        "native_verified":True,"s03_native_verified":True,
        "native_queue_verified":True,"task_status":{},
        "stop_active":False,"student_serving":True,
        "chat_state":"idle","chat_recent":False,
        "direct_tasks_pending":False,
        "completed":{},"existing_tasks":[],"progress":{},
        "resources":{"available_cpu_slots":8,"available_gpu1_slots":1,
                     "disk_free_bytes":30_000_000_000,
                     "checkpoint_disk_reserve_bytes":10_000_000_000},
        "native_writes_available":False,"gpu1_peak_verified":True,
        "gpu1_owner_lease":True,"gpu1_teacher_active":False,
        "gpu1_trainer_active":False,"offsite_restore_verified":True,
        "license_privacy_verified":True,"gpu1_write_budget_verified":True,
        "now_unix":2000,
    }
    defaults.update(values)
    return defaults


class ChatFirstPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix=load_matrix()

    def test_60_logical_tasks_not_60_daemons(self):
        self.assertEqual(len(self.matrix["tasks"]),60)
        self.assertEqual(len({x["task_id"] for x in self.matrix["tasks"]}),60)
        self.assertTrue(all(x["state"]=="PLANNED_NOT_ENQUEUED"
                            for x in self.matrix["tasks"]))

    def test_stop_never_queues_worms(self):
        for key,value in (("stop_active",True),("student_serving",False)):
            result=plan(self.matrix, observed(**{key:value}))
            self.assertEqual(result["planned"],[])
            self.assertEqual(result.get("jobs_enqueued",0),0)
        self.assertFalse(recommend_background_admission(observed(stop_active=True))
                         ["background_training_allowed"])

    def test_new_owner_task_pauses_all_new_background_claims(self):
        result=plan(self.matrix,observed(direct_tasks_pending=True))
        self.assertEqual(result["planned"],[])
        self.assertEqual(result["background_policy"]["state"],"DIRECT_TASKS_FIRST")
        self.assertEqual(result["jobs_enqueued"],0)

    def test_active_chat_admits_max_one_cpu_background_and_zero_gpu(self):
        for state in ("generating","streaming","thinking","connecting"):
            result=plan(self.matrix,observed(chat_state=state))
            self.assertEqual(result["state"],"SOURCE_PLAN_ONLY")
            self.assertLessEqual(len(result["planned"]),1)
            self.assertTrue(all(self._cpu_only(row) for row in result["planned"]))
            self.assertEqual(result["background_policy"]["new_worm_gpu_claims_max"],0)

    @staticmethod
    def _cpu_only(row):
        return row.get("lane") not in ("FORGE","TEACHERS") and row["task_id"] not in {
            "NOX-V46-05","NOX-V46-06","NOX-V46-46","NOX-V46-47"}

    def test_recent_chat_cap_is_two(self):
        result=plan(self.matrix,observed(chat_recent=True))
        self.assertLessEqual(len(result["planned"]),2)
        self.assertTrue(all(self._cpu_only(row) for row in result["planned"]))
        self.assertEqual(result["background_policy"]["state"],"CHAT_RECENT_LOW_BACKGROUND")

    def test_idle_without_new_model_release_cannot_train(self):
        result=plan(self.matrix,observed())
        self.assertEqual(result["state"],"SOURCE_PLAN_ONLY")
        self.assertLessEqual(len(result["planned"]),4)
        self.assertEqual(result["background_policy"]["new_worm_gpu_claims_max"],0)
        self.assertFalse(result["background_policy"]["background_training_allowed"])

    def test_sleep_mode_has_six_cpu_budget_but_gpu_requires_lineage(self):
        row=recommend_background_admission(observed(owner_sleep_mode=True))
        self.assertEqual(row["new_worm_cpu_claims_max"],6)
        self.assertEqual(row["new_worm_gpu_claims_max"],0)
        self.assertFalse(row["background_training_allowed"])
        row=recommend_background_admission(observed(
            owner_sleep_mode=True,new_model_release_verified=True,
            quality_hold_active=False,checkpoint_restorable=True))
        self.assertEqual(row["new_worm_gpu_claims_max"],1)
        self.assertTrue(row["background_training_allowed"])
        row=recommend_background_admission(observed(
            owner_sleep_mode=True,new_model_release_verified=True,
            quality_hold_active=True,checkpoint_restorable=True))
        self.assertEqual(row["new_worm_gpu_claims_max"],0)
        self.assertFalse(row["background_training_allowed"])

    def test_missing_evidence_holds_and_never_mutates(self):
        for row in (None, {}, observed(chat_recent=None), observed(direct_tasks_pending=None)):
            result=recommend_background_admission(row)
            self.assertEqual(result["native_mutations"],0)
            self.assertFalse(result["stop_overridden"])
            self.assertEqual(result["new_worm_gpu_claims_max"],0)
        result=plan(self.matrix,observed(chat_recent=None))
        self.assertEqual(result["planned"],[])
        self.assertEqual(result["state"],"HOLD_BACKGROUND_CHAT_OR_DIRECT_STATE")

    def test_source_planning_is_not_native_completion(self):
        result=plan(self.matrix,observed())
        self.assertEqual(result["jobs_enqueued"],0)
        self.assertEqual(result["actual_training_started"],False)
        self.assertEqual(result["state"],"SOURCE_PLAN_ONLY")


if __name__=="__main__":
    unittest.main()
