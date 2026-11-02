"""Native source contract: optional P01/P03 FirstBoot download approval is
independent from separately signed read-only A1 research. No fake policy."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/nox_selfbuilder/onehost_builder.py'

def original_boot_method():
    tree = ast.parse(SOURCE.read_text('utf-8'), filename=str(SOURCE))
    owner = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'OneHostSelfBuilder')
    func = next(x for x in owner.body if isinstance(x, ast.FunctionDef) and x.name == 'native_a_boot')
    ns = {}
    exec(compile(ast.Module(body=[func],type_ignores=[]),str(SOURCE),'exec'),ns)
    return ns['native_a_boot']

class First:
    def __init__(self,state,schema='NOX-FIRSTBOOT-RECEIPT-v1'):
        self.state,self.schema,self.calls=state,schema,0
    def run(self,session,*,now):
        self.calls+=1
        return {'schema':self.schema,'status':self.state,'downloaded':0,'release_accepted':False}

class Research:
    def __init__(self,state='READY_FOR_EXISTING_IDLE_TICK'):
        self.state,self.calls=state,0
    def boot(self,session,*,now):
        self.calls+=1
        return {'schema':'NOX-A1-INITIATIVE-SOURCE-v1','state':self.state}

class NativeFixture:
    native_a_boot=None
    def __init__(self,first,research):
        self._a_firstboot,self._a_native_bridge=first,research
        self.guards=0
    def _a_guard(self,session):
        self.guards+=1
        if session!='native':
            raise PermissionError('NATIVE_SESSION_REQUIRED')

class IndependentConsent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        NativeFixture.native_a_boot=original_boot_method()
    def check(self,first='HOLD',research='READY_FOR_EXISTING_IDLE_TICK',schema='NOX-FIRSTBOOT-RECEIPT-v1'):
        f,r=First(first,schema),Research(research)
        host=NativeFixture(f,r)
        return f,r,host,host.native_a_boot('native',now='fixture')
    def test_download_hold_does_not_block_separately_signed_research(self):
        _,r,host,receipt=self.check()
        self.assertEqual(receipt['state'],'READY_FOR_EXISTING_IDLE_TICK')
        self.assertTrue(receipt['firstboot_pending_separate_consent'])
        self.assertFalse(receipt['firstboot_download_approved_by_a1'])
        self.assertEqual(r.calls,1)
        self.assertEqual(host.guards,3)
    def test_stop_revokes_research(self):
        _,r,_,receipt=self.check('STOPPED')
        self.assertEqual(receipt['state'],'HOLD')
        self.assertEqual(r.calls,0)
    def test_research_denied_even_if_firstboot_pending(self):
        _,r,_,receipt=self.check('HOLD','HOLD')
        self.assertEqual(receipt['state'],'HOLD')
        self.assertEqual(r.calls,1)
    def test_queued_not_claimed_installed(self):
        _,r,_,receipt=self.check('QUEUED_NOT_INSTALLED')
        self.assertEqual(receipt['state'],'READY_FOR_EXISTING_IDLE_TICK')
        self.assertFalse(receipt['firstboot_download_approved_by_a1'])
        self.assertEqual(r.calls,1)
    def test_unknown_firstboot_status_rejected(self):
        _,r,_,receipt=self.check('PASS')
        self.assertEqual(receipt['state'],'HOLD')
        self.assertEqual(r.calls,0)
    def test_untrusted_firstboot_schema_rejected(self):
        f,r=First('HOLD','FORGED'),Research()
        host=NativeFixture(f,r)
        with self.assertRaises(PermissionError):
            host.native_a_boot('native',now='fixture')
        self.assertEqual(r.calls,0)
    def test_untrusted_session_rejected(self):
        f,r=First('HOLD'),Research()
        host=NativeFixture(f,r)
        with self.assertRaises(PermissionError):
            host.native_a_boot('browser',now='fixture')
        self.assertEqual(f.calls,0)
    def test_already_present_never_grants_download_via_a1(self):
        _,r,_,receipt=self.check('ALREADY_PRESENT')
        self.assertEqual(receipt['state'],'READY_FOR_EXISTING_IDLE_TICK')
        self.assertFalse(receipt['firstboot_download_approved_by_a1'])
        self.assertEqual(r.calls,1)

if __name__=='__main__':unittest.main()
