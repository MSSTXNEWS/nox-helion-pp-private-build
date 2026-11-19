"""Fail-closed STOP regression for original NOX full-base FORGE.

Does not import torch/DeepSpeed, create a model, access OneHost, or touch S03.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from nox_runpod.teacher_mesh.v135 import train_full_base_zero3 as train


class STOPDuringOptimizer(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.custom=self.root/"owner-STOP"
        self.native=self.root/"native-STOP"
        self.patch=patch.object(train,"STOP_PATHS",(str(self.native),))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        class FakeTrainerCallback:
            pass
        self.callback=train._stop_callback(FakeTrainerCallback,self.custom)

    def test_initially_running_then_custom_stop_after_start(self):
        control=SimpleNamespace(should_training_stop=False)
        self.assertIs(self.callback.on_train_begin(None,None,control),control)
        self.assertIs(self.callback.on_step_begin(None,None,control),control)
        self.custom.write_text("STOP")
        with self.assertRaisesRegex(RuntimeError,"HOLD_STOP_DURING_TRAINING"):
            self.callback.on_substep_end(None,None,control)
        self.assertFalse(control.should_training_stop)
        self.assertTrue(train._stop_active(self.custom))

    def test_every_optimizer_save_or_eval_hook_refuses_native_stop(self):
        self.native.touch()
        for name in ("on_train_begin","on_epoch_begin","on_step_begin",
                     "on_substep_end","on_step_end","on_prediction_step",
                     "on_evaluate","on_save"):
            with self.subTest(hook=name):
                with self.assertRaisesRegex(RuntimeError,"HOLD_STOP_DURING_TRAINING"):
                    getattr(self.callback,name)(None,None,SimpleNamespace())
        self.assertTrue(self.native.exists())

    def test_dangling_stop_symlink_also_blocks(self):
        self.custom.symlink_to(self.root/"NONEXISTENT_TARGET")
        self.assertTrue(train._stop_active(self.custom))
        with self.assertRaisesRegex(RuntimeError,"HOLD_STOP_DURING_TRAINING"):
            self.callback.on_step_begin(None,None,SimpleNamespace())

    def test_after_removing_stop_new_safe_callback_can_run(self):
        control=SimpleNamespace()
        self.native.touch()
        with self.assertRaises(RuntimeError):
            self.callback.on_step_begin(None,None,control)
        self.native.unlink()
        self.assertIs(self.callback.on_step_begin(None,None,control),control)
        self.assertFalse(train._stop_active(self.custom))

    def test_adaptive_save_at_first_step_five_minutes_and_final_step(self):
        state=SimpleNamespace(global_step=1,max_steps=100)
        control=SimpleNamespace(should_save=False)
        with patch.object(train.time,"monotonic",return_value=100.0):
            self.callback.on_train_begin(None,state,control)
            self.callback.on_step_end(None,state,control)
            self.assertTrue(control.should_save)
            self.callback.on_save(None,state,control)
        state.global_step=2
        with patch.object(train.time,"monotonic",return_value=200.0):
            control=SimpleNamespace(should_save=False)
            self.callback.on_step_end(None,state,control)
            self.assertFalse(control.should_save)
        state.global_step=3
        with patch.object(train.time,"monotonic",return_value=401.0):
            control=SimpleNamespace(should_save=False)
            self.callback.on_step_end(None,state,control)
            self.assertTrue(control.should_save)
            self.callback.on_save(None,state,control)
        state.global_step=4
        with patch.object(train.time,"monotonic",return_value=450.0):
            control=SimpleNamespace(should_save=False)
            self.callback.on_step_end(None,state,control)
            self.assertFalse(control.should_save)
        state.global_step=100
        with patch.object(train.time,"monotonic",return_value=451.0):
            control=SimpleNamespace(should_save=False)
            self.callback.on_step_end(None,state,control)
            self.assertTrue(control.should_save)

    def test_adaptive_save_respects_stop(self):
        state=SimpleNamespace(global_step=10,max_steps=100)
        self.native.touch()
        control=SimpleNamespace(should_save=False)
        with self.assertRaisesRegex(RuntimeError,"HOLD_STOP_DURING_TRAINING"):
            self.callback.on_step_end(None,state,control)
        self.assertFalse(control.should_save)

    def test_training_script_wires_callback_and_checks_before_trainer_run(self):
        source=Path(train.__file__).read_text(encoding="utf8")
        self.assertIn("callbacks=[_stop_callback(TrainerCallback,Path(args.stop_file))]",source)
        self.assertIn("save_steps=args.max_steps",source)
        self.assertIn("HOLD_STOP_BEFORE_TRAIN",source)
        self.assertIn("HOLD_STOP_AFTER_TRAIN",source)
        self.assertIn("HOLD_STOP_AFTER_EVALUATE",source)
        self.assertNotIn("model.save_pretrained(",source)
        self.assertNotIn("production_promoted':True",source)


if __name__=="__main__":
    unittest.main()
