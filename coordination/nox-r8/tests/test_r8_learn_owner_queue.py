"""D05 source-only contract and SQLite migration; does not start GPU training."""
from pathlib import Path
import sqlite3,re
root=Path(__file__).resolve().parent
cs=(root/'src/MainWindow.xaml.cs').read_text(encoding='utf-8')
html=(root/'src/index.html').read_text(encoding='utf-8')
for token in ('WindowsIdentity.GetCurrent()', 'MessageBoxButton.YesNo', 'SELFTEST_NO_OWNER_CONSENT',
              'AWAITING_VERIFIED_WORKER', 'CANCELLED_BY_OWNER','trainingStarted=false',
              'NO_ATTESTED_GPU_WORKER','temperature.gpu','hottest >= 65','ReadLearnQueue()'):
 assert token in cs, token
assert 'gpuCount = names.Count' in cs, 'D05_MULTIGPU_TELEMETRY_HOLD'
assert 'sensorReadLock.WaitAsync(0)' in cs, 'D05_STOP_NOT_BLOCKED_BY_SENSORS_HOLD'
for token in ('id="learnRequest"','id="learnCancel"', "post('learn.request',{requestId})",
              "post('learn.cancel',{requestId})","case 'learn.receipt'","case 'learn.queue'"):
 assert token in html,token
assert 'case "learn.start"' not in cs
m=re.search(r'CREATE TABLE IF NOT EXISTS learn_requests \(.*?\);', cs, re.S)
assert m,'SQLite LEARN schema missing'
db=sqlite3.connect(':memory:')
db.executescript(m.group())
db.executescript("CREATE UNIQUE INDEX idx_learn_pending_owner ON learn_requests(owner_sid) WHERE state='AWAITING_VERIFIED_WORKER';")
db.execute("INSERT INTO learn_requests(owner_sid,requested_at,consent_at,model,state) VALUES(?,?,?,?,?)",
 ('S-1-5-21-test','now','now','nox-qwen-clean:latest','AWAITING_VERIFIED_WORKER'))
assert db.execute('SELECT checkpoint_sha256 FROM learn_requests').fetchone()[0] is None
try:
 db.execute("INSERT INTO learn_requests(owner_sid,requested_at,consent_at,model,state) VALUES(?,?,?,?,?)",('S-1-5-21-test','now','now','model','AWAITING_VERIFIED_WORKER'))
 raise AssertionError('duplicate pending request admitted')
except sqlite3.IntegrityError: pass
db.execute("UPDATE learn_requests SET state='CANCELLED_BY_OWNER' WHERE owner_sid=?",('S-1-5-21-test',))
assert db.execute('SELECT state FROM learn_requests').fetchone()[0]=='CANCELLED_BY_OWNER'

# C#11 raw literal contents must be at least as indented as closing delimiter.
# The original R8 D05 Windows compile failed with CS8999 on this migration.
raw_start=cs.index('command.CommandText = """')
assert raw_start>=0
raw_end=cs.index('""";',raw_start+len('command.CommandText = """'))
assert raw_end>raw_start
raw_lines=cs[raw_start:raw_end].splitlines()[1:]
assert all(not line.strip() or line.startswith('          ') for line in raw_lines), 'CS8999 SQL raw literal indentation'

print('D05 SOURCE_ONLY SQLITE/OWNER QUEUE CONTRACT PASS; GPU NOT RUN')

# D05 TECH-FIRST: preparation consent + STOP require independent SQLite
# readback; foreign trainer_state files never become authenticated GPU progress.
learn = cs.split('private void RequestLearn(string requestId)', 1)[1].split('private void CancelLearnRequest(string requestId)', 1)[0]
cancel = cs.split('private void CancelLearnRequest(string requestId)', 1)[1].split('private object GetTrainingState()', 1)[0]
training = cs.split('private object GetTrainingState()', 1)[1]
assert 'NOX_LEARN_CONSENT_SQLITE_READBACK_HOLD' in learn
assert learn.index('tx.Commit();') < learn.index('NOX_LEARN_CONSENT_SQLITE_READBACK_HOLD')
assert 'SELECT model,state,consent_at,checkpoint_sha256 FROM learn_requests WHERE id=$id AND owner_sid=$sid' in learn
assert 'NOX_LEARN_STOP_SQLITE_READBACK_HOLD' in cancel
assert cancel.index('tx.Commit();') < cancel.index('NOX_LEARN_STOP_SQLITE_READBACK_HOLD')
assert "WHERE owner_sid=$sid AND state='AWAITING_VERIFIED_WORKER'" in cancel
assert 'progressVerified = false' in training
assert 'checkpointVerified = false' in training
assert 'measuredTrainingRuns = Array.Empty<object>()' in training
assert 'observedExternalRuns = states' in training
assert "case 'training':" in html and 'r.checkpointVerified===true' in html
assert "case 'learn.queue':" in html and "case 'learn.receipt':" in html
print('D05 TECH-FIRST SOURCE_ONLY consent/STOP SQLite readback + untrusted progress HOLD PASS')

# 2026-11-07 B06: tests track stricter real owner-correlated Qwen/LEARN IPC.
# Not an owner-PC or Windows integration proof.
assert 'case "learn.request": HandleLearnRequest(Text("requestId")); break;' in cs
assert 'case "learn.cancel": HandleLearnCancel(Text("requestId")); break;' in cs
assert "case 'learn.denied':" in html
assert "pendingLearnRequest=requestId" in html and "pendingLearnStop=requestId" in html
assert "PERSISTENCE_UNKNOWN_HOLD" in cs
print("B06 SOURCE_ONLY: LEARN UI requestId + owner uncertainty assertions")
