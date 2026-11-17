"""Source-only admission regressions; no inference or native measurements."""
import copy
import time
import unittest
import owner_resource_policy as policy


def dimensions(fields, capacity):
    return {'capacity':dict(zip(fields,capacity)),
            **{k:dict.fromkeys(fields,0) for k in ('used','pending_reserved','chat_reserved')}}


def snapshot(slots=1):
    return {'schema':'NOX_RESOURCE_POLICY_V1','native_verified':True,'instance_id':60509551,
            'observed_at':time.time(),'chat_active':False,'chat_budget_admitted':True,
            'host':dimensions(policy.HOST_FIELDS,[10,10000,10000,slots]),
            'gpus':[dict(uuid='GPU-a',**dimensions(policy.GPU_FIELDS,[32000,1]))]}


def demand(slots=1,gpu=False):
    return {'resource':'GPU_EXCLUSIVE' if gpu else 'CPU_IO',
            'resource_demand':{'host':dict(zip(policy.HOST_FIELDS,[1,100,100,slots])),
              'gpus':{'GPU-a':{'vram_mib':1000,'compute_fraction':.1}} if gpu else {}}}


class DiscreteModelSlots(unittest.TestCase):
    def test_one_measured_slot_admits_one_job_not_two(self):
        budget=policy.Budget(snapshot())
        self.assertEqual(budget.host['model_slots'],1)
        self.assertIsNone(budget.reserve(demand()))
        self.assertEqual(budget.host['model_slots'],0)
        self.assertEqual(budget.reserve(demand()),'WAIT_HOST_MEASURED_REMAINDER')

    def test_used_pending_and_chat_slots_are_subtracted(self):
        s=snapshot(4)
        s['host']['used']['model_slots']=1
        s['host']['pending_reserved']['model_slots']=1
        s['host']['chat_reserved']['model_slots']=1
        b=policy.Budget(s)
        self.assertEqual(b.host['model_slots'],1)
        self.assertIsNone(b.reserve(demand()))
        self.assertEqual(b.reserve(demand()),'WAIT_HOST_MEASURED_REMAINDER')

    def test_fractional_snapshot_counts_rejected(self):
        for group in ('capacity','used','pending_reserved','chat_reserved'):
            with self.subTest(group=group):
                s=snapshot();s['host'][group]['model_slots']=.5
                with self.assertRaisesRegex(policy.PolicyHold,'HOLD_POLICY_MODEL_SLOT_COUNT'):
                    policy.Budget(s)

    def test_fractional_demand_cannot_consume_partial_slot(self):
        b=policy.Budget(snapshot());before=copy.deepcopy(b.host)
        self.assertEqual(b.reserve(demand(.5)),'HOLD_POLICY_MODEL_SLOT_COUNT')
        self.assertEqual(b.host,before)

    def test_slot_does_not_override_measured_compute_or_vram_cap(self):
        for field,used in (('compute_fraction',.8),('vram_mib',27000)):
            with self.subTest(field=field):
                s=snapshot();s['gpus'][0]['used'][field]=used
                b=policy.Budget(s)
                self.assertEqual(b.reserve(demand(gpu=True)),'WAIT_GPU_MEASURED_REMAINDER')
                self.assertEqual(b.host['model_slots'],1)
                self.assertEqual(b.host['cpu_cores'],8.5)

    def test_chat_still_yields_and_zero_capacity_still_holds(self):
        s=snapshot();s['chat_active']=True
        self.assertEqual(policy.Budget(s).reserve(demand()),'WAIT_CHAT_SOFT_YIELD')
        self.assertEqual(policy.Budget(snapshot(0)).reserve(demand()),'WAIT_HOST_MEASURED_REMAINDER')


if __name__=='__main__':unittest.main()
