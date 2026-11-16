"""Source-only, fail-closed launch plan for the pinned Maya DeepSeek engine on 2x V100.

This module renders argv only. It never launches Maya, creates CUDA contexts,
packs files, starts a service, or changes owner STOP/lease state. Native inputs
must come from the existing owner inspector; absent/unknown evidence is HOLD.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import maya_launch_preflight_v1 as preflight

MAYA_BINARY = Path(
    "/root/nox/engine_builds/maya-c81fab6c9d63-cu124-sm70-v1/build/maya-ds4"
)
MAYA_BINARY_SHA256 = "3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20"
MAYA_MODEL_ID = "deepseek-v4.1-flash"
MAYA_API_URL = "http://127.0.0.1:8080/v1/chat/completions"
MAYA_MODELS_URL = "http://127.0.0.1:8080/v1/models"
MAYA_ROUTE_STATE = "/root/nox/config/maya_ds4_owner_route_v1.json"
GPU_NAMES = ("Tesla V100-SXM2-32GB", "Tesla V100-SXM2-32GB")
GPU_IDS = (0, 1)
TP = 2

# Conservative first smoke profile; these are command inputs, not measured tuning.
MAX_CONTEXT = 4096
RESERVE_MIB = 3072
PARALLEL = 1


def build_source_plan(*, owner_stop, observed_binary_sha256, gpu_names,
                      verified_files, tensor_types, model_file_paths):
    """Return exact argv only after pinned source preflight; never launch it."""
    if owner_stop is not False:
        return {"state": "HOLD_OWNER_STOP", "launchable": False}
    if observed_binary_sha256 != MAYA_BINARY_SHA256:
        return {"state": "HOLD_MAYA_BINARY_SHA256", "launchable": False}
    if tuple(gpu_names) != GPU_NAMES:
        return {"state": "HOLD_TWO_V100_IDENTITY", "launchable": False}

    checked = preflight.evaluate_source_plan(
        stop_present=False,
        gpu_ids=GPU_IDS,
        tp=TP,
        max_context=MAX_CONTEXT,
        reserve_mib=RESERVE_MIB,
        verified_files=verified_files,
        tensor_types=tensor_types,
        model_file_paths=model_file_paths,
    )
    if checked.get("state") != "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE":
        return {"state": checked.get("state", "HOLD_PREFLIGHT_UNKNOWN"),
                "launchable": False}

    pack_dir = checked["packer_output_dir"]
    argv = [
        str(MAYA_BINARY),
        "--pack", pack_dir,
        "--gpus", "0,1",
        "--tp", "2",
        "--max-context", str(MAX_CONTEXT),
        "--reserve-mib", str(RESERVE_MIB),
        "--expert-profile", "none",
        "--mmap-experts", "auto",
        "--dspark", "none",
        "--parallel", str(PARALLEL),
        "--serve",
    ]
    server_config_path = str(Path(pack_dir).parent / "maya-ds4-owner.json")
    server_config = {
        "exe": str(MAYA_BINARY),
        "args": argv[1:-1],
        "cwd": str(MAYA_BINARY.parents[1]),
        "tokenizer": str(Path(pack_dir) / "tokenizer"),
        "model_name": MAYA_MODEL_ID,
        "gpu": list(GPU_IDS),
        "port": 8080,
        "host": "127.0.0.1",
    }
    manager = {
        "kind": "project_maya_official_server",
        "module": "serve.server",
        "engine": "maya",
        "config_path": server_config_path,
        "argv_template": [
            "<owner_verified_maya_python>", "-m", "serve.server",
            "--engine", "maya", "--config", server_config_path,
            "--host", "127.0.0.1", "--port", "8080",
        ],
        "working_directory": str(MAYA_BINARY.parents[1]),
        "bind": "127.0.0.1",
        "api_url": MAYA_API_URL,
        "models_url": MAYA_MODELS_URL,
        "model": MAYA_MODEL_ID,
        "owner_route_state": MAYA_ROUTE_STATE,
        "launch_only_after_owner_stop_lease_resources_and_pack_gates": True,
    }
    return {
        "state": "SOURCE_ONLY_COMMAND_READY_NOT_LAUNCHABLE",
        "launchable": False,
        "argv": argv,
        "env": {"CUDA_VISIBLE_DEVICES": "0,1"},
        "model_pack": pack_dir,
        "server_config": server_config,
        "server_manager": manager,
        "model_content_sha256": "REQUIRES_NATIVE_PINNED_READBACK",
        "engine_sha256": MAYA_BINARY_SHA256,
        "gpu_names": list(GPU_NAMES),
        "gpus": list(GPU_IDS),
        "tensor_parallel": TP,
        "context_tokens": MAX_CONTEXT,
        "vram_reserve_mib": RESERVE_MIB,
        "parallel_requests": PARALLEL,
        "expert_mapping": "auto",
        "drafting": "disabled",
        "precision_override": "none; GGUF quantization is defined by the verified model files",
        "protocol": "Project Maya official OpenAI-compatible serve.server on loopback; engine uses Maya native stdin/stdout protocol",
        "measured": False,
    }


class LaunchPlanTests(unittest.TestCase):
    def valid_inputs(self):
        return {
            "owner_stop": False,
            "observed_binary_sha256": MAYA_BINARY_SHA256,
            "gpu_names": GPU_NAMES,
            "verified_files": [{"path": "fixture", "bytes": 1,
                                "sha256": "0" * 64, "sha_verified": True}],
            "tensor_types": ["IQ2_XXS", "IQ4_NL"],
            "model_file_paths": ["fixture"],
        }

    def test_stop_unknown_and_present_block(self):
        for value in (None, True):
            args = self.valid_inputs()
            args["owner_stop"] = value
            with patch.object(preflight, "evaluate_source_plan") as evaluator:
                result = build_source_plan(**args)
            self.assertEqual(result["state"], "HOLD_OWNER_STOP")
            self.assertFalse(result["launchable"])
            evaluator.assert_not_called()

    def test_binary_and_gpu_identity_are_pinned(self):
        args = self.valid_inputs()
        args["observed_binary_sha256"] = "0" * 64
        self.assertEqual(build_source_plan(**args)["state"], "HOLD_MAYA_BINARY_SHA256")
        args = self.valid_inputs()
        args["gpu_names"] = ("Tesla V100", "Tesla V100")
        self.assertEqual(build_source_plan(**args)["state"], "HOLD_TWO_V100_IDENTITY")

    def test_exact_command_is_source_only_and_has_no_dtype_override(self):
        args = self.valid_inputs()
        checked = {
            "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
            "packer_output_dir": "/verified/model/maya-ds4",
        }
        with patch.object(preflight, "evaluate_source_plan", return_value=checked):
            result = build_source_plan(**args)
        self.assertEqual(result["state"], "SOURCE_ONLY_COMMAND_READY_NOT_LAUNCHABLE")
        self.assertFalse(result["launchable"])
        self.assertEqual(result["argv"], [
            str(MAYA_BINARY), "--pack", "/verified/model/maya-ds4",
            "--gpus", "0,1", "--tp", "2", "--max-context", "4096",
            "--reserve-mib", "3072", "--expert-profile", "none",
            "--mmap-experts", "auto", "--dspark", "none",
            "--parallel", "1", "--serve",
        ])
        self.assertFalse(any(arg.lower() in ("--fp8", "--bf16", "--dtype")
                             for arg in result["argv"]))
        self.assertEqual(result["protocol"], "Project Maya official OpenAI-compatible serve.server on loopback; engine uses Maya native stdin/stdout protocol")
        self.assertFalse(result["measured"])


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        unittest.main(argv=[sys.argv[0]], verbosity=2)
    raise SystemExit("Source-only plan module. Use --self-test; no launcher is implemented.")
