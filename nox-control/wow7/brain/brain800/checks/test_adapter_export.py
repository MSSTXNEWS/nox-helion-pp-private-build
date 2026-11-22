"""Offline regression cases; run from repository root: python -m unittest discover -s tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import struct
import unittest

from brain800.adapter_export import export_pairs, file_digest, validate_manifest


class AdapterExchangeTest(unittest.TestCase):
    def setUp(self):
        self.files=TemporaryDirectory()
        self.addCleanup(self.files.cleanup)
        self.root=Path(self.files.name)
        self.row={"language":"es","approved":True,"training_opt_in":True,"training_scope":"skill",
                  "manually_deidentified":True,"personal_facts":False,
                  "provenance":{"kind":"synthetic","id":"sample-a"},
                  "prompt":"¿Cómo retomar el audio?","chosen":"Desde la pausa.","rejected":"Repetir todo."}

    def export(self,rows):
        source=self.root/"examples.jsonl"
        source.write_text("\n".join(json.dumps(row) for row in rows),encoding="utf8")
        return export_pairs(source,self.root/"export")

    def test_shapes(self):
        stats=self.export([self.row,self.row])
        self.assertEqual(stats["pairs"],1)
        read=lambda f: [json.loads(v) for v in (self.root/"export"/f).read_text(encoding="utf8").splitlines()]
        self.assertEqual(read("sft.jsonl")[0]["messages"],read("dpo.jsonl")[0]["prompt"]+read("dpo.jsonl")[0]["chosen"])
        self.assertEqual([r["label"] for r in read("kto_train.jsonl")],[True,False])

    def test_requires_review_and_rejects_contact(self):
        for invalid in ({"approved":False},{"training_opt_in":False},{"personal_facts":True},
                        {"training_scope":"facts"},{"manually_deidentified":False},{"chosen":"A test@example.invalid"}):
            with self.subTest(invalid=tuple(invalid)), self.assertRaises(ValueError):
                self.export([self.row,dict(self.row,**invalid)])
            self.assertFalse((self.root/"export").exists())

    def test_exact_model_and_artifact(self):
        path=self.root/"adapter_model.safetensors"
        header={f"model.q_proj.lora_{name}.weight":{"dtype":"F32","shape":shape,"data_offsets":span}
                for name,shape,span in (("A",[1,2],[0,8]),("B",[2,1],[8,16]))}
        encoded=json.dumps(header).encode()
        path.write_bytes(struct.pack("<Q",len(encoded))+encoded+bytes(16))
        inventory={"role":"main_glm","architecture":"FixtureGLM","base_model":"fixture/GLM","revision":"a"*40,"target_modules":["q_proj"]}
        manifest=dict(inventory,adapter_sha256=file_digest(path))
        config={"peft_type":"LORA","r":1,"task_type":"CAUSAL_LM","target_modules":["q_proj"],"base_model_name_or_path":"fixture/GLM"}
        self.assertFalse(validate_manifest(inventory,manifest,config,path)["loaded"])
        for invalid in ({"role":"router"},{"architecture":"OtherGLM"},{"base_model":"fixture/Other"},{"revision":"main"},
                        {"target_modules":["k_proj"]},{"adapter_sha256":"0"*64}):
            with self.subTest(invalid=tuple(invalid)), self.assertRaises(ValueError):
                validate_manifest(inventory,dict(manifest,**invalid),config,path)


if __name__=="__main__": unittest.main()
