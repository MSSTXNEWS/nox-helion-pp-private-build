#!/usr/bin/env python3
"""Incremental project-executor installation through the existing owner route.

No model/trainer restart, no historical claim reset, no second task controller.
The approved source package is a local Git workspace with no remote credentials.
The installer returns after actual worker admission; long jobs finish separately.
"""
from __future__ import annotations
import ast
import base64
import copy
import ctypes
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}
SPEC = {'schema': 'NOX_COMPLETE_EXECUTOR_INSTALL_SPEC_V1', 'assets': {'ce_runtime_2c4735938dacd2a062ed.py': '2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102', 'ce_runtime_391e1178dc8a65e8f1bc.py': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'ce_runtime_f6b2f98ac5c7c291ffef.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'ce_runtime_79a4797dfc06776455f6.py': '79a4797dfc06776455f6d530baeabcab5c1cb77f925bac82d2ace740c150d91d', 'ce_runtime_b745dece2bccbf632d26.py': 'b745dece2bccbf632d26c694d664e6b3c6d780b72a395bab4d845ef389437c0a', 'ce_runtime_d0ff44d4752128c26779.py': 'd0ff44d4752128c267799202620c34d2503241dad1f7008f8b3539f49efc18b5', 'ce_runtime_119115603be6dba84121.py': '119115603be6dba84121dc2c9c3460482e85fe59f4e5b2598551bcd62ffbdff1', 'ce_runtime_7f18d69529582b65f7b8.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'ce_runtime_126c77c1281b74676930.py': '126c77c1281b7467693063bfe33d17c89eb0d553a1e8ff112ae058994e0a30ba', 'ce_runtime_7fc312fccf354d01f69a.py': '7fc312fccf354d01f69a65b2090fb6eeaa78b72c2ca479d640dab9c6f1f119a6', 'ce_baseline_bb2c543979ad58801d97.source': 'bb2c543979ad58801d97290e9edf1fe035435c8e9e5f0ebaced4abf3ecbf9053', 'ce_baseline_4d1274059d034bb9b96a.source': '4d1274059d034bb9b96a445e26601d33da54ea309c8a5233df6512a2d546020f', 'ce_baseline_d9ec6a8250a167d774ba.source': 'd9ec6a8250a167d774ba5090219cfaac3ad2995ddd88228d1abe5514fc9dd791', 'ce_baseline_c676fdda4fa47d316eb1.source': 'c676fdda4fa47d316eb10572c5718868a01408d450a5a0d91a7133ff20507799', 'ce_baseline_8657ad367e6dd25b48ca.source': '8657ad367e6dd25b48ca8d6d7c4a947c0e1b0d4b979d63fbdaaf2a8e9ba5e74c', 'ce_baseline_006fc038f43682fa36d2.source': '006fc038f43682fa36d2310f2343c83a42fd28897e7debfbe0d63536ee069729', 'ce_baseline_d35064a3fc5707dfc174.source': 'd35064a3fc5707dfc174852fc4de5030ee6ea2276fd0a4d06850ffff71ee0c64', 'ce_baseline_66a6617d6f582876dbdc.source': '66a6617d6f582876dbdcb9791273c5eca724e3633a65bf1c93ecb4b2f2b14947', 'ce_baseline_e3b0c44298fc1c149afb.source': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'ce_baseline_092db7d32a048c1706da.source': '092db7d32a048c1706da5fc4cf1fcb04a33781e23bbe42252ea14f990985b582', 'ce_baseline_dc19594b45a7fae32bf9.source': 'dc19594b45a7fae32bf9bdde665620c2eec1a29bb02ba03758baa53a8158c509', 'ce_baseline_b4ece67144248808a12c.source': 'b4ece67144248808a12c7c84450d61a919984ad756f6f15b46e0686c6d65ff96', 'ce_baseline_21f8538fec15d39b4dbc.source': '21f8538fec15d39b4dbc875a4087be1c911c60b06ba04e2c682e8810f7b8b8fd', 'ce_baseline_3efe025681c3a54cbfac.source': '3efe025681c3a54cbfac10f0da6f20ff7b2e249ed087b8db39d582002f32c080', 'ce_baseline_b3c5d26011400b110a1b.source': 'b3c5d26011400b110a1b88849c7aebfc0c7d8c636e541f8ab8d89d37ceed0db7', 'ce_baseline_0fff97b7e758e3e43073.source': '0fff97b7e758e3e43073c11ea348b73b60a0d47fc406855ba5f0f748e42b18c5', 'ce_baseline_fd815f9a743bfcdf6e71.source': 'fd815f9a743bfcdf6e71a8ebb035a180c031aa8f0c5e0484164d36aaf309f6cf', 'ce_baseline_97c433b8893514f5812b.source': '97c433b8893514f5812b69fd53b0bb1e25d1fcd7b290f35c72407ad54b989667', 'ce_baseline_fc5d6c564c651c2abc81.source': 'fc5d6c564c651c2abc818005da461711cdfc2c5cedff9146c6db8b12a6037eb5', 'ce_baseline_623bfb4ba2d28d3dd3db.source': '623bfb4ba2d28d3dd3dbc5e46852ed5be5c29d516d20a390aed69c2ec5c3089c', 'ce_baseline_9201bc3629682a577c80.source': '9201bc3629682a577c80a66c1040ef244b82f89b3b2cab26ce06ba3c95db38b2', 'ce_baseline_d6042e38549360ace8f9.source': 'd6042e38549360ace8f9136fc2c36e0c195d54666e0dca34944955bf70e9e9c0', 'ce_baseline_2860173d8d6ed7147af2.source': '2860173d8d6ed7147af2392f82c5fe4df5880ebc781ad359f15dcb30617fc391', 'ce_baseline_970d6681ce5dc57156e2.source': '970d6681ce5dc57156e23746fa8df213eb5746c7a6b19354a0ca864e87830c4f', 'ce_baseline_6aa9265942695d2b54b3.source': '6aa9265942695d2b54b33a0192dc1ebfb912277e86c909eeb4f49a1b45477edd', 'ce_baseline_8d2070c2f0819e7d1c2b.source': '8d2070c2f0819e7d1c2b5cf2bdb5acb0e9a7f1c027a180ba0528e89ead3f894d', 'ce_baseline_60e28219f670a8449a56.source': '60e28219f670a8449a56f6f9ab8641624c424d01447c9d156b1ecf5ce914d1fa', 'ce_plans_283ff826ba1180398888.json': '283ff826ba11803988884e35aa6b20dfa3d658e9887059e2e604f05062f5ad4a', 'ce_blobs_fa3d69e506d727295094.source': 'fa3d69e506d72729509455f2c26b5974bb5dbbb10a0baf295c66aca92e46a9f5', 'ce_plans_e7c99335a4a790202f22.json': 'e7c99335a4a790202f229a41ddd6420cc4f8a0d85765af931e00818eb726b13f', 'ce_blobs_f7b69405224c63868b76.source': 'f7b69405224c63868b767792d68c3b0d73e2561b37216e2e855ca34ec93d5f2f', 'ce_plans_de41f4de77a043c695fe.json': 'de41f4de77a043c695fe12ccb3a60a389c4cd112102a9257dbf1c7b47c25d5eb', 'ce_blobs_7e625acddd71fe95988e.source': '7e625acddd71fe95988e626de71b17f31f992abbfdb3b006e83d4568ce74a03d', 'ce_plans_67e819b4ff1b94cc5bdd.json': '67e819b4ff1b94cc5bdd6547702ce5383f5ea8a0cb42a44428a1b7740c147e09', 'ce_blobs_b980a61884965f4838f8.source': 'b980a61884965f4838f8deafd43dac2ea4642e41dea7870d6a6904ee5a274fc6', 'ce_plans_4037501920f2e9f3ea41.json': '4037501920f2e9f3ea41c9b623b8a2aae1c942edb1308a186b1398c646e7bee7', 'ce_blobs_06940cb13bd568d4cfaa.source': '06940cb13bd568d4cfaa893aab9e43c6d0b03010163cba13f2f5bf5ea144db00', 'ce_plans_9b80e2075b52602ac9e1.json': '9b80e2075b52602ac9e113d9dbe1e2f4458ed555d50abd7623ae5ecb408fb2ee', 'ce_blobs_f336c58fb5062aec6d5b.source': 'f336c58fb5062aec6d5b4d99986adc0386159bc6013f0429cb2dae88daf7eb81', 'ce_contracts_b40696685ca2b7c848a2.json': 'b40696685ca2b7c848a233f2d193d3cb57442d6b1046d2488c7d5b29ac1821b7', 'ce_manifests_a1a62c3b43d63e28f49e.json': 'a1a62c3b43d63e28f49eb4a0794e5efc4898d303c2b6544a597ab2f5626b2618', 'ce_manifests_e040c40bd8ee3d29b0cc.json': 'e040c40bd8ee3d29b0ccc2240322975da37cacff73b3752b32a34d5a2a9beacb'}, 'runtime_paths': {'ce_runtime_2c4735938dacd2a062ed.py': 'scripts/owner_autonomy_pool.py', 'ce_runtime_391e1178dc8a65e8f1bc.py': 'scripts/owner_subagent_dispatcher.py', 'ce_runtime_f6b2f98ac5c7c291ffef.py': 'scripts/owner_subagent_processes.py', 'ce_runtime_79a4797dfc06776455f6.py': 'scripts/owner_project_executor.py', 'ce_runtime_b745dece2bccbf632d26.py': 'scripts/owner_project_test_runner.py', 'ce_runtime_d0ff44d4752128c26779.py': 'scripts/owner_project_native.py', 'ce_runtime_119115603be6dba84121.py': 'scripts/owner_project_model_client.py', 'ce_runtime_7f18d69529582b65f7b8.py': 'scripts/owner_project_model_bridge.py', 'ce_runtime_126c77c1281b74676930.py': 'scripts/owner_project_planner.py', 'ce_runtime_7fc312fccf354d01f69a.py': 'scripts/owner_subagent_instruction_truth.py'}, 'package_files': {'plans/283ff826ba11803988884e35aa6b20dfa3d658e9887059e2e604f05062f5ad4a.json': 'ce_plans_283ff826ba1180398888.json', 'blobs/fa3d69e506d72729509455f2c26b5974bb5dbbb10a0baf295c66aca92e46a9f5': 'ce_blobs_fa3d69e506d727295094.source', 'plans/e7c99335a4a790202f229a41ddd6420cc4f8a0d85765af931e00818eb726b13f.json': 'ce_plans_e7c99335a4a790202f22.json', 'blobs/f7b69405224c63868b767792d68c3b0d73e2561b37216e2e855ca34ec93d5f2f': 'ce_blobs_f7b69405224c63868b76.source', 'plans/de41f4de77a043c695fe12ccb3a60a389c4cd112102a9257dbf1c7b47c25d5eb.json': 'ce_plans_de41f4de77a043c695fe.json', 'blobs/7e625acddd71fe95988e626de71b17f31f992abbfdb3b006e83d4568ce74a03d': 'ce_blobs_7e625acddd71fe95988e.source', 'plans/67e819b4ff1b94cc5bdd6547702ce5383f5ea8a0cb42a44428a1b7740c147e09.json': 'ce_plans_67e819b4ff1b94cc5bdd.json', 'blobs/b980a61884965f4838f8deafd43dac2ea4642e41dea7870d6a6904ee5a274fc6': 'ce_blobs_b980a61884965f4838f8.source', 'plans/4037501920f2e9f3ea41c9b623b8a2aae1c942edb1308a186b1398c646e7bee7.json': 'ce_plans_4037501920f2e9f3ea41.json', 'blobs/06940cb13bd568d4cfaa893aab9e43c6d0b03010163cba13f2f5bf5ea144db00': 'ce_blobs_06940cb13bd568d4cfaa.source', 'plans/9b80e2075b52602ac9e113d9dbe1e2f4458ed555d50abd7623ae5ecb408fb2ee.json': 'ce_plans_9b80e2075b52602ac9e1.json', 'blobs/f336c58fb5062aec6d5b4d99986adc0386159bc6013f0429cb2dae88daf7eb81': 'ce_blobs_f336c58fb5062aec6d5b.source', 'contracts/b40696685ca2b7c848a233f2d193d3cb57442d6b1046d2488c7d5b29ac1821b7.json': 'ce_contracts_b40696685ca2b7c848a2.json', 'manifests/a1a62c3b43d63e28f49eb4a0794e5efc4898d303c2b6544a597ab2f5626b2618.json': 'ce_manifests_a1a62c3b43d63e28f49e.json', 'manifests/e040c40bd8ee3d29b0ccc2240322975da37cacff73b3752b32a34d5a2a9beacb.json': 'ce_manifests_e040c40bd8ee3d29b0cc.json'}, 'expected_native': {'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_subagent_dispatcher.py': '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e', 'scripts/owner_subagent_processes.py': 'c1d5adfcc83300d749b42f66d50f41d5c62c4df52215e43cfc0b891e7c91101b', 'scripts/owner_autonomy_pool.py': '2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102', 'scripts/owner_subagent_instruction_truth.py': 'd03691b84954402558f1e23e1403043eb9c7d115eb57be575524c05502d0529a', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'config/owner_native_subagents.json': 'f283db153b763b8bc8e77dd57fedc3cd091c3a5336f40a6d9c805efbdf95d900'}, 'protected_processes': {'chat': {'pid': 3266857, 'start_ticks': 172046662}, 'proxy': {'pid': 3703386, 'start_ticks': 175609570}, 'web': {'pid': 3505392, 'start_ticks': 173653097}}, 'source_bootstrap': {'schema': 'NOX_PROJECT_SOURCE_BOOTSTRAP_V1', 'root': '/root/nox/projects/owner_executor/source_workspace', 'files': {'forge_split_guard.py': 'ce_baseline_bb2c543979ad58801d97.source', 'merge_web_source.py': 'ce_baseline_4d1274059d034bb9b96a.source', 'native_v29_full_bridge.py': 'ce_baseline_d9ec6a8250a167d774ba.source', 'nox_runpod/teacher_mesh/v38/durable_runtime.py': 'ce_baseline_c676fdda4fa47d316eb1.source', 'nox_runpod/teacher_mesh/v38/synaptic_brain.py': 'ce_baseline_8657ad367e6dd25b48ca.source', 'owner_chat_request_ledger.py': 'ce_baseline_006fc038f43682fa36d2.source', 'owner_dispatcher_mentor.py': 'ce_baseline_d35064a3fc5707dfc174.source', 's03_existing_readback.py': 'ce_baseline_66a6617d6f582876dbdc.source', 'source_tests/__init__.py': 'ce_baseline_e3b0c44298fc1c149afb.source', 'source_tests/test_cache_race.py': 'ce_baseline_092db7d32a048c1706da.source', 'source_tests/test_owner_chat_request_scope.py': 'ce_baseline_dc19594b45a7fae32bf9.source', 'source_tests/test_request_ledger.py': 'ce_baseline_b4ece67144248808a12c.source', 'test_3b05_skill_ancestor_swap.py': 'ce_baseline_21f8538fec15d39b4dbc.source', 'test_forge_split_guard.py': 'ce_baseline_3efe025681c3a54cbfac.source', 'test_nox_1a03_cursor_admission.py': 'ce_baseline_b3c5d26011400b110a1b.source', 'test_nox_existing_cache_race.py': 'ce_baseline_0fff97b7e758e3e43073.source', 'test_nox_forge_split_coverage.py': 'ce_baseline_fd815f9a743bfcdf6e71.source', 'test_nox_merge_overlay_paths.py': 'ce_baseline_97c433b8893514f5812b.source', 'test_nox_s03_readback_revoke.py': 'ce_baseline_fc5d6c564c651c2abc81.source', 'test_nox_skill_evidence_strict_json.py': 'ce_baseline_623bfb4ba2d28d3dd3db.source', 'test_nox_warm_cache_final_revision.py': 'ce_baseline_9201bc3629682a577c80.source', 'test_nox_work_progress_time_order.py': 'ce_baseline_d6042e38549360ace8f9.source', 'test_s03_readback_contract.py': 'ce_baseline_2860173d8d6ed7147af2.source', 'test_work_progress_changes.py': 'ce_baseline_970d6681ce5dc57156e2.source', 'test_work_progress_durable_write.py': 'ce_baseline_6aa9265942695d2b54b3.source', 'test_work_progress_pinned_read.py': 'ce_baseline_8d2070c2f0819e7d1c2b.source', 'work_progress.py': 'ce_baseline_60e28219f670a8449a56.source'}, 'source_refs': [{'repository': 'https://gitlab.com/s-grouptwet/nox-helion-pp-private-build', 'commit': '78ee41fb4ac1e48128fdce2eb25e52d40c70cc15'}, {'repository': 'https://gitlab.com/s-grouptwet/nox-helion-pp-private-build', 'commit': '895c5ed3f5e08b8c473e873aed768ac56e60767f'}], 'manifest_sha256': 'abcde7635a603c8297499d62706d3c3232504f9b3e99446897f13cad25a0a566'}, 'catalog_append': [{'id': '1A03.project.cursor_admission.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q1_RUNTIME_CHAT', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 2, 'title': 'Implement request cursor admission through existing local NOX model and protected source tests', 'params': {'parent_task_id': '1A03', 'contract_sha256': 'b40696685ca2b7c848a233f2d193d3cb57442d6b1046d2488c7d5b29ac1821b7'}}, {'id': '3A02.project.readback_revoke.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 1, 'title': 'Observed owner revocation during connection entry prevents the SQL read.', 'params': {'parent_task_id': '3A02', 'plan_sha256': '283ff826ba11803988884e35aa6b20dfa3d658e9887059e2e604f05062f5ad4a'}}, {'id': '3A03.project.cache_revision_lock.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 1, 'title': 'Final native revision lookup runs outside the cache mutex; revocation completes and fences the result.', 'params': {'parent_task_id': '3A03', 'plan_sha256': 'e7c99335a4a790202f229a41ddd6420cc4f8a0d85765af931e00818eb726b13f'}}, {'id': '6V14-04.project.receipt_time_order.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q1_RUNTIME_CHAT', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 1, 'title': 'Latest receipt ordering compares actual timezone-aware instants before applying the limit.', 'params': {'parent_task_id': '6V14-04', 'plan_sha256': 'de41f4de77a043c695fe12ccb3a60a389c4cd112102a9257dbf1c7b47c25d5eb'}}, {'id': '3B05.project.strict_skill_json.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 1, 'title': 'Duplicate keys and nonfinite JSON cannot certify skill journal or marker evidence.', 'params': {'parent_task_id': '3B05', 'plan_sha256': '67e819b4ff1b94cc5bdd6547702ce5383f5ea8a0cb42a44428a1b7740c147e09'}}, {'id': '4A02.project.forge_split_coverage.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q3_TRAINING_WEIGHTS', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 1, 'title': 'Every independent train/dev/holdout split includes all required task categories.', 'params': {'parent_task_id': '4A02', 'plan_sha256': '4037501920f2e9f3ea41c9b623b8a2aae1c942edb1308a186b1398c646e7bee7'}}, {'id': '0V14-14.project.overlay_paths.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q4_INTEGRATION_ACCEPTANCE', 'source_sha256': '391e1178dc8a65e8f1bc256ce1608dbb5167e0029bd4443b77b000e78d22694b', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 1, 'title': 'Overlay manifest paths cannot escape the output root or import a symlinked foreign source.', 'params': {'parent_task_id': '0V14-14', 'plan_sha256': '9b80e2075b52602ac9e113d9dbe1e2f4458ed555d50abd7623ae5ecb408fb2ee'}}], 'project_executor': {'schema': 'NOX_PROJECT_EXECUTOR_CONFIG_V1', 'enabled': True, 'max_workers': 3, 'package_root': '/root/nox/state/dispatcher/project_executor/package', 'state_root': '/root/nox/state/dispatcher/project_executor/run', 'roots': {'NOX_PROJECT_SOURCE': {'path': '/root/nox/projects/owner_executor/source_workspace', 'integration_kind': 'SOURCE_WORKSPACE', 'allowed_paths': ['forge_split_guard.py', 'merge_web_source.py', 'native_v29_full_bridge.py', 'nox_runpod/teacher_mesh/v38/durable_runtime.py', 'nox_runpod/teacher_mesh/v38/synaptic_brain.py', 'owner_chat_request_ledger.py', 'owner_dispatcher_mentor.py', 's03_existing_readback.py', 'source_tests/__init__.py', 'source_tests/test_cache_race.py', 'source_tests/test_owner_chat_request_scope.py', 'source_tests/test_request_ledger.py', 'test_3b05_skill_ancestor_swap.py', 'test_forge_split_guard.py', 'test_nox_1a03_cursor_admission.py', 'test_nox_existing_cache_race.py', 'test_nox_forge_split_coverage.py', 'test_nox_merge_overlay_paths.py', 'test_nox_s03_readback_revoke.py', 'test_nox_skill_evidence_strict_json.py', 'test_nox_warm_cache_final_revision.py', 'test_nox_work_progress_time_order.py', 'test_s03_readback_contract.py', 'test_work_progress_changes.py', 'test_work_progress_durable_write.py', 'test_work_progress_pinned_read.py', 'work_progress.py'], 'deny_paths': []}}, 'sandbox': {'backend': 'chroot_seccomp', 'python': '/usr/bin/python3.12', 'python_sha256': '1396795801a792fc4a0faa7a47762751e85c76293b4fd925f32c49e27c0f978a', 'stdlib': '/usr/lib/python3.12', 'uid': 65534, 'gid': 65534, 'memory_mb': 256}, 'source_pins': {'owner_project_executor.py': '79a4797dfc06776455f6d530baeabcab5c1cb77f925bac82d2ace740c150d91d', 'owner_project_test_runner.py': 'b745dece2bccbf632d26c694d664e6b3c6d780b72a395bab4d845ef389437c0a'}, 'model': {'expected_model_id': '/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf', 'max_tokens': 900, 'lock_path': '/root/nox/state/dispatcher/project_model_slot.lock', 'source_pins': {'owner_project_model_client.py': '119115603be6dba84121dc2c9c3460482e85fe59f4e5b2598551bcd62ffbdff1', 'owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'owner_project_planner.py': '126c77c1281b7467693063bfe33d17c89eb0d553a1e8ff112ae058994e0a30ba'}}, 'dependency_manifest': {'path': '/root/nox/state/dispatcher/project_executor/package/manifests/a1a62c3b43d63e28f49eb4a0794e5efc4898d303c2b6544a597ab2f5626b2618.json', 'sha256': 'a1a62c3b43d63e28f49eb4a0794e5efc4898d303c2b6544a597ab2f5626b2618'}}, 'startup_observe_seconds': 45}
ROOT = Path('/root/nox')
SERVICE = 'nox-dispatcher-t855u'
CONFIG = 'config/owner_native_subagents.json'
STATE = 'state/dispatcher/state.json'
STATUS = 'status/agents_t856u.json'
MAX_BYTES = 32*1024*1024
SHA = re.compile(r'^[a-f0-9]{64}$')
IDENT = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
QUEUE_IDS = ('Q1_RUNTIME_CHAT','Q2_MEMORY_KNOWLEDGE','Q3_TRAINING_WEIGHTS','Q4_INTEGRATION_ACCEPTANCE')
PROJECT_HANDLER = 'owner_native_project_work'
LEGACY_LEAF_SHA = '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e'
RUNTIME_MODULES = frozenset({
    'owner_autonomy_pool.py','owner_subagent_processes.py','owner_subagent_dispatcher.py',
    'owner_subagent_instruction_truth.py','owner_project_executor.py','owner_project_test_runner.py',
    'owner_project_native.py','owner_project_planner.py','owner_project_model_client.py',
    'owner_project_model_bridge.py',
})

class Hold(RuntimeError):
    pass

def require(condition, code):
    if not condition:
        raise Hold('HOLD_COMPLETE_EXECUTOR_' + code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()

def read_regular(path, maximum=MAX_BYTES):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in
            (path, *path.parents)), 'PATH_SCOPE')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                'FILE_BOUND')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= maximum and (before.st_dev, before.st_ino,
            before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino,
            after.st_size, after.st_mtime_ns), 'FILE_CHANGED')
    return raw

def atomic(path, raw, mode=0o600):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'PATH_SCOPE')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.nox-project-executor-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def preimages(root, expected):
    result = {}
    for relative, pin in expected.items():
        require(SHA.fullmatch(pin) is not None, 'EXPECTED_SOURCE_PIN')
        raw = read_regular(Path(root) / relative)
        require(digest(raw) == pin, 'PREIMAGE_' + Path(relative).name)
        result[relative] = raw
    return result

def apply_transaction(root, changes, before):
    """Compare immediately before each write; roll back only our own bytes."""
    applied = []
    try:
        for relative, raw in changes.items():
            path = Path(root) / relative
            previous = before.get(relative)
            try:
                current = read_regular(path)
            except FileNotFoundError:
                current = None
            require(current == previous, 'CONCURRENT_FILE_CHANGE_' + Path(relative).name)
            applied.append(relative)
            atomic(path, raw, 0o644 if relative.endswith('.py') else 0o600)
            require(read_regular(path) == raw, 'WRITE_READBACK_' + Path(relative).name)
        return applied
    except BaseException:
        rollback_transaction(root, changes, before, applied)
        raise

def rollback_transaction(root, changes, before, applied):
    outcomes = {}
    for relative in reversed(applied):
        path = Path(root) / relative
        try:
            if read_regular(path) != changes[relative]:
                outcomes[relative] = 'FOREIGN_CHANGE_PRESERVED'
            elif before.get(relative) is None:
                # Unreferenced additive files are retained. No existing data is deleted.
                outcomes[relative] = 'ADDITIVE_FILE_RETAINED_UNREFERENCED'
            else:
                atomic(path, before[relative], 0o644 if relative.endswith('.py') else 0o600)
                outcomes[relative] = 'PREIMAGE_RESTORED'
        except (OSError, Hold):
            outcomes[relative] = 'ROLLBACK_IO_FAILED'
    return outcomes

def supervisor(action, name=SERVICE):
    require(name == SERVICE and action in ('status', 'stop', 'start'), 'SUPERVISOR_SCOPE')
    result = subprocess.run(['supervisorctl', action, name], capture_output=True,
                            text=True, timeout=25)
    if action == 'status':
        match = re.fullmatch(re.escape(name) + r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED)\b(?:\s+pid\s+(\d+))?.*',
                             result.stdout.strip())
        require(match is not None, 'SERVICE_STATUS')
        return {'state': match[1], 'pid': int(match[2]) if match[2] else None}
    require(result.returncode == 0, 'SERVICE_' + action.upper())
    return {'action': action, 'rc': result.returncode}

def process_identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        tail = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        if tail[0] not in ('R', 'S', 'D', 'I'):
            return None
        return {'pid': pid, 'start_ticks': int(tail[19]),
                'ppid': int(tail[1]), 'pgrp': int(tail[2])}
    except (OSError, ValueError, IndexError):
        return None

def stop_clear(root):
    names = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
             'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
    return not any(path.exists() or path.is_symlink() for path in
                   [*(Path(root) / name for name in names), Path('/workspace/NOX_STOP')])

def queue_idle(root):
    value = json.loads(read_regular(Path(root) / STATE))
    require(isinstance(value.get('tasks'), dict), 'QUEUE_SCHEMA')
    active = [key for key, row in value['tasks'].items()
              if isinstance(row, dict) and row.get('status') == 'running']
    return value, active

def protected_snapshot(specification):
    result = {}
    for label, expected in specification['protected_processes'].items():
        identity = process_identity(expected['pid'])
        require(identity and identity['start_ticks'] == expected['start_ticks'],
                'PROTECTED_PROCESS_' + label)
        result[label] = identity
    return result

def descendant_snapshot(director_pid, proc_root=Path('/proc')):
    """Bounded exact process census; it authorizes no signals or child kills."""
    require(type(director_pid) is int and director_pid>1,'CHILD_CENSUS_DIRECTOR')
    pending=[director_pid];seen=set();result={}
    while pending:
        parent=pending.pop(0)
        if parent in seen:continue
        seen.add(parent);require(len(seen)<=64,'CHILD_CENSUS_BOUND')
        try:threads=list((Path(proc_root)/str(parent)/'task').iterdir())
        except FileNotFoundError:continue
        require(len(threads)<=128,'CHILD_CENSUS_THREAD_BOUND')
        for thread in threads:
            if not thread.name.isdigit():continue
            try:text=(thread/'children').read_text()
            except FileNotFoundError:continue
            require(len(text)<=4096,'CHILD_CENSUS_OUTPUT_BOUND')
            children=text.split();require(all(x.isdigit() for x in children),'CHILD_CENSUS_SCHEMA')
            for child in map(int,children):
                identity=process_identity(child)
                if identity is None:continue
                require(identity['ppid']==parent,'CHILD_CENSUS_PARENT_CHANGED')
                if child!=director_pid:
                    result[child]=identity;pending.append(child)
    return [result[pid] for pid in sorted(result)]


def live_previous_descendants(previous):
    result=[]
    for old in previous:
        current=process_identity(old['pid'])
        # Reparented old workers still count; a reused PID with new start ticks does not.
        if current and current['start_ticks']==old['start_ticks']:result.append(current)
    return result


def wait_previous_descendants_stopped(previous, timeout=8):
    deadline=time.monotonic()+timeout
    while True:
        remaining=live_previous_descendants(previous)
        if not remaining:return {'observed':len(previous),'all_exact_processes_exited':True}
        require(time.monotonic()<deadline,'OLD_CHILDREN_ALIVE_NO_NATIVE_RESTART')
        time.sleep(.25)


def stop_checked():
    observed = supervisor('status')
    previous = process_identity(observed.get('pid'))
    if observed['state'] not in ('STOPPED', 'FATAL', 'EXITED'):
        try:
            supervisor('stop')
        except (OSError, subprocess.SubprocessError, Hold):
            pass  # The control response is not authoritative; reconcile the actual service.
    deadline = time.monotonic() + 15
    while True:
        current = supervisor('status')
        old_alive = process_identity(previous['pid']) if previous else None
        if (current['state'] in ('STOPPED', 'FATAL', 'EXITED')
                and (old_alive is None or old_alive != previous)):
            return current
        require(time.monotonic() < deadline, 'STOP_NOT_VERIFIED_NO_FILE_ROLLBACK')
        time.sleep(.5)

def start_checked(root, require_native_status=True):
    try:
        supervisor('start')
    except (OSError, subprocess.SubprocessError, Hold):
        pass
    deadline = time.monotonic() + 20
    stable = None
    stable_since = None
    while time.monotonic() < deadline:
        observed = supervisor('status')
        identity = process_identity(observed.get('pid'))
        if observed['state'] == 'RUNNING' and identity:
            loaded = not require_native_status
            try:
                status_doc = json.loads(read_regular(Path(root) / STATUS, 2 * 1024 * 1024))
                native = status_doc.get('native_subexecutors') or {}
                director = native.get('director') or {}
                loaded = (director.get('pid') == identity['pid']
                    and director.get('process_starttime') == identity['start_ticks']
                    and 0 <= time.time() - native.get('observed_at', 0) <= 15)
            except (OSError, ValueError, TypeError, Hold):
                pass
            if loaded:
                if identity != stable:
                    stable, stable_since = identity, time.monotonic()
                elif time.monotonic() - stable_since >= 2:
                    return identity
        elif observed['state'] in ('FATAL', 'EXITED'):
            break
        time.sleep(.5)
    raise Hold('HOLD_COMPLETE_EXECUTOR_STARTUP_NOT_VERIFIED')


def relpath(value):
    require(isinstance(value,str) and 1<=len(value)<=240 and not value.startswith('/')
            and '\\' not in value and '\x00' not in value, 'RELATIVE_PATH')
    pieces=value.split('/')
    require(all(piece not in ('','.','..') and not piece.startswith('.') for piece in pieces), 'RELATIVE_PATH')
    return value


def decode_assets(bundle, specification):
    require(specification.get('schema')=='NOX_COMPLETE_EXECUTOR_INSTALL_SPEC_V1','SPEC_SCHEMA')
    expected=specification.get('assets')
    require(isinstance(expected,dict) and 1<=len(expected)<=512 and set(bundle)==set(expected),'BUNDLE_FILESET')
    result={};total=0
    for name,pin in expected.items():
        require(isinstance(name,str) and '/' not in name and SHA.fullmatch(str(pin)) is not None,'BUNDLE_PIN')
        value=bundle[name]
        require(isinstance(value,str) and len(value)<=4*1024*1024,'BUNDLE_SIZE')
        raw=base64.b64decode(value,validate=True);total+=len(raw)
        require(len(raw)<=2*1024*1024 and total<=32*1024*1024 and digest(raw)==pin,'BUNDLE_DIGEST')
        if name.endswith('.py'):compile(raw,name,'exec')
        result[name]=raw
    return result


def installed_paths(specification, assets):
    paths=specification.get('runtime_paths')
    require(isinstance(paths,dict) and paths,'RUNTIME_FILESET')
    result={}
    for name,relative in paths.items():
        require(name in assets and relpath(relative)=='scripts/'+Path(relative).name
                and Path(relative).name in RUNTIME_MODULES,'RUNTIME_PATH')
        require(relative not in result,'RUNTIME_DUPLICATE_PATH')
        result[relative]=assets[name]
    require({'scripts/owner_subagent_dispatcher.py','scripts/owner_subagent_processes.py',
             'scripts/owner_autonomy_pool.py','scripts/owner_subagent_instruction_truth.py',
             'scripts/owner_project_executor.py','scripts/owner_project_test_runner.py',
             'scripts/owner_project_native.py'}<=set(result),'RUNTIME_REQUIRED_BINDING')
    return result


def package_changes(root, specification, assets):
    base=Path(root)/'state/dispatcher/project_executor/package'
    result={}
    for relative,name in specification.get('package_files',{}).items():
        relative=relpath(relative);pieces=relative.split('/')
        require(len(pieces)==2 and pieces[0] in ('plans','blobs','contracts','manifests')
                and name in assets,'PACKAGE_SCOPE')
        expected=pieces[1][:-5] if pieces[1].endswith('.json') else pieces[1]
        require(SHA.fullmatch(expected) is not None and digest(assets[name])==expected,'PACKAGE_ADDRESS')
        if pieces[0]!='blobs':
            doc=json.loads(assets[name]);require(isinstance(doc,dict),'PACKAGE_DOCUMENT')
        result[str((base/relative).relative_to(root))]=assets[name]
    require(result,'EMPTY_PROJECT_PACKAGE')
    return result


def _git(workspace, args, timeout=15):
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
         'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0',
         'GIT_AUTHOR_NAME':'NOX Owner Executor','GIT_AUTHOR_EMAIL':'nox-owner@localhost',
         'GIT_COMMITTER_NAME':'NOX Owner Executor','GIT_COMMITTER_EMAIL':'nox-owner@localhost'}
    command=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
             '-c','commit.gpgsign=false','-C',str(workspace),*args]
    result=subprocess.run(command,capture_output=True,text=True,timeout=timeout,env=env)
    require(result.returncode==0,'GIT_BOOTSTRAP_'+args[0].upper())
    require(len(result.stdout)<=262144,'GIT_OUTPUT_BOUND')
    return result.stdout.strip()


def publish_directory_no_replace(source, destination):
    libc=ctypes.CDLL(None,use_errno=True)
    function=getattr(libc,'renameat2',None)
    require(function is not None,'DIRECTORY_NOREPLACE_UNAVAILABLE')
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    function.restype=ctypes.c_int
    result=function(-100,os.fsencode(source),-100,os.fsencode(destination),1)
    if result!=0:
        raise Hold('HOLD_COMPLETE_EXECUTOR_DIRECTORY_PUBLISH_'+str(ctypes.get_errno()))
    fd=os.open(Path(destination).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def bootstrap_source(root, specification, assets, request):
    """Only create a fresh approved workspace; never replay its seed over edits."""
    seed=specification.get('source_bootstrap')
    require(isinstance(seed,dict) and seed.get('schema')=='NOX_PROJECT_SOURCE_BOOTSTRAP_V1','SEED_SCHEMA')
    target=Path(root)/'projects/owner_executor/source_workspace'
    require(seed.get('root')==str(target),'SEED_ROOT')
    files=seed.get('files');require(isinstance(files,dict) and 1<=len(files)<=256,'SEED_FILES')
    rows={}
    for relative,name in files.items():
        relative=relpath(relative)
        require(name in assets and relative!='NOX_EXECUTOR_BOOTSTRAP.json','SEED_ASSET')
        rows[relative]=digest(assets[name])
    manifest={'schema':'NOX_PROJECT_SOURCE_BASELINE_V1','files':rows,
              'source_refs':seed.get('source_refs',[])}
    manifest_sha=digest(encoded(manifest))
    require(manifest_sha==seed.get('manifest_sha256'),'SEED_MANIFEST_PIN')
    marker=target/'NOX_EXECUTOR_BOOTSTRAP.json'
    if target.exists() or target.is_symlink():
        previous=json.loads(read_regular(marker,65536))
        require(previous.get('schema')=='NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
                and previous.get('manifest_sha256')==manifest_sha and (target/'.git').is_dir()
                and not (target/'.git').is_symlink(),'EXISTING_WORKSPACE_OWNER')
        # A previous successful job may have changed files; do not re-seed them.
        return {**previous,'reused_without_source_reset':True,
                'current_git_head':_git(target,['rev-parse','HEAD'])}
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    require(not any(p.is_symlink() for p in (target.parent,*target.parent.parents)),'SEED_PARENT')
    stage=Path(tempfile.mkdtemp(prefix='nox-project-seed-'+request+'-',dir=target.parent))
    for relative,name in files.items():atomic(stage/relative,assets[name],0o644)
    _git(stage,['init','--initial-branch=nox-owner-project-source'])
    _git(stage,['add','--',*sorted(files)])
    _git(stage,['commit','-m','Initialize exact owner-approved project source baseline'])
    commit=_git(stage,['rev-parse','HEAD'])
    require(re.fullmatch(r'[a-f0-9]{40}',commit) is not None,'SEED_GIT_COMMIT')
    for relative,name in files.items():require(read_regular(stage/relative)==assets[name],'SEED_READBACK')
    receipt={'schema':'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1','manifest_sha256':manifest_sha,
             'root':str(target),'initial_git_head':commit,'source_file_count':len(files),
             'file_pins':rows,'source_refs':seed.get('source_refs',[]),'request':request,
             'source_scope':'INITIAL_SOURCE_WORKSPACE_NOT_SERVING_DEPLOYMENT',
             'created_at':time.time()}
    atomic(stage/'NOX_EXECUTOR_BOOTSTRAP.json',encoded(receipt))
    publish_directory_no_replace(stage,target)
    require(json.loads(read_regular(marker,65536))==receipt,'SEED_RECEIPT_READBACK')
    return receipt


def prepare_config(raw, runtime_changes, specification, root, request, source):
    config=json.loads(raw)
    require(config.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and config.get('instance_id')==60509551
            and config.get('owner_authorized') is True and config.get('mode')=='NORMAL'
            and config.get('target')==3,'EXISTING_CONFIG')
    catalog=copy.deepcopy(config.get('catalog'))
    require(isinstance(catalog,dict) and catalog.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1'
            and isinstance(catalog.get('tasks'),list) and digest(encoded(catalog))==config.get('catalog_sha256'),'EXISTING_CATALOG')
    before_rows=copy.deepcopy(catalog['tasks']);existing={row['id'] for row in before_rows}
    require(len(existing)==len(before_rows),'EXISTING_CATALOG_DUPLICATE')
    new=copy.deepcopy(specification.get('catalog_append'))
    require(isinstance(new,list) and 1<=len(new)<=295,'NEW_CATALOG_SIZE')
    callback=digest(runtime_changes['scripts/owner_subagent_dispatcher.py'])
    new_ids=set()
    package=specification.get('package_files',{})
    for row in new:
        tid=row.get('id');params=row.get('params')
        require(isinstance(tid,str) and IDENT.fullmatch(tid) and tid not in existing|new_ids
                and row.get('handler')==PROJECT_HANDLER and row.get('queue_id') in QUEUE_IDS
                and row.get('source_sha256')==callback and row.get('resource')=='CPU_LIGHT'
                and isinstance(row.get('deps'),list) and isinstance(params,dict),'NEW_CATALOG_SCOPE')
        require(set(params)<={'parent_task_id','plan_sha256','contract_sha256'}
                and isinstance(params.get('parent_task_id'),str)
                and tid.startswith(params['parent_task_id']+'.')
                and ('plan_sha256' in params or 'contract_sha256' in params),'PROJECT_REFERENCE')
        for key,directory in (('plan_sha256','plans'),('contract_sha256','contracts')):
            if key in params:
                pin=params[key];require(SHA.fullmatch(str(pin)) is not None
                    and directory+'/'+pin+'.json' in package,'PROJECT_REFERENCE_PIN')
        new_ids.add(tid)
    known=existing|new_ids
    require(all(all(dep in known and dep!=row['id'] for dep in row['deps']) for row in new),'PROJECT_DEPENDENCY')
    # New rows must be a DAG; already-existing success dependencies stay native-owned.
    remaining={row['id']:set(dep for dep in row['deps'] if dep in new_ids) for row in new}
    while remaining:
        ready={key for key,deps in remaining.items() if not deps}
        require(ready,'PROJECT_DEPENDENCY_CYCLE')
        remaining={key:deps-ready for key,deps in remaining.items() if key not in ready}
    project=copy.deepcopy(specification.get('project_executor'))
    require(isinstance(project,dict) and project.get('schema')=='NOX_PROJECT_EXECUTOR_CONFIG_V1'
            and project.get('enabled') is True and project.get('max_workers')==3,'PROJECT_CONFIG')
    require(project.get('package_root')==str(Path(root)/'state/dispatcher/project_executor/package')
            and project.get('state_root')==str(Path(root)/'state/dispatcher/project_executor/run'),'PROJECT_CONFIG_ROOTS')
    roots=project.get('roots')
    require(isinstance(roots,dict) and set(roots)=={'NOX_PROJECT_SOURCE'}
            and roots['NOX_PROJECT_SOURCE'].get('path')==str(Path(root)/'projects/owner_executor/source_workspace')
            and roots['NOX_PROJECT_SOURCE'].get('integration_kind')=='SOURCE_WORKSPACE','PROJECT_SOURCE_ROOT')
    pins=project.get('source_pins')
    require(isinstance(pins,dict),'PROJECT_SOURCE_PINS')
    for name in ('owner_project_executor.py','owner_project_test_runner.py'):
        require(pins.get(name)==digest(runtime_changes['scripts/'+name]),'PROJECT_SOURCE_PIN_'+name)
    config.update(execution_mode='NATIVE_PROJECT_V1',project_executor=project,
                  owner_request=request,owner_source_sha=source,global_worker_cap=3)
    for relative,raw_source in runtime_changes.items():
        if relative.startswith('scripts/'):
            config.setdefault('module_pins',{})[Path(relative).name]=digest(raw_source)
    historical=set(config.get('historical_leaf_source_sha256',[]));historical.add(LEGACY_LEAF_SHA)
    require(all(SHA.fullmatch(str(pin)) is not None for pin in historical),'HISTORICAL_PIN')
    config['historical_leaf_source_sha256']=sorted(historical)
    catalog['tasks'].extend(new);config['catalog']=catalog;config['catalog_sha256']=digest(encoded(catalog))
    require(config['catalog']['tasks'][:len(before_rows)]==before_rows,'HISTORICAL_CATALOG_CHANGED')
    return encoded(config)


def preservation(root, baseline):
    current,_=queue_idle(root);old=baseline['tasks'];new=current['tasks']
    missing=sorted(set(old)-set(new))
    historical={key:row for key,row in old.items() if row.get('status') in ('done','failed','blocked')}
    changed=[key for key,row in historical.items()
             if any(row.get(field)!=new.get(key,{}).get(field) for field in ('owner_claim','result'))]
    return {'original_ids':len(old),'missing_original_ids':missing,
            'historical_claim_receipt_entries':len(historical),
            'changed_historical_claim_receipt_ids':changed,
            'new_ids':sorted(set(new)-set(old)),'verified':not missing and not changed}


def acceptance_snapshot(root, task_ids):
    status=json.loads(read_regular(Path(root)/STATUS,2*1024*1024));native=status.get('native_subexecutors') or {}
    director=supervisor('status');observed=process_identity(director.get('pid'))
    workers=[]
    for row in native.get('workers',[])[:10]:
        identity=process_identity(row.get('pid'))
        if (observed and identity and identity['ppid']==observed['pid']
                and identity['start_ticks']==row.get('process_starttime')
                and type(row.get('heartbeat_at')) in (int,float)
                and 0<=time.time()-row['heartbeat_at']<=30):
            workers.append({**identity,'role':row.get('role'),'current_task':row.get('current_task'),
                            'heartbeat_at':row.get('heartbeat_at')})
    state,_=queue_idle(root)
    tasks=[{'id':tid,'status':state['tasks'].get(tid,{}).get('status','not_admitted'),
            'claim_present':bool(state['tasks'].get(tid,{}).get('owner_claim'))} for tid in task_ids]
    return {'director':observed,'workers':workers,'tasks':tasks,'observed_at':time.time(),
            'native_last_admission':native.get('last_admission')}


def save_receipt(root, request, receipt):
    path=Path(root)/'state/dispatcher'/('complete_executor_install_'+request+'.json')
    raw=encoded(receipt);atomic(path,raw)
    require(read_regular(path)==raw,'RECEIPT_READBACK')
    print('NOX_MAINT_COMPLETE_EXECUTOR_INSTALL='+raw.decode(),flush=True)


PREFLIGHT_BASE = b'def value():\n    return 1\n'
PREFLIGHT_PATCH = b'def value():\n    return 2\n'
PREFLIGHT_TEST = b'''import asyncio
import sqlite3
import threading
import unittest
import httpx
from fastapi import FastAPI
import source

class NativePreflight(unittest.TestCase):
    def test_source_patch(self):
        self.assertEqual(source.value(), 2)
    def test_asgi_dependencies(self):
        app = FastAPI()
        @app.get('/probe')
        async def probe():
            return {'probe': 2}
        async def check():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture.local') as client:
                response = await client.get('/probe')
                self.assertEqual(response.json(), {'probe': 2})
        asyncio.run(check())
    def test_sqlite_extension(self):
        with sqlite3.connect(':memory:') as connection:
            self.assertEqual(connection.execute('select 2').fetchone(), (2,))
    def test_thread_allowed(self):
        result = []
        thread = threading.Thread(target=lambda: result.append(2))
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [2])
'''


def sandbox_preflight(root, runtime, package, project, request):
    """Run only a fixed fixture with pinned modules before any live-code write."""
    require(project.get('sandbox',{}).get('backend')=='chroot_seccomp','NATIVE_SANDBOX_BACKEND')
    require(project['sandbox'].get('uid')==65534 and project['sandbox'].get('gid')==65534,
            'NATIVE_SANDBOX_IDENTITY')
    stage=Path(root)/'state/dispatcher/complete_executor_preflight'/request
    require(not stage.exists() and not stage.is_symlink(),'PREFLIGHT_ALREADY_EXISTS')
    require(not any(p.is_symlink() for p in stage.parents),'PREFLIGHT_PATH')
    stage.mkdir(parents=True,mode=0o700)
    module_dir=stage/'modules';module_dir.mkdir(mode=0o700)
    for name in ('owner_project_executor.py','owner_project_test_runner.py'):
        raw=runtime['scripts/'+name]
        require(digest(raw)==project['source_pins'][name],'PREFLIGHT_SOURCE_PIN')
        atomic(module_dir/name,raw,0o644)
    fixture=stage/'source';fixture.mkdir(mode=0o700)
    atomic(fixture/'source.py',PREFLIGHT_BASE,0o644)
    atomic(fixture/'test_source.py',PREFLIGHT_TEST,0o644)
    config=copy.deepcopy(project)
    config.update(package_root=str(stage/'package'),state_root=str(stage/'run'),
                  roots={'PREFLIGHT_SOURCE':{'path':str(fixture),
                    'integration_kind':'SOURCE_WORKSPACE',
                    'allowed_paths':['source.py','test_source.py'],'deny_paths':[]}})
    dependency=config.get('dependency_manifest')
    require(isinstance(dependency,dict) and set(dependency)=={'path','sha256'},'PREFLIGHT_DEPENDENCY_REQUIRED')
    dependency_path=Path(dependency['path'])
    require(dependency_path.is_absolute() and dependency_path.is_relative_to(Path(root)/'state/dispatcher/project_executor/package/manifests'),
            'PREFLIGHT_DEPENDENCY_PATH')
    relative=str(dependency_path.relative_to(root))
    raw=package.get(relative)
    require(isinstance(raw,bytes) and digest(raw)==dependency['sha256'],'PREFLIGHT_DEPENDENCY_PIN')
    manifest_path=stage/'dependency-manifest.json';atomic(manifest_path,raw)
    config['dependency_manifest']={'path':str(manifest_path),'sha256':dependency['sha256']}
    loader=importlib.util.spec_from_file_location('_nox_approved_project_executor_preflight',module_dir/'owner_project_executor.py')
    require(loader is not None and loader.loader is not None,'PREFLIGHT_LOADER')
    executor=importlib.util.module_from_spec(loader);loader.loader.exec_module(executor)
    plan={'schema':'NOX_PROJECT_WORK_PLAN_V1','task_id':'NATIVE-PREFLIGHT.source.1',
          'parent_task_id':'NATIVE-PREFLIGHT','queue_id':'Q4_INTEGRATION_ACCEPTANCE',
          'root_id':'PREFLIGHT_SOURCE','operation':'apply_reviewed_files','review_origin':'OWNER_REVIEWED',
          'context':[{'path':'source.py','sha256':digest(PREFLIGHT_BASE)},
                     {'path':'test_source.py','sha256':digest(PREFLIGHT_TEST)}],
          'files':[{'path':'source.py','before_sha256':digest(PREFLIGHT_BASE),
                    'after_sha256':digest(PREFLIGHT_PATCH),'payload_sha256':digest(PREFLIGHT_PATCH)}],
          'verification':{'kind':'python_unittest','modules':['test_source'],'min_tests':4,'timeout_sec':45},
          'acceptance_scope':'SOURCE_PATCH_TESTED','original_task_accepted':False}
    reference=executor.materialize_plan(plan,{digest(PREFLIGHT_PATCH):PREFLIGHT_PATCH},config)
    result=executor.prepare(reference,config,digest(('preflight:'+request).encode())[:24],
                            stop_check=lambda:not stop_clear(root))
    evidence=result.get('project_evidence') or {};tests=evidence.get('tests') or {};facts=tests.get('sandbox') or {}
    summary={'schema':'NOX_NATIVE_PROJECT_SANDBOX_PREFLIGHT_V1','state':result.get('state'),
             'tests_run':result.get('tests_run'),'sandbox':facts,'reason':evidence.get('reason'),
             'dependency_manifest_sha256':dependency['sha256'],
             'runtime_source_pins':config['source_pins'],'evidence_sha256':result.get('project_evidence_sha256'),
             'source_unchanged':read_regular(fixture/'source.py')==PREFLIGHT_BASE,
             'fixture_only':True,'business_task_completed':False,'model_inference_called':False,
             'original_task_accepted':False,'path':str(stage),'at':time.time()}
    atomic(stage/'preflight_receipt.json',encoded(summary))
    print('NOX_MAINT_COMPLETE_EXECUTOR_PREFLIGHT='+encoded(summary).decode(),flush=True)
    require(result.get('state')=='PREPARED' and result.get('passed') is True
            and result.get('sandbox_verified') is True and result.get('trusted_tests_unchanged') is True
            and result.get('tests_run')==4 and tests.get('passed') is True
            and tests.get('failures')==0 and tests.get('errors')==0 and tests.get('skipped')==0
            and facts.get('uid')==65534 and facts.get('gid')==65534
            and all(facts.get(key) is True for key in ('network_denied','fork_denied','exec_denied',
                'host_path_hidden','no_new_privs','seccomp_filter'))
            and summary['source_unchanged'],'NATIVE_SANDBOX_PREFLIGHT_FAILED')
    return summary


def stable_three(snapshots):
    if len(snapshots)!=2:return False
    a,b=snapshots
    identity=lambda row:(row['pid'],row['start_ticks'],row['ppid'])
    if (len(a.get('workers',[]))!=3 or len(b.get('workers',[]))!=3
            or not a.get('director') or a['director']!=b.get('director')):return False
    old={identity(row):row for row in a['workers']};new={identity(row):row for row in b['workers']}
    if len(old)!=3 or set(old)!=set(new):return False
    return (b['observed_at']-a['observed_at']>=1
            and all(new[key]['heartbeat_at']>old[key]['heartbeat_at'] for key in old))


def install(bundle, specification, root=ROOT):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[a-f0-9]{40}',source),'OWNER_CONTEXT')
    root=Path(root);assets=decode_assets(bundle,specification)
    runtime=installed_paths(specification,assets);package=package_changes(root,specification,assets)
    before=preimages(root,specification['expected_native'])
    require(CONFIG in before,'CONFIG_PREIMAGE_REQUIRED')
    config=prepare_config(before[CONFIG],runtime,specification,root,request,source)
    changes={**runtime,**package,CONFIG:config}
    for relative in changes:
        if relative not in before:
            try:previous=read_regular(root/relative)
            except FileNotFoundError:previous=None
            require(previous is None or previous==changes[relative],'UNPINNED_EXISTING_PATH_'+Path(relative).name)
            before[relative]=previous
    require(stop_clear(root),'OWNER_STOP')
    protected=protected_snapshot(specification)
    lockpath=root/'state/owner_maintenance.lock'
    require(not lockpath.is_symlink(),'MAINTENANCE_LOCK_PATH')
    fd=os.open(lockpath,os.O_RDWR|os.O_NOFOLLOW)
    applied=[];final_baseline=None;old_descendants=[];receipt={'schema':'NOX_COMPLETE_EXECUTOR_INSTALL_V1',
        'request':request,'source_sha':source,'state':'PREFLIGHT','started_at':time.time(),
        'training_started':False,'model_restarted':False,'original_tasks_accepted':0}
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise Hold('HOLD_COMPLETE_EXECUTOR_MAINTENANCE_BUSY') from exc
        preimages(root,specification['expected_native']);require(stop_clear(root),'OWNER_STOP_CHANGED')
        receipt['native_sandbox_preflight']=sandbox_preflight(root,runtime,package,
                json.loads(config)['project_executor'],request)
        require(stop_clear(root),'OWNER_STOP_AFTER_PREFLIGHT')
        require(protected_snapshot(specification)==protected,'PROTECTED_CHANGED')
        deadline=time.monotonic()+40
        while True:
            original,active=queue_idle(root)
            if not active:break
            require(time.monotonic()<deadline,'ACTIVE_CLAIMS_NOT_DRAINED');time.sleep(.5)
        running=supervisor('status');previous=process_identity(running.get('pid'))
        require(running['state']=='RUNNING' and previous,'ORIGINAL_DIRECTOR')
        require(protected_snapshot(specification)==protected,'PROTECTED_CHANGED')
        backup=root/'state/dispatcher/complete_executor_rollback'/request
        require(not backup.exists(),'BACKUP_EXISTS');backup.mkdir(parents=True,mode=0o700)
        for relative,raw in before.items():
            if raw is not None and relative in changes:atomic(backup/relative,raw)
        atomic(backup/'original_queue_snapshot.json',encoded(original))
        receipt.update(previous_director=previous,backup_path=str(backup))
        # Bootstrap contains approved source only and is unreferenced by the old config.
        receipt['source_bootstrap']=bootstrap_source(root,specification,assets,request)
        old_descendants=descendant_snapshot(previous['pid'])
        receipt['previous_descendants']=old_descendants
        stop_checked();require(process_identity(previous['pid']) is None,'OLD_DIRECTOR_ALIVE')
        receipt['previous_descendants_stopped']=wait_previous_descendants_stopped(old_descendants)
        require(stop_clear(root),'OWNER_STOP_AFTER_DRAIN')
        final_baseline,active=queue_idle(root);require(not active,'ACTIVE_CLAIM_AFTER_STOP')
        atomic(backup/'final_stopped_queue_snapshot.json',encoded(final_baseline))
        receipt['final_stopped_queue_sha256']=digest(encoded(final_baseline))
        require(protected_snapshot(specification)==protected,'PROTECTED_CHANGED')
        applied=apply_transaction(root,changes,before)
        require(stop_clear(root),'OWNER_STOP_BEFORE_START')
        receipt['new_director']=start_checked(root)
        require(protected_snapshot(specification)==protected,'PROTECTED_CHANGED')
        receipt.update(state='INSTALLED_NATIVE_ADMISSION_PENDING',
                       installed_files={name:digest(raw) for name,raw in changes.items()},
                       protected_processes=protected)
    except BaseException as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_COMPLETE_EXECUTOR_INSTALL_EXCEPTION'
        try:
            observed=supervisor('status');stopped=observed['state'] in ('STOPPED','FATAL','EXITED')
            if applied:
                stop_checked();stopped=True
                receipt['rollback']=rollback_transaction(root,changes,before,applied)
            if stopped and stop_clear(root):
                require(not live_previous_descendants(old_descendants),'OLD_CHILDREN_ALIVE_NO_NATIVE_RESTART')
                require(all(raw is None or read_regular(root/name)==raw for name,raw in before.items() if name in changes),'ROLLBACK_NOT_VERIFIED')
                receipt['restored_director']=start_checked(root)
                receipt['restart_original']='RUNNING_VERIFIED'
        except Exception as recovery:
            receipt['recovery']=str(recovery) if isinstance(recovery,Hold) else 'HOLD_RECOVERY_UNVERIFIED'
        receipt['finished_at']=time.time();save_receipt(root,request,receipt);raise
    finally:os.close(fd)
    # Long real jobs continue through the original dispatcher. Do not wait for
    # model/test completion or run the four previous diagnostic leaves again.
    ids=[row['id'] for row in specification['catalog_append']]
    snapshots=[];last=None;deadline=time.monotonic()+min(45,max(10,specification.get('startup_observe_seconds',30)))
    try:
        while time.monotonic()<deadline:
            require(stop_clear(root),'OWNER_STOP_DURING_ADMISSION')
            require(protected_snapshot(specification)==protected,'PROTECTED_CHANGED')
            try:
                last=acceptance_snapshot(root,ids)
                if len(last['workers'])==len({row['pid'] for row in last['workers']})==3:
                    snapshots.append(last)
                    if len(snapshots)>2:snapshots=[snapshots[0],snapshots[-1]]
                    if len(snapshots)==2:
                        if stable_three(snapshots) and any(row['claim_present'] for row in last['tasks']):break
            except (OSError,ValueError,TypeError,Hold):pass
            time.sleep(2)
        receipt.update(readback=last,process_snapshots=snapshots,
                       queue_preservation=preservation(root,final_baseline))
        live3=bool(last and stable_three(snapshots) and last is snapshots[-1])
        admitted=bool(last and any(row['claim_present'] for row in last['tasks']))
        running=bool(last and any(row['status']=='running' for row in last['tasks']))
        receipt['three_live_workers_verified']=live3
        receipt['state']=('INSTALLED_WORK_RUNNING' if live3 and admitted and running else
                          'INSTALLED_WORK_ADMITTED' if live3 and admitted else
                          'INSTALLED_WORK_PENDING_ADMISSION')
        require(receipt['queue_preservation']['verified'],'QUEUE_PRESERVATION_FAILED')
    except (OSError,ValueError,TypeError,Hold) as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_COMPLETE_EXECUTOR_ADMISSION_READBACK'
        receipt['readback']=last;receipt['process_snapshots']=snapshots
    receipt['finished_at']=time.time();save_receipt(root,request,receipt)
    return receipt


def main():
    try:install(BUNDLE,SPEC)
    except Exception as exc:
        value=str(exc) if isinstance(exc,Hold) else type(exc).__name__
        print('NOX_MAINT_COMPLETE_EXECUTOR_ERROR='+json.dumps({'error':value[:240]}),flush=True)
        raise
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)


if __name__=='__main__':main()
