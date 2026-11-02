import unittest
from dataclasses import replace
from datetime import datetime, timezone
from src.nox_selfbuilder.firstboot_coordinator import FirstBootCallbacks, FirstBootCoordinator

NOW = datetime(2026, 11, 1, 16, 30, tzinfo=timezone.utc)
D31 = 'a'*64
D32 = 'b'*64


def policy(**overrides):
    p={"schema":"NOX-ONEHOST-FIRSTBOOT-POLICY-v1", "windows_sid_attested":True,
       "source_lock_verified":True,"signed_by_native_owner":True,
       "allow_firstboot_downloads":True,"installer_consent_recorded":True,
       "expiry_utc":"2026-11-02T16:30:00+00:00", "approved_scan_roots":["C:\\NOX"],
       "reviewed_artifacts":{
          "31":{"sha256":D31,"version":"r1","rights_receipt_id":"owner31",
                 "license_review_passed":True,"hardware_compatible":True,"model_tag":"qwen2.5-coder:7b"},
          "32":{"sha256":D32,"version":"r2","rights_receipt_id":"owner32",
                 "license_review_passed":True,"hardware_compatible":True,"model_tag":"qwen3-embedding:0.6b"}}}
    p.update(overrides)
    return p


class State:
    def __init__(self):
        self.p=policy();self.present={"11":True,"49":True};self.rows=[]
        self.stop=False;self.epoch=0;self.accept=True;self.fake_digest=False;self.persisted=[];self.calls=[];self.native_checks=[];self.queued=set();self.ingested=[]
        self.app=FirstBootCoordinator(FirstBootCallbacks(
            policy=lambda _:self.p,
            installed=lambda _:{"schema":"NOX-P03-L01-INSTALLED-v1","items":self.present},
            discover=lambda _,roots:self.rows,
            dispatch=self.dispatch,
            persist=self.persist,
            ingest=self.ingest,
            stopped=lambda:self.stop,
            stop_epoch=lambda:self.epoch))
    def dispatch(self,s,route,art):
        self.native_checks.append((s,route,art))
        key=(s,art['id'],art['sha256'])
        already=key in self.queued
        if self.accept and not already:
            self.queued.add(key)
            self.calls.append((route,art))
        return {"ack":self.accept,"native_durable_queue":self.accept,
                "id":art['id'],"sha256":("0"*64 if self.fake_digest else art['sha256']),
                "already_queued":already}
    def persist(self,s,doc):
        self.persisted.append(doc)
        return self.accept
    def ingest(self,s,artifact):
        self.ingested.append(artifact)
        return {"ack": True, "s03_readback": True, "sha256": artifact["sha256"]}


class Tests(unittest.TestCase):
    def test_enqueues_only_reviewed_models_with_natively_signed_consent(self):
        s=State();r=s.app.run('S',now=NOW)
        self.assertEqual(r['status'],'QUEUED_NOT_INSTALLED')
        self.assertEqual(r['enqueued_ids'],[31,32])
        self.assertEqual(len(s.calls),2)
        self.assertEqual(r['downloaded'],0)
        self.assertTrue(all(x['route']=='P03_REVIEWED_MODEL_QUEUE' for x in s.persisted[0]['planned']))

    def test_dedupe_second_boot(self):
        s=State();s.app.run('S',now=NOW);r=s.app.run('S',now=NOW)
        self.assertEqual(len(s.calls),2)
        self.assertEqual(r['enqueued_ids'],[])
        self.assertEqual(r['status'],'ALREADY_QUEUED_NOT_INSTALLED')

    def test_native_queue_dedupe_is_scoped_to_principal(self):
        s=State()
        self.assertEqual(s.app.run('owner_A',now=NOW)['enqueued_ids'],[31,32])
        self.assertEqual(s.app.run('owner_B',now=NOW)['enqueued_ids'],[31,32])
        self.assertEqual(len(s.calls),4)
        self.assertEqual(s.app.run('owner_A',now=NOW)['already_queued_ids'],[31,32])
        self.assertEqual(len(s.calls),4)

    def test_stop_epoch_mid_scan_prevents_persist_and_dispatch(self):
        s=State()
        def scan(session,roots):
            s.epoch += 1  # Real STOP and fast reset: boolean is already clear.
            return []
        s.app.callbacks=replace(s.app.callbacks, discover=scan)
        r=s.app.run('owner_A',now=NOW)
        self.assertEqual(r['status'],'STOPPED')
        self.assertEqual(s.persisted,[])
        self.assertEqual(s.calls,[])

    def test_stop_epoch_during_native_dispatch_suppresses_late_ack(self):
        s=State()
        original=s.dispatch
        def dispatch(session, route, art):
            receipt=original(session,route,art)
            s.epoch += 1  # Late native ACK after STOP+RESET.
            return receipt
        s.app.callbacks=replace(s.app.callbacks, dispatch=dispatch)
        r=s.app.run('owner_A',now=NOW)
        self.assertEqual(r['status'],'HOLD')
        self.assertEqual(r['enqueued_ids'],[])
        self.assertEqual(r['held'][-1]['reason'],'STOP_DURING_DISPATCH_READBACK_REQUIRED')
        self.assertEqual(len(s.calls),1)

    def test_stop_during_persist_prevents_any_enqueue(self):
        s=State()
        original=s.persist
        def persist(session, intent):
            result=original(session,intent)
            s.epoch += 1
            return result
        s.app.callbacks=replace(s.app.callbacks, persist=persist)
        r=s.app.run('owner_A',now=NOW)
        self.assertEqual(r['status'],'STOPPED')
        self.assertEqual(s.calls,[])

    def test_missing_stop_epoch_fails_closed(self):
        s=State()
        s.app.callbacks=replace(s.app.callbacks, stop_epoch=lambda:None)
        self.assertEqual(s.app.run('owner_A',now=NOW)['reason'],'NATIVE_STOP_EPOCH_REQUIRED')
        self.assertEqual(s.calls,[])

    def test_native_installed_integer_key_rejected_without_extra_queue(self):
        s=State()
        s.present={11:True,"49":True}
        r=s.app.run("owner_A",now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"NATIVE_INSTALLED_ITEM_INVALID")
        self.assertEqual(s.persisted,[])
        self.assertEqual(s.calls,[])

    def test_native_installed_mixed_key_alias_rejected(self):
        s=State()
        s.present={"11":True,11:True,"49":True}
        r=s.app.run("owner_A",now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"NATIVE_INSTALLED_ITEM_INVALID")
        self.assertEqual(s.calls,[])

    def test_no_native_consent_no_dispatch(self):
        s=State();s.p=policy(installer_consent_recorded=False)
        r=s.app.run('S',now=NOW)
        self.assertEqual(r['status'],'HOLD');self.assertEqual(s.calls,[])

    def test_missing_manifest_hold_not_unverified_pull(self):
        s=State();s.p=policy(reviewed_artifacts={})
        r=s.app.run('S',now=NOW)
        self.assertEqual(r['enqueued_ids'],[]);self.assertEqual(len(r['held']),2)

    def test_expired_policy_holds(self):
        s=State();s.p=policy(expiry_utc='2026-10-31T10:00:00Z')
        self.assertEqual(s.app.run('S',now=NOW)['status'],'HOLD')

    def test_found_code_untrusted_and_never_executed(self):
        s=State();s.rows=[{"sha256":"c"*64,"kind":"SOURCE_CANDIDATE","size_bytes":123}]
        r=s.app.run('S',now=NOW)
        self.assertEqual(r['found_candidates'],1)
        self.assertFalse(s.persisted[0]['executed_code'])
        self.assertEqual(s.persisted[0]['found'][0]['status'],'DISCOVERED_UNTRUSTED_NOT_IMPORTED')

    def test_bad_scan_hash_holds_all(self):
        s=State();s.rows=[{"sha256":"bad","kind":"SOURCE_CANDIDATE","size_bytes":123}]
        self.assertEqual(s.app.run('S',now=NOW)['status'],'HOLD')
        self.assertEqual(s.calls,[])

    def test_stop_cancels_before_planning(self):
        s=State();s.stop=True
        self.assertEqual(s.app.run('S',now=NOW)['status'],'STOPPED')

    def test_failed_native_queue_cannot_claim_installed(self):
        s=State();s.accept=False
        self.assertEqual(s.app.run('S',now=NOW)['reason'],'NATIVE_S03_INTENT_READBACK_REQUIRED')
        self.assertEqual(s.calls,[])

    def test_idempotent_queue_ack_digest(self):
        s=State()
        s.fake_digest=True
        r=s.app.run('S',now=NOW)
        self.assertEqual(r['enqueued_ids'],[])
        self.assertEqual(r['status'],'HOLD')
        self.assertEqual(r['held'],[{'id':31,'reason':'NATIVE_QUEUE_ACK_OR_DIGEST_MISMATCH'}])
        self.assertEqual(len(s.calls),1)  # Never dispatch 32 after uncertain 31.
        self.assertEqual(r['downloaded'],0)

    def test_partial_native_ack_holds_but_preserves_queue_receipt(self):
        s=State()
        original=s.dispatch
        def partial(session, route, art):
            result=original(session,route,art)
            if art['id']==32:
                result['sha256']='0'*64  # Native ACK is inconsistent.
            return result
        s.app.callbacks=replace(s.app.callbacks,dispatch=partial)
        receipt=s.app.run('owner_A',now=NOW)
        self.assertEqual(receipt['status'],'HOLD')
        self.assertEqual(receipt['enqueued_ids'],[31])
        self.assertEqual(receipt['held'],[{'id':32,'reason':'NATIVE_QUEUE_ACK_OR_DIGEST_MISMATCH'}])
        self.assertFalse(receipt['release_accepted'])

    def test_one_unreviewed_artifact_never_claims_full_firstboot(self):
        s=State()
        s.p=policy()
        s.p['reviewed_artifacts'].pop('32')
        receipt=s.app.run('owner_A',now=NOW)
        self.assertEqual(receipt['status'],'HOLD')
        self.assertEqual(receipt['enqueued_ids'],[31])
        self.assertEqual(receipt['held'],[{'id':32,'reason':'PINNED_LICENSE_HARDWARE_ARTIFACT_REQUIRED'}])
        self.assertFalse(receipt['release_accepted'])

    def test_normalize_duplicate_asset_hash(self):
        s=State();s.rows=[{"sha256":"f"*64,"kind":"SOURCE_CANDIDATE","size_bytes":123}]*2
        self.assertEqual(s.app.run('S',now=NOW)['found_candidates'],1)

    def test_conflicting_digest_metadata_holds_before_native_ingest_or_queue(self):
        s = State()
        digest = "f" * 64
        s.p = policy(allow_local_knowledge_ingest=True,
                     reviewed_local_artifacts={digest: {"rights_verified": True,
                                                        "content_safe_for_s03": True}})
        for mismatched in (
            {"sha256": digest, "kind": "DESIGN_CANDIDATE", "size_bytes": 123},
            {"sha256": digest, "kind": "SOURCE_CANDIDATE", "size_bytes": 124},
        ):
            s.rows = [{"sha256": digest, "kind": "SOURCE_CANDIDATE", "size_bytes": 123}, mismatched]
            r = s.app.run("owner_A", now=NOW)
            self.assertEqual(r["status"], "HOLD")
            self.assertEqual(r["reason"], "LOCAL_SCAN_CONFLICTING_DIGEST_METADATA")
            self.assertEqual(s.persisted, [])
            self.assertEqual(s.calls, [])
            self.assertEqual(s.ingested, [])

    def test_auto_ingest_only_owner_reviewed_s03_safe_materials(self):
        s=State()
        digest="f"*64
        s.p=policy(allow_local_knowledge_ingest=True,reviewed_local_artifacts={digest:{"rights_verified":True,"content_safe_for_s03":True}})
        s.rows=[{"sha256":digest,"kind":"SOURCE_CANDIDATE","size_bytes":100}]
        r=s.app.run("S",now=NOW)
        self.assertEqual(r["local_knowledge_ingested"],1)
        self.assertEqual(len(s.ingested),1)

    def test_uncertain_s03_ingest_ack_blocks_all_following_p03_dispatch(self):
        digest = "f" * 64
        for invalid in (
            {"ack": True, "s03_readback": False, "sha256": digest},
            {"ack": True, "s03_readback": True, "sha256": "0" * 64},
            {"ack": False, "s03_readback": True, "sha256": digest},
            {},
            None,
        ):
            with self.subTest(invalid=invalid):
                s = State()
                s.p = policy(allow_local_knowledge_ingest=True,
                             reviewed_local_artifacts={
                                 digest: {"rights_verified": True, "content_safe_for_s03": True}})
                s.rows = [{"sha256": digest, "kind": "SOURCE_CANDIDATE", "size_bytes": 100}]
                s.app.callbacks = replace(s.app.callbacks, ingest=lambda _session, _art: invalid)
                receipt = s.app.run("owner_A", now=NOW)
                self.assertEqual(receipt["status"], "HOLD")
                self.assertEqual(receipt["reason"],
                                 "NATIVE_S03_INGEST_ACK_OR_DIGEST_MISMATCH_READBACK_REQUIRED")
                self.assertEqual(s.calls, [])
                self.assertFalse(receipt["release_accepted"])

    def test_uncertain_second_s03_ack_does_not_dispatch_p03_models(self):
        first, second = "e" * 64, "f" * 64
        s = State()
        s.p = policy(allow_local_knowledge_ingest=True,
                     reviewed_local_artifacts={
                         first: {"rights_verified": True, "content_safe_for_s03": True},
                         second: {"rights_verified": True, "content_safe_for_s03": True}})
        s.rows = [
            {"sha256": first, "kind": "SOURCE_CANDIDATE", "size_bytes": 100},
            {"sha256": second, "kind": "SOURCE_CANDIDATE", "size_bytes": 100}]
        def partial_ack(_session, artifact):
            s.ingested.append(artifact)
            return {"ack": True, "s03_readback": True,
                    "sha256": artifact["sha256"] if len(s.ingested) == 1 else "0" * 64}
        s.app.callbacks = replace(s.app.callbacks, ingest=partial_ack)
        receipt = s.app.run("owner_A", now=NOW)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["reason"],
                         "NATIVE_S03_INGEST_ACK_OR_DIGEST_MISMATCH_READBACK_REQUIRED")
        self.assertEqual(len(s.ingested), 2)
        self.assertEqual(s.calls, [])
        self.assertFalse(receipt["release_accepted"])

    def test_unreviewed_no_ingest(self):
        s=State();s.p=policy(allow_local_knowledge_ingest=True)
        s.rows=[{"sha256":"f"*64,"kind":"SOURCE_CANDIDATE","size_bytes":100}]
        r=s.app.run("S",now=NOW)
        self.assertEqual(r["local_knowledge_ingested"],0)
        self.assertEqual(s.ingested,[])

    def test_stop_during_final_s03_ingest_without_pending_queue_fails_closed(self):
        s=State(); digest="f"*64
        s.present={"11":True,"31":True,"32":True,"49":True}
        s.p=policy(allow_local_knowledge_ingest=True,
                   reviewed_local_artifacts={digest:{"rights_verified":True,
                                                     "content_safe_for_s03":True}})
        s.rows=[{"sha256":digest,"kind":"SOURCE_CANDIDATE","size_bytes":100}]
        native_ingest=s.ingest
        def ingest_then_stop(session, artifact):
            ack=native_ingest(session, artifact)
            s.epoch += 1 # STOP then fast RESET: boolean is false again
            return ack
        s.app.callbacks=replace(s.app.callbacks, ingest=ingest_then_stop)
        receipt=s.app.run("owner_A", now=NOW)
        self.assertEqual(receipt["status"], "STOPPED")
        self.assertEqual(receipt["reason"], "NATIVE_STOP_DURING_S03_INGEST_READBACK_REQUIRED")
        self.assertFalse(receipt["release_accepted"])
        self.assertEqual(s.calls, [])

    def test_policy_rejects_fake_authority(self):
        s=State();s.p=policy(signed_by_native_owner=False)
        r=s.app.run('S',now=NOW)
        self.assertEqual(r['status'],'HOLD');self.assertEqual(s.calls,[])

if __name__=='__main__':unittest.main()
