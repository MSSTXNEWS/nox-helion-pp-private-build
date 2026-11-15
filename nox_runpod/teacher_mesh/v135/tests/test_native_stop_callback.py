"""NOX full-base STOP regression: source-only, no GPU/model/service needed."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nox_runpod.teacher_mesh.v135 import train_full_base_zero3 as trainer


class CallbackBase:
    pass


class TestNativeStop(unittest.TestCase):
    def test_all_known_stop_markers_checked_even_when_default_file_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'onehost_stop'
            b=Path(temp)/'other_existing_stop'
            with patch.object(trainer,'STOP_PATHS',(str(a),str(b))):
                trainer.assert_native_stop_clear(str(a))
                b.touch()
                with self.assertRaisesRegex(RuntimeError,'HOLD_NATIVE_STOP_ACTIVE'):
                    trainer.assert_native_stop_clear(str(a))
                b.unlink()
                a.touch()
                with self.assertRaisesRegex(RuntimeError,'HOLD_NATIVE_STOP_ACTIVE'):
                    trainer.assert_native_stop_clear(str(a))

    def test_custom_stop_file_cannot_bypass_required_native_markers(self):
        with tempfile.TemporaryDirectory() as temp:
            default=Path(temp)/'official_STOP'
            arbitrary=Path(temp)/'NEVER_STOP'
            with patch.object(trainer,'STOP_PATHS',(str(default),)):
                with self.assertRaisesRegex(RuntimeError,'HOLD_UNAPPROVED_STOP_FILE'):
                    trainer.assert_native_stop_clear(str(arbitrary))

    def test_callback_checks_at_substep_and_each_optimizer_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            first=Path(temp)/'STOP'
            other=Path(temp)/'STOP.flag'
            with patch.object(trainer,'STOP_PATHS',(str(first),str(other))):
                cb=trainer.make_native_stop_callback(str(first),CallbackBase)
                control=object()
                hooks=('on_train_begin','on_epoch_begin','on_step_begin',
                       'on_substep_end','on_step_end','on_evaluate','on_save')
                for hook in hooks:
                    with self.subTest(hook=hook,phase='clear'):
                        self.assertIs(getattr(cb,hook)(None,None,control),control)
                other.touch()
                for hook in hooks:
                    with self.subTest(hook=hook,phase='stopped'):
                        with self.assertRaisesRegex(RuntimeError,'HOLD_NATIVE_STOP_ACTIVE'):
                            getattr(cb,hook)(None,None,control)

    def test_callback_never_uses_fake_success_or_suppresses_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'STOP'
            with patch.object(trainer,'STOP_PATHS',(str(a),)):
                cb=trainer.make_native_stop_callback(str(a),CallbackBase)
                a.touch()
                with self.assertRaisesRegex(RuntimeError,'HOLD_NATIVE_STOP_ACTIVE'):
                    cb.on_substep_end(None,None,None)
                self.assertFalse(hasattr(cb,'perform_training'))
                self.assertFalse(hasattr(cb,'new_scheduler'))


if __name__=='__main__':
    unittest.main()
