"""Deterministic regression for NOX V133 GitHub Actions safety policy."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from coordination.onepass.native_job_gate_audit import audit,check_workflow


class NativeWorkflowPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.folder=self.root/".github"/"workflows"
        self.folder.mkdir(parents=True)

    def store(self,name,src):
        path=self.folder/name
        path.write_text(src,encoding="utf8")
        return path

    def test_actor_only_does_not_authorize_automatic_remote_ssh(self):
        path=self.store("unsafe.yml","""
name: test
on:
  push: {branches: [feature]}
  workflow_dispatch:
jobs:
  native:
    if: github.actor == 'MSSTXNEWS'
    env: {NOX2: placeholder}
    runs-on: ubuntu-latest
    steps:
      - run: python -m nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe
""")
        unsafe,native=check_workflow(path,root=self.root)
        self.assertEqual(len(unsafe),1)
        self.assertEqual(len(native),1)

    def test_manual_yes_disables_autorun_even_with_push_event(self):
        path=self.store("safe.yml","""
on:
  push: {branches: [feature]}
  workflow_dispatch:
    inputs:
      allow_native:
        type: choice
        options: ['NO','YES']
        default: 'NO'
jobs:
  native:
    if: github.event_name == 'workflow_dispatch' && inputs.allow_native == 'YES'
    env: {NOX2: placeholder}
    runs-on: ubuntu-latest
    steps: [{run: python -m nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe}]
""")
        unsafe,native=check_workflow(path,root=self.root)
        self.assertEqual(unsafe,[])
        self.assertEqual(len(native),1)

    def test_manual_only_with_no_push_is_safe(self):
        path=self.store("only-manual.yml","""
on:
  workflow_dispatch:
jobs:
  native:
    env: {NOX2: placeholder}
    runs-on: ubuntu-latest
    steps: [{run: python -m nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe}]
""")
        self.assertEqual(check_workflow(path,root=self.root)[0],[])

    def test_source_ci_without_native_secret_remains_automatic(self):
        path=self.store("source.yml","""
on: {push: {branches: [feature]}}
jobs:
  source:
    runs-on: ubuntu-latest
    steps:
      - run: python -m unittest
""")
        unsafe,native=check_workflow(path,root=self.root)
        self.assertEqual(unsafe,[])
        self.assertEqual(native,[])

    def test_pull_request_target_native_is_unsafe(self):
        path=self.store("pr-target.yml","""
on:
  pull_request_target: {branches: [main]}
jobs:
  dangerous:
    if: github.actor == 'MSSTXNEWS'
    env: {NOX2: placeholder}
    runs-on: ubuntu-latest
    steps: [{run: echo safety-check}]
""")
        self.assertEqual(len(check_workflow(path,root=self.root)[0]),1)

    def test_parser_errors_fail_closed(self):
        self.store("bad.yml","on:\n  push:\n     : [\n")
        for x in range(4):self.store(f"good{x}.yml","on: push\njobs: {}\n")
        result=audit(self.root)
        self.assertEqual(result["release_state"],"HOLD")
        self.assertEqual(len(result["yaml_parse_errors"]),1)
        self.assertEqual(result["files_checked"],5)


if __name__=="__main__":
    unittest.main()
