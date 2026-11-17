"""Isolated source tests only. No GPU/native/owner training is performed."""
import ast
import hashlib
import json
from pathlib import Path
import random
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from nox_runpod.teacher_mesh.v135.resource_safe_point import TrainerResourceControl
from nox_runpod.teacher_mesh.v135.curate_teacher_distillation import build, split_group
from nox_runpod.teacher_mesh.v135.curate_teacher_distillation import _file_sha
import re


class FakeTrainer:
    def __init__(self, root, controller=None, broken=False):
        self.args=SimpleNamespace(output_dir=str(root),seed=73,gradient_accumulation_steps=2,ignore_data_skip=False)
        self.state=SimpleNamespace(global_step=0,epoch=0)
        self.control=SimpleNamespace(should_save=False)
        self.rng=random.Random(73); self.weight=1.; self.momentum=0.; self.cursor=0
        self.trace=[]; self.error=None; self.stop=False; self.broken=broken
        self.callback=controller.callback(object,self.stop_check) if controller else None
    def stop_check(self):
        if self.stop: raise RuntimeError('HOLD_STOP_TEST')
    def state_dict(self):
        return dict(weight=self.weight,momentum=self.momentum,cursor=self.cursor,rng=self.rng.getstate())
    def train(self):
        try:
            for step in range(1,5):
                for substep in range(2):
                    self.momentum=.9*self.momentum+self.rng.random();self.cursor+=1
                self.weight-=.01*self.momentum
                self.state.global_step=step;self.state.epoch=step/4
                self.trace.append(self.state_dict())
                if self.callback:
                    self.callback.on_step_end(self.args,self.state,self.control)
                    if self.control.should_save:
                        path=Path(self.args.output_dir)/f'checkpoint-{step}';path.mkdir()
                        (path/'trainer_state.json').write_text(json.dumps(vars(self.state)))
                        (path/'mp_rank_00_model_states.pt').write_text(json.dumps({'weight':self.weight}))
                        (path/'zero_optim_states.pt').write_text(json.dumps({'momentum':self.momentum,'cursor':self.cursor}))
                        if not self.broken: (path/'rng_state.pth').write_text(json.dumps(self.rng.getstate()))
                        self.callback.on_save(self.args,self.state,self.control)
                        self.control.should_save=False
            if self.callback: self.callback.on_train_end(self.args,self.state,self.control)
        except BaseException as ex: self.error=ex


class SafePointTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.threads=[]
    def tearDown(self):
        for trainer,thread in self.threads:
            trainer.stop=True;thread.join(2)
        self.tmp.cleanup()
    def start(self,admission=lambda receipt:True,broken=False):
        controller=TrainerResourceControl('6A03',admission)
        self.assertTrue(controller.request_soft_yield('6A03','optimizer_step','a'*64,0))
        self.assertFalse(controller.observation()['yield_completed'])
        trainer=FakeTrainer(self.root,controller,broken)
        thread=threading.Thread(target=trainer.train,daemon=True);self.threads.append((trainer,thread));thread.start()
        deadline=time.monotonic()+3
        while controller.observation()['state'] not in ('PAUSED','FAILED') and time.monotonic()<deadline: time.sleep(.005)
        return controller,trainer,thread
    def test_pause_then_resume_matches_uninterrupted_optimizer_rng_cursor(self):
        c,t,thread=self.start();obs=c.observation();self.assertEqual(obs['state'],'PAUSED')
        self.assertEqual(t.cursor,2);time.sleep(.05);self.assertEqual(t.cursor,2)
        self.assertFalse(obs['vram_released']);self.assertTrue(obs['yield_completed'])
        receipt=obs['receipt'];checkpoint=Path(receipt['checkpoint'])
        restored=FakeTrainer(self.root)
        restored.weight=json.loads((checkpoint/'mp_rank_00_model_states.pt').read_text())['weight']
        saved=json.loads((checkpoint/'zero_optim_states.pt').read_text());restored.momentum=saved['momentum'];restored.cursor=saved['cursor']
        rng=json.loads((checkpoint/'rng_state.pth').read_text());restored.rng.setstate((rng[0],tuple(rng[1]),rng[2]))
        self.assertEqual(restored.state_dict(),t.state_dict())
        self.assertTrue(c.request_resume('6A03',receipt['checkpoint_sha256']));thread.join(2)
        self.assertFalse(thread.is_alive());self.assertIsNone(t.error)
        baseline=FakeTrainer(self.root);baseline.train();self.assertEqual(t.trace,baseline.trace)
    def test_denied_resume_leaves_paused(self):
        c,t,thread=self.start(lambda _:False)
        self.assertFalse(c.request_resume('6A03',c.observation()['receipt']['checkpoint_sha256']))
        self.assertEqual(c.observation()['state'],'PAUSED');self.assertEqual(t.cursor,2)
    def test_changed_checkpoint_cannot_resume(self):
        c,t,thread=self.start();r=c.observation()['receipt'];(Path(r['checkpoint'])/'rng_state.pth').write_text('tampered')
        with self.assertRaisesRegex(RuntimeError,'CHANGED'): c.request_resume('6A03',r['checkpoint_sha256'])
        self.assertEqual(t.cursor,2)
    def test_missing_rng_never_acknowledges_pause(self):
        c,t,thread=self.start(broken=True);thread.join(2)
        self.assertEqual(c.observation()['state'],'FAILED');self.assertFalse(c.observation()['yield_completed'])
        self.assertRegex(str(t.error),'INCOMPLETE_STATE')
    def test_stop_while_paused_never_advances_optimizer(self):
        c,t,thread=self.start();t.stop=True;thread.join(2)
        self.assertEqual(t.cursor,2);self.assertEqual(c.observation()['state'],'FAILED')
    def test_wrong_task_or_boundary_rejected(self):
        c=TrainerResourceControl('6A03',lambda _:True)
        self.assertFalse(c.request_soft_yield('4A02','optimizer_step','a'*64,0))
        self.assertFalse(c.request_soft_yield('6A03','embedding_batch','a'*64,0))
        self.assertFalse(c.request_resume('6A03','a'*64))


class ThreewayTests(unittest.TestCase):
    def test_actual_trainer_verifier_pins_dev_before_training(self):
        source=Path(__file__).parent/'nox_runpod/teacher_mesh/v135/train_full_base_zero3.py'
        module=ast.parse(source.read_text())
        selected=ast.Module(body=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in ('_json','verify_inputs')],type_ignores=[])
        namespace=dict(Path=Path,json=json,_file_sha=_file_sha,_SHA=re.compile(r'^[0-9a-f]{64}$'))
        exec(compile(selected,str(source),'exec'),namespace)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);student=root/'student';data=root/'data';student.mkdir();data.mkdir()
            for name in ('config.json','tokenizer_config.json'): (student/name).write_text('{}')
            (student/'fixture.safetensors').write_bytes(b'fixture')
            manifest=dict(schema='NOX_V135_VERIFIED_TEACHER_DISTILL_CORPUS_V2',source_groups_disjoint=True,answer_cross_split_disjoint=True,train_rows=300,dev_rows=30,holdout_rows=30)
            native=dict(student_shard_bytes=7,student_base_sha256='b'*64)
            for part in ('train','dev','holdout'):
                (data/(part+'.jsonl')).write_text('isolated gate fixture\n')
                digest=_file_sha(data/(part+'.jsonl'));manifest[part+'_sha256']=digest;native[part+'_dataset_sha256']=digest
            (data/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(namespace['verify_inputs'](student,data,root/'output',native),manifest)
            (data/'dev.jsonl').write_text('changed fixture\n')
            with self.assertRaisesRegex(RuntimeError,'DATASET_SHA'):
                namespace['verify_inputs'](student,data,root/'output',native)

    def fixtures(self):
        rows=[]
        for part in ('train','dev','holdout'):
            groups=[f'fixture-group-{i:06d}' for i in range(500) if split_group(f'fixture-group-{i:06d}',threeway=True)==part][:4]
            for group in groups:
                prompt=f'Explain the isolated fixture {group}';answer=f'The approved fixture content is {group}.'
                rows.append(dict(prompt=prompt,completion=answer,teacher_role='coder' if part=='train' else 'qwen-language',teacher_model_sha256='a'*64,
                    source_group=group,source_uri='https://example.invalid/'+group,source_license='owner-authored',rights_verified=True,privacy_approved=True,
                    independent_validation_passed=True,training_allowed=True,source_content_sha256=hashlib.sha256((prompt+'\n'+answer).encode()).hexdigest()))
        return rows
    def test_threeway_exact_hashes_provenance_and_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixtures.jsonl';source.write_text(''.join(json.dumps(r)+'\n' for r in self.fixtures()))
            a=build(source,root/'first',minimum_train=4,minimum_holdout=4,minimum_dev=4)
            b=build(source,root/'second',minimum_train=4,minimum_holdout=4,minimum_dev=4)
            self.assertEqual(a,b);self.assertTrue(a['schema'].endswith('V2'));seen=set()
            for part in ('train','dev','holdout'):
                payload=(root/'first'/(part+'.jsonl')).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(),a[part+'_sha256'])
                rows=[json.loads(line) for line in payload.splitlines()];groups={r['source_group'] for r in rows}
                self.assertFalse(groups&seen);seen|=groups;self.assertTrue(all(r['external_publication_allowed'] is False for r in rows))
                self.assertEqual((root/'first'/(part+'.jsonl')).stat().st_mode&0o777,0o600)
    def test_cross_split_duplicate_answer_rejected_without_output(self):
        rows=self.fixtures()
        for row in rows:
            row['completion']='Repeated fixture completion'
            row['source_content_sha256']=hashlib.sha256((row['prompt']+'\n'+row['completion']).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixtures.jsonl';source.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaisesRegex(ValueError,'CROSS_SPLIT'): build(source,root/'out',minimum_train=4,minimum_holdout=4,minimum_dev=4)
            self.assertFalse((root/'out').exists())
    def test_insufficient_dev_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixtures.jsonl';source.write_text(''.join(json.dumps(r)+'\n' for r in self.fixtures()))
            with self.assertRaisesRegex(ValueError,'COUNTS'): build(source,root/'out',minimum_train=4,minimum_holdout=4,minimum_dev=5)
            self.assertFalse((root/'out').exists())

if __name__=='__main__': unittest.main()
