"""NOX selftools: 30 self-improvement tools behind one registry."""
import importlib

from .registry import Registry, ToolError  # noqa: F401

MODULES = (
    "repo_read", "repo_grep", "self_map", "task_board", "log_tail", "patch_apply", "branch_pr",
    "backup_before_edit", "rollback", "sandbox_run", "test_runner", "eval_gate", "lint_syntax",
    "health_probe", "speed_bench", "svc_ctl", "disk_guard", "gpu_alloc", "mem_alloc",
    "priority_ctl", "corpus_build", "train_ctl", "judge_run", "rag_index", "lora_swap",
    "advisor_ask", "web_fetch", "pc_pull", "model_dl", "inspector_hook")


def build_registry(audit_path=None):
    reg = Registry(audit_path)
    for m in MODULES:
        importlib.import_module("." + m, __package__).register(reg)
    return reg
