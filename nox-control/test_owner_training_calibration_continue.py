from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('calibration_fixture',HERE/'test_owner_training_calibration_proof.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
entry=fixture.load('owner_training_calibration_continue');proof=fixture.p


class ContinuationAdmissionTests(fixture.CalibrationFixture):
    def setUp(self):
        super().setUp()
        for name,value in {'ROOT':self.root,'STATE':self.state,'SCRIPTS':self.scripts,'OUTPUT':self.output,
                           'POINTER':proof.POINTER,'WRAPPER':self.scripts/'run_train_volta_t866u.sh',
                           'EXTERNAL_STOP':self.root/'external/NOX_STOP'}.items():
            handle=patch.object(entry,name,value);handle.start();self.addCleanup(handle.stop)
        self.command=Mock(side_effect=AssertionError('unexpected service mutation'))
        def atomic(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.helper=types.SimpleNamespace(atomic=atomic,command=self.command,HEAVY_SERVICES={},
            health=lambda:{'8081':200},gpu=lambda:{},progress=lambda:{'step':20},
            service_state=lambda name=None:{'state':'STOPPED'},
            program_config=lambda name:{'command':'/bin/bash '+str(entry.WRAPPER)})
        self.resume=types.SimpleNamespace(STOPPED=('STOPPED','EXITED','FATAL'),verify_policy=lambda value:None,
            resource_admission=lambda helper:{'admitted':True})
        self.loaded={'owner_training_calibration_proof':proof,'owner_native_repair':self.helper,
            'owner_training_resume':self.resume,'owner_training_calibration_guard':object(),'owner_training_disk_guard':object()}

    def test_owner_pause_retains_original20_pointer_and_never_starts(self):
        pause=self.state/'TRAIN_PAUSE_REQUEST.flag';pause.write_bytes(b'OWNER_PAUSE')
        old_pointer=proof.read(proof.POINTER)
        with patch.object(entry,'load',side_effect=lambda name:self.loaded[name]),redirect_stdout(io.StringIO()):
            result,context,success=entry.admit(self.context,'300','c'*40)
        self.assertTrue(success);self.assertEqual(result['state'],'CALIBRATION_VERIFIED_OWNER_PAUSE_RETAINED')
        self.assertTrue(result['optimizer_steps_verified']);self.assertFalse(result['training_started'])
        self.assertEqual(proof.read(proof.POINTER),old_pointer);self.assertEqual(pause.read_bytes(),b'OWNER_PAUSE')
        self.command.assert_not_called();self.assertNotIn('five_step_receipt',result)

    def test_external_stop_blocks_before_any_admission_or_service_change(self):
        entry.EXTERNAL_STOP.parent.mkdir();entry.EXTERNAL_STOP.write_bytes(b'owner stop')
        before=proof.read(proof.POINTER)
        with patch.object(entry,'load',side_effect=lambda name:self.loaded[name]),redirect_stdout(io.StringIO()):
            result,_,success=entry.admit(self.context,'300','c'*40)
        self.assertFalse(success);self.assertEqual(result['error'],'HOLD_CALIBRATED_CONTINUATION_OWNER_STOP')
        self.assertEqual(proof.read(proof.POINTER),before);self.command.assert_not_called()

    def test_foreign_hold_cannot_be_cleared_by_positive_historical_checkpoint(self):
        hold=self.state/'TRAIN_HOLD.flag';hold.write_bytes(b'FOREIGN_HOLD')
        with patch.object(entry,'load',side_effect=lambda name:self.loaded[name]),redirect_stdout(io.StringIO()):
            result,_,success=entry.admit(self.context,'300','c'*40)
        self.assertFalse(success);self.assertEqual(result['error'],'HOLD_CALIBRATED_CONTINUATION_COMPLETION_FLAG')
        self.assertEqual(hold.read_bytes(),b'FOREIGN_HOLD');self.command.assert_not_called()

    def test_installed_guard_with_already_fatal_trainer_is_not_active_continuation_success(self):
        initial,record,pointer=self.continuation()
        record['steps']=[{'kind':'single_native_training_started','data':{'process':{'pid':400,'starttime':500}}}]
        record['state']=proof.STATE_STARTED
        self.helper.service_state=lambda name=None:{'state':'FATAL'}
        (self.state/'train_wants_gpu1').write_bytes(b'preserve-reservation')
        guard=types.SimpleNamespace(trainer_process=lambda:None)
        chain=types.SimpleNamespace(install_guard_or_pause=lambda *args:({'state':'NATIVE_DISK_GUARD_VERIFIED'},True))
        loaded={**self.loaded,'owner_training_calibration_guard':guard,
                'owner_training_recovery_chain':chain,'owner_training_calibration_guard_entry':object()}
        env={'NOX_OWNER_REQUEST_ID':'300','NOX_OWNER_SOURCE_SHA':'c'*40}
        with patch.dict(os.environ,env),patch.object(entry,'load',side_effect=lambda name:loaded[name]),\
             patch.object(entry,'admit',return_value=(record,initial,True)),redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main(self.context),2)
        saved=proof.document(self.state/'owner_calibrated_continuation_chain_300.json')
        self.assertEqual(saved['state'],'GENERIC_GUARD_VERIFIED_CONTINUATION_NOT_RUNNING')
        self.assertFalse(saved['continuation_running_at_end']);self.assertTrue(saved['continuation_started'])
        self.assertEqual(saved['current_admission_context'],initial)
        self.command.assert_not_called()


if __name__=='__main__':unittest.main()
