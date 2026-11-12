"""Offline contracts for NOX PRIME five-model downloader, no real network."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
from unittest import TestCase,main
from unittest.mock import patch
import nox_prime_download_five_v1 as d

class DownloadFiveTests(TestCase):
    def test_exact_five_curated_models(self):
        self.assertEqual(len(d.MODELS),5)
        self.assertEqual(d.MODELS[0][1],"Qwen/Qwen3-0.6B")
        self.assertEqual(d.MODELS[2][1],"Qwen/Qwen3-4B")
        self.assertEqual(d.MODELS[4][1],"Qwen/Qwen3.5-2B")
    def test_upstream_paths_do_not_traverse(self):
        self.assertTrue(d.matches("model.safetensors"))
        self.assertTrue(d.matches("tokenizer.json"))
        self.assertFalse(d.matches("../private.json"))
        self.assertFalse(d.matches("/tmp/data.json"))
        self.assertFalse(d.matches("unverified_python_module.py"))
    def test_require_official_license_and_revision(self):
        def info(model_id,revision,files_metadata):
            return SimpleNamespace(id=model_id,sha="b"*40,
                card_data=SimpleNamespace(license="cc-by-nc-4.0"),
                siblings=[SimpleNamespace(rfilename="model.safetensors",size=8)])
        with self.assertRaises(RuntimeError):
            d.official_metadata(SimpleNamespace(model_info=info),"Qwen/Qwen3-0.6B")
    def test_real_file_checksum_then_skip_duplicate(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/"brain").mkdir()
            files={"model.safetensors":8,"config.json":3}
            def info(mid,revision,files_metadata):
                return SimpleNamespace(id=mid,sha="c"*40,
                    card_data=SimpleNamespace(license="apache-2.0"),
                    siblings=[SimpleNamespace(rfilename=n,size=v) for n,v in files.items()])
            callcount=[]
            def snapshot_download(repo_id,revision,local_dir,allow_patterns,max_workers):
                callcount.append(repo_id)
                p=Path(local_dir);p.mkdir(parents=True,exist_ok=True)
                (p/"model.safetensors").write_bytes(b"12345678")
                (p/"config.json").write_bytes(b"abc")
            fake=SimpleNamespace(HfApi=lambda:SimpleNamespace(model_info=info),
                                 snapshot_download=snapshot_download)
            with patch.dict(sys.modules,{"huggingface_hub":fake}),\
                 patch.object(d.shutil,"disk_usage",return_value=SimpleNamespace(free=200_000_000_000)):
                first=d.download(root)
                second=d.download(root)
            self.assertEqual(first["completed"],5)
            self.assertEqual(second["completed"],5)
            self.assertEqual(len(callcount),5) # second run never downloads
            item=next((Path(root/"brain"/"models"/"NOX_PRIME_V5"/d.MODELS[0][0]).glob("revision_*")))
            self.assertEqual(json.loads((item/"NOX_WEIGHTS_SHA256.json").read_text())["state"],"SHA256_CHECKED")
            (item/"model.safetensors").write_bytes(b"tampered!")
            with self.assertRaises(RuntimeError):
                d.check_existing(item,item/"NOX_WEIGHTS_SHA256.json",files,"c"*40)
    def test_disk_reserve_fails_before_download(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/"brain").mkdir()
            def info(mid,revision,files_metadata):
                return SimpleNamespace(id=mid,sha="c"*40,
                    card_data=SimpleNamespace(license="apache-2.0"),
                    siblings=[SimpleNamespace(rfilename="model.safetensors",size=8)])
            fake=SimpleNamespace(HfApi=lambda:SimpleNamespace(model_info=info),
                                 snapshot_download=lambda **kwargs:self.fail("download called"))
            with patch.dict(sys.modules,{"huggingface_hub":fake}),\
                 patch.object(d.shutil,"disk_usage",return_value=SimpleNamespace(free=10_000_000_000)):
                with self.assertRaises(RuntimeError):
                    d.download(root)
if __name__=="__main__":
    main()
