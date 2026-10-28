"""NOX V16 E01 R03 exact-source offline regressions, not Windows acceptance."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from d02_admission import BASE_COMMIT, BASE_TREE, CANONICAL_CORES, check, overall, file_evidence

CSS = """.nox-cinema-control::before {pointer-events:none;}
.nox-cinema-control[data-nox-float=\"true\"] {animation:none;filter:brightness(1)}
.nox-cinema-control[data-nox-float=\"true\"]::after {pointer-events:none;animation:float 6s} 
@media (prefers-reduced-motion: reduce) {.nox-cinema-control::after{animation:none}}"""
JS = """function isActive(){return !disposed&&!doc.hidden&&hostVisible&&intersectVisible;}
function syncVisible(){root.dataset.noxFxVisible=isActive()?"true":"false";if(isActive())wake();else sleep();}
function loop(now){if(!isActive())return;}
intersectVisible=items.some(x=>x.isIntersecting);syncVisible();
setVisible(value){hostVisible=value===true;syncVisible();}
if(preference)sleep();const mode="REDUCED";"""
ASSETS_DIR = tempfile.TemporaryDirectory()
ASSETS = Path(ASSETS_DIR.name)
NAMES = ('home','menu','core','sections')
for n in NAMES:
    (ASSETS/n).write_bytes(('original-d02-'+n).encode())

def receipt(n):
    data=(ASSETS/n).read_bytes()
    return {'path':n,'pre_sha256':hashlib.sha256(data).hexdigest(),
            'post_sha256':hashlib.sha256(data).hexdigest(),
            'git_blob_sha1':hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()}

def fixture():
    return {'git_commit': BASE_COMMIT, 'git_tree': BASE_TREE,
      'owner6_source_lock': {'owner':6,'verified':True,'git_commit':BASE_COMMIT,
           'git_tree':BASE_TREE,'readback_receipt':'fixture','all_source_sha256':'fixture'},
      'mount_candidates':['PR67'],'core_ids':list(CANONICAL_CORES),
      'orb_ids':['HELION',*CANONICAL_CORES], 'cinema_css':CSS,'cinema_js':JS,
      'asset_root':str(ASSETS),'asset_receipts':[receipt(p) for p in NAMES],
      'changed_paths':['proposals/P01/G1_01_D02_WOW_ADMISSION/d02_admission.py']}

class Admission(unittest.TestCase):
    def test_ten_negative_regressions(self):
        edits=[('git_commit','f'*40),('owner6_source_lock',{}),
          ('mount_candidates',['PR63','PR67']),('core_ids',['WRONG']*8),
          ('orb_ids',['HELION',*CANONICAL_CORES,'EXTRA']),
          ('cinema_css',CSS+'\n.nox-cinema-control[data-nox-float="true"]{animation:float 1s}'),
          ('cinema_js',JS.replace('&&hostVisible','')),
          ('cinema_css',CSS.replace('prefers-reduced-motion: reduce','not-reduced')),
          ('asset_receipts',[]),('changed_paths',['Packages/P02/host.py'])]
        for i,(k,v) in enumerate(edits,1):
            with self.subTest(task=i):
                s=fixture();s[k]=v
                self.assertEqual(check(s)[f'E01-G1-{i:02d}'],'HOLD')
    def test_safe_animation_none_override(self):
        x=fixture()
        x['cinema_css'] = x['cinema_css'].replace('animation:none;filter:brightness(1)', 'animation:none!important;filter:brightness(1)')
        self.assertEqual(check(x)['E01-G1-06'], 'SOURCE_GATE_PASS')
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

    def test_all_ten_source_only_gates_with_actual_fixture_bytes(self):
        x=overall(fixture())
        self.assertEqual(len(x['checks']),10)
        self.assertEqual(set(x['checks'].values()),{'SOURCE_GATE_PASS'})
        self.assertEqual(x['source_admission'],'CANDIDATE_ONLY')
        self.assertEqual(x['integrated'],'HOLD')

    def test_animation_on_base_or_hover_click_target_hold(self):
        for selector in ('.nox-cinema-control', '.nox-cinema-control:hover',
                         '.nox-cinema-control[data-nox-float="true"]'):
            with self.subTest(selector=selector):
                x=fixture();x['cinema_css']+=f'\n{selector}{{animation:jump 1s}}'
                self.assertEqual(check(x)['E01-G1-06'],'HOLD')

    def test_transform_on_click_target_hold_even_if_animation_none(self):
        x=fixture();x['cinema_css']+='\n.nox-cinema-control:hover{transform:translateY(-3px)}'
        self.assertEqual(check(x)['E01-G1-06'],'HOLD')

    def test_pseudo_light_animation_allowed_if_noninteractive(self):
        x=fixture();x['cinema_css']+='\n.nox-cinema-control::after{animation:float 3s;pointer-events:none}'
        self.assertEqual(check(x)['E01-G1-06'],'SOURCE_GATE_PASS')

    def test_missing_pseudo_pointer_veto_hold(self):
        x=fixture();x['cinema_css']=x['cinema_css'].replace('::after {pointer-events:none;', '::after {')
        self.assertEqual(check(x)['E01-G1-06'],'HOLD')

    def test_old_single_active_visibility_hold(self):
        x=fixture();x['cinema_js']='root.dataset.noxFxVisible=(!doc.hidden&&active);if(disposed||!active||doc.hidden)return;'
        self.assertEqual(check(x)['E01-G1-07'],'HOLD')

    def test_each_veto_required(self):
        for fragment in ('&&hostVisible','&&intersectVisible','!doc.hidden',
                         'hostVisible=value===true','intersectVisible=items.some(x=>x.isIntersecting)',
                         'if(!isActive())return'):
            with self.subTest(fragment=fragment):
                x=fixture();x['cinema_js']=x['cinema_js'].replace(fragment,'INVALID')
                self.assertEqual(check(x)['E01-G1-07'],'HOLD')

    def test_reduced_js_sleep_required(self):
        x=fixture();x['cinema_js']=x['cinema_js'].replace('if(preference)sleep();','')
        self.assertEqual(check(x)['E01-G1-08'],'HOLD')

    def test_fake_or_missing_asset_bytes_hold(self):
        x=fixture();x['asset_receipts'][0]['post_sha256']='a'*64
        self.assertEqual(check(x)['E01-G1-09'],'HOLD')
        x=fixture();x['asset_root']='/definitely-absent-nox-original-media'
        self.assertEqual(check(x)['E01-G1-09'],'HOLD')
        x=fixture();x['asset_receipts'][0]['git_blob_sha1']='b'*40
        self.assertEqual(check(x)['E01-G1-09'],'HOLD')

    def test_path_escape_or_binary_blocked(self):
        for path in ('proposals/P01/../P02/hijack.py',
                     'proposals/P01/\\private.py', 'proposals/P01/test.EXE',
                     'proposals/P01//double.py'):
            with self.subTest(path=path):
                x=fixture();x['changed_paths']=[path]
                self.assertEqual(check(x)['E01-G1-10'],'HOLD')

    def test_malformed_file_hash_receipt_is_hold_not_exception(self):
        self.assertFalse(file_evidence(ASSETS, {'home': {'sha256':None,'git_blob_sha1':3}}))
        self.assertFalse(file_evidence(ASSETS, {'home': None}))
        self.assertFalse(file_evidence('/definitely-missing-archive', {'home':{}}))

if __name__=='__main__':unittest.main()
