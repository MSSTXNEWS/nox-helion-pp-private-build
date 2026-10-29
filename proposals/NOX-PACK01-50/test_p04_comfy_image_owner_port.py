import unittest
import p04_comfy_image_owner_port as m

class Fake:
    def __init__(self): self.calls=[];self.result={'status':'QUEUED_NOT_RENDERED','prompt_id':'abcde123'}
    def prepare(self, **args):
        self.calls.append(('prepare',args));return {'prompt':{'6':{}},'client_id':'trusted-native'}
    def submit(self, prepared, *, native_authorized):
        self.calls.append(('submit',prepared,native_authorized));return self.result

class Tests(unittest.TestCase):
    def setUp(self):
        self.fake=Fake();self.allow=True;self.stopped=False;self.backend=True
        self.selection=dict(workflow={'6':{}},workflow_digest='a'*64,prompt_node='6',prompt='hello',model='native-model',client_id='trusted-native')
        self.port=m.P04ComfyOwnerPort(self.fake,
            select_approved_request=lambda _:dict(self.selection),
            native_permission=lambda _s,_r:self.allow,
            native_stop=lambda:self.stopped,
            native_backend_ready=lambda:self.backend)
    def test_preexisting_comfy_api_reused(self):
        res=self.port.generate('native-session',{})
        self.assertEqual(res['status'],'QUEUED_NOT_RENDERED');self.assertFalse(res['accepted'])
        self.assertEqual([x[0] for x in self.fake.calls],['prepare','submit'])
    def test_no_native_consent_no_queued_image(self):
        self.allow=False
        with self.assertRaises(m.ImageDenied):self.port.generate('native-session',{})
        self.assertEqual(self.fake.calls,[])
    def test_ui_cannot_choose_workflow_or_endpoint(self):
        for payload in ({'workflow':{}},{'url':'https://elsewhere.invalid'}, {'prompt':'fake'}):
            with self.assertRaises(m.ImageDenied):self.port.generate('native-session',payload)
    def test_stop_denies_backend(self):
        self.stopped=True
        with self.assertRaises(m.ImageHold):self.port.generate('native-session',{})
        self.assertEqual(self.fake.calls,[])
    def test_offline_backend_denied(self):
        self.backend=False
        self.assertFalse(self.port.available())
        with self.assertRaises(m.ImageHold):self.port.generate('native-session',{})
    def test_malformed_native_selection_hold(self):
        self.selection['endpoint']='https://attacker.invalid'
        with self.assertRaises(m.ImageHold):self.port.generate('native-session',{})
        self.assertEqual(self.fake.calls,[])
    def test_no_false_rendered_success(self):
        self.fake.result={'status':'RENDERED','prompt_id':'abc'}
        with self.assertRaises(m.ImageHold):self.port.generate('native-session',{})
    def test_missing_existing_comfy_port_hold(self):
        with self.assertRaises(m.ImageHold):m.P04ComfyOwnerPort(object(),select_approved_request=lambda _: {},
           native_permission=lambda *_:True,native_stop=lambda:False,native_backend_ready=lambda:True)
    def test_revoked_after_prepare_does_not_submit(self):
        def prepare(**args): self.allow=False;return {'prompt':{},'client_id':'native'}
        self.fake.prepare=prepare
        with self.assertRaises(m.ImageDenied):self.port.generate('native-session',{})
        self.assertEqual(self.fake.calls,[])

if __name__=='__main__':unittest.main()
