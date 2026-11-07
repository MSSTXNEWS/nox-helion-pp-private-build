"""R8 integration contract tests for native task state, AMD sensor, model UI and voice.

These run on source only. They DO NOT attest installed Windows, GPU training, audio,
model inference or release E07. Run python -m unittest discover tests -p
'test_r8_helper11_21_integrations.py' from coordination/nox-r8/.
"""
from __future__ import annotations
from pathlib import Path
import re
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]
CS = (ROOT / "overrides/src/MainWindow.xaml.cs").read_text(encoding="utf-8-sig")
HTML = (ROOT / "overrides/src/index.html").read_text(encoding="utf-8-sig")


class R8HelperIntegrationContract(unittest.TestCase):
    def test_task_toggle_target_idempotent(self):
        # Native code uses the requested state, not !oldState.
        self.assertIn('UPDATE tasks SET complete=$complete WHERE id=$id', CS)
        self.assertIn('case "tasks.toggle": {', CS)
        self.assertIn('completeField.ValueKind == JsonValueKind.True', CS)
        self.assertIn('completeField.ValueKind == JsonValueKind.False', CS)
        self.assertIn('HandleTaskToggle(taskId, desiredComplete, Text("requestId"))', CS)
        self.assertNotIn('UPDATE tasks SET complete=CASE WHEN complete=0 THEN 1 ELSE 0 END', CS)
        self.assertIn('post(\'tasks.toggle\',{id:x.id,complete:cb.checked,requestId})', HTML)
        self.assertIn('case \'tasks.toggle.uncertain\'', HTML)
        self.assertIn('NOX_TASK_TOGGLE_COMMIT_UNKNOWN_HOLD', CS)
        self.assertIn('NOX_TASK_TOGGLE_READBACK_UNKNOWN_HOLD', CS)
        self.assertIn('v?.complete===pendingTaskToggle.target', HTML)

    def test_sqlite_idempotence_fixture(self):
        # A real SQLite fixture demonstrates the target update repeated twice is
        # idempotent, not proof of COM/WPF IPC concurrency behavior.
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, complete INTEGER NOT NULL)')
            db.execute('INSERT INTO tasks VALUES (1,0)')
            for intended in (1, 1, 0, 0, 1, 1):
                db.execute('UPDATE tasks SET complete=? WHERE id=?', (intended, 1))
                self.assertEqual(db.execute('SELECT complete FROM tasks WHERE id=1').fetchone()[0], intended)
        finally:
            db.close()

    def test_amd_real_hotspot_or_hold(self):
        self.assertIn("root/LibreHardwareMonitor", CS)
        self.assertIn("SensorType -eq 'Temperature'", CS)
        self.assertIn("GetAmdGpuTelemetryOrHold()", CS)
        self.assertIn('AMD_HOTSPOT_MISSING_OR_INVALID_HOLD', CS)
        self.assertIn('AMD_SENSOR_TIMEOUT_HOLD', CS)
        for invariant in ('hotSpot <= 0', 'hotSpot > 125',
                          'thermalHold = true', 'trainingSafe = false',
                          'vramTotalMiB = (double?)null',
                          'utilizationPercent = (int?)null'):
            self.assertIn(invariant, CS)

    def test_model_pending_owner_survives_stale_health(self):
        self.assertIn('picker.disabled=true', HTML)
        self.assertIn('picker.value=pendingModel.model', HTML)
        self.assertIn("$('modelPicker').disabled=true", HTML)
        self.assertIn("$('modelPicker').disabled=false", HTML)
        self.assertIn('pendingModel={requestId,model,previous:committedModel}', HTML)
        self.assertIn('case \'model.select.receipt\'', HTML)

    def test_voice_on_device_only_and_manual_send(self):
        for identifier in ('voiceListen', 'voiceStop', 'voiceRu', 'voiceEs'):
            self.assertIn('id="'+identifier+'"', HTML)
        self.assertIn('Recognition.available({langs:[lang],processLocally:true})', HTML)
        self.assertIn("status!=='available'", HTML)
        self.assertIn("recognition.processLocally=true", HTML)
        self.assertIn("if(!('processLocally' in recognition))", HTML)
        self.assertIn('voiceRecognizer=null;', HTML)
        self.assertIn('current.abort()', HTML)
        self.assertIn('v.localService===true', HTML)
        self.assertIn("route('core');$('prompt').focus()", HTML)
        # Dictation must not automatically dispatch Chat.
        voice = HTML.split("$('voiceListen').onclick=async()=>", 1)[1].split("$('speak').onclick=", 1)[0]
        self.assertNotIn("post('chat'", voice)
        self.assertNotIn("$('send').click()", voice)
        self.assertNotIn('SpeechRecognition.install(', voice)

    def test_training_is_not_promoted_by_telemetry(self):
        self.assertIn('NO_ATTESTED_GPU_WORKER', CS)
        self.assertIn('AWAITING_VERIFIED_WORKER', CS)
        self.assertIn('checkpointVerified = false', CS)


if __name__ == '__main__':
    unittest.main()
