import json,unittest
from nox_selfbuilder.wow_design import (parse_design_proposals,propose_design,
                                        approve_design,DesignHold,SECTIONS)
H='a'*40
S='git:'+H+':approved/source.py'
def idea(variant,section='РАБОТА',route='commands'):
    return {'id':f'v{variant}','title':f'Вариант {variant}',
      'layout':['ORBITAL','CINEMATIC','WORKSPACE'][variant-1],
      'rationale':'Киноязык NOX без замены D02','screens':[
      {'section':section,'title':'Новый рабочий экран','route_id':route,
      'buttons':[{'label':'Открыть модуль','action_id':'open-module',
                  'purpose':'Переход с проверенным обработчиком'}]}]}
RAW=lambda:json.dumps({'variants':[idea(i) for i in range(1,4)],'source_ids':[S]},ensure_ascii=False)
class WowTest(unittest.TestCase):
    def parse(self,raw=None):return parse_design_proposals(raw or RAW(),current_head=H,required_source_ids=(S,))
    def test_three(self):
        p=self.parse();self.assertEqual(len(p['variants']),3);self.assertEqual(p['menu_sections'],list(SECTIONS))
    def test_src(self):self.assertEqual(self.parse()['source_head'],H)
    def test_d02(self):self.assertTrue(self.parse()['home_d02_unchanged'])
    def test_code_not_installed(self):self.assertFalse(self.parse()['code_installed'])
    def test_no_live_button(self):self.assertEqual(self.parse()['variants'][0]['screens'][0]['buttons'][0]['status'],'CONTRACT_REQUIRED')
    def test_new_route_requires_contract(self):
        p=json.loads(RAW());p['variants'][0]['screens'][0]['route_id']='my-new-route'
        self.assertEqual(self.parse(json.dumps(p))['variants'][0]['screens'][0]['route_status'],'NEW_CONTRACT_REQUIRED')
    def test_ninth_menu_denied(self):
        p=json.loads(RAW());p['variants'][0]['screens'][0]['section']='MY_NEW_MENU'
        with self.assertRaises(DesignHold):self.parse(json.dumps(p))
    def test_duplicate_variants(self):
        p=json.loads(RAW());p['variants'][1]['id']='v1'
        with self.assertRaises(DesignHold):self.parse(json.dumps(p))
    def test_untrusted_source(self):
        p=json.loads(RAW());p['source_ids']=['git:'+H+':impostor.py']
        with self.assertRaises(DesignHold):self.parse(json.dumps(p))
    def test_bad_dangerous_action(self):
        p=json.loads(RAW());p['variants'][0]['screens'][0]['buttons'][0]['action_id']='../../etc'
        with self.assertRaises(DesignHold):self.parse(json.dumps(p))
    def test_prompt_only_with_owner_consent(self):
        called=[]
        with self.assertRaises(DesignHold):
            propose_design(task='Create menu variants',source_head=H,
                source_evidence=[{'source_id':S,'verified':True}],
                native_authorize=lambda *_:False,local_coder=lambda _:called.append(1),
                stop_requested=lambda:False,s03_record=lambda *_:None)
        self.assertFalse(called)
    def test_p02_model_and_s03_actual_receipt(self):
        saved=[]
        p=propose_design(task='Improve original MENU and visual sections',source_head=H,
                source_evidence=[{'source_id':S,'verified':True}],
                native_authorize=lambda *_:True,local_coder=lambda _:RAW(),
                stop_requested=lambda:False,s03_record=lambda *args:saved.append(args))
        self.assertEqual(saved[0][0],'WOW_DESIGN_CANDIDATE')
        self.assertEqual(saved[0][1]['proposal_sha256'],p['proposal_sha256'])
    def test_revoke_after_inference(self):
        seen=[]
        def allow(*_):seen.append(True);return len(seen)==1
        with self.assertRaises(DesignHold):propose_design(
            task='Create three original menu directions',source_head=H,
            source_evidence=[{'source_id':S,'verified':True}],
            native_authorize=allow,local_coder=lambda _:RAW(),
            stop_requested=lambda:False,s03_record=lambda *_:self.fail('No writes'))
    def test_approval_requires_consent(self):
        p=self.parse()
        with self.assertRaises(DesignHold):approve_design(p,variant_id='v1',expected_sha256=p['proposal_sha256'],current_head=H,
          native_authorize=lambda *_:False,stop_requested=lambda:False,s03_record=lambda *_:self.fail('No writes'))
    def test_approval_writes_only_task_not_code(self):
        p=self.parse();saved=[]
        a=approve_design(p,variant_id='v2',expected_sha256=p['proposal_sha256'],current_head=H,
          native_authorize=lambda *_:True,stop_requested=lambda:False,s03_record=lambda *args:saved.append(args))
        self.assertFalse(a['code_generated']);self.assertFalse(a['code_installed']);self.assertIn('D02',a['source_task'])
        self.assertEqual(saved[0][0],'WOW_DESIGN_APPROVED')
    def test_approval_sha_mismatch(self):
        p=self.parse()
        with self.assertRaises(DesignHold):approve_design(p,variant_id='v1',expected_sha256='0'*64,current_head=H,
          native_authorize=lambda *_:True,stop_requested=lambda:False,s03_record=lambda *_:self.fail('No writes'))
    def test_approval_head_drift(self):
        p=self.parse()
        with self.assertRaises(DesignHold):approve_design(p,variant_id='v1',expected_sha256=p['proposal_sha256'],current_head='b'*40,
          native_authorize=lambda *_:True,stop_requested=lambda:False,s03_record=lambda *_:self.fail('No writes'))
    def test_approval_revoked_before_s03(self):
        p=self.parse();n=[]
        def allow(*_):n.append(1);return len(n)==1
        with self.assertRaises(DesignHold):approve_design(p,variant_id='v1',expected_sha256=p['proposal_sha256'],current_head=H,
          native_authorize=allow,stop_requested=lambda:False,s03_record=lambda *_:self.fail('No writes'))
if __name__=='__main__':unittest.main()