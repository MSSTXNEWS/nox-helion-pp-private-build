#!/usr/bin/env python3
"""Test nightly approved-corpus gates and student-only adapter plan. Local only."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import corpus_gate as c
import adapter_recipe as a

def accepted_record(task="validtask1234",cluster="cluster_000000_00",suffix="0"):
    return {
       "task_id":task,
       "cluster_id":cluster,
       "prompt":"Сколько будет два плюс два? "+suffix,
       "completion":"Ответ: четыре. "+suffix,
       "teacher_model":"Qwen/Qwen3-8B",
       "model_card_url":"https://huggingface.co/Qwen/Qwen3-8B",
       "source_kind":"local_open_weights",
       "license":"apache-2.0",
       "quality_score":0.95,
       "quality_verified":True,
       "rights_verified":True,
       "privacy_verified":True,
       "owner_approved":True,
       "review_evidence":"Independent evaluator passed numeric answer check",
    }

class NightlyCorpusTests(unittest.TestCase):
    def test_unreviewed_teacher_answers_cannot_train(self):
        row=accepted_record()
        for key in ("quality_verified","rights_verified","privacy_verified","owner_approved"):
            copy=dict(row,**{key:False})
            self.assertFalse(c.quality_gate(copy)[0],key)
    def test_leaked_secret_field_rejected(self):
        row=accepted_record()
        row["api_key"]="untrusted"
        self.assertEqual(c.quality_gate(row),(False,"UNSAFE_FIELDS"))
    def test_license_and_score_gates(self):
        row=accepted_record()
        row["license"]="unknown"
        self.assertEqual(c.quality_gate(row)[1],"LICENSE_NOT_ALLOWLISTED")
        row["license"]="apache-2.0"
        row["quality_score"]=0.2
        self.assertEqual(c.quality_gate(row)[1],"LOW_QUALITY_SCORE")
    def test_dedup_and_semantic_split(self):
        corpus=c.build_approved_sft([
            accepted_record(),
            accepted_record(),
            accepted_record("othertask12345","cluster_000000_00","1"),
        ])
        self.assertEqual(len(corpus["accepted"]),2)
        self.assertEqual(corpus["rejected"]["DUPLICATE"],1)
        self.assertEqual({r["split"] for r in corpus["accepted"]},
                         {c._split_by_cluster("cluster_000000_00")})
    def test_export_and_adapter_plan_verified(self):
        base=Path("/tmp/nox")
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="unittest_mycelium_",dir=base) as work:
            holdout="cluster_holdout_00000"
            training="cluster_train_000000"
            # Find different hash buckets, don't rely on specific numbers.
            if c._split_by_cluster(holdout)==c._split_by_cluster(training):
                for i in range(1000):
                    alt="cluster_train_"+str(i).zfill(8)
                    if c._split_by_cluster(holdout)!=c._split_by_cluster(alt):
                        training=alt;break
            self.assertNotEqual(c._split_by_cluster(holdout),
                                c._split_by_cluster(training))
            rows=[
              accepted_record("testtask12345",training,"one"),
              accepted_record("othertask12345",holdout,"two"),
            ]
            corpus=c.build_approved_sft(rows)
            self.assertEqual(corpus["train"]+corpus["holdout"],2)
            self.assertEqual(corpus["holdout"],1)
            out=c.export_versioned(work,corpus)
            self.assertEqual(out["status"],"CORPUS_EXPORTED_NO_TRAINING")
            check=a.verify_corpus(out["path"])
            self.assertEqual(check["state"],"VERIFIED_SOURCE_CORPUS")
            planned=a.plan_adapter(corpus_dir=out["path"],
                      base_model_id="NOX3.6-35B-A3B",
                      base_model_sha256="a"*64,
                      checkpoint_sha256="b"*64,
                      target_modules=["q_proj","v_proj"],
                      rank=32,base_revision="c"*40,
                      base_architecture="Qwen3ForCausalLM",
                      base_config_sha256="d"*64,
                      tokenizer_sha256="e"*64,
                      base_weight_manifest_sha256="f"*64)
            self.assertEqual(planned["state"],"RECIPE_ONLY_NOT_TRAINED")
            self.assertFalse(planned["model_weights_updated"])
            self.assertEqual(planned["optimizer_steps_verified"],0)
            self.assertTrue(planned["trl"]["completion_only_loss"])
            self.assertEqual(c.export_versioned(work,corpus)["status"],
                             "HOLD_ALREADY_EXPORTED")
            train_file=Path(out["path"])/"train.jsonl"
            original=train_file.read_text(encoding="utf-8")
            corrupted=original.replace("Ответ: четыре", "Ответ: пять")
            self.assertNotEqual(corrupted,original)
            train_file.write_text(corrupted,encoding="utf-8")
            # Valid JSON, same row count, changed source bytes: HASH gate.
            self.assertEqual(a.verify_corpus(out["path"])["state"],
                             "HOLD_CORPUS_HASH")
    def test_training_recipe_requires_real_checkpoint(self):
        result=a.plan_adapter(corpus_dir="/tmp/nox/unknown",
              base_model_id="NOX3.6-35B-A3B",
              base_model_sha256="not-a-hash",
              checkpoint_sha256="b"*64,
              target_modules=["q_proj"],base_revision="c"*40,
              base_architecture="Qwen3ForCausalLM",
              base_config_sha256="d"*64,
              tokenizer_sha256="e"*64,
              base_weight_manifest_sha256="f"*64)
        self.assertEqual(result["state"],"HOLD_PROVENANCE_HASH")

    def test_untrusted_malformed_record_is_rejected_not_exception(self):
        for key,bad in (("source_kind",[]),("license",None),("license",{})):
            row=accepted_record()
            row[key]=bad
            self.assertFalse(c.quality_gate(row)[0])

    def _approved_threeway(self):
        import hashlib
        groups={}
        for i in range(5000):
            digest=hashlib.sha256(("source-family-%d"%i).encode()).hexdigest()
            split=c._split_by_owner_source_sha(digest)
            groups.setdefault(split,digest)
            if len(groups)==3:break
        self.assertEqual(set(groups),{"train","dev","holdout"})
        data=[];owner_groups={};privacy=[];approved_content={};privacy_by_source={}
        for i,(split,group) in enumerate(sorted(groups.items())):
            source=hashlib.sha256(("receipt-%s"%split).encode()).hexdigest()
            priv=hashlib.sha256(("privacy-%s"%split).encode()).hexdigest()
            owner_groups[source]=group;privacy.append(priv)
            record=accepted_record("reviewtask"+str(i).zfill(6),
                                   "UNTRUSTED_CLIENT_CLUSTER_"+str(i),str(i))
            record.update(source_receipt_sha256=source,
                          privacy_receipt_sha256=priv,
                          source_provenance_verified=True,pii_review="PASS")
            data.append(record)
            approved_content[source]=c.reviewed_payload_sha256(record)
            privacy_by_source[source]=priv
        policy={"signed_by_native_owner":True,
                "allow_source_disjoint_corpus":True,"stop_requested":False,
                "source_group_sha_by_receipt":owner_groups,
                "accepted_privacy_receipt_shas":privacy,
                "approved_content_sha_by_source_receipt":approved_content,
                "privacy_receipt_sha_by_source_receipt":privacy_by_source}
        return data,policy

    def test_owner_pinned_source_disjoint_threeway(self):
        data,policy=self._approved_threeway()
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["status"],"OWNER_PINNED_THREEWAY_CANDIDATES_NOT_TRAINED")
        self.assertEqual((result["train"],result["dev"],result["holdout"]),(1,1,1))
        self.assertEqual(len({row["source_group_sha256"] for row in result["accepted"]}),3)
        self.assertEqual(result["optimizer_updates_verified"],0)
        self.assertFalse(result["native_queue_modified"])
        self.assertEqual(c.export_versioned("/tmp/nox",result)["status"],"HOLD_NO_APPROVED_DATA")

    def test_unpinned_source_and_privacy_receipts_excluded(self):
        data,policy=self._approved_threeway()
        data[0]["source_receipt_sha256"]="f"*64
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["status"],"HOLD_THREEWAY_SOURCE_COVERAGE")
        self.assertEqual(result["rejected"]["UNPINNED_SOURCE_RECEIPT"],1)
        data,policy=self._approved_threeway()
        data[1]["privacy_receipt_sha256"]="f"*64
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["rejected"]["UNPINNED_PRIVACY_RECEIPT"],1)

    def test_owner_stop_and_unsigned_policy_block_candidate(self):
        data,policy=self._approved_threeway()
        for change in ({"stop_requested":True},
                       {"signed_by_native_owner":False},
                       {"allow_source_disjoint_corpus":False}):
            self.assertEqual(c.build_owner_pinned_threeway_sft(
                data,{**policy,**change})["status"],"HOLD_NATIVE_OWNER_POLICY_OR_STOP")

    def test_cross_source_prompt_and_invisible_format_dedup(self):
        data,policy=self._approved_threeway()
        self.assertEqual(c.canonical_hash("\u200bАБВ"),c.canonical_hash("АБВ"))
        data[1]["prompt"]="\u200b"+data[0]["prompt"]
        # Re-pin this altered row as independently owner-reviewed, so this
        # regression reaches the duplicate gate rather than the stricter
        # exact reviewed-payload gate.
        policy["approved_content_sha_by_source_receipt"][
            data[1]["source_receipt_sha256"]]=c.reviewed_payload_sha256(data[1])
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["status"],"HOLD_THREEWAY_SOURCE_COVERAGE")
        self.assertEqual(result["rejected"]["CROSS_SOURCE_DUPLICATE"],1)

    def test_unrelated_approved_privacy_receipt_cannot_clear_source(self):
        data,policy=self._approved_threeway()
        data[0]["privacy_receipt_sha256"]=data[1]["privacy_receipt_sha256"]
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["status"],"HOLD_THREEWAY_SOURCE_COVERAGE")
        self.assertEqual(result["rejected"]["UNPINNED_PRIVACY_RECEIPT"],1)

    def test_substituted_answer_cannot_reuse_approved_source_receipt(self):
        data,policy=self._approved_threeway()
        data[0]["completion"]="Unreviewed replacement training response"
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["status"],"HOLD_THREEWAY_SOURCE_COVERAGE")
        self.assertEqual(result["rejected"]["UNPINNED_REVIEWED_PAYLOAD"],1)
        data,policy=self._approved_threeway()
        data[0]["license"]="mit"
        result=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual(result["rejected"]["UNPINNED_REVIEWED_PAYLOAD"],1)

    def test_owner_pinned_task_and_grade_receipt_not_replayable(self):
        # The same answer must not acquire a new job ID, a fabricated higher
        # independent grade or altered evaluator evidence under the old receipt.
        for field,value in (
            ("task_id","forgedtask99999"),
            ("quality_score",0.99),
            ("review_evidence","Substituted evaluator receipt"),
        ):
            data,policy=self._approved_threeway()
            self.assertEqual(c.build_owner_pinned_threeway_sft(data,policy)["status"],
                             "OWNER_PINNED_THREEWAY_CANDIDATES_NOT_TRAINED")
            data[0][field]=value
            result=c.build_owner_pinned_threeway_sft(data,policy)
            self.assertEqual(result["status"],"HOLD_THREEWAY_SOURCE_COVERAGE",field)
            self.assertEqual(result["rejected"]["UNPINNED_REVIEWED_PAYLOAD"],1,field)

    def test_owner_content_privacy_binding_required(self):
        data,policy=self._approved_threeway()
        for key in ("approved_content_sha_by_source_receipt",
                    "privacy_receipt_sha_by_source_receipt"):
            partial={k:v for k,v in policy.items() if k!=key}
            result=c.build_owner_pinned_threeway_sft(data,partial)
            self.assertEqual(result["status"],"HOLD_OWNER_SOURCE_CONTENT_PRIVACY_BINDINGS")

    def test_wrong_source_group_is_not_controlled_by_client_cluster(self):
        data,policy=self._approved_threeway()
        base=c.build_owner_pinned_threeway_sft(data,policy)
        for r in data:r["cluster_id"]="all_same_but_untrusted"
        changed=c.build_owner_pinned_threeway_sft(data,policy)
        self.assertEqual([r["split"] for r in base["accepted"]],
                         [r["split"] for r in changed["accepted"]])



    def test_owner_threeway_export_verifies_in_existing_2d_gate(self):
        data,policy=self._approved_threeway()
        candidate=c.build_owner_pinned_threeway_sft(data,policy)
        with tempfile.TemporaryDirectory(prefix="nox_owner_threeway_",dir="/tmp/nox") as root:
            result=c.export_owner_pinned_threeway(root,candidate)
            self.assertEqual(result["status"],"THREEWAY_SOURCE_CORPUS_EXPORTED_NOT_TRAINED")
            self.assertEqual(result["counts"],{"train":1,"dev":1,"holdout":1})
            self.assertEqual(result["optimizer_updates_verified"],0)
            self.assertFalse(result["native_queue_modified"])
            verified=a.verify_corpus(result["path"])
            self.assertEqual(verified["state"],"VERIFIED_SOURCE_CORPUS")
            self.assertEqual(verified["counts"],result["counts"])
            manifest=json.loads((Path(result["path"])/"manifest.json").read_text())
            self.assertFalse(manifest["owner_corpus_identity_native_verified"])
            self.assertFalse(manifest["new_deepseek_distillation_claimed"])
            self.assertEqual(c.export_owner_pinned_threeway(root,candidate)["status"],
                             "HOLD_ALREADY_EXPORTED")

    def test_threeway_export_rejects_tampering_and_source_overlap(self):
        import copy
        data,policy=self._approved_threeway()
        candidate=c.build_owner_pinned_threeway_sft(data,policy)
        with tempfile.TemporaryDirectory(prefix="nox_owner_threeway_",dir="/tmp/nox") as root:
            forged=copy.deepcopy(candidate)
            forged["accepted"][0]["sft"]["completion"][0]["content"]="unreviewed new answer"
            self.assertEqual(c.export_owner_pinned_threeway(root,forged)["status"],
                             "HOLD_ROW_CONTENT_FINGERPRINT")
            crossed=copy.deepcopy(candidate)
            crossed["accepted"][1]["source_group_sha256"]=crossed["accepted"][0]["source_group_sha256"]
            self.assertEqual(c.export_owner_pinned_threeway(root,crossed)["status"],
                             "HOLD_SOURCE_GROUP_OVERLAP")
            malformed=copy.deepcopy(candidate)
            malformed["accepted"][2]["sft"]={"prompt":[],"completion":[]}
            self.assertEqual(c.export_owner_pinned_threeway(root,malformed)["status"],
                             "HOLD_INVALID_SFT_SHAPE")

if __name__=="__main__":
    unittest.main()
