"""Tests for the original-owner ACTIVATOR-WORM data-only bridge."""
import unittest
from src.nox_selfbuilder.activator_worm import plan_activation, ActivatorHold
def foundation(tags=()):
    return {"schema":"NOX-FOUNDATION-READONLY-v1","model_tags":list(tags),
            "s03":"READONLY_OK_NOT_WRITE_TESTED","gpu":"HARDWARE_OBSERVED_NOT_CUDA_PROOF"}
def catalogs():
    models={"schema":"NOX-P03-DOWNLOAD-CANDIDATES-V1",
       "items":[{"tag":"qwen2.5-coder:7b","role":"coding",
                 "official_page":"https://ollama.com/library/qwen2.5-coder",
                 "download_enabled":False},
                {"tag":"qwen3-embedding:0.6b","role":"RAG",
                 "official_page":"https://ollama.com/library/qwen3-embedding",
                 "download_enabled":False}]}
    modules={"schema":"NOX-P04-MODULE-CANDIDATES-V1",
       "items":[{"name":"peft","role":"LoRA","source":"https://pypi.org/project/peft/",
                 "download_enabled":False}]}
    return models,modules
class ActivatorTests(unittest.TestCase):
    def plan(self, f=None, m=None, p=None, **kwargs):
        a,b=catalogs()
        return plan_activation(foundation=f if f is not None else foundation(),
                               models=m if m is not None else a,
                               modules=p if p is not None else b,
                               source_head="a"*40,owner_scope_verified=True,**kwargs)
    def test_offline_readonly_never_installs(self):
        result=self.plan()
        self.assertEqual(result["state"],"DISCOVERY_AND_OWNER_ACTIONS_ONLY")
        self.assertFalse(result["native_auto_install"])
        self.assertFalse(result["installed_exe_e07"])
        self.assertTrue(all(not x["download_eligible"] for x in result["models"]))
    def test_local_coder_only_offers_source_patch_request(self):
        got=self.plan(f=foundation(["qwen2.5-coder:7b"]))
        self.assertTrue(got["coding_model_observed"])
        self.assertEqual(got["first_patch"],"REQUEST_APPROVED_SELFBUILDER_PROPOSAL")
        self.assertFalse(got["model_weights_sha_verified"])
    def test_native_owner_required(self):
        a,b=catalogs()
        with self.assertRaises(ActivatorHold):
            plan_activation(foundation=foundation(),models=a,modules=b,
                            source_head="a"*40,owner_scope_verified=False)
    def test_fake_native_download_eligibility_rejected(self):
        a,b=catalogs()
        a["items"][0]["download_enabled"]=True
        with self.assertRaises(ActivatorHold): self.plan(m=a,p=b)
    def test_untrusted_model_page_denied(self):
        a,b=catalogs()
        a["items"][0]["official_page"]="https://host.invalid/download"
        with self.assertRaises(ActivatorHold): self.plan(m=a,p=b)
if __name__=="__main__": unittest.main()
