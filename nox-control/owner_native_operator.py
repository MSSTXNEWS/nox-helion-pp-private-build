#!/usr/bin/env python3
"""Explicit owner-command transport; one authenticated SSH session, pinned source.
No push/PR activation, no secret export, no blind retry of native mutations.
"""
from __future__ import annotations
import argparse, base64, contextlib, hashlib, ipaddress, json, os, re, socket, subprocess, sys, time
from pathlib import Path
REPO='MSSTXNEWS/nox-helion-pp-private-build'
OWNER_ID=340718567
INSTANCE=60509551
PIN='SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
FILES={'drive_probe': 'nox-control/owner_native_drive_probe.py', 'audit': 'nox-control/owner_native_audit.py', 'audit_gpu_inventory': 'nox-control/owner_native_audit_gpu_inventory_entry.py', 'inspect': 'nox-control/systemic_relay_20261118/owner_systemic_relay_observe.py', 'stage': 'nox-control/owner_native_stage.py', 'repair': 'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke_entry.py', 'browser_qa': 'nox-control/owner_browser_stream_only_entry.py', 'lifeline': 'nox-control/owner_native_lifeline.py', 'emergency_stop': 'nox-control/owner_native_emergency_stop.py', 'emergency_stop_preflight': 'nox-control/owner_native_emergency_stop_preflight.py'}
MASTER=None

def _subprocess_env_without_nox2():
    """Never forward the owner API credential to child processes."""
    env=os.environ.copy()
    env.pop('NOX2',None)
    return env

def _safe_subprocess_run(*args,**kwargs):
    kwargs['env']=_subprocess_env_without_nox2()
    return subprocess.run(*args,**kwargs)

def _safe_subprocess_check_output(*args,**kwargs):
    kwargs['env']=_subprocess_env_without_nox2()
    return subprocess.check_output(*args,**kwargs)

SCOPED_REPAIR_BUNDLES={'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke_entry.py': (), 'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_counter_reconcile_policy_v1/owner_chat_counter_policy_entry.py': (), 'nox-control/systemic_relay_20261118/next_reviewed_merge_20261118/prepared_v3/owner_systemic_reviewed_merge_embedded_entry.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_v5/owner_chat_decomposition_embedded_entry.py': (), 'nox-control/owner_continuous_executor_install.py': ('cw_test_nox_forge_language_task_coverage.py', 'cw_test_nox_readonly_retry_backoff.py', 'cw_test_nox_warm_cache_limit_contract.py', 'cw_contract_510dbdec4dd2538ebeac.json', 'cw_contract_9efad5217ab0e554a383.json', 'cw_contract_683c5086d66e750d4ed1.json', 'continuous_transaction_helpers.py', 'continuous_dispatcher.py', 'continuous_planner.py', 'continuous_truth.py'), 'nox-control/owner_bounded_cpu_install.py': ('bc_runtime_d5fb476f53e64d2014f2.py', 'bc_runtime_6c67e567e669b993d016.py', 'bc_runtime_2c83ec53f7ee7c2d76bc.py', 'bc_runtime_294473d35d4870f50467.py'), 'nox-control/owner_project_runtime_update.py': ('ru_runtime_fcb77cc59eb9a88dde68.py', 'ru_runtime_84d54c647b0a63447aca.py', 'ru_runtime_52e62a143d16f387899f.py', 'ru_runtime_aa0dd1c8266106b599ce.py', 'ru_plans_a171fa7a94084a1f4b67.data', 'ru_blobs_fa3d69e506d727295094.data', 'ru_plans_79b77425ff05d3337c2e.data', 'ru_blobs_b980a61884965f4838f8.data', 'ru_plans_dd24421576ae4160fa01.data', 'ru_blobs_7e625acddd71fe95988e.data', 'ru_blobs_4b06687bbad8fe6ab046.data', 'ru_contracts_eece310e5608fa9c633d.data'), 'nox-control/owner_complete_executor_install.py': ('ce_runtime_2c4735938dacd2a062ed.py', 'ce_runtime_71dd03dee52f1673c297.py', 'ce_runtime_f6b2f98ac5c7c291ffef.py', 'ce_runtime_687ea3b3548badf9b7ba.py', 'ce_runtime_35b0e94f9c883da017e4.py', 'ce_runtime_d0ff44d4752128c26779.py', 'ce_runtime_119115603be6dba84121.py', 'ce_runtime_7f18d69529582b65f7b8.py', 'ce_runtime_126c77c1281b74676930.py', 'ce_runtime_485d4a4a571c434afb98.py', 'ce_baseline_bb2c543979ad58801d97.source', 'ce_baseline_4d1274059d034bb9b96a.source', 'ce_baseline_d9ec6a8250a167d774ba.source', 'ce_baseline_c676fdda4fa47d316eb1.source', 'ce_baseline_8657ad367e6dd25b48ca.source', 'ce_baseline_006fc038f43682fa36d2.source', 'ce_baseline_d35064a3fc5707dfc174.source', 'ce_baseline_66a6617d6f582876dbdc.source', 'ce_baseline_e3b0c44298fc1c149afb.source', 'ce_baseline_092db7d32a048c1706da.source', 'ce_baseline_dc19594b45a7fae32bf9.source', 'ce_baseline_b4ece67144248808a12c.source', 'ce_baseline_21f8538fec15d39b4dbc.source', 'ce_baseline_3efe025681c3a54cbfac.source', 'ce_baseline_b3c5d26011400b110a1b.source', 'ce_baseline_f299d32099c25ea1822c.source', 'ce_baseline_0fff97b7e758e3e43073.source', 'ce_baseline_fd815f9a743bfcdf6e71.source', 'ce_baseline_97c433b8893514f5812b.source', 'ce_baseline_fc5d6c564c651c2abc81.source', 'ce_baseline_623bfb4ba2d28d3dd3db.source', 'ce_baseline_9201bc3629682a577c80.source', 'ce_baseline_d6042e38549360ace8f9.source', 'ce_baseline_2860173d8d6ed7147af2.source', 'ce_baseline_970d6681ce5dc57156e2.source', 'ce_baseline_6aa9265942695d2b54b3.source', 'ce_baseline_8d2070c2f0819e7d1c2b.source', 'ce_baseline_60e28219f670a8449a56.source', 'ce_plans_283ff826ba1180398888.json', 'ce_blobs_fa3d69e506d727295094.source', 'ce_plans_e7c99335a4a790202f22.json', 'ce_blobs_f7b69405224c63868b76.source', 'ce_plans_de41f4de77a043c695fe.json', 'ce_blobs_7e625acddd71fe95988e.source', 'ce_plans_67e819b4ff1b94cc5bdd.json', 'ce_blobs_b980a61884965f4838f8.source', 'ce_plans_4037501920f2e9f3ea41.json', 'ce_blobs_06940cb13bd568d4cfaa.source', 'ce_plans_9b80e2075b52602ac9e1.json', 'ce_blobs_f336c58fb5062aec6d5b.source', 'ce_contracts_b40696685ca2b7c848a2.json', 'ce_manifests_79a8efb2d344479471bd.json', 'ce_manifests_e040c40bd8ee3d29b0cc.json'), 'nox-control/owner_post_reset_state_observe.py': (), 'nox-control/owner_chat_markdown_asset_install_v2.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'nox-v24-chat-markdown-final.js'), 'nox-control/owner_chat_markdown_metadata.py': (), 'nox-control/owner_chat_markdown_asset_install.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'nox-v24-chat-markdown-final.js'), 'nox-control/owner_workspace_browser_acceptance_v6.py': ('owner_workspace_browser_acceptance_v5.py', 'owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_checkpoint_proof_v2.py': (), 'nox-control/owner_workspace_browser_acceptance_v5.py': ('owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_chat_markdown_acceptance.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_memfd_progress.py': (), 'nox-control/owner_qwen_successor_checkpoint_proof.py': (), 'nox-control/owner_qwen_successor_observe_v2.py': (), 'nox-control/owner_workspace_browser_acceptance_v3.py': ('owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_entry_v2.py': ('owner_qwen_successor_install_v2.py', 'owner_qwen_execution_successor.py', 'qwen_student_training_entry_successor.py', 'owner_qwen_successor_guard.py', 'owner_qwen_successor_status.py', 'owner_qwen_successor_media_handoff.py', 'owner_qwen_successor_media_guard.py', 'owner_qwen_successor_handback_retry.py', 'owner_qwen_successor_hermes_hydrate.py', 'owner_qwen_successor_watch.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_workspace_browser_acceptance_v2.py': ('owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_entry.py': ('owner_qwen_successor_install.py', 'owner_qwen_execution_successor.py', 'qwen_student_training_entry_successor.py', 'owner_qwen_successor_guard.py', 'owner_qwen_successor_status.py', 'owner_qwen_successor_media_handoff.py', 'owner_qwen_successor_media_guard.py', 'owner_qwen_successor_handback_retry.py', 'owner_qwen_successor_hermes_hydrate.py', 'owner_qwen_successor_watch.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_workspace_browser_acceptance.py': ('owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_budget_failure_diagnose.py': (), 'nox-control/owner_workspace_asset_install.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'workspace-owner-capabilities.js'), 'nox-control/owner_qwen_public_memfd_access_probe.py': (), 'nox-control/owner_training_control_readonly_batch.py': ('owner_qwen_transport_budget_observe.py', 'owner_admin_control_structure_probe.py', 'owner_qwen_public_memfd_access_probe.py'), 'nox-control/owner_qwen_transport_budget_observe.py': (), 'nox-control/owner_admin_control_structure_probe.py': (), 'nox-control/owner_qwen_transport_budget_finalize_6914959637.py': (), 'nox-control/owner_chat_page_diagnose.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_chat_action_routing_install.py': ('owner_chat_stream_action_routing.py', 'owner_download_status_entry.py', 'owner_native_repair.py'), 'nox-control/owner_chat_plan_api_probe.py': (), 'nox-control/owner_chat_stream_asset_install_v2.py': ('nox-v135-resonance-owner-bridge-coalesced.js', 'owner_media_acceptance_entry.py', 'owner_native_repair.py'), 'nox-control/owner_qwen_transport_rollback_entry.py': ('owner_qwen_transport_rollback.py', 'owner_qwen_transport_revision_install.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py', 'owner_qwen_transport_failed_diagnostic.json'), 'nox-control/owner_qwen_transport_budget_entry.py': ('owner_qwen_revision_install.py', 'qwen_student_training_entry_revision.py', 'owner_qwen_transport_budget_install.py', 'qwen_student_training_entry_transport_budget.py', 'owner_qwen_execution_revision.py', 'owner_qwen_revision_guard.py', 'owner_qwen_revision_status.py', 'owner_qwen_revision_media_handoff.py', 'owner_qwen_revision_media_guard.py', 'owner_qwen_revision_handback_retry.py', 'owner_hermes_revision_hydrate.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_chat_stream_asset_install.py': ('nox-v135-resonance-owner-bridge-coalesced.js', 'owner_media_acceptance_entry.py', 'owner_native_repair.py'), 'nox-control/owner_browser_asset_identity_entry.py': ('owner_browser_normal_motion_entry.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py', 'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py', 'owner_chat_normal_motion_qa.py', 'owner_chat_asset_identity_qa.py'), 'nox-control/owner_qwen_held_media_smoke_v2_entry.py': ('owner_qwen_held_media_smoke_v2.py', 'owner_media_acceptance_entry.py', 'owner_qwen_revision_install.py', 'owner_native_repair.py', 'owner_download_status_entry.py'), 'nox-control/owner_browser_normal_motion_entry.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py', 'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py', 'owner_chat_normal_motion_qa.py'), 'nox-control/owner_qwen_held_media_smoke_entry.py': ('owner_qwen_held_media_smoke.py', 'owner_media_acceptance_entry.py', 'owner_qwen_revision_install.py', 'owner_native_repair.py', 'owner_download_status_entry.py'), 'nox-control/owner_qwen_transport_install_entry.py': ('owner_qwen_revision_install.py', 'qwen_student_training_entry_revision.py', 'owner_qwen_transport_revision_install.py', 'qwen_student_training_entry_transport_candidate.py', 'owner_qwen_execution_revision.py', 'owner_qwen_revision_guard.py', 'owner_qwen_revision_status.py', 'owner_qwen_revision_media_handoff.py', 'owner_qwen_revision_media_guard.py', 'owner_qwen_revision_handback_retry.py', 'owner_hermes_revision_hydrate.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_reviewed_rescue_catalog_append.py': ('rv_plan_379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json', 'rv_payload_5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926.source', 'rv_payload_4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821.source'), 'nox-control/owner_kernel_self_fd_install.py': ('sf_runtime_192d0c1b7b87447d4f08.py', 'sf_plan_457dbaf4484cfb5b7e14.json', 'sf_payload_5201af0115e1ead68d33.source', 'sf_payload_4329f7389b24cfbb1fbb.source', 'sf_fd_descriptor_768d28516014a124a380.json'), 'nox-control/owner_reviewed_proc_followup_catalog_append.py': ('fu_plan_3f620116ee563127d7e94bfeac7aae1408aaa4f1752f431fee774c49023e6509.json', 'fu_payload_a71051c085f8bfdbeda93f3f4c16501444ca35942ac4ca7f3a46d7bd16acfbbc.source', 'fu_payload_f5c8eb6b42e71efa38745bc6f729a989b4a199999d7c3b9aa45cebbde36f851a.source'), 'nox-control/owner_model_slot_recovery.py': ('slot_contract_3f43e152774c159bbe45.json', 'slot_contract_60a6abf6691f6c3fb186.json', 'slot_transaction_helpers.py', 'slot_model_client.py'), 'nox-control/owner_c02_memory_progress_install.py': ('c02_contract_4a8f20c371f3211c2351.json', 'c02_test_nox_c02_existing_cognition.py', 'c02_test_nox_c02_optional_starvation.py', 'c02_transaction_helpers.py'), 'nox-control/owner_c02_memory_reviewed_recovery.py': ('c02r_payload_b504248ac1ae4a093382.source', 'c02r_plan_5d05ba50d058981ce8ba.json', 'c02r_transaction_helpers.py'), 'nox-control/systemic_relay_20261118/owner_systemic_relay_entry.py': ('systemic_owner_subagent_dispatcher.py', 'systemic_owner_subagent_processes.py', 'systemic_owner_project_native.py', 'systemic_owner_project_planner.py', 'systemic_owner_subagent_instruction_truth.py', 'systemic_owner_systemic_refill.py', 'systemic_transaction_helpers.py', 'systemic_cache_fill_ttl.json', 'systemic_forge_read_budget.json', 'systemic_relay_manifest.json', 'systemic_skill_journal_budget.json'), 'nox-control/systemic_relay_20261118/owner_eval_checkpoint_prepare.py': (), 'nox-control/systemic_relay_20261118/owner_systemic_reviewed_entry.py': ('reviewed_systemic_transaction_helpers.py', 'reviewed_cache_ttl_plan.json', 'reviewed_cache_ttl_payload.source', 'reviewed_forge_budget_plan.json', 'reviewed_forge_budget_payload.source', 'reviewed_skill_budget_plan.json', 'reviewed_skill_budget_payload.source'), 'nox-control/systemic_relay_20261118/next_pack_44368502183/package/native_publish_entry_d58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212.py': (), 'nox-control/systemic_relay_20261118/tooling/owner_nox_acceleration_entry.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_v4/owner_chat_decomposition_embedded_entry.py': ()}
SCOPED_REPAIR_BUNDLES['nox-control/owner_browser_stream_only_entry.py']=('owner_chat_browser_qa.py','owner_chat_browser_transport_qa.py','owner_chat_browser_release_qa.py','owner_chat_stream_only_qa.py')
SCOPED_REPAIR_EXTRA_PATHS={'nox-control/owner_continuous_executor_install.py': ('nox-control/continuous_executor_20261118/assets/cw_test_nox_forge_language_task_coverage.py', 'nox-control/continuous_executor_20261118/assets/cw_test_nox_readonly_retry_backoff.py', 'nox-control/continuous_executor_20261118/assets/cw_test_nox_warm_cache_limit_contract.py', 'nox-control/continuous_executor_20261118/assets/cw_contract_510dbdec4dd2538ebeac.json', 'nox-control/continuous_executor_20261118/assets/cw_contract_9efad5217ab0e554a383.json', 'nox-control/continuous_executor_20261118/assets/cw_contract_683c5086d66e750d4ed1.json', 'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py', 'nox-control/continuous_executor_20261118/assets/continuous_dispatcher.py', 'nox-control/continuous_executor_20261118/assets/continuous_planner.py', 'nox-control/continuous_executor_20261118/assets/continuous_truth.py'), 'nox-control/owner_bounded_cpu_install.py': ('nox-control/complete_executor_budget_20261118/assets/bc_runtime_d5fb476f53e64d2014f2.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_6c67e567e669b993d016.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_2c83ec53f7ee7c2d76bc.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_294473d35d4870f50467.py'), 'nox-control/owner_project_runtime_update.py': ('nox-control/complete_executor_retries_20261118/assets/ru_runtime_fcb77cc59eb9a88dde68.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_84d54c647b0a63447aca.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_52e62a143d16f387899f.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_aa0dd1c8266106b599ce.py', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_a171fa7a94084a1f4b67.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_fa3d69e506d727295094.data', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_79b77425ff05d3337c2e.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_b980a61884965f4838f8.data', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_dd24421576ae4160fa01.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_7e625acddd71fe95988e.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_4b06687bbad8fe6ab046.data', 'nox-control/complete_executor_retries_20261118/assets/ru_contracts_eece310e5608fa9c633d.data'), 'nox-control/owner_complete_executor_install.py': ('nox-control/complete_executor_20261118/assets/ce_runtime_2c4735938dacd2a062ed.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_71dd03dee52f1673c297.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_f6b2f98ac5c7c291ffef.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_687ea3b3548badf9b7ba.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_35b0e94f9c883da017e4.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_d0ff44d4752128c26779.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_119115603be6dba84121.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_7f18d69529582b65f7b8.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_126c77c1281b74676930.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_485d4a4a571c434afb98.py', 'nox-control/complete_executor_20261118/assets/ce_baseline_bb2c543979ad58801d97.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_4d1274059d034bb9b96a.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d9ec6a8250a167d774ba.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_c676fdda4fa47d316eb1.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_8657ad367e6dd25b48ca.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_006fc038f43682fa36d2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d35064a3fc5707dfc174.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_66a6617d6f582876dbdc.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_e3b0c44298fc1c149afb.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_092db7d32a048c1706da.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_dc19594b45a7fae32bf9.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_b4ece67144248808a12c.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_21f8538fec15d39b4dbc.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_3efe025681c3a54cbfac.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_b3c5d26011400b110a1b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_f299d32099c25ea1822c.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_0fff97b7e758e3e43073.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_fd815f9a743bfcdf6e71.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_97c433b8893514f5812b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_fc5d6c564c651c2abc81.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_623bfb4ba2d28d3dd3db.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_9201bc3629682a577c80.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d6042e38549360ace8f9.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_2860173d8d6ed7147af2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_970d6681ce5dc57156e2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_6aa9265942695d2b54b3.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_8d2070c2f0819e7d1c2b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_60e28219f670a8449a56.source', 'nox-control/complete_executor_20261118/assets/ce_plans_283ff826ba1180398888.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_fa3d69e506d727295094.source', 'nox-control/complete_executor_20261118/assets/ce_plans_e7c99335a4a790202f22.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_f7b69405224c63868b76.source', 'nox-control/complete_executor_20261118/assets/ce_plans_de41f4de77a043c695fe.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_7e625acddd71fe95988e.source', 'nox-control/complete_executor_20261118/assets/ce_plans_67e819b4ff1b94cc5bdd.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_b980a61884965f4838f8.source', 'nox-control/complete_executor_20261118/assets/ce_plans_4037501920f2e9f3ea41.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_06940cb13bd568d4cfaa.source', 'nox-control/complete_executor_20261118/assets/ce_plans_9b80e2075b52602ac9e1.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_f336c58fb5062aec6d5b.source', 'nox-control/complete_executor_20261118/assets/ce_contracts_b40696685ca2b7c848a2.json', 'nox-control/complete_executor_20261118/assets/ce_manifests_79a8efb2d344479471bd.json', 'nox-control/complete_executor_20261118/assets/ce_manifests_e040c40bd8ee3d29b0cc.json'), 'nox-control/owner_chat_markdown_asset_install_v2.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/nox-v24-chat-markdown-final.js'), 'nox-control/owner_chat_markdown_asset_install.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/nox-v24-chat-markdown-final.js'), 'nox-control/owner_workspace_browser_acceptance_v6.py': ('nox-control/owner_workspace_browser_acceptance_v5.py', 'nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_workspace_browser_acceptance_v5.py': ('nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_workspace_browser_acceptance_v3.py': ('nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_qwen_successor_entry_v2.py': ('nox-control/owner_qwen_successor_install_v2.py', 'nox-control/owner_qwen_execution_successor.py', 'nox-control/qwen_student_training_entry_successor.py', 'nox-control/owner_qwen_successor_guard.py', 'nox-control/owner_qwen_successor_status.py', 'nox-control/owner_qwen_successor_media_handoff.py', 'nox-control/owner_qwen_successor_media_guard.py', 'nox-control/owner_qwen_successor_handback_retry.py', 'nox-control/owner_qwen_successor_hermes_hydrate.py', 'nox-control/owner_qwen_successor_watch.py'), 'nox-control/owner_workspace_browser_acceptance_v2.py': ('nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_qwen_successor_entry.py': ('nox-control/owner_qwen_successor_install.py', 'nox-control/owner_qwen_execution_successor.py', 'nox-control/qwen_student_training_entry_successor.py', 'nox-control/owner_qwen_successor_guard.py', 'nox-control/owner_qwen_successor_status.py', 'nox-control/owner_qwen_successor_media_handoff.py', 'nox-control/owner_qwen_successor_media_guard.py', 'nox-control/owner_qwen_successor_handback_retry.py', 'nox-control/owner_qwen_successor_hermes_hydrate.py', 'nox-control/owner_qwen_successor_watch.py'), 'nox-control/owner_workspace_browser_acceptance.py': ('nox-control/owner_chat_page_diagnose.py',), 'nox-control/owner_workspace_asset_install.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/workspace-owner-capabilities.js'), 'nox-control/owner_training_control_readonly_batch.py': ('nox-control/owner_qwen_transport_budget_observe.py', 'nox-control/owner_admin_control_structure_probe.py', 'nox-control/owner_qwen_public_memfd_access_probe.py'), 'nox-control/owner_chat_action_routing_install.py': ('nox-control/owner_chat_stream_action_routing.py',), 'nox-control/owner_chat_stream_asset_install_v2.py': ('coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js',), 'nox-control/owner_qwen_transport_rollback_entry.py': ('nox-control/owner_qwen_transport_rollback.py', 'nox-control/owner_qwen_transport_revision_install.py', 'nox-control/owner_qwen_transport_failed_diagnostic.json'), 'nox-control/owner_qwen_transport_budget_entry.py': ('nox-control/owner_qwen_transport_budget_install.py', 'nox-control/qwen_student_training_entry_transport_budget.py'), 'nox-control/owner_chat_stream_asset_install.py': ('coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js',), 'nox-control/owner_browser_asset_identity_entry.py': ('nox-control/owner_browser_normal_motion_entry.py', 'nox-control/owner_chat_normal_motion_qa.py', 'nox-control/owner_chat_asset_identity_qa.py'), 'nox-control/owner_qwen_held_media_smoke_v2_entry.py': ('nox-control/owner_qwen_held_media_smoke_v2.py',), 'nox-control/owner_browser_normal_motion_entry.py': ('nox-control/owner_chat_normal_motion_qa.py',), 'nox-control/owner_qwen_transport_install_entry.py': ('nox-control/owner_qwen_transport_revision_install.py', 'nox-control/qwen_student_training_entry_transport_candidate.py'), 'nox-control/owner_reviewed_rescue_catalog_append.py': ('nox-control/complete_executor_rescue_20261118/assets/rv_plan_379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json', 'nox-control/complete_executor_rescue_20261118/assets/rv_payload_5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926.source', 'nox-control/complete_executor_rescue_20261118/assets/rv_payload_4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821.source'), 'nox-control/owner_kernel_self_fd_install.py': ('nox-control/complete_executor_proc_identity_20261118/assets/sf_runtime_192d0c1b7b87447d4f08.py', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_plan_457dbaf4484cfb5b7e14.json', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_payload_5201af0115e1ead68d33.source', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_payload_4329f7389b24cfbb1fbb.source', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_fd_descriptor_768d28516014a124a380.json'), 'nox-control/owner_reviewed_proc_followup_catalog_append.py': ('nox-control/complete_executor_followup_20261118/assets/fu_plan_3f620116ee563127d7e94bfeac7aae1408aaa4f1752f431fee774c49023e6509.json', 'nox-control/complete_executor_followup_20261118/assets/fu_payload_a71051c085f8bfdbeda93f3f4c16501444ca35942ac4ca7f3a46d7bd16acfbbc.source', 'nox-control/complete_executor_followup_20261118/assets/fu_payload_f5c8eb6b42e71efa38745bc6f729a989b4a199999d7c3b9aa45cebbde36f851a.source'), 'nox-control/owner_model_slot_recovery.py': ('nox-control/model_slot_recovery_20261118/assets/slot_contract_3f43e152774c159bbe45.json', 'nox-control/model_slot_recovery_20261118/assets/slot_contract_60a6abf6691f6c3fb186.json', 'nox-control/model_slot_recovery_20261118/assets/slot_transaction_helpers.py', 'nox-control/model_slot_recovery_20261118/assets/slot_model_client.py'), 'nox-control/owner_c02_memory_progress_install.py': ('nox-control/c02_memory_progress_20261118/assets/c02_contract_4a8f20c371f3211c2351.json', 'nox-control/c02_memory_progress_20261118/assets/c02_test_nox_c02_existing_cognition.py', 'nox-control/c02_memory_progress_20261118/assets/c02_test_nox_c02_optional_starvation.py', 'nox-control/c02_memory_progress_20261118/assets/c02_transaction_helpers.py'), 'nox-control/owner_c02_memory_reviewed_recovery.py': ('nox-control/c02_memory_progress_20261118/recovery_assets/c02r_payload_b504248ac1ae4a093382.source', 'nox-control/c02_memory_progress_20261118/recovery_assets/c02r_plan_5d05ba50d058981ce8ba.json', 'nox-control/c02_memory_progress_20261118/recovery_assets/c02r_transaction_helpers.py'), 'nox-control/systemic_relay_20261118/owner_systemic_relay_entry.py': ('nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_dispatcher.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_processes.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_project_native.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_project_planner.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_instruction_truth.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_systemic_refill.py', 'nox-control/systemic_relay_20261118/assets/systemic_transaction_helpers.py', 'nox-control/systemic_relay_20261118/assets/systemic_cache_fill_ttl.json', 'nox-control/systemic_relay_20261118/assets/systemic_forge_read_budget.json', 'nox-control/systemic_relay_20261118/assets/systemic_relay_manifest.json', 'nox-control/systemic_relay_20261118/assets/systemic_skill_journal_budget.json'), 'nox-control/systemic_relay_20261118/owner_eval_checkpoint_prepare.py': (), 'nox-control/systemic_relay_20261118/owner_systemic_reviewed_entry.py': ('nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_systemic_transaction_helpers.py', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_cache_ttl_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_cache_ttl_payload.source', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_forge_budget_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_forge_budget_payload.source', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_skill_budget_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_skill_budget_payload.source')}

FROZEN_BROWSER_PAGE_DEPENDENCIES={
    'owner_browser_stream_only_entry.py':'nox-control/pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
}
FROZEN_BROWSER_DEPENDENCIES={
    'owner_browser_stream_only_entry.py':'nox-control/pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
    'owner_chat_stream_only_qa.py':'nox-control/pinned/browser_normal_v1/owner_chat_stream_only_qa.py',
}
FROZEN_BROWSER_ENTRIES=('nox-control/owner_browser_normal_motion_entry.py',
                        'nox-control/owner_browser_asset_identity_entry.py')

def repair_bundle_paths(action,entrypoint,paths):
    if action not in ('repair','browser_qa') or entrypoint not in SCOPED_REPAIR_BUNDLES:return paths
    selected=SCOPED_REPAIR_BUNDLES[entrypoint]
    if len(set(selected))!=len(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_DUPLICATE_ALLOWLIST')
    overrides=(FROZEN_BROWSER_DEPENDENCIES if entrypoint in FROZEN_BROWSER_ENTRIES else
               FROZEN_BROWSER_PAGE_DEPENDENCIES if entrypoint in ('nox-control/owner_chat_page_diagnose.py',
                   'nox-control/owner_workspace_browser_acceptance.py','nox-control/owner_workspace_browser_acceptance_v2.py','nox-control/owner_workspace_browser_acceptance_v3.py','nox-control/owner_workspace_browser_acceptance_v5.py','nox-control/owner_chat_markdown_acceptance.py','nox-control/owner_workspace_browser_acceptance_v6.py') else {})
    if not set(overrides).issubset(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_FROZEN_SCOPE')
    found={}
    for path in (*paths,*SCOPED_REPAIR_EXTRA_PATHS.get(entrypoint,()),*overrides.values()):
        name=Path(path).name
        if name not in selected or name in overrides and path!=overrides[name]:continue
        if name in found:raise RuntimeError('HOLD_SCOPED_BUNDLE_DUPLICATE_SOURCE')
        found[name]=path
    if set(found)!=set(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_MISSING_SOURCE')
    result=tuple(found[name] for name in selected)
    if any(not Path(path).is_file() for path in result):raise RuntimeError('HOLD_SCOPED_BUNDLE_MISSING_FILE')
    return result

def authorize_event(action):
    e=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_EVENT_NAME')!='issue_comment':raise RuntimeError('HOLD_EVENT_SCOPE')
    c=e.get('comment',{});owner=e.get('repository',{}).get('owner',{})
    if (c.get('user',{}).get('id')!=OWNER_ID or owner.get('id')!=OWNER_ID or c.get('author_association')!='OWNER'
            or e.get('issue',{}).get('number')!=256 or e.get('sender',{}).get('id')!=OWNER_ID):raise RuntimeError('HOLD_OWNER_COMMAND_IDENTITY')
    sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise RuntimeError('HOLD_SOURCE_PIN')
    if c.get('body')!=f'/nox-maintain {INSTANCE} {sha} {action}':raise RuntimeError('HOLD_EXACT_OWNER_COMMAND')
    if _safe_subprocess_check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise RuntimeError('HOLD_CHECKOUT_MISMATCH')
    return c['id']

def run_native(action,request_id):
    global MASTER
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
    key=os.environ.get('NOX2','')
    if not key:raise RuntimeError('HOLD_OWNER_API_CREDENTIAL_UNAVAILABLE')
    instance_result=s.api('GET',f'/instances/{INSTANCE}/',key)
    target=instance_result.get('instances') if isinstance(instance_result,dict) else None
    if not isinstance(target,dict) or str(target.get('id'))!=str(INSTANCE):target=None
    def public_state(value):
        return value if isinstance(value,str) and re.fullmatch('[a-zA-Z0-9_-]{1,40}',value) else None
    print('NOX_MAINT_INSTANCE_STATE='+json.dumps({'instance':INSTANCE,'found':target is not None,
        'actual_status':public_state(target.get('actual_status')) if target else None,
        'intended_status':public_state(target.get('intended_status')) if target else None,
        'cur_state':public_state(target.get('cur_state')) if target else None,
        'num_gpus':int(str(target.get('num_gpus'))) if target and re.fullmatch('[0-9]{1,2}',str(target.get('num_gpus'))) else None,
        'read_only_provider_lookup':True,'provider_mutations':0},sort_keys=True),flush=True)
    if not target or target.get('actual_status')!='running' or str(target.get('num_gpus'))!='2':raise RuntimeError('HOLD_EXACT_RUNNING_INSTANCE')
    ip=target.get('public_ipaddr')
    if not ipaddress.ip_address(ip).is_global:raise RuntimeError('HOLD_INSTANCE_ROUTE')
    port=None
    for m in target.get('ports',{}).get('22/tcp',[]):
        value=str(m.get('HostPort',''))
        if not value.isdigit() or not 1<=int(value)<=65535:continue
        try:
            with socket.create_connection((ip,int(value)),timeout=6) as sock:
                sock.settimeout(5)
                if sock.recv(128).startswith(b'SSH-2.0'):port=int(value);break
        except OSError:continue
    if port is None:raise RuntimeError('HOLD_CURRENT_SSH_ROUTE')
    s.RUNNER.mkdir(parents=True,mode=0o700,exist_ok=True)
    known=s.RUNNER/'known_hosts'
    p=_safe_subprocess_run(['ssh-keyscan','-T','8','-t','ed25519','-p',str(port),ip],capture_output=True,text=True,timeout=12)
    known.write_text(p.stdout[:8000]);known.chmod(0o600)
    fp=_safe_subprocess_run(['ssh-keygen','-lf',str(known),'-E','sha256'],capture_output=True,text=True,timeout=8)
    if p.returncode or fp.returncode or PIN not in fp.stdout:raise RuntimeError('HOLD_OWNER_HOST_PIN')
    print('NOX_MAINT_HOST_PIN=VERIFIED',flush=True)
    _safe_subprocess_run(['ssh-keygen','-q','-t','ed25519','-N','','-C','nox-owner-maint-'+os.environ.get('GITHUB_RUN_ID','manual'),'-f',str(s.KEY)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=12)
    s.KEY.chmod(0o600);public=s.KEY.with_suffix('.pub').read_text().strip()
    if not public.startswith('ssh-ed25519 ') or len(public)>700:raise RuntimeError('HOLD_PUBLIC_KEY_FORMAT')
    if s.match(key,public):raise RuntimeError('HOLD_KEY_COLLISION')
    s.TRACK.write_text(json.dumps({'public':public,'key_id':None}));s.TRACK.chmod(0o600)
    s.api('POST',f'/instances/{INSTANCE}/ssh/',key,{'ssh_key':public})
    ids=[]
    for _ in range(6):
        ids=s.match(key,public)
        if ids:break
        time.sleep(2)
    if len(ids)!=1:raise RuntimeError('HOLD_KEY_ATTACH_NOT_VERIFIED')
    s.TRACK.write_text(json.dumps({'public':public,'key_id':ids[0]}))
    sock=s.RUNNER/'owner-ssh.sock'
    common=['ssh','-T','-i',str(s.KEY),'-p',str(port),'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
         '-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','NumberOfPasswordPrompts=0',
         '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','ControlPath='+str(sock)]
    host='root@'+ip
    # Classify SSH failures without printing stderr, user names, IPs, keys,
    # file paths or host fingerprints. Used only for owner diagnostics.
    # Distinguish wrong key propagation from a down socket or mux failure.
    def ssh_failure_class(stderr):
        if not isinstance(stderr, str):
            return 'UNKNOWN'
        message = stderr[:2048].lower()
        rules = (
            ('authentication refused: bad ownership or modes', 'BAD_AUTHORIZED_KEYS_PERMISSIONS'),
            ('permission denied (publickey)', 'PUBLICKEY_REJECTED'),
            ('too many authentication failures', 'TOO_MANY_AUTH_FAILURES'),
            ('host key verification failed', 'HOST_KEY_REJECTED'),
            ('remote host identification has changed', 'HOST_KEY_REJECTED'),
            ('connection reset by', 'CONNECTION_RESET'),
            ('connection closed by', 'CONNECTION_CLOSED'),
            ('connection refused', 'CONNECTION_REFUSED'),
            ('connection timed out', 'CONNECTION_TIMEOUT'),
            ('operation timed out', 'CONNECTION_TIMEOUT'),
            ('no route to host', 'ROUTE_UNAVAILABLE'),
            ('network is unreachable', 'ROUTE_UNAVAILABLE'),
            ('controlpath', 'MUX_SOCKET_FAILURE'),
            ('mux_client', 'MUX_SOCKET_FAILURE'),
            ('kex_exchange_identification', 'KEX_FAILURE'),
            ('banner exchange', 'KEX_FAILURE'),
        )
        return next((code for token, code in rules if token in message), 'UNKNOWN')
    # Authenticate the persistent connection, not a disposable 'true' session.
    # Retry only before any payload has been sent.
    for attempt in range(8):
        try:
            r=_safe_subprocess_run(common+['-o','ControlMaster=yes','-o','ControlPersist=90','-N','-f',host],capture_output=True,text=True,timeout=25)
        except subprocess.TimeoutExpired:r=None
        if r is not None and r.returncode==0 and sock.exists():
            MASTER=common+['-O','exit',host]
            break
        reason = 'PROCESS_TIMEOUT' if r is None else ssh_failure_class(r.stderr)
        print('NOX_MAINT_AUTH_ATTEMPT='+str(attempt+1)+'_RETRY',flush=True)
        print('NOX_MAINT_SSH_FAILURE_CLASS='+reason,flush=True)
        time.sleep(5)
    else:raise RuntimeError('HOLD_SSH_AUTHENTICATION')
    check=_safe_subprocess_run(common+['-O','check',host],capture_output=True,text=True,timeout=8)
    if check.returncode:raise RuntimeError('HOLD_SSH_MASTER_NOT_ALIVE')
    print('NOX_MAINT_AUTHENTICATED_INSTANCE=60509551',flush=True)
    payload=Path(FILES[action]).read_text()
    if action=='audit_gpu_inventory':
        pinned_helpers=(
            ('__NOX_AUDIT_HELPER_B64__','nox-control/pinned/owner_audit_gpu_v1/owner_native_audit.py','e5c439c6733fcb276bec58dbf8af5193694645ac'),
            ('__NOX_GPU_HELPER_B64__','nox-control/pinned/owner_audit_gpu_v1/owner_native_gpu_inventory.py','3a3ff33e7709539d5ff6ab6b8614d694a9d2becb'),
        )
        for placeholder,path,expected_blob in pinned_helpers:
            raw=Path(path).read_bytes()
            header=b'blob '+str(len(raw)).encode('ascii')+bytes([0])
            if len(raw)>256*1024 or hashlib.sha1(header+raw).hexdigest()!=expected_blob:
                raise RuntimeError('HOLD_COMPOSITE_HELPER_SOURCE_PIN')
            if payload.count(placeholder)!=1:
                raise RuntimeError('HOLD_COMPOSITE_HELPER_BUNDLE')
            payload=payload.replace(placeholder,json.dumps(base64.b64encode(raw).decode('ascii')))
    if action == 'lifeline':
        assets={}
        for path in ('nox-control/nox_native_lifeline.py',
                     'nox-control/lifeline.example.json',
                     'nox-control/supervisor/nox-lifeline-guard.conf'):
            source=Path(path)
            if not source.is_file() or source.stat().st_size > 32768:
                raise RuntimeError('HOLD_LIFELINE_SOURCE_SCOPE')
            raw=source.read_bytes()
            assets[source.name]={'content':base64.b64encode(raw).decode('ascii'),
                                 'sha256':__import__('hashlib').sha256(raw).hexdigest()}
        payload=payload.replace('__NOX_BUNDLE_JSON__',json.dumps(assets))
    elif action in ('stage','repair','browser_qa'):
        assets={}
        for path in repair_bundle_paths(action,FILES[action],('nox-control/nox_cold_drive.py','nox-control/owner_native_audit.py',
                     'nox-control/owner_native_inspect.py','nox-control/hybrid_training_entry.py',
                     'nox-control/owner_capacity_probe.py','nox-control/owner_component_tasks.py',
                     'nox-control/owner_dispatcher_mentor.py','nox-control/nox_pc_export.py',
                     'nox-control/owner_chat_probe.py','nox-control/owner_native_repair.py',
                     'nox-control/owner_media_install.py','nox-control/owner_media_runtime.py',
                     'nox-control/owner_chat_source_patch.py','nox-control/owner_chat_stream.py',
                     'nox-control/owner_chat_ui.py','nox-control/owner-chat-ui.js','nox-control/owner-presence.js',
                     'nox-control/owner_event_outbox.py','nox-control/owner_chat_browser_qa.py',
                     'nox-control/owner_task_plans.py','nox-control/owner_task_lifecycle.py',
                     'nox-control/owner_task_lifecycle.json','nox-control/owner_senior_gateway.py',
                     'nox-control/owner_storage_reclaim.py','nox-control/owner_browser_diagnostic.py',
                     'nox-control/owner_storage_remaining_audit.py',
                     'nox-control/owner_s03_diagnostic.py','nox-control/owner_ram_duplicate_reclaim.py',
                     'nox-control/owner_browser_qa_entry.py',
                     'nox-control/owner_s03_prepare_entry.py','nox-control/owner_s03_gateway.py',
                     'nox-control/owner_s03_activate_entry.py','nox-control/owner_adapter_lineage_audit.py',
                     'nox-control/owner_s03_recover_activate.py','nox-control/owner_s03_content_reindex_entry.py',
                     'nox-control/owner_chat_layout_entry.py','nox-control/owner_chat_composer_entry.py',
                     'nox-control/owner_training_failure_probe.py',
                     'nox-control/owner_training_status.py','nox-control/owner_builder_proc_probe.py',
                     'nox-control/owner_builder_drive_public_proof.json',
                     'nox-control/owner_log_selected_size_probe.py','nox-control/owner_log_space_probe.py',
                     'nox-control/owner_browser_runtime_inspect.py',
                     'nox-control/owner_browser_stream_only_entry.py',
                     'nox-control/owner_browser_runtime_repair_entry.py','nox-control/owner_hermes_ram_preflight.py',
                     'nox-control/owner_training_status_entry.py','nox-control/owner_training_status_binding.py',
                     'nox-control/owner_training_amp_calibration.py','nox-control/owner_training_scaler_probe.py',
                     'nox-control/owner_training_placement_recovery.py','nox-control/owner_training_restore_preflight.py',
                     'nox-control/owner_calibration_receipt_read.py','nox-control/owner_chat_runtime_snapshot.py',
                     'nox-control/owner_browser_transport_qa_entry.py','nox-control/owner_chat_browser_transport_qa.py',
                     'nox-control/owner_browser_release_qa_entry.py','nox-control/owner_chat_browser_release_qa.py',
                     'nox-control/owner_chat_stream_only_qa.py',
                     'nox-control/owner_checkpoint_page_action.py',
                     'nox-control/owner_training_source_delta.py',
                     'nox-control/owner_chat_reports_state_entry.py',
                     'nox-control/owner_checkpoint_backup_transport.py','nox-control/owner_checkpoint_backup_export.py',
                     'nox-control/owner_checkpoint_backup_size_probe.py',
                     'nox-control/owner_checkpoint_backup_pager.py','nox-control/owner_checkpoint_backup_pager_entry.py',
                     'nox-control/owner_checkpoint_backup_deflated.py','nox-control/owner_checkpoint_backup_deflated_entry.py',
                     'nox-control/owner_training_restore_probe.py',
                     'nox-control/owner_checkpoint_backup_public_key.json',
                     'nox-control/owner_training_resume.py','nox-control/owner_training_recovery_entry.py',
                     'nox-control/owner_training_config_preflight.py','nox-control/owner_training_disk_guard.py',
                     'nox-control/owner_training_disk_guard_entry.py',
                     'nox-control/owner_training_recovery_chain.py','nox-control/owner_training_jsonl_recovery.py',
                     'nox-control/owner_training_jsonl_observe.py','nox-control/owner_training_recovery_observe.py',
                     'nox-control/owner_training_corpus_probe.py',
                     'nox-control/owner_chat_evidence_entry.py','nox-control/owner_chat_evidence.py',
                     'nox-control/owner_chat_evidence_patch.py',
                     'nox-control/owner_download_status_entry.py','nox-control/owner_download_status.py',
                     'nox-control/owner_capacity_measure_entry.py','nox-control/owner_media_fixture_export.py',
                     'nox-control/owner_media_fixture_transport.py','nox-control/owner_media_fixture_public_key.json',
                     'nox-control/owner_drive_ram_prepare.py','nox-control/owner_drive_ram_bridge.py',
                     'nox-control/owner_drive_ram_assets.json','nox-control/owner_drive_ram_envelope.json',
                     'nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py',
                     'nox_runpod/teacher_mesh/v137/owner_self_observation.py',
                     'nox-control/owner_hermes_qa_batch.py',
                     'nox-control/owner_builder_cold_storage_entry.py',
                     'nox-control/owner_builder_archive_reclaim.py',
                     'nox-control/owner_qwen_disk_rearm_entry.py',
                     'nox-control/owner_builder_cold_location.py',
                     'nox-control/owner_drive_storage_bridge.py',
                     'nox-control/owner_builder_cold_chat_binding.py',
                     'nox-control/owner_hermes_warm_move.py',
                     'nox-control/owner_hermes_hydrate.py',
                     'coordination/onepass/nox-v135-resonance-owner-bridge.js',
                     'coordination/onepass/nox-v137-owner-self-status.js',
                     'nox-control/owner_qwen_training_status_entry.py',
                     'nox-control/owner_qwen_training_status.py',
                     'nox-control/owner_subagent_fresh_install_entry.py',
                     'nox-control/owner_subagent_dispatcher_fresh.py',
                     'nox-control/owner_subagent_hash_recovery_entry.py',
                     'nox-control/owner_subagent_install_entry.py',
                     'nox-control/pinned/qwen_status_v1/owner_qwen_training_observe.py',
                     'nox-control/owner_builder_extent_dedupe.py',
                     'nox-control/owner_qwen_media_handoff.py',
                     'nox-control/owner_media_training_handoff.py',
                     'nox-control/owner_qwen_window_entry.py',
                     'nox-control/owner_qwen_install_entry.py',
                     'nox-control/owner_qwen_guard_install_entry.py',
                     'nox-control/owner_qwen_guard_activate_entry.py',
                     'nox-control/owner_qwen_window_observe_entry.py',
                     'nox-control/owner_qwen_current_observe.py',
                     'nox-control/owner_qwen_execution_revision.py',
                     'nox-control/qwen_student_training_entry_revision.py',
                     'nox-control/owner_qwen_revision_guard.py',
                     'nox-control/owner_qwen_revision_status.py',
                     'nox-control/owner_qwen_revision_media_handoff.py',
                     'nox-control/owner_qwen_revision_media_guard.py',
                     'nox-control/owner_qwen_revision_handback_retry.py',
                     'nox-control/owner_hermes_revision_hydrate.py',
                     'nox-control/owner_qwen_revision_install.py',
                     'nox-control/owner_qwen_revision_rollback.py',
                     'nox-control/owner_qwen_revision_failed_diagnostic.json',
                     'nox-control/owner_qwen_retry_rollback.py',
                     'nox-control/owner_qwen_retry_failed_diagnostic.json',
                     'nox-control/owner_media_acceptance_entry.py',
                     'nox-control/owner_qwen_held_media_smoke.py',
                     'nox-control/owner_qwen_revision_observe.py',
                     'nox-control/owner_qwen_media_retry_observe.py',
                     'nox-control/owner_capacity_current_load_entry.py',
                     'nox-control/owner_qwen_training_guard.py',
                     'nox-control/owner_qwen_media_guard.py',
                     'nox-control/owner_qwen_media_handoff_entry.py',
                     'nox-control/owner_media_inbox_fair.py',
                     'nox-control/owner_media_inbox_fair_entry.py',
                     'nox-control/owner_qwen_handback_retry.py',
                     'nox-control/owner_subagent_instruction_truth.py',
                     'coordination/NOX_STORAGE_STREAMING_20261115/download_manifest.json')):
            p=Path(path)
            if p.is_file():assets[p.name]=base64.b64encode(p.read_bytes()).decode('ascii')
        payload=payload.replace('__NOX_BUNDLE_JSON__',json.dumps(assets))
    sha=os.environ['NOX_PINNED_SOURCE_SHA']
    script=f"set -euo pipefail\nNOX_OWNER_SOURCE_SHA={sha} NOX_OWNER_REQUEST_ID={int(request_id)} python3 - <<'NOX_OWNER_PAYLOAD'\n"+payload+"\nNOX_OWNER_PAYLOAD\n"
    timeout=150 if action in ('audit','inspect','drive_probe','emergency_stop_preflight','audit_gpu_inventory') else 900
    # Reuse the authenticated channel. A dead master must not fall back to
    # a fresh, potentially ambiguous TCP connection while starting a mutation.
    r=_safe_subprocess_run(common+['-o','ControlMaster=no','-o','ProxyCommand=false',host,'bash','-se'],input=script,capture_output=True,text=True,timeout=timeout)
    for line in r.stdout.splitlines():
        if line.startswith('NOX_MAINT_') and len(line)<180000:print(line,flush=True)
    print('NOX_MAINT_REMOTE_EXIT_CODE='+str(r.returncode),flush=True)
    if r.returncode:
        err=r.stderr.lower()
        cls='AUTH' if 'permission denied' in err else 'TIMEOUT' if 'timed out' in err else 'CONNECTION' if 'connect' in err else 'PAYLOAD'
        print('NOX_MAINT_FAILURE_CLASS='+cls,flush=True)
    marker='NOX_MAINT_'+action.upper()+'_COMPLETE=true'
    if r.returncode or marker not in r.stdout:raise RuntimeError('HOLD_NATIVE_PAYLOAD_INCOMPLETE')
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=FILES);args=p.parse_args();good=False
    try:
        request=authorize_event(args.action)
        print('NOX_MAINT_AUTHORIZED_COMMENT_ID='+str(request),flush=True)
        good=run_native(args.action,request)
    except Exception as e:
        code=str(e)
        print('NOX_MAINT_RESULT='+(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_'+type(e).__name__.upper()),flush=True)
    finally:
        if MASTER:
            with contextlib.suppress(Exception):_safe_subprocess_run(MASTER,capture_output=True,timeout=8)
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
        try:
            if not s.cleanup():good=False
        except Exception:print('NOX_MAINT_CLEANUP=HOLD');good=False
        with contextlib.suppress(OSError):s.KEY.unlink()
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
