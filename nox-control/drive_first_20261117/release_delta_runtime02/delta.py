#!/usr/bin/env python3
"""Deterministic no-loss local delta. Preview by default; root supplies fresh Drive guard to apply."""
import argparse
import copy
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

HERE=Path(__file__).resolve().parent
PLAN='NOX_FAST_CHAT_SIX_IMPLEMENTATION_20261117.json'
CONCEPT='NOX_Unique_Concept_20261117.md'
MEGA='NOX_MEGA_LIBRARY_START_20261117.md'
OLD_HEADING='## Актуальный срез v2.4: подтверждено, частично выполнено, остаётся HOLD'
HIST_HEADING='## Исторический срез v2.4 до runtime 0.2 и canary v4'
BEGIN='<!-- NOX_RUNTIME02_DELTA_BEGIN -->'
END='<!-- NOX_RUNTIME02_DELTA_END -->'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read_json(path):return json.loads(Path(path).read_text())
def encoded(obj):return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def need(value,code):
    if not value:raise ValueError(code)
def stamp(value):
    parsed=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
    need(parsed.tzinfo is not None,'TIMESTAMP_REQUIRES_TIMEZONE')
    return parsed

def normalize_outcome(kind,item,facts):
    need(isinstance(item,dict) and item.get('state') in ('PENDING','OBSERVED'),'OUTCOME_STATE')
    if item['state']=='PENDING':
        need(item.get('receipt') is None,'PENDING_MUST_NOT_CONTAIN_RECEIPT')
        return {'state':'PENDING'}
    need(type(item.get('run_id')) is int and item['run_id']>0 and type(item.get('job_id')) is int and item['job_id']>0,'OUTCOME_RUN_JOB_REQUIRED')
    need(isinstance(item.get('source_commit'),str) and re.fullmatch('[a-f0-9]{40}',item['source_commit']),'OUTCOME_SOURCE_COMMIT_REQUIRED')
    data=item.get('receipt');need(isinstance(data,dict),'OUTCOME_RECEIPT_REQUIRED')
    status=data.get('status');need(isinstance(status,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,119}',status),'OUTCOME_STATUS')
    base={k:item[k] for k in ('state','run_id','job_id','source_commit')}
    original_pin=item.get('source_receipt_sha256')
    need(original_pin is None or isinstance(original_pin,str) and re.fullmatch('[a-f0-9]{64}',original_pin),'OUTCOME_SOURCE_RECEIPT_SHA')
    base['raw_receipt_canonical_sha256']=original_pin or sha(canonical(data))
    if kind=='source_stage':
        keys=('status','source_staging_only','directory','files','bytes','bundle_sha256','runtime_imported','runtime_bound','model_downloads','model_requests','new_services','workers_started','legacy_patch_repeated','native_chat_canary_pass','completion_scope','partial_destination_may_exist','error_type','owner_request_id','credentials_read_or_exported','serialization')
        projected={k:data[k] for k in keys if k in data}
        if status=='SOURCE_INSTALLED_NOT_BOUND':
            expected=facts['source_stage']
            need(data.get('bundle_sha256')==expected['bundle_sha256'] and data.get('directory')==expected['directory'],'STAGING_BUNDLE_BINDING')
            need(data.get('files')==12 and data.get('bytes')==expected['bytes'],'STAGING_SIZE_COUNT')
            need(data.get('source_staging_only') is True and data.get('runtime_bound') is False and data.get('runtime_imported') is False,'STAGING_SCOPE')
            need(all(data.get(k)==0 for k in ('model_requests','model_downloads','new_services','workers_started')),'STAGING_UNEXPECTED_EFFECT')
            actual=data.get('file_pins');need(isinstance(actual,list),'STAGING_PINS_REQUIRED')
            view=lambda rows:sorted((x.get('path'),x.get('bytes'),x.get('sha256')) for x in rows)
            need(view(actual)==view(expected['expected_file_pins']),'STAGING_FILE_PIN_MISMATCH')
            projected['file_pins']=[{k:x[k] for k in ('path','bytes','sha256','created') if k in x} for x in actual]
        else:need(status.startswith('HOLD'),'STAGING_UNSUPPORTED_STATUS')
    else:
        need(data.get('mode')=='reconcile','READONLY_MODE_REQUIRED')
        need(data.get('model_requests')==0 and data.get('dialogs_created')==0,'RECONCILIATION_MUST_NOT_GENERATE')
        need(not data.get('own_stream_stop_attempted') and data.get('native_canary_pass') is False,'RECONCILIATION_NOT_CANARY_PASS')
        if 'own_dialog_id' in data:need(data['own_dialog_id']==facts['readonly_reconcile']['fixed_dialog_id'],'RECONCILE_WRONG_DIALOG')
        if data.get('reconciliation_pass') is True:
            need(data.get('history_reconciliation_pass') is True and data.get('ui_asset_acceptance_pass') is True,'RECONCILIATION_PROOF_INCOMPLETE')
            need(data.get('terminal_receipt_fields_recovered') is False and data.get('prior_stream_timings_recovered') is False,'RECONCILIATION_OVERCLAIM')
        keys=('status','mode','phase','error_phase','error_class','own_dialog_id','reconciliation_pass','history_reconciliation_pass','ui_asset_acceptance_pass','ui_status','native_canary_pass','native_chat_canary_pass','dialogs_created','model_requests','external_http_requests','model_reloads','terminal_receipt_fields_recovered','prior_stream_timings_recovered','authenticated_login','auth_path_resolved','owner_request_id','owner_ui_sha256','total_ms','python_version')
        projected={k:data[k] for k in keys if k in data}
        diagnostic=data.get('history_http_diagnostic')
        if isinstance(diagnostic,dict):projected['history_http_diagnostic']={k:diagnostic[k] for k in ('status','bytes_read','truncated','sha256','content_type','json_decoded','json_type','error_class') if k in diagnostic}
    base['receipt']=projected
    return base

def normalized_outcomes(outcomes,facts):
    need(outcomes.get('schema')=='NOX_V24_RUNTIME02_NATIVE_OUTCOMES_V1','OUTCOMES_SCHEMA')
    return {key:normalize_outcome(key,outcomes[key],facts) for key in ('source_stage','readonly_reconcile')}

def normalized_history(outcomes,facts):
    history=outcomes.get('history',[]);need(isinstance(history,list),'OUTCOME_HISTORY_LIST')
    result=[]
    for row in history:
        need(isinstance(row,dict) and row.get('kind') in ('source_stage','readonly_reconcile'),'OUTCOME_HISTORY_KIND')
        need(row.get('outcome',{}).get('state')=='OBSERVED','OUTCOME_HISTORY_OBSERVED')
        result.append({'kind':row['kind'],'outcome':normalize_outcome(row['kind'],row['outcome'],facts)})
    return result

def record_outcome(outcomes,kind,item,facts):
    clean=normalize_outcome(kind,item,facts)
    stored={k:clean[k] for k in ('state','run_id','job_id','source_commit','receipt')}
    stored['source_receipt_sha256']=clean['raw_receipt_canonical_sha256']
    previous=outcomes[kind]
    if previous.get('state')=='OBSERVED' and canonical(normalize_outcome(kind,previous,facts))!=canonical(clean):
        entry={'kind':kind,'outcome':copy.deepcopy(previous)}
        history=outcomes.setdefault('history',[])
        if entry not in history:history.append(entry)
    outcomes[kind]=stored
    normalized_history(outcomes,facts)
    return stored

def latest_native_facts(outcomes,facts=None):
    facts=facts or {}
    rec=outcomes['readonly_reconcile'];stage=outcomes['source_stage']
    data=rec.get('receipt',{});stage_data=stage.get('receipt',{})
    return {'read_only_run_id':rec.get('run_id'),'read_only_job_id':rec.get('job_id'),
        'read_only_status':data.get('status','PENDING'),'authenticated_login':data.get('authenticated_login'),
        'ui_asset_acceptance_pass':data.get('ui_asset_acceptance_pass') is True,
        'visual_acceptance_pass':False,'history_http_diagnostic':copy.deepcopy(data.get('history_http_diagnostic')),
        'dialogs_created':data.get('dialogs_created'),'model_requests':data.get('model_requests'),
        'source_stage_status':stage_data.get('status','PENDING'),'new_stage_acceptance_pending':stage_data.get('status')!='SOURCE_INSTALLED_NOT_BOUND',
        'partial_destination_may_exist':False if stage_data.get('status')=='SOURCE_INSTALLED_NOT_BOUND' else stage_data.get('partial_destination_may_exist'),
        'installed_source_files':stage_data.get('files') if stage_data.get('status')=='SOURCE_INSTALLED_NOT_BOUND' else None,
        'installed_source_bytes':stage_data.get('bytes') if stage_data.get('status')=='SOURCE_INSTALLED_NOT_BOUND' else None,
        'created_source_files':sum(x.get('created') is True for x in stage_data.get('file_pins',[])) if stage_data.get('status')=='SOURCE_INSTALLED_NOT_BOUND' else None,
        'runtime_bound':False,'native_canary_pass':False,
        'history_error_code':facts.get('history_contract_evidence',{}).get('error_code'),
        'history_parser_root_cause_confirmed':facts.get('history_contract_evidence',{}).get('parser_root_cause_confirmed',False),
        'history_cause_verification_scope':facts.get('history_contract_evidence',{}).get('cause_verification_scope'),
        'history_wrapper_query_fix_applied':False,
        'historical_stage_diagnostic':copy.deepcopy(facts.get('source_stage_readonly_diagnostic')),
        'other_team_o1_hardening':copy.deepcopy(facts.get('other_team_o1_permission_hardening')),
        'NEXT_READY':facts.get('history_contract_evidence',{}).get('NEXT_READY','Determine the actual history handler/query contract without repeating generation.')+' Source-only staging does not bind runtime; preserve existing O1/O5 ownership and separate host binding/acceptance.'}

def result_text(value,pending):
    if value['state']=='PENDING':return pending
    return f"**{value['receipt']['status']}**, run `{value['run_id']}`, job `{value['job_id']}`; source `{value['source_commit']}`"

def section(facts,outcomes):
    stage=result_text(outcomes['source_stage'],'**PENDING**: новая native-установка исходников ещё не подтверждена')
    reconcile=result_text(outcomes['readonly_reconcile'],'**PENDING**: read-only проверка фиксированного диалога ещё не выполнена')
    latest=latest_native_facts(outcomes,facts)
    fresh=''
    if latest['ui_asset_acceptance_pass'] and latest['authenticated_login'] is True:
        diagnostic=latest['history_http_diagnostic'] or {}
        cause='Подтверждён код **INVALID_LIMIT**; причина в handler/parser ещё проверяется.'
        if latest['history_parser_root_cause_confirmed']:
            cause='Вторая команда **O0 воспроизвела ошибку передачи query** в существующем wrapper: `url.query` имеет тип bytes и попадает в строку с лишней пунктуацией, после чего parser отклоняет limit. Исправление через ASCII decode готовится; native patch и успешный history readback ещё не подтверждены.'
        fresh=f"\n**Свежий native-факт:** read-only run `{latest['read_only_run_id']}` / job `{latest['read_only_job_id']}` подтвердил авторизацию и доставку точного HTML/CSS/JS (**UI asset PASS**, без visual PASS). Итог — **{latest['read_only_status']}**: history HTTP `{diagnostic.get('status','UNKNOWN')}`, `{diagnostic.get('content_type','UNKNOWN')}`, {diagnostic.get('bytes_read','UNKNOWN')} байт, SHA `{diagnostic.get('sha256','UNKNOWN')}`. {cause} **0 create / 0 model request / 0 STOP**; это не новый ответ модели и не native canary PASS. Предыдущий `HOLD_MAINTENANCE_BUSY` сохранён в истории. Последний source staging: **{latest['source_stage_status']}**; runtime не связан с host.\n\n**NEXT_READY:** передать подготовку исправления query и read-only проверку того же собственного диалога владельцу **O0**. Новую генерацию не повторять. После source-only установки binding и приёмка остаются отдельной работой существующих O1/O5.\n"
    stage_diagnostic=facts.get('source_stage_readonly_diagnostic')
    if stage_diagnostic:
        fresh+=f"\n**История нашей диагностики staging:** run `{stage_diagnostic['run_id']}` / job `{stage_diagnostic['job_id']}`, comment `{stage_diagnostic['comment_id']}`, source `{stage_diagnostic['source_commit']}` завершился `READ_ONLY_DIAGNOSTIC_COMPLETE` за {stage_diagnostic['elapsed_ms']} мс. В тот момент нового каталога не было, **0 из 12 файлов** присутствовали; priority был `0775` (dev 36, inode 2157348507), CHAT_ACTIVE **1 → 1**. Записей, сети и захвата блокировок — 0. Это исторический снимок до следующего изменения прав, а не актуальные разрешения после O1. Исходный staging `HOLD_DIRECTORY_OWNER_OR_MODE` сохранён как отдельная попытка.\n"
    hardening=facts.get('other_team_o1_permission_hardening')
    if hardening:
        fresh+=f"\n**Следующее изменение другой команды O1:** run `{hardening['run_id']}` / job `{hardening['job_id']}` выполнил hardening: `/root/nox` и `state/priority` → `0755`, proxy и **9 supervisor configs** → `0644`; bytes исходников не изменены. Собственная установка chat-патча O1 завершилась **HOLD_FILENOTFOUNDERROR**, `installed=false`, заменённых файлов 0. Это не наша установка runtime. В их preflight {hardening['preflight_utc']} наблюдались CHAT_ACTIVE=0, MODE=IDLE и 2 свободных слота; это снимок, не постоянный допуск.\n"
    return f'''{BEGIN}
## Текущая дельта v2.4: runtime 0.2, canary v4 и reconciliation

**Версия 2.4 / plan_revision 5 сохранена.** V3-политика и расписания подтверждены для **15 active = 12 A/B + 3 D**; все **240 карточек / 54 шага / 9 пакетов** сохранены. `execution_enabled=false`: исходники, отдельные native-факты и принятие работающей функции учитываются раздельно.

| Контур | Последнее доказательство | Текущий допуск |
|---|---|---|
| Совместимые integration/controller **0.2.0** | **26 + 20 + 2 = 48 PASS**: 46 авторских и 2 независимых lifecycle tests | **SOURCE_TESTED**, native binding не подтверждён. Два независимых блокера исправлены: неизвестный load не освобождает RAM handle/lease; устаревший fencing token не урегулирует текущий lease. |
| Прежний staging `0c40501f9068` | Исторически установлены 17 файлов; directory сохранён | **Не активировать старый runtime**: его lifecycle исправления заменены совместимой 0.2. Старые bytes не удаляются, legacy policy не запускается повторно. |
| Новый source-only staging | **12 файлов / {facts['source_stage']['bytes']} байт**, bundle `{facts['source_stage']['bundle_sha256']}` | {stage}. Даже успех означает только `SOURCE_INSTALLED_NOT_BOUND`, без импорта/запуска runtime, модели или новых workers. |
| Native canary v4 | Run **44147786817 / job 134267516216**, один собственный диалог и **1 model request** | **HOLD_BOUNDED_CANARY_FAILURE**. Own dialog `{facts['canary_v4']['own_dialog_id']}`; native chat/S03/terminal acceptance не подтверждены. Автоматически повторять генерацию нельзя. |
| Причина прежнего UI hash mismatch | Native served HTML **14519 байт**, SHA `{facts['ui_transform']['served_html_sha256']}`; exact composition с `owner_chat_ui` SHA `{facts['ui_transform']['owner_ui_sha256']}` | Причина установлена: штатное HTML-дополнение. Исправленный checker принимает только точные bytes при совпадающем helper pin; это отдельно от результата чата. |
| Read-only reconciliation | Проверенный source SHA `{facts['readonly_reconcile']['source_sha256']}`; `run(False, …, reconcile_dialog_id=RECONCILE_DIALOG_ID)` | {reconcile}. Только официальный login и разрешённые GET; **0 create / 0 model request / 0 STOP**. |
{fresh}

V4 source `{facts['canary_v4']['source_sha']}`, comment `{facts['canary_v4']['owner_request_id']}`, сообщил итог **4221 мс**, но terminal flags и stream timings не сохранил. Это не clean TTFT и не время принятого ответа. Даже успешный history/UI reconciliation не восстанавливает потерянные terminal fields и не становится `native_canary_pass=true`.

Source commits совместимой пары: integrations `{facts['runtime02']['integration_source_commit']}`, controller `{facts['runtime02']['controller_source_commit']}`. Подтверждённые контракты: неизвестный release ACK требует readback без повторного освобождения; owner pause объединяется с local pause; TRAIN → WORK → TRAIN использует проверенный checkpoint. Защита chat/core/Engram сохраняется. Полная работоспособность модели, обучения и Drive не выводится из локальных fixtures.

**Учёт дальнейших результатов:** обновлять поля `runtime02_delta.native_outcomes.source_stage` / `readonly_reconcile` только по фактическим run/job/source и receipt. Предыдущие наблюдения сохраняются в `native_outcome_history`; v4 canary HOLD остаётся отдельным фактом. До отдельного binding/acceptance общий план остаётся выключенным; новые метрики ускорения остаются **N/A**.
{END}
'''

def markdown_delta(name,text,block):
    need(BEGIN not in text,'DELTA_ALREADY_PRESENT')
    if name==MEGA:
        old='## Состояние';new='## Исторический срез до runtime 0.2 и canary v4'
        need(text.count(old)==1,'MEGA_ANCHOR')
        changes=[(old,new),('### Новые пакеты v2.4 и общий журнал','### Пакеты до runtime 0.2: исторические статусы и общий журнал')]
        modified=text
        for before,after in changes:
            need(modified.count(before)==1,'MEGA_HEADING_ANCHOR');modified=modified.replace(before,after,1)
        anchor='## Главное';need(modified.count(anchor)==1,'MEGA_INSERT_ANCHOR')
    else:
        need(text.count(OLD_HEADING)==1,'CURRENT_HEADING_ANCHOR')
        changes=[(OLD_HEADING,HIST_HEADING)];modified=text.replace(OLD_HEADING,HIST_HEADING,1);anchor=HIST_HEADING
    modified=modified.replace(anchor,block+'\n'+anchor,1)
    restored=modified.replace(block+'\n','',1)
    for before,after in reversed(changes):restored=restored.replace(after,before,1)
    need(restored==text,'MARKDOWN_NO_LOSS_CHECK')
    return modified

def build_candidates(release,base,facts,outcomes):
    original={}
    for entry in base['files']:
        raw=(release/entry['file']).read_bytes();need(sha(raw)==entry['sha256'] and len(raw)==entry['bytes'],'BASE_SHA_DRIFT:'+entry['file']);original[entry['file']]=raw
    normalized=normalized_outcomes(outcomes,facts);block=section(facts,normalized)
    new={name:markdown_delta(name,raw.decode(),block).encode() for name,raw in original.items() if name!=PLAN}
    before=read_json(release/PLAN);j=copy.deepcopy(before)
    historical={'snapshot_id':'V24_BEFORE_RUNTIME02_AND_NATIVE_V4_DELTA','source_base_sha256':next(x['sha256'] for x in base['files'] if x['file']==PLAN),'snapshot_fix':copy.deepcopy(j['snapshot_fix']),'current_readiness':copy.deepcopy(j['current_readiness']),'native_canary':copy.deepcopy(j['native_release']['native_canary']),'source_staging':copy.deepcopy(j['native_release']['source_staging']),'published_packages':copy.deepcopy(j['published_packages']),'limits':copy.deepcopy(j['limits']),'state_delta':j['state_delta']}
    j['historical_snapshots'].append(historical)
    j['runtime02_delta']=copy.deepcopy(facts);j['runtime02_delta']['native_outcomes']=normalized
    j['runtime02_delta']['native_outcome_history']=normalized_history(outcomes,facts)
    j['runtime02_delta']['latest_native_facts']=latest_native_facts(normalized,facts)
    j['native_release']['source_staging'].update(activation_policy=facts['old_staging']['activation_policy'],superseded_for_activation=True,delete_requested=False)
    j['native_release']['runtime02_source_staging']=copy.deepcopy(facts['source_stage']);j['native_release']['runtime02_source_staging']['native_outcome']=normalized['source_stage']
    j['native_release']['runtime02_source_staging']['historical_read_only_diagnostic']=copy.deepcopy(facts.get('source_stage_readonly_diagnostic'))
    j['native_release']['other_team_o1_permission_hardening']=copy.deepcopy(facts.get('other_team_o1_permission_hardening'))
    j['native_release']['native_canary']=copy.deepcopy(facts['canary_v4'])
    j['native_release']['read_only_reconciliation']=copy.deepcopy(facts['readonly_reconcile']);j['native_release']['read_only_reconciliation']['native_outcome']=normalized['readonly_reconcile']
    j['snapshot_fix'].update(status='STATIC_UI_APPLIED_EXACT_OWNER_TRANSFORM_IDENTIFIED_V4_CHAT_HOLD',canary=copy.deepcopy(facts['canary_v4']),ui_transform=copy.deepcopy(facts['ui_transform']))
    rec=normalized['readonly_reconcile'];staged=normalized['source_stage']
    for key,native_key in [('source_stage','runtime02_source_staging'),('readonly_reconcile','read_only_reconciliation')]:
        if normalized[key]['state']=='OBSERVED':
            actual_status=normalized[key]['receipt']['status']
            j['runtime02_delta'][key]['status']=actual_status
            j['native_release'][native_key]['status']=actual_status
            j['native_release'][native_key]['native_attempt_observed']=True
    j['current_readiness'].update(fast_visible_chat='V4_ONE_REQUEST_HOLD_READONLY_RECONCILIATION_PENDING',actual_binding='RUNTIME02_SOURCE_TESTED_NEW_STAGE_PENDING_OLD_STAGING_DO_NOT_ACTIVATE',web_v6='EXACT_OWNER_UI_COMPOSITION_IDENTIFIED_CORRECTED_NATIVE_CHECK_PENDING')
    if staged['state']=='OBSERVED':
        j['current_readiness']['actual_binding']='RUNTIME02_'+staged['receipt']['status']+'_NOT_HOST_BOUND'
    if rec['state']=='OBSERVED':
        j['current_readiness']['fast_visible_chat']='READONLY_'+rec['receipt']['status']
        if rec['receipt'].get('ui_asset_acceptance_pass') is True:
            j['current_readiness']['web_v6']='SERVED_ASSET_COMPOSITION_VERIFIED_READ_ONLY'
            j['snapshot_fix']['status']='AUTH_AND_SERVED_UI_ASSETS_PASS_READONLY_HISTORY_HOLD'
            ui=copy.deepcopy(facts['ui_transform'])
            ui.pop('corrected_native_acceptance_pass',None)
            ui.update(status='SERVED_UI_ASSET_ACCEPTANCE_PASS_NATIVE_READ_ONLY',corrected_native_ui_asset_acceptance_pass=True,native_canary_pass=False,visual_acceptance_pass=False,evidence_scope='Latest native read-only receipt verifies authenticated served asset bytes; not history, visual or model acceptance')
            j['snapshot_fix']['ui_transform']=ui;j['runtime02_delta']['ui_transform']=copy.deepcopy(ui)
    j['native_release']['read_only_reconciliation']['previous_outcomes']=[x['outcome'] for x in j['runtime02_delta']['native_outcome_history'] if x['kind']=='readonly_reconcile']
    j['native_release']['runtime02_source_staging']['previous_outcomes']=[x['outcome'] for x in j['runtime02_delta']['native_outcome_history'] if x['kind']=='source_stage']
    for package in j['published_packages']:
        if package['kind'] in ('integration','controller'):
            package.update(status='RUNTIME02_SOURCE_TESTED_NATIVE_BINDING_PENDING',source_version='0.2.0',old_staging_activation='FORBIDDEN_SUPERSEDED_LIFECYCLE_SOURCE')
        elif package['kind']=='ui':package['status']='NATIVE_SERVED_UI_ASSETS_PASS_HISTORY_HOLD_VISUAL_NOT_ACCEPTED' if rec.get('receipt',{}).get('ui_asset_acceptance_pass') is True else 'STATIC_UI_APPLIED_EXACT_TRANSFORM_IDENTIFIED_V4_HOLD_RECONCILE_SEPARATE'
    j['limits']=[x for x in j['limits'] if not x.startswith('Latest scoped canary resolved auth')]
    j['limits'] += ['Native v4 run44147786817 submitted one own model request and ended HOLD; no accepted terminal/S03/timing receipt is inferred. Fixed own-dialog read-only reconciliation must not generate again.','Historical staged0c405 runtime must not be activated. Matching runtime0.2 source tests passed48=26+20+2; new12-file source staging does not bind runtime.']
    j['state_delta']='V24_RUNTIME02_SOURCE_TESTED_NATIVE_V4_HOLD_WITH_EXPLICIT_OUTCOME_SLOTS'
    j['updated_at_utc']=base['prepared_utc'];j['local_revision_external_writes_performed']=False
    j['local_release_publication'].update(new_local_concept_sha256=sha(new[CONCEPT]),delta_base_concept_sha256=sha(original[CONCEPT]),prepared_runtime02_delta_utc=base['prepared_utc'],fresh_drive_guard_required_before_apply=True)
    j.pop('payload_sha256_without_self_hash',None);j['payload_sha256_without_self_hash']=sha(canonical(j));new[PLAN]=encoded(j)
    for key in ('card_crosswalk','workpackages','topological_order','source_pins','source_commit','automation_policy_readback','restart_policy'):
        need(j[key]==before[key],'PROTECTED_PLAN_STRUCTURE_CHANGED:'+key)
    need(len(j['card_crosswalk'])==240 and sum(len(x['steps']) for x in j['workpackages'])==54 and len(j['workpackages'])==9,'COUNTS_CHANGED')
    need(j['execution_enabled'] is False and j['organization']['enabled_count']==15,'EXECUTION_OR_AUTOMATION_CHANGED')
    need(j['schema_version']=='2.4' and j['plan_revision']==5,'VERSION_CHANGED')
    return original,new,block,{'cards':240,'steps':54,'workpackages':9,'protected_structures_exact':True,'markdown_body_reversible_exact':True,'payload_sha256_without_self_hash':j['payload_sha256_without_self_hash']}

def validate_guard(guard,base,now=None):
    need(guard.get('same_drive_ids') is True and guard.get('all_five_verified') is True,'FRESH_DRIVE_GUARD_REQUIRED')
    observed=stamp(guard['verified_utc']);current=now or datetime.datetime.now(datetime.timezone.utc)
    need(observed>=stamp(base['prepared_utc']) and -120<=(current-observed).total_seconds()<=900,'DRIVE_GUARD_STALE_OR_FUTURE')
    rows={x['file']:x for x in guard.get('files',[])};need(len(rows)==5,'DRIVE_GUARD_FILE_COUNT')
    for entry in base['files']:
        row=rows.get(entry['file'],{})
        need(all(row.get(k)==entry[k] for k in ('sha256','bytes','drive_id')) and row.get('byte_exact') is True and row.get('matches_frozen') is True,'DRIVE_GUARD_PREIMAGE_MISMATCH')

def preview(release,base,facts,outcomes):
    old,new,block,checks=build_candidates(release,base,facts,outcomes)
    patch=''.join(''.join(difflib.unified_diff(old[n].decode().splitlines(True),new[n].decode().splitlines(True),fromfile='a/'+n,tofile='b/'+n,n=3)) for n in sorted(old))
    (HERE/'DELTA_PREVIEW.patch').write_text(patch);(HERE/'DELTA_CURRENT_SECTION.md').write_text(block)
    latest=latest_native_facts(normalized_outcomes(outcomes,facts),facts)
    receipt={'schema':'NOX_V24_RUNTIME02_DELTA_PREVIEW_V1','status':'PREPARED_NOT_APPLIED_FRESH_DRIVE_GUARD_REQUIRED','frozen_files_modified':False,'checks':checks,'delta_facts_sha256':sha((HERE/'DELTA_FACTS.json').read_bytes()),'outcomes_sha256':sha((HERE/'NATIVE_OUTCOMES.json').read_bytes()),'patch_sha256':sha(patch.encode()),'latest_native_facts':latest,'historical_outcome_count':len(normalized_history(outcomes,facts)),'files':[{'file':n,'base_sha256':sha(old[n]),'candidate_sha256':sha(new[n]),'candidate_bytes':len(new[n])} for n in sorted(new)],'NEXT_READY':{'owner':'root','action':latest['NEXT_READY']+' Preserve prior HOLD evidence; fresh raw Drive readback of five unchanged base files before local apply and same-ID publication.','native_status':{'source_stage':latest['source_stage_status'],'readonly_reconcile':latest['read_only_status'],'runtime_bound':False,'native_canary_pass':False},'claim_state':'Only delta directory owned; five frozen files remain untouched'}}
    (HERE/'PREVIEW_RECEIPT.json').write_bytes(encoded(receipt));return receipt

def apply_local(release,base,facts,outcomes,guard):
    validate_guard(guard,base);old,new,block,checks=build_candidates(release,base,facts,outcomes)
    backup=release/'backups'/('v24_before_runtime02_'+sha(canonical(base))[:12]);backup.mkdir(parents=True,exist_ok=True)
    for name,raw in old.items():
        target=backup/name
        if target.exists():need(target.read_bytes()==raw,'BACKUP_COLLISION')
        else:target.write_bytes(raw)
    (backup/'BASE_SHA256.json').write_bytes(encoded(base))
    temps={}
    try:
        for name,raw in new.items():
            fd,temp=tempfile.mkstemp(prefix='.runtime02-delta-',dir=release)
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            temps[name]=Path(temp)
        need(all((release/name).read_bytes()==raw for name,raw in old.items()),'CONCURRENT_LOCAL_DRIFT')
        for name,path in temps.items():os.replace(path,release/name)
        directory_fd=os.open(release,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        for path in temps.values():
            if path.exists():path.unlink()
    need(all((release/name).read_bytes()==raw for name,raw in new.items()),'LOCAL_APPLY_READBACK_FAILED')
    receipt={'schema':'NOX_V24_RUNTIME02_LOCAL_APPLY_V1','status':'APPLIED_LOCAL_ONLY_NOT_PUBLISHED','applied_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'backup':str(backup),'checks':checks,'fresh_drive_guard_sha256':sha(canonical(guard)),'files':[{'file':n,'bytes':len(raw),'sha256':sha(raw)} for n,raw in sorted(new.items())],'external_writes':0,'native_calls':0}
    (HERE/'LOCAL_APPLY_RECEIPT.json').write_bytes(encoded(receipt));return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command')
    sub.add_parser('preview');apply=sub.add_parser('apply');apply.add_argument('--drive-guard',required=True)
    record=sub.add_parser('record');record.add_argument('--kind',choices=['source_stage','readonly_reconcile'],required=True);record.add_argument('--receipt',required=True);record.add_argument('--run-id',type=int,required=True);record.add_argument('--job-id',type=int,required=True);record.add_argument('--source-commit',required=True)
    args=parser.parse_args();base=read_json(HERE/'BASE_SHA256.json');facts=read_json(HERE/'DELTA_FACTS.json');outcomes=read_json(HERE/'NATIVE_OUTCOMES.json');release=Path(base['source_release_directory'])
    if args.command=='record':
        raw=read_json(args.receipt);data=raw.get('data',raw)
        item={'state':'OBSERVED','run_id':args.run_id,'job_id':args.job_id,'source_commit':args.source_commit,'receipt':data}
        record_outcome(outcomes,args.kind,item,facts)
        (HERE/'NATIVE_OUTCOMES.json').write_bytes(encoded(outcomes))
        result=preview(release,base,facts,outcomes)
    elif args.command=='apply':result=apply_local(release,base,facts,outcomes,read_json(args.drive_guard))
    else:result=preview(release,base,facts,outcomes)
    print(json.dumps({'status':result['status'],'files':result.get('files'),'checks':result.get('checks')},ensure_ascii=False))
if __name__=='__main__':main()
