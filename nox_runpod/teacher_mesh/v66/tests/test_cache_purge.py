import ast
import unittest
from nox_runpod.teacher_mesh.v66 import cache_purge

class CachePurgeSourceContract(unittest.TestCase):
    def source(self):
        start="python3 - <<'PYREMOTE'\n"
        end="\nPYREMOTE"
        assert cache_purge.REMOTE.count(start)==1
        return cache_purge.REMOTE.split(start,1)[1].split(end,1)[0]

    def test_embedded_python_compiles(self):
        ast.parse(self.source())

    def test_exact_pip_cache_only(self):
        s=self.source()
        self.assertIn("CACHE=Path('/root/.cache/pip')",s)
        self.assertIn("CACHE.resolve(strict=True)!=CACHE",s)
        self.assertIn("HOLD_UNSAFE_CACHE_ENTRY",s)
        self.assertIn("st.st_nlink!=1",s)

    def test_no_targeting_models_checkpoint_s03(self):
        s=self.source()
        self.assertNotIn("shutil.rmtree",s)
        self.assertNotIn("os.system",s)
        self.assertNotIn("subprocess.run(",s)
        for field in ('model_files_touched','memory_files_touched',
                     'checkpoint_files_touched','hf_cache_touched','tmp_files_touched'):
            self.assertIn("'"+field+"':False",s)

    def test_protection_and_pre_post_space_readback(self):
        s=self.source()
        for marker in ("HOLD_GLOBAL_STOP_SIGNAL","HOLD_CACHE_BUSY",
                       "HOLD_PARTIAL_CACHE_PURGE","free_before_bytes",
                       "free_after_bytes","remaining_cache_bytes"):
            self.assertIn(marker,s)

    def test_no_unverified_success(self):
        code=cache_purge.main.__code__
        self.assertTrue(any(isinstance(x,str) and "HOLD_NOT_FULLY_VERIFIED" in x
                            for x in code.co_consts))
        self.assertIn("NATIVE_PIP_CACHE_CLEANED",repr(code.co_consts))

    def test_prekey_retry_is_bounded_and_never_retries_after_key_track(self):
        source=cache_purge.__file__
        with open(source,encoding="utf-8") as stream:
            text=stream.read()
        self.assertIn("for attempt in range(1,4)",text)
        self.assertIn("if ssh.TRACK.exists() or attempt==3",text)
        self.assertIn("HOLD_NATIVE_PROBE_EXCEPTION",text)

if __name__=="__main__":
    unittest.main()
