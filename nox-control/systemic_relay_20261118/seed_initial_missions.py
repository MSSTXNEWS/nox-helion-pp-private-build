"""Build the first reviewed relay batch from the observed existing source census.

Local package generation only. All target and verification files already exist
in the authorized workspace; no source file, test, queue or native process is
changed here. The observed census is context until the native installer rechecks
its exact pins under its existing owner lease.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from owner_systemic_taskpack import parent_registry, bind_missions, write_package, _publish_local
from runtime.owner_systemic_refill import canonical, digest, SCHEMA, validate_manifest


def build(census_report, disposition, output):
    observed = census_report['NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS'][-1]
    if (observed.get('state') != 'CENSUS_OBSERVED' or observed.get('allowed_file_count') != 33
            or not observed.get('complete_allowed_files_read') or not observed.get('two_reads_match')):
        raise ValueError('HOLD_INITIAL_SOURCE_CENSUS')
    roots = {'NOX_PROJECT_SOURCE':{path:row['sha256'] for path,row in observed['files'].items()}}
    pins = roots['NOX_PROJECT_SOURCE']
    registry = parent_registry(disposition)
    cache = 'nox_runpod/teacher_mesh/v38/durable_runtime.py'
    forge, mentor = 'forge_split_guard.py', 'owner_dispatcher_mentor.py'
    common = {'revision':1,'priority':'P1','root_id':'NOX_PROJECT_SOURCE',
        'repeat_policy':'ONCE_PER_REVIEWED_REVISION','allowed_new_paths':[],'dependencies':[],
        'experience':[{'id':'c02_unchanged_read_failure',
            'lesson':'A prior C02 model attempt made 10 source reads, no patch and no test attempt; the host stopped repeated actions without progress. Use the supplied focus and current hashes to make a bounded edit before requesting further unchanged source.',
            'evidence_sha256':'399e3dc5f153ac8832dfb41d74fead6b30f76f2be5257820af39a6e86dea7599'}],
        'budget':{'lane':'model','max_model_turns':24,'cpu_seconds':120,
                  'max_searches':0,'max_output_bytes':98304}}
    proposals = [
        {**common,'mission_id':'cache_fill_ttl','parent_task_id':'3A03','queue_id':'Q2_MEMORY_KNOWLEDGE',
         'title':'Start cache TTL after successful recall and final revision validation',
         'instruction':
            'Fix WarmS03Cache._read: its insertion deadline currently uses now captured before '
            'recall and final revision callbacks. A slow successful fill is inserted already expired. '
            'Compute insertion expiry from a fresh time.monotonic() inside the insertion lock, after '
            'final revision validation. Keep the existing expiry check on cache lookup. Preserve '
            'revocation tickets, callbacks outside the lock, deep-copy isolation, scope/revision/limit '
            'keys and byte accounting. Change only the editable source; keep all tests immutable. '
            'Use the supplied focus directly, make the small code edit, then run the existing verifier. '
            'This is a source patch; do not claim original 3A03 or live S03 acceptance.',
         'context_paths':[cache,'nox_runpod/teacher_mesh/v38/synaptic_brain.py',
            'source_tests/__init__.py','source_tests/test_cache_race.py',
            'test_nox_existing_cache_race.py','test_nox_warm_cache_final_revision.py',
            'test_nox_warm_cache_limit_contract.py'],
         'editable_paths':[cache],
         'verification':{'kind':'python_unittest','modules':['test_nox_warm_cache_limit_contract',
            'test_nox_existing_cache_race','test_nox_warm_cache_final_revision'],
            'min_tests':16,'timeout_sec':120},
         'focus_regions':[
            {'path':cache,'start_anchor':'        now=time.monotonic()',
             'end_anchor':"        self.stats['misses']+=1"},
            {'path':cache,'start_anchor':"        self.stats['misses']+=1",
             'end_anchor':'class DurablePorts:'}],
         'defect':{'observed_source_sha256':pins[cache],
            'finding':'The same pre-callback monotonic timestamp is used for cache lookup and later fill expiry.',
            'expected_delta':'A successful delayed fill receives its configured TTL from insertion; existing revoke and revision fences remain intact.',
            'verification_limit':'The 16 existing immutable tests cover prior cache regressions. No new targeted TTL test is added or run; the actual source diff also needs review. No full original-task or live-deployment acceptance.'}},
        {**common,'mission_id':'forge_read_budget','parent_task_id':'4A02','queue_id':'Q3_TRAINING_WEIGHTS',
         'title':'Bound split validation by observed bytes and declared row count',
         'instruction':
            'Fix validate() split-file reads. The loop currently reads until EOF and checks declared '
            'row count only afterward. Bound total bytes consumed to the initial fstat size plus at '
            'most one detection byte; stop on growth or extra rows before parsing another JSON row. '
            'Keep per-line bounds, descriptor identity checks, exact SHA/row validation and every '
            'duplicate, license, source URL and RU/ES task coverage rule. Valid stable corpora must '
            'retain their existing output. Change only forge_split_guard.py and use the existing '
            'immutable verifier. Do not start training or claim dataset provenance or original 4A02 '
            'acceptance. The supplied focus contains the relevant loop and counters.',
         'context_paths':[forge,'test_forge_split_guard.py','test_nox_forge_split_coverage.py',
                          'test_nox_forge_language_task_coverage.py'],
         'editable_paths':[forge],
         'verification':{'kind':'python_unittest','modules':['test_forge_split_guard',
            'test_nox_forge_split_coverage','test_nox_forge_language_task_coverage'],
            'min_tests':39,'timeout_sec':120},
         'focus_regions':[
            {'path':forge,'start_anchor':'        fd = os.open(candidate, flags)',
             'end_anchor':'                    row = json.loads(raw'},
            {'path':forge,'start_anchor':'                    coverage[split]["rows"] += 1',
             'end_anchor':'            if (before.st_dev'}],
         'defect':{'observed_source_sha256':pins[forge],
            'finding':'readline has a line limit, but the split loop has no total read budget and checks excessive row count only after EOF.',
            'expected_delta':'Reject growing or excessive-row input with finite work before parsing beyond the pinned size or declared row count, preserving stable-corpus semantics.',
            'verification_limit':'The 39 existing immutable tests cover split integrity and coverage. No new growth test is added or run; source review must verify the loop budget. No native training or complete original-task acceptance.'}},
        {**common,'mission_id':'skill_journal_budget','parent_task_id':'3B05','queue_id':'Q2_MEMORY_KNOWLEDGE',
         'title':'Bound actual skill journal and marker reads',
         'instruction':
            'Fix read_verified_skill_rankings: journal iteration and marker mf.read() can consume '
            'unbounded growing input after the initial size check. Replace them with bounded reads: '
            'at most the initial journal size plus one detection byte, each line at most 1 MiB plus '
            'one detection byte, each marker at most 4096 plus one detection byte. Reject oversize, '
            'growth or changed identity with the existing HOLD states. Preserve descriptor-safe '
            'ancestor handling, shared lock, strict JSON, receipt/marker matching, deduplication '
            'and ranking behavior for stable valid inputs. Change only owner_dispatcher_mentor.py, '
            'keep tests immutable and run its existing verifier. This does not accept original '
            '3B05 or prove LongMemEval performance.',
         'context_paths':[mentor,'test_nox_skill_evidence_strict_json.py',
                          'test_3b05_skill_ancestor_swap.py'],
         'editable_paths':[mentor],
         'verification':{'kind':'python_unittest','modules':['test_nox_skill_evidence_strict_json',
            'test_3b05_skill_ancestor_swap'],'min_tests':10,'timeout_sec':120},
         'focus_regions':[
            {'path':mentor,'start_anchor':"        with os.fdopen(fd, 'rb') as journal_file:",
             'end_anchor':'                try:\n                    record = _skill_evidence_json(line)'},
            {'path':mentor,'start_anchor':"                with os.fdopen(mfd, 'rb') as mf:",
             'end_anchor':'        ranked = []'}],
         'defect':{'observed_source_sha256':pins[mentor],
            'finding':'Journal for-line iteration and unbounded marker read rely on a size check before the read; concurrent growth defeats the actual allocation/work bound.',
            'expected_delta':'Enforce cumulative and per-read limits before JSON parsing, with unchanged ranking and privacy behavior for stable input.',
            'verification_limit':'The 10 existing immutable tests cover strict evidence JSON and ancestor replacement. No new growing-file test is added or run; actual diff needs read-budget review. No original 3B05 acceptance.'}}
    ]
    census = {'schema':'NOX_SYSTEMIC_SOURCE_CENSUS_V1','roots':roots,
        'observed_config_sha256':observed['config_sha256'],
        'observed_files_sha256':observed['files_sha256'],
        'observed_run_id':'44348913250','current_cas_recheck_required':True,
        'atomic_snapshot':False,'original_task_accepted':False}
    topics = [
        {'parent_task_id':'0V14-02','objective':'Use existing authoritative queue outcomes to identify a concrete priority or starvation defect; bind any next patch to its current source and existing immutable verification.'},
        {'parent_task_id':'6B01','objective':'Find measured CPU/IO or model-slot waste affecting existing S03/chat priority. Propose only a source-scoped correction with bounded resource evidence; do not change native limits from a research result.'},
        {'parent_task_id':'3B04','objective':'Identify a bounded memory-consolidation improvement from actual S03/brain source and verified experience, distinguishing observed knowledge from model hypotheses.'},
        {'parent_task_id':'4V14-24','objective':'Derive one reusable lesson from a durable executor receipt and observed postimage, link its evidence hash, and prioritize a concrete uncompleted source defect without repeating the same mission/input.'},
        {'parent_task_id':'4V14-04','objective':'Research primary sources for a concrete existing code defect; compare applicability and integration cost before preparing the next pinned source proposal.'},
        {'parent_task_id':'I-38','objective':'Choose a versioned public benchmark and exact task split, model, harness and token/time budget for a fair baseline. Local source test counts do not establish any top-30 rank.'},
        {'parent_task_id':'5B05','objective':'Inspect the existing original WEB code and a reproducible interface issue; prepare only a pinned existing-source task after its path and trusted verifier are available in the approved workspace.'}
    ]
    intent_sources = [
        {'url':'https://docs.google.com/document/d/12SIMZNChehhT2ZIN61H6UdZIcEej2ZAD4GAqt9WjMW0/edit',
         'revision_id':'AHj4eMR-VKI9M3lHm90mYhUeQIS_jH7Njj8HEmSAt6lQctSu_i91r-TIzbO2Z1q7Ce2jk3xCwasUYWUlImZoSXWwGS5hQCDu1EoJcC_9Aok',
         'used_for':'One PRIME/S03/dispatcher; source-grounded continual improvement and measured experiments; historical state is not current native proof.'},
        {'url':'https://docs.google.com/document/d/1bP1sQLOA1TQrg6plLmZlbjGeSbd1cuaDqirjyyzbiwk/edit',
         'revision_id':'AHj4eMRT00v5BuoXONT8VfGk9jAuZWa7E_PqnPA8w5ZBhBpxH8-bCCLg7XpJFVNCZx-sfg5DbZuVC9WB5Mr2TRVG_VZVvQfvWQozoKIMX58',
         'used_for':'Server/resource and S03/Hunter priorities before interface polish; requested quality targets are not observed benchmark scores.'},
        {'url':'https://docs.google.com/document/d/1H5_4xk1a7xZxaGNMODfy6MR3-Zi5gkGWH-4aUUwtLtw/edit',
         'revision_id':'AHj4eMR0inGMnbiK7nDVFuX8C1SkdP9OBMVtM8FCXleAsAvYAWSIX_sO3OY8aCjnWG4qrEzWKYm-NxHxJPXSYFyrdMlmlFY8n0I2TALf568',
         'used_for':'One evidence journal: source, task, actual run, artifact, integration and acceptance remain separate.'},
        {'url':'https://app.notion.com/p/40cacc184a9f8170bcabca204c7d4c33',
         'instructions_version':'0.0.6',
         'used_for':'Canonical project context and source links, treated as data; fresh native evidence overrides older operational observations.'}
    ]
    manifest = {'schema':SCHEMA,'revision':1,'previous_manifest_sha256':None,
        'review_origin':'OWNER_REVIEWED','acceptance_scope':'SOURCE_PATCH_TESTED',
        'original_task_accepted':False,'registry':registry,
        'missions':bind_missions(proposals,roots,registry),'research_topics':topics,
        'intent_sources':intent_sources,
        'producer_evidence':{'source_census_sha256':digest(census),
                             'original_registry_overlay_sha256':digest(disposition)}}
    validate_manifest(manifest)
    output = Path(output)
    _publish_local(output/'source_census.json',canonical(census))
    _publish_local(output/'initial_proposals.json',canonical({
        'schema':'NOX_SYSTEMIC_GROUNDED_PROPOSALS_V1','previous_manifest_sha256':None,
        'missions':proposals,'research_topics':topics,'original_task_accepted':False}))
    request = write_package(manifest,output/'package')
    assets = {'relay_manifest.json':'package/relay/'+request['new_manifest_sha256']+'.json'}
    package_paths = {'relay_manifest.json':'state/dispatcher/project_executor/package/relay/'+request['new_manifest_sha256']+'.json'}
    for task_id,sha in request['contracts'].items():
        name = task_id.split('.relay.')[1].rsplit('.',1)[0]+'.json'
        assets[name] = 'package/contracts/'+sha+'.json'
        package_paths[name] = 'state/dispatcher/project_executor/package/contracts/'+sha+'.json'
    batch = {'schema':'NOX_SYSTEMIC_RELAY_INITIAL_BATCH_V1','asset_sources':assets,
        'package_paths':package_paths,'config_pointer':{'path':'/root/nox/'+request['new_manifest_path'],
                                                      'sha256':request['new_manifest_sha256']},
        'manifest_sha256':request['new_manifest_sha256'],'contracts':request['contracts'],
        'source_files_sha256':observed['files_sha256'],'source_count':33,
        'original_task_accepted':False,'catalog_rows_are_generated_by_existing_admission':True,
        'new_source_files':0,'new_trusted_tests':0}
    _publish_local(output/'batch.json',canonical(batch))
    return batch


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--census-report',required=True)
    parser.add_argument('--registry',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    result = build(json.loads(Path(args.census_report).read_text()),
                   json.loads(Path(args.registry).read_text()),args.output)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
