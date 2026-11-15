"""V146: exercise original Windows PC read-only probe in real pwsh + local HTTP fixture.

Source-only: no NOX native process, owner cookie, backup route, S03 or GPU access.
"""
from __future__ import annotations
import http.server
import pathlib
import shutil
import subprocess
import threading
import unittest

SCRIPT=pathlib.Path(__file__).parent/"windows"/"NOX_ONEPASS_VERIFY_WINDOWS.ps1"
BEGIN="# NOX_V146_WINDOWS_PC_PROBE_BEGIN"
END="# NOX_V146_WINDOWS_PC_PROBE_END"

class Fixture(http.server.BaseHTTPRequestHandler):
    codes={"/api/nox/status":200,"/api/install/capabilities":401}
    requests=[]
    def do_GET(self):
        Fixture.requests.append((self.command,self.path,self.headers.get("Authorization"),
                                 self.headers.get("Cookie")))
        self.send_response(Fixture.codes.get(self.path,404))
        self.end_headers()
    def do_POST(self):
        Fixture.requests.append((self.command,self.path,self.headers.get("Authorization"),
                                 self.headers.get("Cookie")))
        self.send_response(405)
        self.end_headers()
    def log_message(self,*args):
        pass

class Source(unittest.TestCase):
    def test_no_false_native_pass_without_owner_cookie(self):
        source=SCRIPT.read_text(encoding="utf8")
        self.assertEqual(source.count(BEGIN),1)
        self.assertEqual(source.count(END),1)
        region=source.split(BEGIN,1)[1].split(END,1)[0]
        for required in ("$request.Method = 'GET'","$request.AllowAutoRedirect = $false",
                         "$request.UseDefaultCredentials = $false",
                         "$request.Credentials = $null","$request.Proxy = $null",
                         "'http://127.0.0.1:8766' + $path"):
            self.assertIn(required,region)
        self.assertNotIn("'/api/install/backup'",region.split("function Test-AnonymousPcRoute",1)[1])
        self.assertIn("windows_pc_backup_handler_authenticated = $false",source)
        self.assertIn("windows_pc_handler_registration_verified = $false",source)
        self.assertIn("404 { return 'HTTP_404_AUTH_MASKED_OR_ROUTE_UNKNOWN' }",region)
        self.assertNotIn("ROUTE_NOT_REGISTERED",region)
        self.assertIn("windows_pc_owner_cookie_e2e = 'NOT_TESTED'",source)
        self.assertIn("windows_pc_status_anonymous = Test-AnonymousPcRoute '/api/nox/status'",source)
        self.assertIn("windows_pc_capabilities_anonymous = Test-AnonymousPcRoute '/api/install/capabilities'",source)

    @unittest.skipUnless(shutil.which("pwsh"),"pwsh required; GitHub CI enforces pwsh presence")
    def test_real_http_200_401_404_and_forbidden_backup(self):
        source=SCRIPT.read_text(encoding="utf8")
        region=source.split(BEGIN,1)[1].split(END,1)[0]
        Fixture.requests=[]
        Fixture.codes={"/api/nox/status":200,"/api/install/capabilities":401}
        server=http.server.HTTPServer(("127.0.0.1",8766),Fixture)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        def run(cmd):
            return subprocess.run(["pwsh","-NoProfile","-NonInteractive","-Command",
                                   region+"\n"+cmd],capture_output=True,
                                  text=True,timeout=20)
        try:
            r=run("Test-AnonymousPcRoute '/api/nox/status'; Test-AnonymousPcRoute '/api/install/capabilities'")
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(r.stdout.strip().splitlines(),[
                "ANONYMOUS_200_NO_OWNER_PROOF","AUTH_REQUIRED_NO_OWNER_PROOF"])
            self.assertEqual([x[:2] for x in Fixture.requests],
                             [("GET","/api/nox/status"),("GET","/api/install/capabilities")])
            self.assertTrue(all(a is None and c is None for _,_,a,c in Fixture.requests))
            Fixture.codes["/api/install/capabilities"]=404
            r=run("Test-AnonymousPcRoute '/api/install/capabilities'")
            self.assertEqual(r.returncode,0,r.stderr)
            # Fixture implements the URL in do_GET but deliberately returns 404,
            # reproducing an owner-cookie ACL that masks protected endpoints.
            self.assertEqual(r.stdout.strip(),"HTTP_404_AUTH_MASKED_OR_ROUTE_UNKNOWN")
            before=len(Fixture.requests)
            r=run("Test-AnonymousPcRoute '/api/install/backup'")
            self.assertNotEqual(r.returncode,0)
            self.assertIn("HOLD_WINDOWS_PC_UNAPPROVED_READONLY_ROUTE",r.stderr)
            self.assertEqual(len(Fixture.requests),before,"forbidden backup attempted HTTP")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=4)

if __name__=="__main__":
    unittest.main()
