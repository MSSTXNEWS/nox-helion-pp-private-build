"""Run the original pinned seven-case cache suite in its declared source package."""
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch


ROOT=Path(__file__).resolve().parent
PATH=ROOT/'source_tests/test_cache_race.py'
SPEC=importlib.util.spec_from_file_location('nox_original_cache_race',PATH)
ORIGINAL=importlib.util.module_from_spec(SPEC)
with patch.object(sys,'argv',[str(PATH),'--runtime',
     str(ROOT/'nox_runpod/teacher_mesh/v38/durable_runtime.py'),
     '--v38',str(ROOT/'nox_runpod/teacher_mesh/v38')]):
    SPEC.loader.exec_module(ORIGINAL)


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromModule(ORIGINAL)
