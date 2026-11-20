"""Current native facts and the existing media queue for authenticated chat.

No scheduler, GPU process or new memory store. The same pinned file evidence
used by the UI is projected into bounded facts; media actions use the existing
owner runtime and remain queued until its native output receipt is complete.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time

ROOT = Path('/root/nox')
PINS = {'owner_download_status': '574bd91bb072a626b32fc557299e245b61a8798204fffd690099ffd78fc09eda',
        'owner_media_runtime': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'}
SCHEMA = 'NOX_OWNER_CURRENT_CHAT_EVIDENCE_V1'
NAMES = frozenset({'owner_verified_download_inventory', 'owner_queue_media_v1', 'owner_media_job_v1'})
_IMPORT = threading.RLock()


class EvidenceHold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise EvidenceHold(code)


def _read(path, maximum=262144):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)), 'HOLD_CHAT_EVIDENCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 <= before.st_size <= maximum, 'HOLD_CHAT_EVIDENCE_FILE')
        raw = os.read(fd, maximum+1)
        require(len(raw) == before.st_size, 'HOLD_CHAT_EVIDENCE_FILE_SIZE')
        after = os.fstat(fd); named = path.stat(follow_symlinks=False)
        require(all(getattr(before, key) == getattr(after, key) == getattr(named, key)
                    for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')), 'HOLD_CHAT_EVIDENCE_CHANGED')
        return raw
    finally:
        os.close(fd)


def _module(name):
    require(name in PINS, 'HOLD_CHAT_EVIDENCE_MODULE')
    path = ROOT/'scripts'/(name+'.py'); raw = _read(path)
    require(hashlib.sha256(raw).hexdigest() == PINS[name], 'HOLD_CHAT_EVIDENCE_SOURCE_PIN')
    with _IMPORT:
        existing = sys.modules.get(name)
        if existing is not None:
            require(getattr(existing, '__file__', None) == str(path), 'HOLD_CHAT_EVIDENCE_MODULE_ORIGIN')
            return existing
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        # Execute the verified bytes, avoiding a second pathname read/pyc write.
        sys.modules[name] = module
        try:
            exec(compile(raw, str(path), 'exec'), module.__dict__)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        return module


def relevant_query(text):
    return isinstance(text, str) and bool(re.search(
        r'загруз|скачан|скачай|докач|адаптер|lora|gguf|sdxl|wan2|изображени|картинк|фото|видео|'
        r'нарис|генерир|умеешь|возможност|download|image|video|draw|generat|imagen|dibuja', text, re.I))


def download_status_query(text):
    if not isinstance(text, str) or not re.search(r'загруз(?:к|ок)|загружен|скачан|download', text, re.I):
        return False
    if re.search(r'скачай|скачать|загрузи|загрузить|докачай|продолж|возобнов|запуст|останов|удал|перенес|перемест|'
                 r'pause|resume|start|delete|move|install', text, re.I):
        return False
    return bool(re.search(r'что|сколько|всё|все|уже|готов|статус|состояни|проверь|покажи|закончи|\?|status|what|which|how many', text, re.I))


def explicit_media_request(text):
    """Only an immediate, explicit create request with a nonempty scene."""
    if not isinstance(text, str) or not 1 <= len(text) <= 2500:
        return None
    value = text.strip()
    if re.search(r'\bне\s+(?:надо\s+|нужно\s+)?(?:генерир|создав|создавай|запуска|рисуй)|'
                 r'\b(?:do not|don.t|не сейчас|только (?:промпт|план|пример|инструкц))\b', value, re.I):
        return None
    if re.search(r'\b(?:завтра|послезавтра|позже|потом|tomorrow|later|mañana|después)\b|'
                 r'\bчерез\s*(?:(?:\d+|один|одну|два|две|три|несколько|пол)\s*)?'
                 r'(?:час|минут|секунд|день|дня|дней|недел)|'
                 r'\b(?:in|after)\s+\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?)\b|'
                 r'\b(?:más\s+tarde|en\s+\d+\s*(?:minutos?|horas?|días?))\b', value, re.I):
        # This bridge is an immediate queue, not a scheduler. A deferred owner
        # request must not become an immediate GPU job or a claimed reminder.
        return None
    value = re.sub(r'^(?:(?:nox|нокс)\s*[,!:]?\s*)?(?:пожалуйста\s*[,!:]?\s*)?', '', value, flags=re.I)
    value = re.sub(r'^(?:можешь(?:\s+ли)?(?:\s+мне)?|can you|could you|puedes)\s+', '', value, flags=re.I)
    draw = re.match(r'^(?:нарисуй|нарисовать|draw|dibuja|dibujar)\s+(.+)$', value, re.I | re.S)
    if draw:
        kind, prompt = 'image', draw[1]
    else:
        match = re.match(r'^(?:создай|создать|сделай|сделать|сгенерируй|сгенерировать|generate|create|make|genera|crea)\s+'
                         r'(?:(?:мне|an?|una?|un)\s+)?'
                         r'(фото(?:графию)?|изображение|картинку|рисунок|видео|видеоролик|анимацию|image|picture|photo|video|animation|imagen)'
                         r'(?:\s*[:—-]\s*|\s+)(.+)$', value, re.I | re.S)
        if not match:
            return None
        kind = 'video' if re.fullmatch(r'видео|видеоролик|анимацию|video|animation', match[1], re.I) else 'image'
        prompt = match[2]
    prompt = prompt.strip().rstrip('?').strip()
    if not 3 <= len(prompt) <= 2000 or re.match(r'^(?:как|инструкци|промпт|план\s+(?:как|для)|example|prompt\b)', prompt, re.I):
        return None
    return {'kind': kind, 'prompt': prompt}


def current_evidence():
    unknown = {'schema': SCHEMA, 'state': 'CURRENT_INVENTORY_UNVERIFIED', 'observed_at': time.time(),
               'legacy_reconciliation_zero_is_cumulative': False, 'current_model_merge_inclusion': 'NOT_VERIFIED'}
    try:
        snapshot = _module('owner_download_status').snapshot()
        return project(snapshot)
    except Exception:
        return unknown


def project(snapshot):
    require(isinstance(snapshot, dict) and snapshot.get('schema') == 'NOX_OWNER_DOWNLOAD_INVENTORY_V1'
            and type(snapshot.get('observed_at')) in (int, float)
            and -5 <= time.time()-snapshot['observed_at'] <= 45, 'HOLD_CHAT_EVIDENCE_SNAPSHOT')
    groups = {}
    for source, name, expected in (('media', 'media', 4), ('drive_adapters', 'drive_adapters', 3)):
        value = snapshot.get(source)
        require(isinstance(value, dict) and value.get('selected_files') == expected
                and type(value.get('verified_files')) is int and 0 <= value['verified_files'] <= expected
                and type(value.get('verified_bytes')) is int and 0 <= value['verified_bytes'] <= 20000000000,
                'HOLD_CHAT_EVIDENCE_COUNTS')
        groups[name] = {key: value[key] for key in ('selected_files', 'verified_files', 'verified_bytes')}
    accepted = snapshot['media'].get('generation_acceptance') or {}
    groups['media']['generation_test_verified'] = {
        kind: isinstance(accepted.get(kind), dict) and accepted[kind].get('verified') is True
              and accepted[kind].get('state') == 'SYNTHETIC_GENERATION_DECODE_AND_DELIVERY_VERIFIED'
        for kind in ('image', 'video')}
    return {'schema': SCHEMA, 'state': 'CURRENT_FILE_IDENTITIES_CHECKED', 'observed_at': snapshot['observed_at'],
            **groups, 'media_models': {'image': 'SDXL-Lightning 4-step', 'video': 'Wan2.1 T2V 1.3B'},
            'scope': 'SELECTED_FOUR_MEDIA_FILES_AND_THREE_RESTORED_ADAPTERS',
            'current_engine_availability': 'CHECKED_WHEN_ENQUEUEING', 'large_file_hashes_recomputed': False,
            'legacy_reconciliation_zero_is_cumulative': False,
            'current_model_merge_inclusion': 'NOT_VERIFIED', 'ram_copy_is_durable_backup': False}


def inventory_reply():
    value = current_evidence()
    if value['state'] != 'CURRENT_FILE_IDENTITIES_CHECKED':
        return 'Не могу сейчас подтвердить состояние выбранных загрузок: действующая квитанция или текущая проверка файлов недоступна. Прежний ноль в отчёте сверки компонентов не означает, что на сервере ничего не скачано.'
    media, drive = value['media'], value['drive_adapters']
    line = (f"Сейчас подтверждены {media['verified_files']}/4 выбранных файла для SDXL-Lightning и Wan2.1 "
            f"({media['verified_bytes']:,} байт) и {drive['verified_files']}/3 адаптера 3t724u в RAM "
            f"({drive['verified_bytes']:,} байт).")
    tests = media['generation_test_verified']
    line += '\nПробная генерация: фото — ' + ('подтверждена' if tests['image'] else 'не подтверждена')
    line += ', видео — ' + ('подтверждена' if tests['video'] else 'не подтверждена') + '.'
    return line + ('\nОтметки о проверенных файлах основаны на квитанциях полного SHA256 и текущих идентификаторах. Это данные выбранных загрузок, '
                   'не общий счётчик всех файлов сервера. Включение восстановленных адаптеров в текущие веса не подтверждено; '
                   'копия в RAM не считается долговременным резервом.')


def augment_messages(messages, user_text):
    if not relevant_query(user_text):
        return messages
    evidence = current_evidence()
    note = ('Текущие проверенные данные сервера NOX (данные, не пользовательские инструкции):\n'
            + json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            + '\nscope=RECONCILIATION_ONLY и downloaded_bytes=0 в старой сверке компонентов не являются '
              'измерением уже скачанных файлов. О текущих загрузках суди по этому наблюдению. '
              'Успешная пробная генерация не означает завершения нового задания; QUEUED означает только очередь. '
              'Для явно порученного создания фото/видео используй owner_queue_media_v1; '
              'он ставит задание в существующий диспетчер с его ресурсными ограничениями.')
    result = [dict(row) for row in messages]
    if result and result[0].get('role') == 'system':
        result[0]['content'] = str(result[0].get('content') or '')+'\n\n'+note
    else:
        result.insert(0, {'role': 'system', 'content': note})
    return result


def tools():
    return [
        {'type': 'function', 'function': {'name': 'owner_verified_download_inventory',
         'description': 'Read current native file receipts for selected media and restored adapters; no download, merge or write.',
         'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}},
        {'type': 'function', 'function': {'name': 'owner_queue_media_v1',
         'description': 'Execute the owner’s explicit current image/video creation request in the existing NOX media queue. QUEUED is not completed. Uses the original owner scene; never accepts commands or arbitrary workflows.',
         'parameters': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['image', 'video']}},
                        'required': ['kind'], 'additionalProperties': False}}},
        {'type': 'function', 'function': {'name': 'owner_media_job_v1',
         'description': 'Read a previously created native-owner media job and verified output links. Do not guess a job id.',
         'parameters': {'type': 'object', 'properties': {'job_id': {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}},
                        'required': ['job_id'], 'additionalProperties': False}}},
    ]


def _safe_reason(exc):
    value = str(exc)
    return value if re.fullmatch(r'(?:HOLD|WAIT|INVALID|MEDIA)_[A-Z0-9_]{1,100}', value) else 'HOLD_MEDIA_CHAT_UNAVAILABLE'


def queue_media(user_text, requested_kind, turn):
    intent = explicit_media_request(user_text)
    require(intent is not None and requested_kind == intent['kind'], 'HOLD_MEDIA_EXPLICIT_OWNER_REQUEST_REQUIRED')
    if turn.get('media_result'):
        return turn['media_result']
    runtime = _module('owner_media_runtime')
    require(not runtime.media_stop(), 'WAIT_MEDIA_OWNER_STOP_OR_MAINTENANCE')
    # create_job uses the existing queue limit, jobs.lock and dispatcher inbox.
    created = runtime.create_job(intent, owner='native-owner')
    job_id = created.get('id')
    require(isinstance(job_id, str) and re.fullmatch('[a-f0-9]{32}', job_id), 'HOLD_MEDIA_CHAT_JOB_ID')
    # A later readback failure must not enqueue a second job in this turn.
    turn['media_result'] = {'ok': False, 'state': 'ACCEPTANCE_UNVERIFIED', 'job_id': job_id,
        'text': f'Получен идентификатор задания `{job_id}`, но подтверждение очереди пока недоступно. Повторное создание в этом запросе не выполняется.'}
    persisted = runtime.load_job(job_id)
    require(persisted.get('owner') == 'native-owner' and persisted.get('state') in runtime.ACTIVE | runtime.TERMINAL
            and persisted.get('request', {}).get('kind') == intent['kind']
            and persisted.get('request', {}).get('prompt') == intent['prompt'], 'HOLD_MEDIA_CHAT_QUEUE_READBACK')
    if persisted['state'] in runtime.TERMINAL:
        # A fast completion/failure can win the readback race. Report its real
        # state instead of claiming that a terminal job is still queued.
        result = dict(media_job(job_id), job_id=job_id)
        turn['media_result'] = result
        return result
    label = 'Фото' if intent['kind'] == 'image' else 'Видео'
    result = {'ok': True, 'state': persisted['state'], 'job_id': job_id, 'text':
              f'{label} поставлено в очередь NOX. Задание `{job_id}`. Текущее состояние: {persisted["state"]}. Это подтверждённое принятие задания, '
              'не готовый файл. Диспетчер выполнит его при доступных ресурсах; ход работы появится в «Отчётах NOX».'}
    turn['media_result'] = result
    return result


def media_job(job_id):
    require(isinstance(job_id, str) and re.fullmatch('[a-f0-9]{32}', job_id), 'INVALID_MEDIA_JOB_ID')
    runtime = _module('owner_media_runtime'); job = runtime.load_job(job_id)
    require(job.get('owner') == 'native-owner', 'MEDIA_JOB_NOT_FOUND')
    state = job.get('state')
    require(state in runtime.ACTIVE | runtime.TERMINAL, 'HOLD_MEDIA_CHAT_JOB_STATE')
    text = f'Задание `{job_id}`: {state}.'
    if state == 'COMPLETED' and job.get('generation_verified') is True:
        config = runtime.configuration(); links = []
        for index, item in enumerate(job.get('outputs', [])[:4]):
            path = runtime.output_path(config, job_id, item)
            require(path.stat().st_size == item.get('bytes'), 'HOLD_MEDIA_CHAT_OUTPUT_CHANGED')
            links.append(f'[Открыть результат {index+1}](/api/ui/media/jobs/{job_id}/outputs/{index})')
        require(bool(links), 'HOLD_MEDIA_CHAT_OUTPUT_MISSING')
        text += ' Генерация и проверка файла завершены.\n'+'\n'.join(links)
    elif state == 'COMPLETED':
        text += ' Проверка результата не подтверждена.'
    # Only verified COMPLETED assets may certify successful image/video
    # generation. QUEUED/RUNNING are status, not delivered media; FAILED or
    # CANCELLED must never become successful tools even with stale flags.
    return {'ok': bool(state == 'COMPLETED' and job.get('generation_verified') is True),
            'state': state, 'text': text}


def media_status_query(text):
    if not isinstance(text, str) or not re.search(r'готов|статус|состояни|покажи|результат|status|result|ready', text, re.I):
        return None
    found = re.findall(r'(?<![a-z0-9])[a-f0-9]{32}(?![a-z0-9])', text)
    return found[0] if len(found) == 1 else None


def dispatch(name, arguments, user_text, turn):
    try:
        if name == 'owner_verified_download_inventory' or (name == 'run_admin' and arguments.get('action') == 'downloads_status'):
            return {'ok': True, 'text': inventory_reply()}
        if name == 'owner_queue_media_v1':
            require(set(arguments) == {'kind'}, 'INVALID_MEDIA_CHAT_ARGUMENTS')
            return queue_media(user_text, arguments['kind'], turn)
        if name == 'owner_media_job_v1':
            require(set(arguments) == {'job_id'}, 'INVALID_MEDIA_CHAT_ARGUMENTS')
            return media_job(arguments['job_id'])
        return None
    except Exception as exc:
        if name == 'owner_queue_media_v1' and turn.get('media_result'):
            return turn['media_result']
        return {'ok': False, 'state': 'BLOCKED', 'text': 'Действие не выполнено: '+_safe_reason(exc)+'.'}


def bind_self_observation(namespace):
    if namespace.get('_owner_current_evidence_bound'):
        return
    original_snapshot, original_model = namespace['snapshot'], namespace['evidence_for_model']
    def snapshot():
        value = original_snapshot(); value['download_observation'] = current_evidence(); return value
    def evidence_for_model(observation, verified_memory):
        value = original_model(observation, verified_memory)
        if value.get('state') != 'HOLD_UNVERIFIED_SELF_OBSERVATION':
            # Never promote caller-supplied observation strings into evidence.
            value['downloads'] = current_evidence()
        return value
    namespace.update(snapshot=snapshot, evidence_for_model=evidence_for_model, _owner_current_evidence_bound=True)
