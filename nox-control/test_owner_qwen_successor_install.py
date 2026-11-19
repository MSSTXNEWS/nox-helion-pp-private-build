"""Concrete successor safety boundaries; no native services or model imports."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest import mock


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

I=load('owner_qwen_successor_install')
S=load('owner_qwen_execution_successor')
G=load('owner_qwen_training_guard')
REF={'request':'7000000001','source_sha':'a'*40,'receipt_sha256':'b'*64}
WHO={'pid':23456,'start_ticks':123456,'boot_id':'9c0ecc02-85c1-452b-b8ae-521e9a11fd03'}
LIVE={'service':{'state':'RUNNING','pid':23455},'process_identity':WHO}


def context(area):
    return {'context':REF,'execution':{'reference':REF,'directory':area,
        'descriptor':{'created_at':time.time()-20,'activation_issuer_sha256':'c'*64,
                      'bootstrap':{'expires_at':time.time()+3500}}}}


def ready(ctx):
    return {'schema':'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1','execution_revision':REF,
        'process_identity':dict(WHO),'watcher_source_sha256':I.PINS[I.WATCHER],
        'verifier_sha256':I.PINS[I.SHARED_ASSET], 'issuer_source_sha256':'c'*64,
        'armed_at':time.time()-5,'start_capability':False}


def old_policy():
    cp={'successful_updates':25,'evaluated_at_update':10,'holdout_loss':1.2653611116111279,
        'observed_file_bytes':519902179,'attempted_updates':25,'skipped_updates':0,
        'manifest_sha256':I.ORIGINAL_ANCHOR['manifest_sha256'],'student_state_sha256':I.ORIGINAL_ANCHOR['student_state_sha256']}
    result=G.policy_step(None,cp,16*1024**3,43278336,1794816284.2044637,G.DEFAULT_POLICY,1.2653611116111279)
    result['observed_distinct_evaluations']=0
    return result


class SuccessorTests(unittest.TestCase):
    def test_successor_anchor_and_exact_current_sources_match_shared(self):
        self.assertEqual(I.ANCHOR,S.ANCHOR);self.assertEqual(I.ORIGINAL_ANCHOR,S.ORIGINAL_ANCHOR)
        self.assertEqual(I.PREDECESSOR_REF,S.PREDECESSOR['reference'])
        self.assertEqual(I.OLD_SOURCES[I.SHARED],S.PREDECESSOR['verifier_sha256'])
        self.assertEqual(I.OLD_SOURCES[I.STUDENT],S.PREDECESSOR['runtime_entry_sha256'])
        self.assertEqual(I.OLD_SOURCES[I.SELF],S.PREDECESSOR['activation_issuer_sha256'])
        for asset in I.CANDIDATES:
            raw=Path(__file__).with_name(asset).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),I.PINS[asset],asset)

    def test_only_exact_current_hold_and_absent_pause_are_admitted(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(I,'STATE',Path(folder)),mock.patch.object(I,'global_stop'):
            raw=b'OWNER_QWEN_WINDOW_FAILED request=6914959637 goal=1000\n'
            self.assertEqual(I.digest(raw),I.FLAGS['TRAIN_HOLD.flag'])
            (I.STATE/'TRAIN_HOLD.flag').write_bytes(raw)
            self.assertEqual(I.exact_flags(),{'TRAIN_HOLD.flag':raw})
            (I.STATE/'TRAIN_PAUSE_REQUEST.flag').symlink_to(I.STATE/'missing')
            with self.assertRaisesRegex(RuntimeError,'UNEXPECTED_PAUSE'):I.exact_flags()

    def test_predecessor_absence_rejects_any_finalizer_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            area=Path(folder);(area/'operation_result.json').write_text('{}')
            self.assertTrue(I.predecessor_absence(area)['finalizer_absent'])
            (area/'finalize-unknown.json').symlink_to(area/'missing')
            with self.assertRaisesRegex(RuntimeError,'FINALIZER_OR_ACTIVATION'):I.predecessor_absence(area)

    def test_preserved_quality_history_accepts_fresh_age_without_rearming_it(self):
        old=old_policy();live=copy.deepcopy(old);live['evaluation_age_updates']=0;live['last_free_bytes']=17000000000
        cp={'successful_updates':25,'attempted_updates':25,'skipped_updates':0,'evaluated_at_update':25,
            'manifest_sha256':I.ANCHOR['manifest_sha256'],'student_state_sha256':I.ANCHOR['student_state_sha256']}
        before={'state':'BOOTSTRAP_EVALUATION','policy_state':live,'checkpoint':cp}
        self.assertEqual(I.migration_policy(before,old,cp),old)
        self.assertTrue(old['inhibit'])
        before['policy_state']['best_holdout_loss']=0.001
        with self.assertRaisesRegex(RuntimeError,'PRESERVED_QUALITY'):I.migration_policy(before,old,cp)

    def test_real_evaluation_preserves_history_and_unchanged_disk_policy(self):
        old=old_policy();old_copy=copy.deepcopy(old)
        cp={'successful_updates':25,'attempted_updates':25,'skipped_updates':0,'evaluated_at_update':25,
            'holdout_loss':1.2218,'observed_file_bytes':519905811,'manifest_sha256':'f'*64,'student_state_sha256':'e'*64}
        ctx={'lineage':{'targets':{'parameters':43278336}},'certificate':{'final_holdout_loss':1.3033105581998825}}
        changed=I.resumed_policy(G,old,cp,ctx,{'policy':G.DEFAULT_POLICY},16*1024**3,time.time())
        self.assertEqual(old,old_copy);self.assertFalse(changed['inhibit']);self.assertEqual(changed['observed_distinct_evaluations'],1)
        self.assertEqual(changed['disk_floor_bytes'],old['disk_floor_bytes'])
        with self.assertRaisesRegex(RuntimeError,'NOT_PERMISSIVE'):
            I.resumed_policy(G,old,cp,ctx,{'policy':G.DEFAULT_POLICY},10*1024**3,time.time())

    def test_ready_record_pins_and_start_capability_are_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx=context(Path(folder));value=ready(ctx);I.create(Path(folder)/'watcher_ready.json',I.encode(value))
            self.assertEqual(I.ready_record(ctx)[0],value)
            for key,replacement in [('start_capability',True),('verifier_sha256','f'*64),('execution_revision',I.PREDECESSOR_REF)]:
                wrong={**value,key:replacement};p=Path(folder)/'watcher_ready.json';p.write_bytes(I.encode(wrong))
                with self.assertRaisesRegex(RuntimeError,'WATCHER_READY_BINDING'):I.ready_record(ctx)
                p.write_bytes(I.encode(value))

    def arm_fixture(self,folder,records):
        area=Path(folder);ctx=context(area);child=types.SimpleNamespace(pid=WHO['pid'],poll=lambda:None)
        raw=b'watcher-fixture';pins={**I.PINS,I.WATCHER:I.digest(raw)}
        def spawn(*args,**kwargs):
            (area/'watcher_ready.json').touch(mode=0o600)
            return child
        stack=[]
        for patch in [mock.patch.object(I,'ROOT',area),mock.patch.object(I,'SCRIPTS',area),mock.patch.object(I,'PINS',pins),
                      mock.patch.object(I,'read',return_value=raw),mock.patch.object(I,'create'),
                      mock.patch.object(I,'no_flags'),mock.patch.object(I,'protected'),
                      mock.patch.object(I.subprocess,'Popen',side_effect=spawn),mock.patch.object(I.time,'sleep'),
                      mock.patch.object(I,'ready_record',side_effect=records)]:
            stack.append(patch);patch.start()
        # create() is mocked only for data/source verification; the two log
        # descriptors remain actual private fixture files and are closed.
        for name in ('watcher_stdout.log','watcher_stderr.log'):(area/name).touch(mode=0o600)
        return ctx,child,stack

    def test_arm_retries_incomplete_ready_but_never_semantic_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            transient=json.JSONDecodeError('incomplete','',0)
            ctx,child,patches=self.arm_fixture(folder,[transient,({'process_identity':WHO},b'complete')])
            try:
                got=I.arm_watcher(ctx,object());self.assertIs(got[0],child);self.assertEqual(got[2],I.digest(b'complete'))
            finally:
                for patch in reversed(patches):patch.stop()
        with tempfile.TemporaryDirectory() as folder:
            ctx,_,patches=self.arm_fixture(folder,[RuntimeError('HOLD_QWEN_REVISION_INSTALL_WATCHER_READY_BINDING')])
            try:
                with self.assertRaisesRegex(RuntimeError,'READY_BINDING'):I.arm_watcher(ctx,object())
            finally:
                for patch in reversed(patches):patch.stop()

    def test_immutable_start_receipt_binds_ready_and_exact_process(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(I,'no_flags'),mock.patch.object(I,'protected'),mock.patch.object(I,'trainer',return_value=LIVE):
            ctx=context(Path(folder));r=ready(ctx);rr=I.encode(r);I.create(Path(folder)/'watcher_ready.json',rr)
            start,pin=I.publish_start_receipt(ctx,I.digest(rr),time.time()-1)
            self.assertEqual(I.checked_start_receipt(ctx,pin),start)
            with mock.patch.object(I,'trainer',return_value={**LIVE,'process_identity':{**WHO,'pid':34567}}):
                with self.assertRaisesRegex(RuntimeError,'REPLACED_PROCESS'):I.checked_start_receipt(ctx,pin)
            with self.assertRaises(FileExistsError):I.publish_start_receipt(ctx,I.digest(rr),time.time()-1)

    def test_active_finalize_returns_before_lock_or_any_effect_even_if_cancelled(self):
        ctx=context(Path('/fixture'));shared=types.SimpleNamespace(current_context=lambda _:ctx,
            activation_status=lambda _:{'active':True})
        with mock.patch.object(I,'read',return_value=b'x'),mock.patch.object(I,'digest',side_effect=[I.PINS[I.SHARED_ASSET],'c'*64]),\
             mock.patch.object(I,'module',return_value=shared),mock.patch.object(I,'acquire') as lock,\
             mock.patch.object(I,'activate') as activate,mock.patch.object(I,'owned_pause') as pause:
            out=I.finalize_same_process(REF,'d'*64,10,stop_check=lambda:True)
            self.assertEqual(out['state'],'ALREADY_ACTIVATED_READ_ONLY');self.assertTrue(out['read_only'])
            lock.assert_not_called();activate.assert_not_called();pause.assert_not_called()

    def test_activation_rechecked_inside_controller_before_start_or_flags(self):
        ctx=context(Path('/fixture'));shared=types.SimpleNamespace(current_context=lambda _:ctx,
            activation_status=mock.Mock(side_effect=[{'active':False},{'active':True}]))
        with mock.patch.object(I,'read',return_value=b'x'),mock.patch.object(I,'digest',side_effect=[I.PINS[I.SHARED_ASSET],'c'*64]),\
             mock.patch.object(I,'module',return_value=shared),mock.patch.object(I,'acquire',return_value=987),\
             mock.patch.object(I.os,'close') as close,mock.patch.object(I,'no_flags') as flags,\
             mock.patch.object(I,'checked_start_receipt') as start:
            out=I.finalize_same_process(REF,'d'*64,10)
            self.assertEqual(out['state'],'ALREADY_ACTIVATED_READ_ONLY');flags.assert_not_called();start.assert_not_called()
            close.assert_called_once_with(987)

    def test_finalize_failure_never_adds_flags_or_activates(self):
        ctx=context(Path('/fixture'));shared=types.SimpleNamespace(current_context=lambda _:ctx,activation_status=lambda _:{'active':False})
        with mock.patch.object(I,'read',return_value=b'x'),mock.patch.object(I,'digest',side_effect=[I.PINS[I.SHARED_ASSET],'c'*64]),\
             mock.patch.object(I,'module',return_value=shared),mock.patch.object(I,'acquire',return_value=987),\
             mock.patch.object(I.os,'close'),mock.patch.object(I,'no_flags'),mock.patch.object(I,'protected'),\
             mock.patch.object(I,'checked_start_receipt',side_effect=RuntimeError('HOLD_QWEN_REVISION_INSTALL_START_RECEIPT_REPLACED_PROCESS')),\
             mock.patch.object(I,'activate') as activate,mock.patch.object(I,'owned_pause') as pause:
            out=I.finalize_same_process(REF,'d'*64,10)
            self.assertEqual(out['state'],'HOLD_QWEN_SUCCESSOR_FINALIZE');self.assertIsNone(out['optimizer_permission_issued'])
            self.assertIsNone(out['active']);self.assertEqual(out['activation_observation'],'NOT_RECHECKED_AFTER_EXCEPTION')
            self.assertEqual(out['flag_writes'],0);self.assertEqual(out['service_actions'],0)
            activate.assert_not_called();pause.assert_not_called()

    def test_partial_permit_commit_is_unknown_and_verified_commit_remains_observed(self):
        # The permit can exist before activate() returns; caller fields alone
        # cannot distinguish that from an earlier failure.
        with tempfile.TemporaryDirectory() as folder:
            permit=Path(folder)/'activation.json';permit.write_text('{"active":true}')
            result={'active':False,'optimizer_permission_issued':False}
            I.activation_error_observation(result)
            self.assertIsNone(result['active']);self.assertIsNone(result['optimizer_permission_issued'])
            self.assertEqual(permit.read_text(),'{"active":true}')
            proven={'optimizer_permission_issued':True}
            I.activation_error_observation(proven)
            self.assertIs(proven['active'],True);self.assertIs(proven['optimizer_permission_issued'],True)
            self.assertEqual(proven['activation_observation'],'PERMIT_VERIFIED_BEFORE_EXCEPTION')

    def test_cancellation_reaches_full_checkpoint_chunks_without_writes(self):
        ctx=context(Path('/fixture'));ctx['execution']['descriptor']['bootstrap']['expires_at']=time.time()+100
        with mock.patch.object(I,'no_flags'),mock.patch.object(I,'protected'),mock.patch.object(I,'trainer',return_value=LIVE),\
             mock.patch.object(I,'document',return_value=({'manifest_sha256':'f'*64},b'x')):
            called=[]
            def full(_ctx,*,flags_check):
                called.append(True);flags_check();flags_check();self.fail('second chunk must cancel')
            with mock.patch.object(I,'full_checkpoint',side_effect=full),mock.patch.object(I,'activate') as activate:
                cancel=mock.Mock(side_effect=[False,False,True])
                with self.assertRaisesRegex(RuntimeError,'FINALIZE_CANCELLED'):
                    I.wait_bootstrap(None,ctx,None,{},lambda:None,maximum=10,stop_check=cancel)
                self.assertEqual(called,[True]);activate.assert_not_called()

    def test_global_stop_and_foreign_rollback_file_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(I,'ROOT',Path(folder)):
            marker=Path(folder)/'STOP';marker.write_text('owned elsewhere')
            with self.assertRaisesRegex(RuntimeError,'OWNER_STOP'):I.global_stop()
            self.assertEqual(marker.read_text(),'owned elsewhere')
            file=Path(folder)/'source.py';file.write_bytes(b'bad')
            with self.assertRaisesRegex(RuntimeError,'ROLLBACK_FOREIGN_FILE'):
                I.rollback_preflight([(file,b'old',b'new',0o644)],[],Path(folder),{})
            self.assertEqual(file.read_bytes(),b'bad')

    def test_main_only_one_trainer_start_after_watcher_and_no_pointer_rewind(self):
        tree=ast.parse(Path(I.__file__).read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call)]
        starts=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='command'
                and n.args and isinstance(n.args[0],ast.List) and len(n.args[0].elts)==3
                and isinstance(n.args[0].elts[1],ast.Constant) and n.args[0].elts[1].value=='start'
                and isinstance(n.args[0].elts[2],ast.Name) and n.args[0].elts[2].id=='SERVICE']
        arms=[n for n in calls if isinstance(n.func,ast.Name) and n.func.id=='arm_watcher']
        self.assertEqual(len(starts),1);self.assertEqual(len(arms),1);self.assertLess(arms[0].lineno,starts[0].lineno)
        writes=[n for n in calls if isinstance(n.func,ast.Name) and n.func.id in {'commit','create','replace'}]
        self.assertFalse(any('latest_checkpoint' in ast.unparse(n.args[0]) for n in writes))
        self.assertEqual(len(I.CANDIDATES)+len(I.UTILITIES)+1,13)


class NamedCheckpointTests(unittest.TestCase):
    def test_full_retained_payloads_do_not_relabel_or_rewind_current_pointer(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(I,'OUTPUT',Path(folder)):
            output=Path(folder);lineage={'fixed':'scientific-origin'};ev=[{'step':n} for n in range(1,26)]
            state={'successful_total':25,'attempted_total':25,'skipped_total':0,'holdout_evaluated_successful_total':10,
                   'last_holdout_loss':1.26,'update_evidence':ev}
            name=I.ORIGINAL_ANCHOR['directory'];directory=output/name;directory.mkdir()
            data={k:b'synthetic-'+k.encode() for k in S.REQUIRED|{'README.md'}}
            data['student_state.json']=I.encode(state);data['lineage.json']=I.encode(lineage)
            files={k:I.digest(v) for k,v in data.items()}
            manifest={'files_sha256':files,'successful_total':25,'attempted_total':25,
                      'holdout_evaluated_successful_total':10,'holdout_loss':1.26,'adapter_tensor_sha256':'d'*64}
            for k,v in data.items():(directory/k).write_bytes(v)
            (directory/'checkpoint_manifest.json').write_bytes(I.encode(manifest))
            pointer=I.encode({'directory':I.ANCHOR['directory'],'manifest_sha256':I.ANCHOR['manifest_sha256']})
            (output/'latest_checkpoint.json').write_bytes(pointer)
            ctx={'observer':types.SimpleNamespace(REQUIRED=S.REQUIRED,update_chain=lambda *_:{'adapter_tensor_sha256':'d'*64}),
                 'contract':types.SimpleNamespace(canonical_sha=lambda _:I.ORIGIN_LINEAGE),'lineage':lineage,
                 'certificate':{'update_evidence':ev[:6]}}
            expected={'directory':name,'manifest_sha256':I.digest(I.encode(manifest)),'successful_total':25}
            proof,_,_=I.full_checkpoint(ctx,expected=expected,checkpoint_directory=name,flags_check=lambda:None)
            self.assertTrue(proof['full_files_sha256_verified']);self.assertIsNone(proof['pointer_sha256'])
            self.assertEqual((output/'latest_checkpoint.json').read_bytes(),pointer)
            (directory/'optimizer.pt').write_bytes(b'tampered')
            with self.assertRaisesRegex(RuntimeError,'CHECKPOINT_FULL_SHA'):
                I.full_checkpoint(ctx,expected=expected,checkpoint_directory=name,flags_check=lambda:None)
            self.assertEqual((output/'latest_checkpoint.json').read_bytes(),pointer)


if __name__=='__main__':unittest.main()
