"""Stage-only NOX E02 C13 patch for the exact original P02Store preimage.

Never overwrites the original. Refuses unknown source, collisions, reapplication.
Run: python apply_c13_to_original.py /path/to/p02_runtime.py /new/staged/path/p02_runtime.py
"""
import hashlib
import os
import pathlib
import sys

OWNER_PRE_GIT_BLOB = "3547a044576ed115649bd7b612feac7a384e7bf9"


def git_blob_sha(source: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()


def patch(source: bytes) -> bytes:
    if git_blob_sha(source) != OWNER_PRE_GIT_BLOB:
        raise RuntimeError("HOLD: original P02Store Git preimage differs; NO-LOSS")
    text = source.decode('utf-8')
    edits = [
      ("'p02_gc','p02_meta','p02_messages_by_chat'}",
       "'p02_gc','p02_meta','p02_messages_by_chat',\n                    'p02_messages_stable_seq'}"),
      ("if version != ('1',):\n                    raise P02Error('Incompatible existing P02 schema; refusing downgrade')",
       "if version not in (('1',), ('2',)):\n                    raise P02Error('Incompatible existing P02 schema; refusing downgrade')"),
      ("                    if cols != expected_columns:\n                        raise P02Error('P02_SCHEMA_COLUMNS_MISMATCH; restore verified backup')",
       "                    # C13: permit only the original owner-reviewed V2 field.\n                    if table == 'p02_messages' and version == ('2',):\n                        expected_columns = expected_columns | {'stable_seq'}\n                    if cols != expected_columns:\n                        raise P02Error('P02_SCHEMA_COLUMNS_MISMATCH; restore verified backup')"),
      ("                if self.db.execute('PRAGMA foreign_key_check').fetchone() is not None:\n                    raise P02Error('P02_SCHEMA_FOREIGN_KEY_VIOLATION; restore verified backup')",
       "                if self.db.execute('PRAGMA foreign_key_check').fetchone() is not None:\n                    raise P02Error('P02_SCHEMA_FOREIGN_KEY_VIOLATION; restore verified backup')\n                if version == ('2',):\n                    from p02_history_stable import verify_v2_contract\n                    verify_v2_contract(self.db)"),
      ("if version != ('1',):\n                raise P02Error('Incompatible existing P02 schema; refuse automatic downgrade')",
       "if version not in (('1',), ('2',)):\n                raise P02Error('Incompatible existing P02 schema; refuse automatic downgrade')"),
      ('''            rows = self.db.execute("""SELECT role,content FROM p02_messages WHERE chat_id=?
                       ORDER BY created_at DESC,rowid DESC LIMIT ?""", (chat, limit)).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]''',
       '''            schema = self.db.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone()
            if schema == ('2',):
                # Same original SQLite/ACL. A validated existing V2, no auto-migration.
                from p02_history_stable import stable_history
                return stable_history(self.db, tenant, user, chat, limit)
            if schema != ('1',):
                raise P02Error('P02_HISTORY_SCHEMA_UNRECOGNIZED')
            rows = self.db.execute("""SELECT role,content FROM p02_messages WHERE chat_id=?
                       ORDER BY created_at DESC,rowid DESC LIMIT ?""", (chat, limit)).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]'''),
    ]
    for before, after in edits:
        if text.count(before) != 1:
            raise RuntimeError('HOLD: patch preimage mismatch or already applied')
        text = text.replace(before, after, 1)
    result = text.encode('utf-8')
    compile(result, 'p02_runtime.py', 'exec')
    if result == source:
        raise RuntimeError('HOLD: no source improvement')
    return result


def stage(input_path: str, output_path: str) -> tuple[str, str]:
    src = pathlib.Path(input_path)
    dst = pathlib.Path(output_path)
    if src.resolve() == dst.resolve() or dst.exists() or dst.is_symlink():
        raise RuntimeError('HOLD: original overwrite prohibited')
    if not dst.parent.is_dir() or dst.parent.is_symlink():
        raise RuntimeError('HOLD: unapproved destination')
    original = src.read_bytes()
    after = patch(original)
    fd = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd,'wb') as writer:
            writer.write(after)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    return hashlib.sha256(original).hexdigest(), hashlib.sha256(after).hexdigest()


if __name__=='__main__':
    if len(sys.argv)!=3:
        raise SystemExit('Usage: python apply_c13_to_original.py ORIGINAL.py NEW-STAGED.py')
    print('pre/post SHA256:', *stage(sys.argv[1],sys.argv[2]))
