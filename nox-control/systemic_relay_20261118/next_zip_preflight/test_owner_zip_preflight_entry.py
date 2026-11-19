"""Validate exact one-use reviewed plan, DONE predecessor and owner payload."""
import hashlib,importlib.util,os
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ENTRY=HERE/'owner_zip_reviewed_preflight_entry.py'
OP=REPO/'nox-control/owner_native_operator.py'

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class ReviewedPreflightOwner(unittest.TestCase):
    def test_postimage_and_existing_preimage_pinned(self):
        e=load(ENTRY,'nox_zip_preflight_new')
        self.assertEqual(hashlib.sha256((HERE/'merge_web_source.py').read_bytes()).hexdigest(),
            '9f091b4e608194e6142e0491e9a22896fec8cc32803870214647efee7884e413')
        self.assertEqual(e.SOURCE_SHA,
            '7e9ffd7e6a3c69d8d7529d804ebd8d29d3a9199b1c39a2177eb1bc2a230d55b3')
        self.assertEqual(e.PREDECESSOR_RECEIPT_SHA,
            '4c347d8001d6c67e6f5479cb2af868fdc03e84a7a88203102244d6d359149c3b')
        self.assertEqual(e.CURRENT_CONFIG_SHA,
            '6ba8de14b7498740d5a3ffb7a0216c5387c2ce904c19cf7a16772c1046cdfeb3')

    def test_one_new_reviewed_task_exact_verifier(self):
        e=load(ENTRY,'nox_zip_preflight_plan')
        p=e.reviewed_plan()
        self.assertEqual(p['task_id'],'0V14-14.project.reviewed_zip_preflight_20261119')
        self.assertEqual(p['review_origin'],'OWNER_REVIEWED')
        self.assertEqual(p['verification'],{'kind':'python_unittest',
                          'modules':['test_nox_merge_overlay_paths'],
                          'min_tests':6,'timeout_sec':120})
        self.assertEqual(p['files'][0]['before_sha256'],e.SOURCE_SHA)
        self.assertEqual(p['files'][0]['after_sha256'],e.REVIEWED_SHA)
        self.assertFalse(p['original_task_accepted'])

    def test_scope_unchanged_owner_dispatcher(self):
        e=load(ENTRY,'nox_zip_preflight_bundle')
        o=load(OP,'nox_zip_preflight_owner')
        self.assertEqual(o.FILES['repair'],
            'nox-control/systemic_relay_20261118/next_zip_preflight/owner_zip_reviewed_preflight_entry.py')
        previous=os.getcwd()
        try:
            os.chdir(REPO)
            paths=o.repair_bundle_paths('repair',o.FILES['repair'],())
        finally:
            os.chdir(previous)
        self.assertEqual({Path(p).name for p in paths},e.ASSET_NAMES)
        self.assertEqual(len(paths),3)

    def test_done_predecessor_never_replayed(self):
        t=ENTRY.read_text()
        self.assertIn("DONE_PREDECESSOR_READBACK",t)
        self.assertIn("'status':'done'",t)
        self.assertIn("'postimages':{'merge_web_source.py':SOURCE_SHA}",t)
        self.assertIn("ONE_SHOT_NO_REPLAY",t)
        self.assertNotIn("subprocess.run(",t)
        self.assertNotIn("os.system(",t)
if __name__=='__main__':unittest.main()
