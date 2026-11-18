"""Exact wording projection delta; runtime evidence guards stay unchanged."""
import hashlib

PINS = {'before_sha256': 'b9f4addc252c8a0339e2123680fe5a0ab47cef15e725ecec0747f5934a2759ad', 'before_bytes': 18265, 'after_sha256': '78704531d8fab73357cf66302fde0c31f785e341de5c1ac66a5fb0fd36fdb7a4', 'after_bytes': 19122}
OLD_BLOCK = "    block = ('\\n\\nNOX_CURRENT_MODEL_REFERENCE_V1 (runtime data):\\n'\n             + json.dumps(fact, ensure_ascii=False, separators=(',', ':'), allow_nan=False)\n             + '\\nОтветь кратко по этим данным. Имя GGUF — ссылка из аргументов процесса, не проверка '\n               'содержимого весов или архитектуры. При unverified прямо скажи, что имя текущей модели '\n               'не подтверждено. Не подставляй имя из старого статуса или плана.')\n"
NEW_BLOCK = "    block = '\\n\\nNOX_CURRENT_MODEL_REFERENCE_V2:\\n'\n    if fact['state'] == 'verified_reference':\n        block += (\n            'Проверенное имя файла текущей модели запуска: ' + fact['model_file_reference'] + '.\\n'\n            'Сейчас проверены процесс, его аргументы и принадлежащий ему слушающий сокет '\n            'на маршруте ' + fact['selected_route'] + '.\\n'\n            'Прямо назови эту модель запуска. Содержимое весов, архитектура и обучение '\n            'отдельно не проверялись. Эти неизвестные свойства не отменяют подтверждённое имя запуска.\\n')\n    else:\n        block += (\n            'Для выбранного маршрута ' + fact['selected_route'] + ' проверенного имени текущей '\n            'модели запуска сейчас нет. Скажи об этом прямо; не подставляй имя из старого статуса '\n            'или плана.\\n')\n    block += ('Ответь кратко, обычным языком. Не выводи внутренние флаги, имена полей '\n              'и служебные метки. Адрес маршрута не нужен без отдельного вопроса о нём.')\n"

def transform(raw):
    if len(raw) != PINS['before_bytes'] or hashlib.sha256(raw).hexdigest() != PINS['before_sha256']:
        raise ValueError('HOLD_WORDING_PREIMAGE')
    source = raw.decode('utf-8')
    if source.count(OLD_BLOCK) != 1:
        raise ValueError('HOLD_WORDING_BLOCK_UNIQUE')
    result = source.replace(OLD_BLOCK, NEW_BLOCK).encode('utf-8')
    if len(result) != PINS['after_bytes'] or hashlib.sha256(result).hexdigest() != PINS['after_sha256']:
        raise ValueError('HOLD_WORDING_POSTIMAGE')
    compile(result, 'owner_model_reference_binding.py', 'exec')
    return result
