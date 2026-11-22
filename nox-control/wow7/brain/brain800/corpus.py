"""Private opt-in supervision for operation selection.

Only the JSONL path deliberately supplied by the caller is read. No journal,
S03, chat, connector or implicit discovery is consulted. consent=true attests
the curator selected a public/synthetic or appropriately anonymized example;
it is not a personal data detector. Do not pass unreviewed personal records.
"""
import hashlib
import json
import math
from pathlib import Path
import random
import unicodedata
from collections import Counter, defaultdict

from . import phrases

_FIELDS = {'text', 'data', 'op', 'group', 'consent'}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':'))


def _normalized_text(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def _identity(row):
    canonical = _json([_normalized_text(row['text']), row['data']])
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _unique_dict(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError('Повтор поля JSON')
        obj[k] = v
    return obj


def _validate(row, allowed=None):
    if not isinstance(row, dict) or set(row) != _FIELDS:
        raise ValueError('Ожидаются только text, data, op, group, consent')
    if row['consent'] is not True:
        raise ValueError('Нужно явное согласие куратора consent=true')
    for k, limit in [('text',40000), ('group',200), ('op',200)]:
        if not isinstance(row[k], str) or not row[k].strip() or len(row[k]) > limit:
            raise ValueError('Недопустимое строковое поле '+k)
    if row['group'] != row['group'].strip() or row['op'] != row['op'].strip():
        raise ValueError('Пробелы по краям group/op недопустимы')
    if allowed is not None and row['op'] not in allowed:
        raise ValueError('Метка операции отсутствует в разрешённом реестре')
    if not isinstance(row['data'],dict):
        raise ValueError('Поле data должно содержать объект JSON')
    # Match the execution kernel's input size/depth limits.
    def check(x, depth=0):
        if depth > 15:
            raise ValueError('Слишком глубокая структура data')
        if isinstance(x, (dict,list)):
            if len(x) > 1500:
                raise ValueError('Слишком много элементов в data')
            for y in x.values() if isinstance(x, dict) else x:
                check(y,depth+1)
    check(row['data'])
    if len(_json(row['data']).encode('utf-8')) > 96000:
        raise ValueError('Превышен размер data')


def _no_conflicts(rows):
    seen = {}
    for i,row in enumerate(rows,1):
        key = _identity(row)
        if key in seen and seen[key][0] != row['op']:
            raise ValueError(f'Разные метки для одного примера в записях {seen[key][1]} и {i}')
        seen[key] = row['op'], i


def load_rows(path, allowed_ids):
    """Read an explicit local UTF-8 JSONL file. Reject malformed or non-opted-in rows."""
    if not allowed_ids or isinstance(allowed_ids,(str, bytes)):
        raise ValueError('Нужен явный набор разрешённых идентификаторов операций')
    allowed = set(allowed_ids)
    rows = []
    with Path(path).open('rb') as f:
        lineno = 0
        while raw := f.readline(200001):
            lineno += 1
            if len(raw)>200000:
                raise ValueError(f'Превышен размер строки JSONL {lineno}')
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_dict)
                _validate(row, allowed)
            except (ValueError,TypeError,RecursionError) as exc:
                raise ValueError(f'Некорректная запись JSONL {lineno}: {exc}') from exc
            rows.append(row)
    _no_conflicts(rows)
    return rows


def split_rows(rows, seed=42, validation_fraction=.2):
    """Return (train, held_out); disjoint group and normalized text+canonical data.

    Coincident examples in different groups bind the groups transitively.
    Duplicate supervised pairs within each side are emitted once. Selection
    aims at the requested per-label fraction where whole groups permit.
    """
    if isinstance(validation_fraction,bool) or not 0 < validation_fraction < 1:
        raise ValueError('validation_fraction должна быть между 0 и 1')
    rows = list(rows)
    for row in rows:
        _validate(row)
    _no_conflicts(rows)
    parent = {r['group']:r['group'] for r in rows}
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    owner = {}
    for row in rows:
        fingerprint = _identity(row)
        g = row['group']
        if fingerprint in owner:
            parent[root(g)] = root(owner[fingerprint])
        else:
            owner[fingerprint] = g
    components = defaultdict(list)
    observed = set()
    for row in rows:
        identity = _identity(row)
        if identity not in observed:
            components[root(row['group'])].append(row)
            observed.add(identity)
    if len(components) < 2:
        raise ValueError('Нужны две независимые группы для непересекающегося разбиения')
    labels = Counter(row['op'] for group in components.values() for row in group)
    sizes = {g:Counter(row['op'] for row in rr) for g,rr in components.items()}
    targets = {label:max(1,min(count-1,math.floor(count*validation_fraction+.5))) if count>1 else 0
               for label,count in labels.items()}
    def error(counts):
        return sum(abs(counts[l]-t)/max(1,labels[l]) for l,t in targets.items())
    choices = sorted(components)
    random.Random(seed).shuffle(choices)
    held = set()
    taken = Counter()
    while len(held) < len(components)-1:
        candidates = [g for g in choices if g not in held]
        # Avoid removing all training examples of a label where possible.
        no_loss = [g for g in candidates if all(taken[l]+n < labels[l] for l,n in sizes[g].items())]
        if no_loss:
            candidates = no_loss
        elif held:
            break
        chosen = min(candidates,key=lambda g:error(taken+sizes[g]))
        if held and error(taken+sizes[chosen]) >= error(taken)-1e-12:
            break
        held.add(chosen)
        taken.update(sizes[chosen])
    train = [r for g in sorted(components) if g not in held for r in components[g]]
    valid = [r for g in sorted(components) if g in held for r in components[g]]
    return train, valid


# Four authored alternatives per label. Each is a different wording and a
# different piece of source material. A scenario group is indivisible; the
# seed bank is public synthetic material, not a claim about the other 787 ops.
_VARIANTS = {
    'option_utilities':[
        ('Какой из двух эскизов получит больше с учётом весов?', 'веса: ясность=3, длительность=1; круг: ясность=4, длительность=2; линия: ясность=2, длительность=5'),
        ('Calcula la mejor alternativa ponderando mis criterios.', 'pesos: ritmo=2, color=1; alfa: ritmo=4, color=1; beta: ritmo=2, color=4'),
        ('Распредели варианты по взвешенной оценке.', 'веса: тон=1, ритм=4; волна: тон=5, ритм=1; свет: тон=2, ритм=4'),
        ('¿Qué propuesta gana con estas prioridades?', 'pesos: voz=3, coste=2; A: voz=2, coste=4; B: voz=5, coste=1')],
    'dependency_order':[
        ('Составь допустимую очередность исполнения.', 'набросок → цвет → показ'),
        ('Pon los pasos en un orden que respete sus dependencias.', 'letra -> canto; canto -> edición'),
        ('Что за чем делать, если стрелка означает зависимость?', 'рисунок -> скан; бумага -> скан'),
        ('Dame una secuencia válida para este proyecto.', 'idea -> papel -> cartel')],
    'ready_queue':[
        ('Какие шаги можно брать уже сейчас?', '✓текст -> озвучка; ✓текст -> титры'),
        ('¿Qué puedo empezar sin esperar otras tareas?', '✓boceto -> tinta; tinta -> color'),
        ('Назови доступные для старта задачи.', '✓эскиз -> макет; печать -> вручение'),
        ('Dime cuáles de estas actividades ya están listas para iniciar.', '✓nota -> voz; voz -> corte')],
    'parallel_waves':[
        ('Сгруппируй работы, которые получится делать одновременно.', 'цвет -> зал; звук -> зал'),
        ('Distribuye el proyecto en tandas de trabajo simultáneo.', 'música -> mezcla; voz -> mezcla'),
        ('Выдели волны параллельного выполнения.', 'сюжет -> монтаж; титры -> монтаж; монтаж -> показ'),
        ('¿Qué procesos pueden compartir una misma fase?', 'papel -> marco; tinta -> marco')],
    'blocker_map':[
        ('Укажи, какие незакрытые зависимости мешают каждой задаче.', 'раскадровка -> запись -> сборка'),
        ('Explica por qué está detenida cada actividad.', 'texto -> lectura; lectura -> copia'),
        ('Для каждого шага покажи препятствующих предшественников.', 'кадры -> трейлер; голос -> трейлер'),
        ('Enumera qué trabajo bloquea cada paso.', 'cámara -> toma -> título')],
    'frequency':[
        ('Сколько раз повторяется каждое слово?', 'Река течёт, река блестит.'),
        ('Cuenta las apariciones de cada palabra.', 'Luz azul, luz tenue.'),
        ('Сделай словарь с числом употреблений.', 'Тихий день, тихий свет.'),
        ('Quiero el recuento de palabras por término.', 'Coro canta, canta coro.')],
    'numbers':[
        ('Выпиши все числа из фрагмента.', 'В зале 18 стульев и 2 окна.'),
        ('Recoge los valores numéricos de este párrafo.', 'Hay 5 tomas y 31 segundos.'),
        ('Какие числовые значения встречаются в записи?', 'Частота 48, дорожек 3.'),
        ('Extrae las cantidades escritas con cifras.', 'Se imprimieron 8 copias en 16 minutos.')],
    'sentences':[
        ('Найди границы предложений и раздели текст.', 'Свет погас. Кто там? Тихо!'),
        ('Separa cada oración de este texto.', 'La plaza duerme. El tren sale.'),
        ('Верни по одному предложению на элемент.', 'Пора в зал! Мы готовы.'),
        ('Localiza dónde termina cada frase.', 'Mira arriba. ¿Lo ves?')],
    'reading_time':[
        ('Сколько приблизительно займёт чтение?', 'Капля упала на стол и застыла в полосе света.'),
        ('¿Cuánto tardaré aproximadamente en leer esto?', 'Las hojas cubrían el camino al teatro.'),
        ('Оцени длительность чтения этого абзаца.', 'На сцене загорается мягкий свет, декорации медленно движутся.'),
        ('Dame una estimación de minutos de lectura.', 'Se abre el telón y aparece un puerto tranquilo.')],
    'word_diff':[
        ('Что поменялось в словах между двумя версиями?', ('Открой тихую сцену','Открой ночную сцену')),
        ('¿Qué palabras fueron añadidas o retiradas?', ('La puerta azul','La puerta gris')),
        ('Покажи словесные правки второй редакции относительно первой.', ('Голос слышен','Голос снова слышен')),
        ('Marca el cambio entre estas dos redacciones.', ('Vuelve a casa','Vuelve a la plaza'))],
    'find':[
        ('Покажи, где встречается заданное выражение.', ('эхо','У двери слышно эхо.')),
        ('Localiza las apariciones del término seleccionado.', ('mar','El mar está tranquilo.')),
        ('Найди указанное слово и его место в строке.', ('кадр','Первый кадр готов.')),
        ('Encuentra la posición de la palabra que te doy.', ('luz','La luz vuelve.'))],
    'quote_pairs':[
        ('Вынеси отдельно текст внутри кавычек.', 'Сцена называлась «Маяк».'),
        ('Recupera los pasajes entre comillas.', 'El cartel decía «Silencio».'),
        ('Какие фрагменты здесь заключены в кавычки?', 'Две роли — «Эхо» и «Ветер».'),
        ('Devuelve las citas literales del fragmento.', 'Se oyó «vuelve» y después «espera».')],
    'dedupe_lines':[
        ('Оставь лишь первое вхождение каждой строки.', 'свет\nтень\nсвет'),
        ('Elimina renglones repetidos conservando el orden.', 'uno\ndos\nuno'),
        ('Сверни дубли целых строк в тексте.', 'кадр\nкадр\nзал'),
        ('Deja una sola copia de cada línea.', 'voz\nola\nola')],
}


def seed_rows():
    """65 curated synthetic instances, 13 distinct labels, RU/ES. No private data."""
    out = []
    graph = set(phrases.GRAPH_ACTIONS.values())
    for original, op in phrases.EXAMPLES:
        base = phrases.route_phrase(original)
        if not base or base['op'] != op:
            raise ValueError('Неподдержанный исходный пример: '+op)
        label = op.rsplit('.', 1)[-1]
        def add(index, text, data):
            out.append({'text':text,'data':data,'op':op,'group':f'seed/{op}/{index}','consent':True})
        add('original', original, base['data'])
        for idx,(sentence, material) in enumerate(_VARIANTS[label],1):
            if label in graph:
                data = phrases.graph_data(material)
            elif label == 'option_utilities':
                data = phrases.score_data(material)
            elif label == 'word_diff':
                data = {'text':material[0], 'new_text':material[1]}
            elif label == 'find':
                data = {'query':material[0], 'text':material[1]}
            else:
                data = {'text':material}
            display = ('«'+material[0]+'» → «'+material[1]+'»') if isinstance(material,tuple) else material
            if not data:
                raise ValueError('Невалидная синтетическая задача '+op)
            add(idx, sentence+'\n'+display, data)
    return out
