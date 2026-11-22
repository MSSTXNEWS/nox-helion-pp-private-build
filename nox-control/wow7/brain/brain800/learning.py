"""Local, deterministic operators for learning from annotated examples.

Input order is chronological. Numeric observations use score/target; class
labels use label/prediction. Explicit fields are required for a row to be
eligible for an operator. A missing estimate is returned as null.
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from math import ceil, floor, isfinite, log, log2, sqrt
import re
from statistics import median
from functools import partial


def _mean(values):
    return sum(values) / len(values) if values else None


def _ratio(a, b):
    return a / b if b else None


def _number(value):
    return type(value) in (float, int) and isfinite(value)


def _word_tokens(text):
    return re.findall(r"[^\W_]+", text.casefold())


def _counts(values):
    return dict(sorted(Counter(values).items()))


def _rank(counts):
    return sorted(counts, key=lambda key: (-counts[key], key))


def _group(rows, key):
    result = defaultdict(list)
    for row in rows:
        if isinstance(row.get(key), str):
            result[row[key]].append(row)
    return result


def _class_rows(rows):
    return [r for r in rows if isinstance(r.get("label"), str)
            and isinstance(r.get("prediction"), str)]


def _outcomes(rows):
    return [int(r["label"] == r["prediction"]) for r in _class_rows(rows)]


def _label_quality(rows):
    actual = Counter(r["label"] for r in rows)
    predicted = Counter(r["prediction"] for r in rows)
    correct = Counter(r["label"] for r in rows if r["label"] == r["prediction"])
    result = {}
    for label in sorted(actual.keys() | predicted.keys()):
        tp = correct[label]
        result[label] = {
            "precision": _ratio(tp, predicted[label]),
            "recall": _ratio(tp, actual[label]),
            "f1": _ratio(2 * tp, actual[label] + predicted[label]),
            "support": actual[label],
        }
    return result


def _classification(op, rows, payload):
    rows = _class_rows(rows)
    outcomes = _outcomes(rows)
    if op == "accuracy":
        return _mean(outcomes)
    if op == "error_count":
        return outcomes.count(0)
    if op == "errors":
        return [r for r in rows if r["label"] != r["prediction"]]
    if op == "class_report":
        return _label_quality(rows)
    if op == "macro_f1":
        return _mean([v["f1"] for v in _label_quality(rows).values()])
    if op == "balanced_accuracy":
        return _mean([v["recall"] for v in _label_quality(rows).values() if v["support"]])
    if op == "weighted_f1":
        return _ratio(sum(v["f1"] * v["support"] for v in _label_quality(rows).values()), len(rows))
    if op == "majority_accuracy":
        return _ratio(max(Counter(r["label"] for r in rows).values(), default=0), len(rows))
    if op == "kappa":
        if not rows:
            return None
        actual = Counter(r["label"] for r in rows)
        predicted = Counter(r["prediction"] for r in rows)
        chance = sum(n * predicted[k] for k, n in actual.items()) / len(rows) ** 2
        return _ratio(_mean(outcomes) - chance, 1 - chance)
    # Which classes are confused and in which direction?
    counts = Counter((r["label"], r["prediction"]) for r in rows
                     if r["label"] != r["prediction"])
    return [{"expected": a, "predicted": b, "count": counts[a, b]}
            for a, b in _rank(counts)]


def _quantile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = p * (len(values) - 1)
    return values[floor(idx)] + (idx - floor(idx)) * (values[ceil(idx)] - values[floor(idx)])


def _numeric(op, rows, payload):
    pairs = [(r["score"], r["target"]) for r in rows
             if _number(r.get("score")) and _number(r.get("target"))]
    if not pairs:
        return None
    scores, targets = zip(*pairs)
    errors = [s - t for s, t in pairs]
    absolute = list(map(abs, errors))
    if op == "mae":
        return _mean(absolute)
    if op == "rmse":
        return sqrt(_mean([e * e for e in errors]))
    if op == "median_error":
        return median(absolute)
    if op == "p90_error":
        return _quantile(absolute, 0.9)
    if op == "bias":
        return _mean(errors)
    if op == "within_tolerance":
        tol = payload.get("tolerance", 0.1)
        if not _number(tol) or tol < 0:
            raise ValueError("tolerance must be nonnegative")
        return _mean([e <= tol for e in absolute])
    if op == "r_squared":
        mean = _mean(targets)
        unexplained = _ratio(sum(e * e for e in errors), sum((t - mean) ** 2 for t in targets))
        return None if unexplained is None else 1 - unexplained
    if op == "pearson":
        a, b = _mean(scores), _mean(targets)
        covariance = sum((s - a) * (t - b) for s, t in pairs)
        return _ratio(covariance, sqrt(sum((s - a) ** 2 for s in scores)
                                       * sum((t - b) ** 2 for t in targets)))
    if op == "relative_error":
        return _mean([abs(s - t) / abs(t) for s, t in pairs if t])
    # Least-squares correction for the original prediction.
    x, y = _mean(scores), _mean(targets)
    slope = _ratio(sum((s - x) * (t - y) for s, t in pairs), sum((s - x) ** 2 for s in scores))
    return None if slope is None else {"slope": slope, "intercept": y - slope * x}


def _calibration(op, rows, payload):
    pairs = [(r["confidence"], int(r["label"] == r["prediction"])) for r in _class_rows(rows)
             if _number(r.get("confidence")) and 0 <= r["confidence"] <= 1]
    if op == "brier":
        return _mean([(p - y) ** 2 for p, y in pairs])
    if op == "log_loss":
        return _mean([-log(max(1e-15, p if y else 1 - p)) for p, y in pairs])
    if op == "mean_confidence":
        return _mean([p for p, _ in pairs])
    if op == "signed_gap":
        return _mean([p - y for p, y in pairs])
    bins = defaultdict(list)
    for p, y in pairs:
        bins[min(9, int(p * 10))].append((p, y))
    diagram = [{"lower_bound": i / 10, "count": len(batch),
                "predicted": _mean([p for p, _ in batch]),
                "observed": _mean([y for _, y in batch])}
               for i, batch in sorted(bins.items())]
    if op == "reliability_bins":
        return diagram
    if op == "expected_gap":
        return _ratio(sum(b["count"] * abs(b["predicted"] - b["observed"]) for b in diagram), len(pairs))
    if op == "max_bin_gap":
        return max((abs(b["predicted"] - b["observed"]) for b in diagram), default=None)
    threshold = payload.get("threshold", 0.8)
    if not _number(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be in [0,1]")
    accepted = [y for p, y in pairs if p >= threshold]
    if op == "coverage":
        return _ratio(len(accepted), len(pairs))
    if op == "selective_accuracy":
        return _mean(accepted)
    return sum(y == 0 for y in accepted)


def _edits(op, rows, payload):
    pairs = [(r["before"], r["after"]) for r in rows if isinstance(r.get("before"), str)
             and isinstance(r.get("after"), str)]
    if op == "unchanged_fraction":
        return _mean([a == b for a, b in pairs])
    if op == "length_delta":
        return _mean([len(b) - len(a) for a, b in pairs])
    if op == "token_delta":
        return _mean([len(_word_tokens(b)) - len(_word_tokens(a)) for a, b in pairs])
    if op == "case_only":
        return sum(a != b and a.casefold() == b.casefold() for a, b in pairs)
    if op == "space_only":
        return sum(a != b and a.split() == b.split() for a, b in pairs)
    changes = Counter()
    additions, removals = Counter(), Counter()
    unchanged = total = 0
    for a, b in pairs:
        before, after = _word_tokens(a), _word_tokens(b)
        for tag, i, j, k, m in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if tag != "equal":
                additions.update(after[k:m])
                removals.update(before[i:j])
                if tag == "replace":
                    changes[(" ".join(before[i:j]), " ".join(after[k:m]))] += 1
            else:
                unchanged += j - i
        total += len(before)
    if op == "added_terms":
        return dict(additions.most_common())
    if op == "removed_terms":
        return dict(removals.most_common())
    if op == "replacement_rules":
        return [{"from": a, "to": b, "count": changes[a, b]} for a, b in _rank(changes)]
    if op == "retained_fraction":
        return _ratio(unchanged, total)
    return {t: additions[t] - removals[t] for t in sorted(additions.keys() | removals.keys())
            if additions[t] != removals[t]}


def _preferences(op, rows, payload):
    pairs = [(r["chosen"], r["rejected"]) for r in rows if isinstance(r.get("chosen"), str)
             and isinstance(r.get("rejected"), str) and r["chosen"] != r["rejected"]]
    wins, losses = Counter(a for a, b in pairs), Counter(b for a, b in pairs)
    items = sorted(wins.keys() | losses.keys())
    votes = Counter(pairs)
    if op == "win_count":
        return _counts(a for a, b in pairs)
    if op == "loss_count":
        return _counts(b for a, b in pairs)
    if op == "win_fraction":
        return {v: wins[v] / (wins[v] + losses[v]) for v in items}
    if op == "laplace":
        return {v: (wins[v] + 1) / (wins[v] + losses[v] + 2) for v in items}
    if op == "pair_votes":
        return [{"chosen": a, "rejected": b, "count": votes[a, b]} for a, b in _rank(votes)]
    duels = sorted({tuple(sorted((a, b))) for a, b in pairs})
    if op == "disagreement":
        return [{"a": a, "b": b, "minority_votes": min(votes[a, b], votes[b, a])}
                for a, b in duels if votes[a, b] and votes[b, a]]
    if op == "pair_margin":
        return [{"a": a, "b": b, "net_a": votes[a, b] - votes[b, a]} for a, b in duels]
    if op == "copeland":
        score = Counter({v: 0 for v in items})
        for a, b in duels:
            sign = (votes[a, b] > votes[b, a]) - (votes[a, b] < votes[b, a])
            score[a] += sign
            score[b] -= sign
        return [{"item": v, "score": score[v]} for v in _rank(score)]
    if op == "condorcet":
        return [a for a in items if len(items) > 1
                and all(votes[a, b] > votes[b, a] for b in items if b != a)]
    ratings = {v: 1000.0 for v in items}
    for a, b in pairs:
        expected = 1 / (1 + 10 ** max(-300, min(300, (ratings[b] - ratings[a]) / 400)))
        delta = 24 * (1 - expected)
        ratings[a] += delta
        ratings[b] -= delta
    return ratings


def _distribution(op, rows, payload):
    labels = [r["label"] for r in rows if isinstance(r.get("label"), str)]
    counts = Counter(labels)
    size = len(labels)
    if op == "histogram":
        return _counts(labels)
    if op == "priors":
        return {k: counts[k] / size for k in sorted(counts)}
    if op == "singletons":
        return sorted(k for k in counts if counts[k] == 1)
    if op == "majority":
        return [k for k in sorted(counts) if counts[k] == max(counts.values())]
    if op == "imbalance":
        return max(counts.values()) / min(counts.values()) if counts else None
    if op == "entropy":
        return -sum(n / size * log2(n / size) for n in counts.values()) if size else None
    if op == "gini":
        return 1 - sum((n / size) ** 2 for n in counts.values()) if size else None
    if op == "class_weights":
        return {k: size / (len(counts) * counts[k]) for k in sorted(counts)}
    if op == "transitions":
        jumps = Counter(zip(labels, labels[1:]))
        return [{"from": a, "to": b, "count": jumps[a, b]} for a, b in _rank(jumps)]
    totals = Counter()
    curve = []
    for idx, k in enumerate(labels, 1):
        if k not in totals:
            curve.append({"position": idx, "new_label": k, "distinct": len(totals) + 1})
        totals[k] += 1
    return curve


def _contexts(op, rows, payload):
    groups = _group(rows, "context")
    acc = {k: _mean(_outcomes(v)) for k, v in groups.items() if _outcomes(v)}
    if op == "support":
        return {k: len(v) for k, v in groups.items()}
    if op == "accuracy":
        return acc
    if op == "worst":
        return sorted(k for k in acc if acc[k] == min(acc.values()))
    if op == "disparity":
        return max(acc.values()) - min(acc.values()) if acc else None
    if op == "label_prior":
        return {k: _distribution("priors", v, payload) for k, v in groups.items()}
    if op == "conditional_error":
        return {k: _classification("confusions", v, payload) for k, v in groups.items()}
    if op == "numeric_bias":
        return {k: _numeric("bias", v, payload) for k, v in groups.items()}
    if op == "style_preference":
        return {k: _preferences("win_fraction", v, payload) for k, v in groups.items()}
    if op == "accuracy_interval":
        result = {}
        for k, v in groups.items():
            sample = _outcomes(v)
            if sample:
                p, n, z = _mean(sample), len(sample), 1.96
                center = (p + z * z / (2 * n)) / (1 + z * z / n)
                radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
                result[k] = [max(0.0, center - radius), min(1.0, center + radius)]
        return result
    result = {}
    for k, v in groups.items():
        labels = Counter(r["label"] for r in v if isinstance(r.get("label"), str))
        if labels:
            result[k] = _rank(labels)[0]
    return result


def _time(op, rows, payload):
    outcomes = _outcomes(rows)
    width = payload.get("window", 3)
    if type(width) != int or width < 1:
        raise ValueError("window must be positive integer")
    if op == "window_accuracy":
        return [_mean(outcomes[max(0, i - width + 1):i + 1]) for i in range(len(outcomes))]
    if op == "window_change":
        return (None if len(outcomes) < 2 * width else
                _mean(outcomes[-width:]) - _mean(outcomes[-2 * width:-width]))
    if op == "cumulative":
        good = 0
        result = []
        for i, v in enumerate(outcomes, 1):
            good += v
            result.append(good / i)
        return result
    if op == "longest_error_streak":
        current = best = 0
        for v in outcomes:
            current = 0 if v else current + 1
            best = max(best, current)
        return best
    if op == "since_last_error":
        return len(outcomes) - 1 - max(i for i, v in enumerate(outcomes) if not v) if 0 in outcomes else None
    if op == "first_success":
        return outcomes.index(1) + 1 if 1 in outcomes else None
    if op == "recovery_lengths":
        lengths, run = [], 0
        for v in outcomes:
            if not v:
                run += 1
            elif run:
                lengths.append(run)
                run = 0
        return lengths
    if op == "ewma_accuracy":
        alpha = 2 / (width + 1)
        state = None
        for value in outcomes:
            state = value if state is None else alpha * value + (1 - alpha) * state
        return state
    if op == "label_drift":
        labels = [r["label"] for r in rows if isinstance(r.get("label"), str)]
        if len(labels) < 2 * width:
            return None
        a, b = Counter(labels[-2 * width:-width]), Counter(labels[-width:])
        return sum(abs(a[k] - b[k]) for k in a.keys() | b.keys()) / (2 * width)
    new, seen = [], set()
    for r in rows:
        key = (r.get("label"), r.get("prediction"))
        if all(isinstance(v, str) for v in key) and key[0] != key[1] and key not in seen:
            new.append({"id": r.get("id"), "label": key[0], "prediction": key[1]})
            seen.add(key)
    return new


def _lexical(op, rows, payload):
    docs = [(r, _word_tokens(r["text"])) for r in rows if isinstance(r.get("text"), str)]
    doc_freq = Counter(t for _, words in docs for t in set(words))
    if op == "document_frequency":
        return {k: doc_freq[k] for k in sorted(doc_freq)}
    if op == "idf":
        return {k: 1 + log((1 + len(docs)) / (1 + doc_freq[k])) for k in sorted(doc_freq)}
    if op == "length_profile":
        lengths = [len(w) for _, w in docs]
        return {"average": _mean(lengths), "median": _quantile(lengths, .5), "p90": _quantile(lengths, .9)}
    if op == "duplicates":
        indexes = defaultdict(list)
        for i, (r, words) in enumerate(docs):
            indexes[tuple(words)].append(r.get("id", i))
        return [v for v in indexes.values() if len(v) > 1]
    if op == "label_conflicts":
        labels = defaultdict(set)
        for r, words in docs:
            if isinstance(r.get("label"), str):
                labels[tuple(words)].add(r["label"])
        return [{"text": " ".join(k), "labels": sorted(v)} for k, v in labels.items() if len(v) > 1]
    if op == "bigrams":
        grams = Counter(pair for _, words in docs for pair in zip(words, words[1:]))
        return [{"tokens": list(k), "count": grams[k]} for k in _rank(grams)]
    if op == "class_terms":
        terms = defaultdict(Counter)
        for r, words in docs:
            if isinstance(r.get("label"), str):
                terms[r["label"]].update(words)
        return {k: _rank(v)[:10] for k, v in terms.items()}
    query = payload.get("query", "")
    if not isinstance(query, str):
        raise ValueError("query must be text")
    q = set(_word_tokens(query))
    if op == "novel_terms":
        return sorted(q - doc_freq.keys())
    scores = []
    for i, (r, words) in enumerate(docs):
        tokens = set(words)
        if q & tokens:
            scores.append((len(q & tokens) / len(q | tokens), i, r))
    scores.sort(key=lambda t: (-t[0], t[1]))
    if op == "nearest":
        return [{"id": r.get("id", i), "similarity": s} for s, i, r in scores]
    votes = Counter()
    for s, _, r in scores[:5]:
        if isinstance(r.get("label"), str):
            votes[r["label"]] += s
    return _rank(votes)[0] if votes else None


def _revision(op, rows, payload):
    triples = [(r["original"], r["prediction"], r["label"]) for r in rows
               if all(isinstance(r.get(k), str) for k in ("original", "prediction", "label"))]
    changes = Counter()
    for old, new, label in triples:
        changes["fixed" if new == label and old != label else
                "broken" if new != label and old == label else
                "preserved" if new == label else "still_wrong"] += 1
    if op == "change_table":
        return dict(changes)
    if op == "net_gain":
        return changes["fixed"] - changes["broken"]
    if op == "repair_rate":
        return _ratio(changes["fixed"], changes["fixed"] + changes["still_wrong"])
    if op == "retention":
        return _ratio(changes["preserved"], changes["preserved"] + changes["broken"])
    if op == "correction_precision":
        return _ratio(changes["fixed"], sum(a != b for a, b, y in triples))
    if op == "churn":
        return _mean([a != b for a, b, y in triples])
    if op == "both_wrong_changed":
        return sum(a != b and a != y and b != y for a, b, y in triples)
    if op == "fixed_labels":
        return _counts(y for a, b, y in triples if a != y and b == y)
    if op == "regressed_labels":
        return _counts(y for a, b, y in triples if a == y and b != y)
    return [{"before": a, "after": b, "reference": y} for a, b, y in triples
            if a != b and b != y]


OPS = {}
META = {}


def _run(family, op, payload):
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    rows = payload.get("examples", [])
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("examples must be an array of objects")
    return family(op, rows, payload)


def _register(name, family, spec):
    for line in spec.strip().splitlines():
        op, description = line.split("|", 1)
        key = name + "." + op
        OPS[key] = partial(_run, family, op)
        META[key] = description


_register("classification", _classification, """
accuracy|Вычислить долю точных решений по эталонным меткам.
error_count|Сосчитать ошибочные решения среди размеченных примеров.
errors|Собрать фактические записи с неверными предсказаниями для следующего урока.
class_report|Построить показатели precision, recall, F1 и объёма выборки для каждой метки.
macro_f1|Сопоставить качество распознавания классов через их равный вклад в среднее F1.
balanced_accuracy|Вычислить среднюю полноту распознавания представленных эталонных классов.
weighted_f1|Рассчитать F1 с учётом реальной частоты каждой эталонной метки.
majority_accuracy|Определить долю успехов простейшего решения, всегда выбирающего частую метку.
kappa|Оценить согласие с разметкой с поправкой на случайные совпадения по коэффициенту каппа.
confusions|Найти и упорядочить фактические направления подмены одной метки другой.
""")
_register("numeric", _numeric, """
mae|Рассчитать среднюю абсолютную ошибку числового прогноза.
rmse|Измерить числовую ошибку с повышенным штрафом за крупные промахи.
median_error|Найти медианную абсолютную ошибку прогноза.
p90_error|Найти девяностый процентиль абсолютного отклонения от цели.
bias|Определить систематическое завышение или занижение результата.
within_tolerance|Измерить долю примеров, попавших в заданную абсолютную погрешность.
r_squared|Вычислить долю объяснённой вариации числовой цели.
pearson|Измерить линейную связь исходной оценки с целевой величиной.
relative_error|Вычислить среднюю относительную ошибку по ненулевым целям.
linear_fit|Обучить линейную поправку прогноза и вернуть наклон и свободный член.
""")
_register("calibration", _calibration, """
brier|Вычислить оценку Бриера для заявленной вероятности правильного решения.
log_loss|Оценить уверенные промахи логарифмической функцией потерь.
mean_confidence|Извлечь среднюю заявленную вероятность правильного решения.
signed_gap|Определить направление систематической переуверенности или недоуверенности.
reliability_bins|Построить десять диапазонов уверенности и вернуть заполненные с наблюдаемой точностью.
expected_gap|Рассчитать средневзвешенный разрыв калибровки по диапазонам вероятности.
max_bin_gap|Найти худший разрыв калибровки среди заполненных диапазонов.
coverage|Определить долю случаев, прошедших порог уверенности.
selective_accuracy|Измерить точность решений, прошедших порог уверенности.
confident_errors|Подсчитать случаи ошибочного решения с уверенностью не ниже порога.
""")
_register("edits", _edits, """
unchanged_fraction|Оценить долю исходных текстов, принятых пользователем без изменений.
length_delta|Определить среднее изменение числа символов после редактуры.
token_delta|Измерить среднее изменение числа слов после правки.
case_only|Отделить правки, затрагивающие только регистр текста.
space_only|Подсчитать правки, ограниченные изменением пробельных символов.
added_terms|Извлечь слова, которые пользователь вносит при редактировании.
removed_terms|Извлечь слова, которые пользователь убирает из предложенных формулировок.
replacement_rules|Выучить повторяющиеся замены фрагментов и вернуть количество примеров каждой.
retained_fraction|Определить долю исходных слов, оставленных при редактировании на согласованных местах.
net_terms|Получить баланс вставок и удалений по словам с учётом обратных правок.
""")
_register("preference", _preferences, """
win_count|Подсчитать, сколько раз выбирался каждый вариант в парных сравнениях.
loss_count|Подсчитать, сколько раз каждый вариант уступал сопернику.
win_fraction|Вычислить наблюдаемую долю побед каждого варианта.
laplace|Оценить вероятность выбора со сглаживанием Лапласа на малых выборках.
pair_votes|Собрать направленные голоса по непосредственно сравнивавшимся парам.
disagreement|Выявить пары вариантов, где пользователь делал противоположные выборы.
pair_margin|Вычислить перевес голосов для каждой сравнивавшейся пары.
copeland|Ранжировать варианты по числу выигранных и проигранных попарных противостояний.
condorcet|Найти вариант, непосредственно победивший любой другой в большинстве сравнений.
elo|Обновить рейтинги Эло последовательным проходом по истории предпочтений.
""")
_register("distribution", _distribution, """
histogram|Сосчитать наблюдения по эталонным меткам.
priors|Выучить априорные вероятности меток по их эмпирической частоте.
singletons|Выделить метки, имеющие только один обучающий пример.
majority|Найти все модальные метки с учётом ничьих.
imbalance|Рассчитать отношение частоты самого частого класса к самому редкому.
entropy|Измерить неопределённость разметки в битах энтропии Шеннона.
gini|Вычислить неоднородность набора примеров по индексу Джини.
class_weights|Выдать веса обратной частоты для балансирования последующего обучения.
transitions|Извлечь частоты переходов между последовательными эталонными метками.
discovery_curve|Восстановить моменты появления новых меток по порядку примеров.
""")
_register("context", _contexts, """
support|Оценить число учебных наблюдений в каждом контексте.
accuracy|Сравнить долю верных решений между контекстами.
worst|Найти контексты с минимальной наблюдаемой точностью.
disparity|Рассчитать размах точности между лучшим и худшим контекстами.
label_prior|Выучить отдельные априорные вероятности меток для каждого контекста.
conditional_error|Найти характерные для контекста направления путаницы меток.
numeric_bias|Выявить контексты систематического завышения или занижения числа.
style_preference|Извлечь зависимость парного выбора стиля от рабочей ситуации.
accuracy_interval|Построить приближённый 95-процентный интервал Вильсона для точности каждого контекста.
default_label|Выучить предсказание по умолчанию для каждого известного контекста.
""")
_register("time", _time, """
window_accuracy|Построить последовательность точности в скользящем окне.
window_change|Определить прирост или падение точности между двумя последними полными окнами.
cumulative|Построить траекторию накопленной точности по учебной истории.
longest_error_streak|Найти максимальную последовательность неудач без правильного решения.
since_last_error|Подсчитать успешные решения после последней ошибки.
first_success|Указать порядковый номер первого верного решения.
recovery_lengths|Измерить длины последовательностей ошибок, завершившихся восстановлением.
ewma_accuracy|Обновить оценку точности с экспоненциальным дисконтированием старых наблюдений.
label_drift|Измерить изменение частот меток между окнами расстоянием полной вариации.
novel_errors|Извлечь первое появление каждого нового направления ошибки.
""")
_register("lexical", _lexical, """
document_frequency|Индексировать число примеров, содержащих каждый термин.
idf|Рассчитать сглаженные IDF-веса для ранжирования терминов.
length_profile|Построить профиль длин текстов по среднему, медиане и девяностому процентилю.
duplicates|Найти группы примеров, совпадающих после токенизации и нормализации регистра.
label_conflicts|Выявить одинаковый нормализованный текст с противоречивыми эталонными метками.
bigrams|Извлечь частотные соседние пары токенов.
class_terms|Выучить десять наиболее частых терминов внутри каждого размеченного класса.
novel_terms|Выделить слова запроса, отсутствующие в учебном корпусе.
nearest|Найти похожие примеры по коэффициенту Жаккара множеств слов.
predict_label|Предсказать метку запроса взвешенными голосами пяти ближайших лексических примеров.
""")
_register("revision", _revision, """
change_table|Разбить парные результаты до и после изменения на исправления, поломки и стабильные исходы.
net_gain|Вычислить чистый прирост успешных решений после изменения алгоритма.
repair_rate|Оценить долю ранее ошибочных решений, доведённых до правильного результата.
retention|Измерить сохранность ранее правильных решений после изменения системы.
correction_precision|Измерить, какая часть всех изменившихся решений действительно исправила ошибку.
churn|Определить долю примеров, на которых обновление изменило ответную метку.
both_wrong_changed|Сосчитать изменения, когда прежняя ошибка сменилась другой ошибкой.
fixed_labels|Выявить эталонные классы, получившие исправления после обновления.
regressed_labels|Выявить эталонные классы, по которым утрачены прежние успешные ответы.
broken_changes|Извлечь изменившиеся и всё ещё неверные тройки для обучения на неудачных поправках.
""")


SAMPLE = {
    "examples": [
        {"id": "a", "text": "Тихое приветствие", "label": "личное", "prediction": "личное",
         "original": "афиша", "before": "Добрый вечер!", "after": "Тихий вечер.",
         "confidence": 0.85, "score": 0.8, "target": 1, "context": "чат",
         "chosen": "спокойный", "rejected": "энергичный"},
        {"id": "b", "text": "Начинается показ", "label": "афиша", "prediction": "личное",
         "original": "афиша", "before": "Сегодня премьера", "after": "Сегодня премьера!",
         "confidence": 0.90, "score": 0.4, "target": 0, "context": "кино",
         "chosen": "энергичный", "rejected": "спокойный"},
        {"id": "c", "text": "Тихий вечер", "label": "личное", "prediction": "личное",
         "original": "личное", "before": "Привет", "after": "Привет",
         "confidence": 0.70, "score": 0.9, "target": 1, "context": "чат",
         "chosen": "спокойный", "rejected": "энергичный"},
        {"id": "d", "text": "Тихое приветствие", "label": "афиша", "prediction": "афиша",
         "original": "личное", "before": "В зал", "after": "В  зал",
         "confidence": 0.60, "score": 0.2, "target": 0, "context": "кино",
         "chosen": "яркий", "rejected": "спокойный"}
    ],
    "query": "Тихое приветствие снова", "window": 2, "threshold": .8, "tolerance": .2
}
