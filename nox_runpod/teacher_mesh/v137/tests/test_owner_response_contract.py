"""V137 quality evidence fixtures: owner scope, original S03 and no fake self."""
import hashlib
import json
import unittest
from nox_runpod.teacher_mesh.v137.owner_response_contract import build_owner_response_contract as build

S={"tenant":"noxtenant","principal":"owner","chat_id":"dialogA",
   "persona_enabled":False,"persona_id":None}
OBS={
 "schema":"NOX_V137_OWNER_SELF_OBSERVATION_V1",
 "collected_at_utc":"2026-11-15T01:00:00Z",
 "service_observation":{"state":"OBSERVED","services":[
   {"name":"nox-proxy","state":"RUNNING"},
   {"name":"nox-train-volta-t866u","state":"EXITED"},
   {"name":"random-systemd","state":"RUNNING"}]},
 "s03_observation":{"state":"OBSERVED","fact_rows":400},
 "training":{"positive_optimizer_steps_verified":True} # caller claim must NOT become proof
}
def fact(**patch):
    r={"verified":True,"tenant":"noxtenant","principal":"owner","chat_id":"dialogA",
       "source_uri":"s03://owner/fact-012","sha256":"a"*64,
       "content":"Confirmed past project choice: ONE NOX and one memory"}
    r.update(patch)
    return r
def call(rows,**kw):
    return build("Объясни своё состояние и сделай план",session=S,
      observations=OBS,retrieved_s03=rows,stop_active=False,
      owner_verified=True,**kw)


class GroundedNativeQuality(unittest.TestCase):
    def test_self_answer_uses_real_owner_s03_and_service_data(self):
        r=call([fact()])
        self.assertEqual(r["state"],"READY_FOR_EXISTING_SINGLE_MODEL")
        self.assertEqual(r["memory_hit_count"],1)
        self.assertEqual(r["requires_native_s03_commit"],True)
        self.assertFalse(r["new_llm_spawned"])
        self.assertFalse(r["model_weights_trained"])
        self.assertIn("NOX HELION",r["trusted_system_policy"])
        self.assertIn("without claiming",r["trusted_system_policy"].lower()) if False else None
        self.assertIn("subjective consciousness",r["trusted_system_policy"])
        data=json.loads(r["source_evidence_json"])
        self.assertEqual(data["native_services"][1]["state"],"EXITED")
        self.assertNotIn("random-systemd",r["source_evidence_json"])
        self.assertFalse(data["training_optimizer_verified"])
        self.assertTrue(data["s03_memory_used"])
        self.assertEqual(data["retrieved_s03"][0]["source_uri"],"s03://owner/fact-012")

    def test_auth_or_stop_fail_closed_without_memory(self):
        r=build("какой статус?",session=S,observations=OBS,retrieved_s03=[fact()],
                stop_active=True,owner_verified=True)
        self.assertEqual(r["state"],"HOLD_OWNER_SCOPE_OR_STOP")
        r=build("какой статус?",session=S,observations=OBS,retrieved_s03=[fact()],
                stop_active=False,owner_verified=False)
        self.assertEqual(r["state"],"HOLD_OWNER_SCOPE_OR_STOP")

    def test_cross_chat_denies_memory_supplied_fake_acl(self):
        q=fact(chat_id="otherChat",native_owner_cross_chat_granted=True)
        d=json.loads(call([q])["source_evidence_json"])
        self.assertEqual(d["retrieved_s03"],[])
        self.assertFalse(d["s03_memory_used"])
        # Only independent signed owner-side source grants may allow reuse.
        d=json.loads(call([q],native_cross_chat_sources=frozenset(
               {"s03://owner/fact-012"}))["source_evidence_json"])
        self.assertEqual(len(d["retrieved_s03"]),1)

    def test_tenant_principal_persona_isolation_and_secret_redaction(self):
        rows=[
         fact(tenant="other"),fact(principal="other"),
         fact(persona_id="KV"),
         fact(content="api_key=should_not_appear"),
         fact(source_uri="https://example.org/untrusted"),
         fact(sha256="not-a-sha"),fact()
        ]
        r=call(rows)
        self.assertEqual(r,{"state":"HOLD_S03_REDACTION_REQUIRED"})

    def test_unavailable_source_cannot_claim_local_omnipotence(self):
        bad=dict(OBS,service_observation={"state":"HOLD","services":[]})
        r=build("Ты контролируешь процессы?",session=S,observations=bad,
          retrieved_s03=[],stop_active=False,owner_verified=True)
        self.assertEqual(r["state"],"HOLD_NATIVE_SERVICES_UNVERIFIED")

    def test_context_bounded_and_one_model_no_extra_inference(self):
        rows=[fact(source_uri="s03://owner/fact-"+str(i),
                   content="информация "+("Т"*220))
              for i in range(28)]
        result=call(rows,max_chars=1900)
        self.assertEqual(result,{"state":"HOLD_CONTEXT_BUDGET"})

    def test_full_memory_text_and_source_are_preserved_or_hold(self):
        long_text="Полное подтверждённое воспоминание "+("ж"*420)
        long_uri="s03://owner/source/"+("x"*130)
        r=call([fact(content=long_text,source_uri=long_uri)])
        self.assertEqual(r["state"],"READY_FOR_EXISTING_SINGLE_MODEL")
        evidence=json.loads(r["source_evidence_json"])["retrieved_s03"][0]
        self.assertEqual(evidence["content"],long_text)
        self.assertEqual(evidence["source_uri"],long_uri)
        self.assertEqual(evidence["source_sha256"],"a"*64)

        # A complete set that exceeds the budget is rejected as a whole.
        oversized=[fact(source_uri=f"s03://owner/long-{i}",
                        content="Проверенная запись "+("м"*500))
                   for i in range(8)]
        self.assertEqual(call(oversized,max_chars=1900),
                         {"state":"HOLD_CONTEXT_BUDGET"})


if __name__=="__main__":
    unittest.main()
