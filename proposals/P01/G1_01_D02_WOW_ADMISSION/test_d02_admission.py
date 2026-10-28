"""11 offline regression checks only; not native Windows acceptance."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from d02_admission import BASE_COMMIT, BASE_TREE, CANONICAL_CORES, check, overall, file_evidence

CSS = '.nox-cinema-control::before {pointer-events:none;}\n.nox-cinema-control[data-nox-float="true"]{filter:brightness(1)}\n@media(prefers-reduced-motion:reduce){}'
JS = 'root.dataset.noxFxVisible=(!doc.hidden&&active);if(disposed||!active||doc.hidden)return; const mode="REDUCED";'

def fixture():
    h = 'a'*64
    return {'git_commit': BASE_COMMIT, 'git_tree': BASE_TREE,
      'owner6_source_lock': {'owner':6,'verified':True,'git_commit':BASE_COMMIT,
           'git_tree':BASE_TREE,'readback_receipt':'fixture','all_source_sha256':'fixture'},
      'mount_candidates':['PR67'],'core_ids':list(CANONICAL_CORES),
      'orb_ids':['HELION',*CANONICAL_CORES], 'cinema_css':CSS,'cinema_js':JS,
      'asset_receipts':[{'path':p,'pre_sha256':h,'post_sha256':h} for p in ['home','menu','core','sections']],
      'changed_paths':['proposals/P01/G1_01_D02_WOW_ADMISSION/d02_admission.py']}

class Admission(unittest.TestCase):
    def test_ten_negative_regressions(self):
        edits=[('git_commit','f'*40),('owner6_source_lock',{}),
          ('mount_candidates',['PR63','PR67']),('core_ids',['WRONG']*8),
          ('orb_ids',['HELION',*CANONICAL_CORES,'EXTRA']),
          ('cinema_css',CSS+'\n.nox-cinema-control[data-nox-float="true"]{animation:float 1s}'),
          ('cinema_js',JS.replace('(!doc.hidden&&active)','!doc.hidden')),
          ('cinema_css',CSS.replace('prefers-reduced-motion:reduce','not-reduced')),
          ('asset_receipts',[]),('changed_paths',['Packages/P02/host.py'])]
        for i,(k,v) in enumerate(edits,1):
            with self.subTest(task=i):
                s=fixture();s[k]=v
                self.assertEqual(check(s)[f'E01-G1-{i:02d}'],'HOLD')
    def test_fixture_does_not_claim_windows(self):
        o=overall(fixture())
        self.assertEqual(o['source_admission'],'CANDIDATE_ONLY')
        self.assertEqual(o['windows_accepted'],'NOT_RUN')
    def test_independent_file_bytes_and_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'scene.css';data=b'.a{}';p.write_bytes(data)
            m={'scene.css':{'sha256':hashlib.sha256(data).hexdigest(),
               'git_blob_sha1':hashlib.sha1(b'blob 4\x00'+data).hexdigest()}}
            self.assertTrue(file_evidence(Path(tmp),m))
            p.write_bytes(data+b' ')
            self.assertFalse(file_evidence(Path(tmp),m))

if __name__=='__main__':unittest.main()
