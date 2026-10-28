"""Synthetic-source negative tests; not proof of actual approved D02/WebView2."""
import unittest
from d02_fx_owner_gate import BASE_COMMIT, BASE_TREE, audit, verdict

JS = '''export function installNoxCinemaFX(){validateScene(orbs);
if(orbs.length!==CORE_COUNT+1)throw Error();
if(new Set(ids).size!==CORE_COUNT+1)throw Error();
if(new Set(orbs.map(x=>x.element)).size!==CORE_COUNT+1)throw Error();
root.dataset.noxFxState="idle";
if(event.trusted!==true)return;
if(pendingHostEvents.length<16)pendingHostEvents.push(event);
hostEvents.subscribe(applyHostEvent);eventsReady=true;
mounted.set(root,true);mounted.delete(root);
try{if(unsubscribe)unsubscribe();}catch(error){cleanup=true;}
delete orb.element.dataset.noxFxState;delete root.dataset.noxFxState;
function isActive(){return !disposed&&!doc.hidden&&hostVisible&&intersectVisible;}
if(!isActive())return;
intersectVisible=items.some(x=>x.isIntersecting);
const motion="(prefers-reduced-motion: reduce)";
if(preference)sleep();if(particleCount>=policy.maxParticles)return;
const arc=Math.sin(Math.PI*t);const radius=p.surfaceRadius+arc*p.reach;
const item={done:t>=1};if(position.done)clear();
}'''
PATH = ['proposals/P01/G1_01_D02_WOW_ADMISSION/d02_fx_owner_gate.py']


def run(js=JS, paths=PATH, commit=BASE_COMMIT, tree=BASE_TREE):
    return audit(js, commit=commit, tree=tree, changed_paths=paths)


class D02OverlayAdmission(unittest.TestCase):
    def test_01_source_fixture_passes_all_ten(self):
        self.assertEqual(list(run().values()), ['SOURCE_CHECK_PASS'] * 10)

    def test_02_baseline_mismatch_holds(self):
        self.assertEqual(run(commit='0' * 40)['E01-R04-01'], 'HOLD')

    def test_03_missing_installer_holds(self):
        self.assertEqual(run(JS.replace('export function installNoxCinemaFX', 'function unrelated'))['E01-R04-02'], 'HOLD')

    def test_04_duplicate_element_guard_missing_holds(self):
        self.assertEqual(run(JS.replace('new Set(orbs.map(x=>x.element)).size', 'orbs.length'))['E01-R04-03'], 'HOLD')

    def test_05_native_state_writes_rejected(self):
        for code in ('root.dataset.noxState="idle";',
                     'root.dataset["noxState"]="idle";',
                     'delete root.dataset.noxState;',
                     'root.setAttribute("data-nox-state", "idle");',
                     'root.removeAttribute("data-nox-state");'):
            with self.subTest(code=code):
                self.assertEqual(run(JS + '\n' + code)['E01-R04-04'], 'HOLD')

    def test_06_trusted_event_guard_missing_holds(self):
        self.assertEqual(run(JS.replace('event.trusted!==true', 'event.trusted===false'))['E01-R04-05'], 'HOLD')

    def test_07_cleanup_missing_holds(self):
        self.assertEqual(run(JS.replace('mounted.delete(root)', 'mounted.keep(root)'))['E01-R04-06'], 'HOLD')

    def test_08_visibility_independent_veto_holds(self):
        self.assertEqual(run(JS.replace('&&intersectVisible', ''))['E01-R04-07'], 'HOLD')

    def test_09_reduce_motion_holds(self):
        self.assertEqual(run(JS.replace('if(preference)sleep();', ''))['E01-R04-08'], 'HOLD')

    def test_10_gravity_must_return_to_origin(self):
        self.assertEqual(run(JS.replace('Math.sin(Math.PI*t)', 'Math.cos(Math.PI*t)'))['E01-R04-09'], 'HOLD')

    def test_11_host_and_exe_paths_blocked(self):
        self.assertEqual(run(paths=['coordination/e06/shared-host.py'])['E01-R04-10'], 'HOLD')

    def test_12_metadata_cannot_claim_windows_acceptance(self):
        r=verdict(JS, commit=BASE_COMMIT, tree=BASE_TREE, changed_paths=PATH)
        self.assertEqual(r['windows_accepted'], 'NOT_RUN')
        self.assertEqual(r['source_lock_729'], 'HOLD')
        self.assertEqual(r['weighted_progress'], 'N/D')

if __name__ == '__main__':
    unittest.main()
