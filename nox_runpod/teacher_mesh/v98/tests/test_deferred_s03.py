"""V98 isolated regressions: synthetic data, no server or real memory."""
import ast
import asyncio
import unittest

from nox_runpod.teacher_mesh.v98.deferred_s03_stream_patch import REMOTE

def source_patch():
    body=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
    tree=ast.parse(body)
    compile(body,"<v98-remote>","exec")
    patch=next(n.value.value for n in ast.walk(tree) if isinstance(n,ast.Assign)
               and any(isinstance(x,ast.Name) and x.id=="PATCH" for x in n.targets))
    return patch

class FakeResponse:
    def __init__(self,iterator):
        self.body_iterator=iterator

class V98Tests(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_save_and_no_premature_write(self):
        patch=source_patch()
        original="""async def handle(stream,resp,payload,write,fail=False):
    t_gate=0
    _utext='question'
    body={'messages':[{'role':'user','content':'question'}]}
    _s03_persist_pair=write
    def _s03_user_from_payload(body):return 'question'
    def _last_user_text(body):return 'question'
    def _wrap_ttft(resp,ttft,text):return resp
    def log_line(*args):pass
    LOGS=None
    resp = _wrap_ttft(resp, t_gate, _utext)
    try:
        ans = payload.get('_agent_final') or ''
        if ans:
            _s03_persist_pair('question',ans)
    except Exception:pass
    return resp
"""
        anchor="    resp = _wrap_ttft(resp, t_gate, _utext)\n"
        insert="\n".join(line[8:] for line in patch.rstrip("\n").splitlines())+"\n"
        new=original.replace(anchor,anchor+insert).replace(
            "        ans = payload.get('_agent_final') or ''",
            "        ans = (payload.get('_agent_final') or '') if not stream else ''")
        ns={}
        exec(compile(new,"<synthetic owner>","exec"),ns)
        saved=[];payload={}
        async def gen():
            yield b"data: hi\\n\\n"
            yield b"data: [DONE]\\n\\n"
            payload["_agent_final"]="hello-world"
        resp=await ns["handle"](True,FakeResponse(gen()),payload,lambda q,a:saved.append((q,a)))
        self.assertFalse(saved)
        chunks=[chunk async for chunk in resp.body_iterator]
        self.assertEqual(chunks[-1],b"data: [DONE]\\n\\n")
        self.assertEqual(saved,[("question","hello-world")])
    async def test_cancelled_stream_never_saved(self):
        patch=source_patch()
        self.assertIn("if _nox_finished_normally:",patch)
        self.assertIn("finally:",patch)
        # If consumer stops before the final delta, no postflight write.
        self.assertNotIn("owner_token",patch)

if __name__=="__main__":
    unittest.main()
