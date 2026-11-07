'use strict';
// D03 source contract: compiled WPF/Windows runtime acceptance is still required.
// Run with node test_r8_d03_note_delete_commit_receipt.cjs after staging source.
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const cs=fs.readFileSync(path.join(__dirname,'..','overrides','src','MainWindow.xaml.cs'),'utf8');
const start=cs.indexOf('private void DeleteNote(long id, string requestId)');
const end=cs.indexOf('private void SaveFeedback(',start);
assert.ok(start>=0&&end>start,'real native WPF note delete route missing');
const m=cs.slice(start,end);
const guards=[
 'bool commitAttempted = false;',
 'CheckpointSqlite(db, "PRE_NOTE_DELETE")',
 'commitAttempted = true;',
 'tx.Commit();',
 'NOX_NOTE_DELETE_READBACK_HOLD',
 'if (commitAttempted)',
 'Send("notes.delete.receipt"',
 'Send("notes", ReadNotes())'
];
let last=-1;
for(const guard of guards){let at=m.indexOf(guard);assert.ok(at>last,'unexpected delete commit/ACK ordering: '+guard);last=at;}
assert.ok(m.includes('Send("notice", "NOX_NOTE_DELETE_COMMIT_UNKNOWN_HOLD")'));
assert.ok(m.includes('} else {\n                try { Send("notes.delete.denied"'));
assert.ok(!m.slice(m.indexOf('// Independent SQLite readback completed')).includes('Send("notes.delete.denied"'));
assert.ok(m.indexOf('if (consent != MessageBoxResult.Yes)')<m.indexOf('CheckpointSqlite(db, "PRE_NOTE_DELETE")'));
assert.ok(m.includes('id=$id AND persona=$persona')&&m.includes('AND title=$title AND content=$content AND created_at=$created'));
console.log('D03 R8 SOURCE_ONLY: pre/post-commit note deletion receipts fail-closed PASS');
