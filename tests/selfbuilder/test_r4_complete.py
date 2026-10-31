import unittest, tempfile, json, hashlib
from pathlib import Path
from nox_selfbuilder.complete_builder import CompleteBuilder, SelfBuilderHold
from nox_selfbuilder.p02_coder import P02Coder, CodingHold
from nox_selfbuilder.p04_forge_bridge import request_gpu_training, ForgeHold
HEAD='aa054edd2e7c759cd0b386af86cd88a4d600a489'
EVIDENCE=[{'source_id':'V16','text':'MENU V2 uses existing eight tiles; GPU training lives in development','verified':True}]
OUTPUT={'files':[{'path':'extensions/testpanel/action.py','content':'def add(a, b):\n    return a + b\n'},
                 {'path':'extensions/testpanel/page.mjs','content':'export const status = "HOLD";\n'},
                 {'path':'extensions/testpanel/style.css','content':'.x{color:#fff;}\n'}],
        'source_ids':['V16'],'rationale':'Add a verifiable extension candidate, not a live modification.'}

def builder(generate=None,admission=True):
 return CompleteBuilder(recall=lambda s,t,ss:EVIDENCE,generate=generate or (lambda s,r:json.dumps(OUTPUT)),
    native_authorize=lambda s,route,args:True,source_admission=lambda head:admission)

class CompleteTests(unittest.TestCase):
 def test_multilanguage_staging(self):
  with tempfile.TemporaryDirectory() as t:
   r=builder().propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
   self.assertEqual(len(r['files']),3)
   self.assertFalse(r['merge']);self.assertFalse(r['updated_weights'])
   self.assertEqual(len(list(Path(t).iterdir())),1)
   for x in r['files']:
    self.assertEqual(hashlib.sha256((Path(t)/r['run_id']/x['candidate_file']).read_bytes()).hexdigest(),x['sha256'])
 def test_source_required(self):
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):builder(admission=False).propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
   self.assertEqual(list(Path(t).iterdir()),[])
 def test_no_traversal(self):
  x=dict(OUTPUT,files=[{'path':'../../evil.py','content':'print("foo")\n'}])
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):builder(lambda s,r:json.dumps(x)).propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
   self.assertFalse((Path(t)/'evil.py').exists())
 def test_no_protected_home(self):
  x=dict(OUTPUT,files=[{'path':'Assets/index.html','content':'<h1>fake HOME</h1>'}])
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):builder(lambda s,r:json.dumps(x)).propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
 def test_no_fake_sources(self):
  x=dict(OUTPUT,source_ids=['made-up'])
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):builder(lambda s,r:json.dumps(x)).propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
 def test_bad_python_syntax(self):
  x=dict(OUTPUT,files=[{'path':'extensions/xy/action.py','content':'def malformed(:\n  pass\n'}])
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):builder(lambda s,r:json.dumps(x)).propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
 def test_bounded_css(self):
  x=dict(OUTPUT,files=[{'path':'extensions/xy/look.css','content':'@import url(https://bad.example);'}])
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):builder(lambda s,r:json.dumps(x)).propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
 def test_native_denial(self):
  b=CompleteBuilder(recall=lambda *a:EVIDENCE,generate=lambda *a:json.dumps(OUTPUT),native_authorize=lambda *a:False,source_admission=lambda *a:True)
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(SelfBuilderHold):b.propose(session='trusted',task='Create one verified source-only action',source_head=HEAD,workspace=t)
 def test_p02_installed_model_required(self):
  class Ollama:
   def models(self):return ['model:7b']
   def stream(self,m,ms,stop):
    yield {'delta':json.dumps(OUTPUT),'done':True}
  p=P02Coder(ollama=Ollama(),model_name=lambda:'model:7b',authorize=lambda *a:True,stop_requested=lambda:False)
  res=p('trusted',{'task':'one source','source_head':HEAD})
  self.assertIn('testpanel',res)
 def test_p02_model_not_installed(self):
  class Ollama:
   def models(self):return []
   def stream(self,*a):raise AssertionError('should not run')
  p=P02Coder(ollama=Ollama(),model_name=lambda:'unknown',authorize=lambda *a:True,stop_requested=lambda:False)
  with self.assertRaises(CodingHold):p('trusted',{'task':'one source'})
 def test_p02_stop(self):
  class Ollama:
   def models(self):return ['model:7b']
   def stream(self,*a):raise AssertionError('should not run')
  p=P02Coder(ollama=Ollama(),model_name=lambda:'model:7b',authorize=lambda *a:True,stop_requested=lambda:True)
  with self.assertRaises(CodingHold):p('trusted',{'task':'one source'})
 def test_forge_handoff_not_trained(self):
  r=request_gpu_training(model_sha='a'*64,dataset_sha='b'*64,owner_consent=True,rights_verified=True,
      original_p04_readiness={'status':'HARDWARE_READY_ONLY','runtime_training_verified':False})
  self.assertFalse(r['weights_updated']);self.assertEqual(r['training_steps'],0)
 def test_forge_no_consent(self):
  with self.assertRaises(ForgeHold):request_gpu_training(model_sha='a'*64,dataset_sha='b'*64,owner_consent=False,rights_verified=True,original_p04_readiness={'status':'HARDWARE_READY_ONLY','runtime_training_verified':False})
 def test_forge_gpu_not_ready(self):
  with self.assertRaises(ForgeHold):request_gpu_training(model_sha='a'*64,dataset_sha='b'*64,owner_consent=True,rights_verified=True,original_p04_readiness={'status':'HOLD','runtime_training_verified':False})
if __name__=='__main__':unittest.main()

class IntegrationWorker(unittest.TestCase):
 def test_evolution_multilang_existing_host(self):
  from nox_selfbuilder.evolution import EvolutionWorker
  from test_evolution_worker import Host,job
  class ExistingHost(Host):
   def source_admission(self,head):return head==self.current_source_head()
   def generate(self,session,request):
    self.call_count+=1
    return json.dumps({'files':[{'path':'extensions/coder/page.mjs',
          'content':'export function open() {return "HOLD";}\n'}],
          'source_ids':['NOX-PRODUCT-OWNER-SPEC'],
          'rationale':'Approved additive source-code candidate that requires owner QA.'})
  with tempfile.TemporaryDirectory() as t:
   j=job();j['candidate_language']='multilang'
   h=ExistingHost([j])
   r=EvolutionWorker(h,workspace=t,idle_seconds=.2).tick()
   self.assertEqual(r.status,'CANDIDATE_REVIEW_REQUIRED')
   self.assertEqual(h.call_count,1)
   self.assertEqual(len(list(Path(t).glob('SBX-*/receipt.json'))),1)
   self.assertFalse(r.receipt['merge'])
 def test_evolution_multilang_without_native_callback_holds(self):
  from nox_selfbuilder.evolution import EvolutionWorker
  from test_evolution_worker import Host,job
  with tempfile.TemporaryDirectory() as t:
   j=job();j['candidate_language']='multilang'
   h=Host([j]);r=EvolutionWorker(h,workspace=t,idle_seconds=.2).tick()
   self.assertEqual(r.status,'HOLD')
   self.assertIn('NATIVE_SOURCE_ADMISSION_CALLBACK_REQUIRED',r.receipt['reason'])
   self.assertEqual(h.call_count,0)
