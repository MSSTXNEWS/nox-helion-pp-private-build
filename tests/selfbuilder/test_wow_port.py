import json,unittest
from nox_selfbuilder.wow_onehost_port import WowOneHostPort
from nox_selfbuilder.wow_design import DesignHold
H='b'*40;S='git:'+H+':approved/main.py'
class Session:
 def validate(self):return True
 def __init__(self):self.native=True
class PortTests(unittest.TestCase):
 def setUp(self):
  self.records={};self.events=[];self.allow=True;self.stop=False
  self.payload={'variants':[{'id':f'v{i}','title':f'Direction {i}',
     'layout':['ORBITAL','CINEMATIC','WORKSPACE'][i-1],
     'rationale':'Canonical D02 locked','screens':[{'section':'РАБОТА','title':'Project',
     'route_id':'commands','buttons':[{'label':'Start','action_id':'run-program',
     'purpose':'Launch code candidate under owner approval'}]}]} for i in (1,2,3)],'source_ids':[S]}
  def audit(session,event,record):
   self.events.append(event)
   if event=='WOW_DESIGN_CANDIDATE':self.records[record['proposal_sha256']]=record
  self.port=WowOneHostPort(native_source_head=lambda s:H,
    source_evidence=lambda s,t,h:[{'verified':True,'source_id':S}],
    existing_p02_design_generate=lambda s,r:json.dumps(self.payload,ensure_ascii=False),
    native_authorize=lambda s,a,d:self.allow,
    native_stop=lambda s:self.stop,s03_audit=audit,
    s03_read_proposal=lambda s,sha:self.records.get(sha))
  self.session=Session()
 def test_original_onehost_flow(self):
  p=self.port.propose(self.session,'Design three project views for existing NOX')
  self.assertEqual(len(p['variants']),3)
  decision=self.port.approve(self.session,proposal_sha256=p['proposal_sha256'],variant_id='v2')
  self.assertEqual(decision['state'],'OWNER_ACCEPTED_DESIGN')
  self.assertFalse(decision['code_generated']);self.assertFalse(decision['code_installed'])
  self.assertEqual(self.events,['WOW_DESIGN_CANDIDATE','WOW_DESIGN_APPROVED'])
 def test_renderer_cannot_fabricate_proposal(self):
  with self.assertRaises(DesignHold):self.port.approve(self.session,proposal_sha256='f'*64,variant_id='v1')
 def test_no_auth_no_model(self):
  self.allow=False
  with self.assertRaises(DesignHold):self.port.propose(self.session,'Design three project views for existing NOX')
 def test_stop_blocks(self):
  self.stop=True
  with self.assertRaises(DesignHold):self.port.propose(self.session,'Design three project views for existing NOX')
 def test_head_drift(self):
  p=self.port.propose(self.session,'Design three project views for existing NOX')
  self.port.head=lambda _: 'd'*40
  with self.assertRaises(DesignHold):self.port.approve(self.session,proposal_sha256=p['proposal_sha256'],variant_id='v1')
 def test_review_reject_unknown_option(self):
  p=self.port.propose(self.session,'Design three project views for existing NOX')
  with self.assertRaises(DesignHold):self.port.approve(self.session,proposal_sha256=p['proposal_sha256'],variant_id='v7')
if __name__=='__main__':unittest.main()