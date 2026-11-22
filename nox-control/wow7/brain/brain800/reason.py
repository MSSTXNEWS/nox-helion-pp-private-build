"""Исследовательские операции NOX для чисел, графов, альтернатив и свидетельств."""
from __future__ import annotations

import math
import statistics as st
from collections import Counter, defaultdict, deque
from itertools import combinations

OPS = {}
META = {}
SAMPLES = {}

def operation(key, description, sample):
    def decorate(f):
        OPS[key] = f
        META[key] = description
        SAMPLES[key] = sample
        return f
    return decorate

def numbers(p):
    xs = list(map(float, p["values"]))
    if not xs or not all(map(math.isfinite, xs)):
        raise ValueError("values must contain finite numbers")
    return xs

def quant(xs, q):
    if not 0 <= q <= 1:
        raise ValueError("quantile must be in [0, 1]")
    xs = sorted(xs)
    a, r = divmod(q * (len(xs) - 1), 1)
    return xs[int(a)] * (1-r) + xs[min(int(a)+1, len(xs)-1)] * r

def mad(xs):
    m = st.median(xs)
    return st.median([abs(x-m) for x in xs])

def runs(xs):
    result = []
    for i,x in enumerate(xs):
        if result and result[-1]["value"] == x:
            result[-1]["length"] += 1
        else:
            result.append(dict(start=i,value=x,length=1))
    return result

def add(key,description,sample,f):
    operation(key,description,sample)(f)

N=dict(values=[8,10,12,8,30,33,28],q=.75,threshold=20,window=3,steps=2,offset=1)
def num(k,desc,fn):
    add(k,desc,N,lambda p: fn(numbers(p),p))

num("sample_summary","Сводит размер, минимум, максимум и среднее выборки.",lambda x,p:dict(count=len(x),minimum=min(x),maximum=max(x),mean=st.mean(x)))
num("empirical_quantile","Вычисляет интерполированный квантиль распределения.",lambda x,p:quant(x,p["q"]))
num("median_deviation","Оценивает разброс относительно медианы.",lambda x,p:mad(x))
num("interquartile_fences","Находит границы типичного разброса по межквартильному размаху.",lambda x,p:[quant(x,.25)-1.5*(quant(x,.75)-quant(x,.25)),quant(x,.75)+1.5*(quant(x,.75)-quant(x,.25))])
num("outlier_positions","Отмечает индексы наблюдений дальше трёх масштабированных медианных отклонений.",lambda x,p:[i for i,y in enumerate(x) if abs(y-st.median(x))>3*1.4826*mad(x)])
num("tail_mean","Оценивает среднее верхнего хвоста начиная с выбранного квантиля.",lambda x,p:st.mean(y for y in x if y>=quant(x,p["q"])))
num("value_runs","Разбивает последовательность на серии одинаковых значений.",lambda x,p:runs(x))
num("above_threshold_runs","Находит непрерывные периоды превышения границы.",lambda x,p:[r for r in runs([y>p["threshold"] for y in x]) if r["value"]])
num("trimmed_mean","Оценивает центр выборки после симметричного десятипроцентного усечения.",lambda x,p:st.mean(sorted(x)[len(x)//10:len(x)-len(x)//10]))
num("histogram_counts","Подсчитывает повторения каждого числового значения.",lambda x,p:[dict(value=y,count=n) for y,n in sorted(Counter(x).items())])

def window(p,x):
    w=int(p["window"])
    if not 1<=w<=len(x):
        raise ValueError("window must fit observations")
    return w

def rolling(x,p,f):
    w=window(p,x)
    return [f(x[i:i+w]) for i in range(len(x)-w+1)]

def fit(x):
    if len(x)<2:
        raise ValueError("slope requires at least two observations")
    return st.linear_regression(range(len(x)),x)

def moving_forecast(x,p):
    w=window(p,x)
    series=list(x)
    out=[]
    for i in range(int(p["steps"])):
        y=st.mean(series[-w:])
        series.append(y)
        out.append(y)
    return out

def shift_point(x):
    if len(x)<4: return None
    prefix=[0.0];squares=[0.0]
    for v in x:
        prefix.append(prefix[-1]+v)
        squares.append(squares[-1]+v*v)
    def loss(i,j):
        return max(0.0,squares[j]-squares[i]-(prefix[j]-prefix[i])**2/(j-i))
    n=len(x)
    k=min(range(2,n-1),key=lambda i:loss(0,i)+loss(i,n))
    return dict(split=k,before=st.mean(x[:k]),after=st.mean(x[k:]),reduction=loss(0,n)-loss(0,k)-loss(k,n))

num("adjacent_changes","Показывает изменение между последовательными наблюдениями.",lambda x,p:[b-a for a,b in zip(x,x[1:])])
num("window_average","Сглаживает историю средним по движущемуся окну.",lambda x,p:rolling(x,p,st.mean))
num("window_volatility","Отслеживает изменение волатильности ряда по окнам.",lambda x,p:rolling(x,p,st.pstdev))
num("linear_forecast","Продлевает линейный тренд на заданное число шагов.",lambda x,p:[fit(x).intercept+fit(x).slope*i for i in range(len(x),len(x)+int(p["steps"]))])
num("moving_forecast","Прогнозирует будущие шаги по последнему окну с рекурсивным обновлением.",moving_forecast)
num("turning_points","Находит локальные максимумы и минимумы во времени.",lambda x,p:[dict(index=i,kind="peak" if x[i]>x[i-1] else "valley") for i in range(1,len(x)-1) if (x[i]-x[i-1])*(x[i+1]-x[i])<0])
num("drawdown","Вычисляет максимальное абсолютное падение от прежнего пика.",lambda x,p:max(max(x[:i+1])-y for i,y in enumerate(x)))
num("single_regime_shift","Ищет границу двух режимов с минимальным суммарным квадратом ошибок.",lambda x,p:shift_point(x))
num("autocorrelation_at_lag","Сравнивает ряд с самим собой после временного сдвига.",lambda x,p:st.correlation(x[:-int(p["offset"])],x[int(p["offset"]):]))
num("last_value_backtest","Оценивает абсолютную ошибку прогноза следующим значением по предыдущему.",lambda x,p:st.mean(abs(b-a) for a,b in zip(x,x[1:])))

PAIR=dict(x=[1,2,3,4,5,6],y=[2,3,8,7,9,10],weights=[1,2,1,1,3,2],target=7)
def pair(k,desc,f):
    def run(p):
        a,b=[list(map(float,p[n])) for n in ("x","y")]
        if len(a)!=len(b) or not a: raise ValueError("x and y must have equal nonzero length")
        return f(a,b,p)
    add(k,desc,PAIR,run)

def ranks(x):
    return [sum(y<v for y in x)+(1+sum(y==v for y in x))/2 for v in x]

def weighted(a,w):
    if len(a)!=len(w) or any(i<0 for i in w) or sum(w)<=0:raise ValueError("invalid weights")
    return sum(v*k for v,k in zip(a,w))/sum(w)

def residuals(a,b):
    m,c=st.linear_regression(a,b)
    return [y-(m*x+c) for x,y in zip(a,b)]

pair("pearson_association","Оценивает линейную связь двух измеренных признаков.",lambda a,b,p:st.correlation(a,b))
pair("rank_association","Оценивает монотонную связь признаков по средним рангам.",lambda a,b,p:st.correlation(ranks(a),ranks(b)))
pair("pairwise_gain","Считает среднее попарное изменение результата.",lambda a,b,p:st.mean(y-x for x,y in zip(a,b)))
pair("weighted_gain","Оценивает изменение с учётом веса каждой пары.",lambda a,b,p:weighted([y-x for x,y in zip(a,b)],p["weights"]))
pair("paired_win_rate","Разделяет доли побед, ничьих и проигрышей второго варианта.",lambda a,b,p:dict(win=sum(y>x for x,y in zip(a,b))/len(a),tie=sum(y==x for x,y in zip(a,b))/len(a),loss=sum(y<x for x,y in zip(a,b))/len(a)))
pair("prediction_rmse","Вычисляет квадратичную ошибку прогнозов относительно наблюдений.",lambda a,b,p:math.sqrt(st.mean((x-y)**2 for x,y in zip(a,b))))
pair("prediction_bias","Определяет направление систематического смещения прогнозов относительно факта.",lambda a,b,p:dict(over=sum(x>y for x,y in zip(a,b)),under=sum(x<y for x,y in zip(a,b)),mean_forecast_minus_actual=st.mean(x-y for x,y in zip(a,b))))
pair("regression_residuals","Выделяет отклонения наблюдений от линейной модели.",lambda a,b,p:residuals(a,b))
pair("linear_target_estimate","Оценивает значение при заданном значении объясняющего признака.",lambda a,b,p:st.linear_regression(a,b).slope*p["target"]+st.linear_regression(a,b).intercept)
pair("leave_one_out_slopes","Проверяет чувствительность наклона к исключению каждой пары.",lambda a,b,p:[st.linear_regression(a[:i]+a[i+1:],b[:i]+b[i+1:]).slope for i in range(len(a))])

GRAPH=dict(edges=[["voice","mix"],["text","voice"],["text","subtitle"],["subtitle","mix"],["mix","show"]],start="text",end="show",blocked=["voice"])
def graphinfo(p):
    nodes=set()
    adj=defaultdict(set);rev=defaultdict(set)
    for a,b in p["edges"]:
        nodes.update((a,b));adj[a].add(b);rev[b].add(a)
    nodes.update(p.get("nodes",[]))
    return sorted(nodes),adj,rev

def reach(adj,a,blocked=()):
    if a in blocked:return {}
    dist={a:0};q=deque([a])
    while q:
        v=q.popleft()
        for w in sorted(adj[v]):
            if w not in dist and w not in blocked:
                dist[w]=dist[v]+1;q.append(w)
    return dist

def layers(nodes,adj,rev):
    done=set();out=[]
    while len(done)<len(nodes):
        row=[v for v in nodes if v not in done and rev[v]<=done]
        if not row:break
        out.append(row);done.update(row)
    return dict(layers=out,unresolved=sorted(set(nodes)-done))

def shortest(adj,start,end):
    q=deque([start]);parent={start:None}
    while q:
        v=q.popleft()
        if v==end:
            path=[]
            while v is not None:path.append(v);v=parent[v]
            return path[::-1]
        for w in sorted(adj[v]):
            if w not in parent:parent[w]=v;q.append(w)
    return []

def graph(k,d,f):
    add(k,d,GRAPH,lambda p:f(*graphinfo(p),p))
graph("possible_descendants","Ищет возможные следствия в заданной пользователем модели зависимостей.",lambda ns,a,r,p:sorted(set(reach(a,p["start"]))-{p["start"]}))
graph("possible_ancestors","Находит upstream-факторы, связанные с выбранным исходом.",lambda ns,a,r,p:sorted(set(reach(r,p["end"]))-{p["end"]}))
graph("shortest_explanation_path","Показывает кратчайшую цепочку между двумя заданными событиями.",lambda ns,a,r,p:shortest(a,p["start"],p["end"]))
graph("dependency_layers","Распределяет шаги по слоям готовности и показывает остаток при цикле.",lambda ns,a,r,p:layers(ns,a,r))
graph("mandatory_intermediates","Находит промежуточные узлы, без которых перестаёт существовать путь.",lambda ns,a,r,p:[v for v in ns if v not in (p["start"],p["end"]) and p["end"] in reach(a,p["start"]) and p["end"] not in reach(a,p["start"],[v])])
graph("blocked_impact","Считает, какие достижимые результаты исчезают после блокировки узлов.",lambda ns,a,r,p:sorted(set(reach(a,p["start"]))-set(reach(a,p["start"],p["blocked"]))))
graph("convergent_nodes","Находит этапы, где сходятся несколько непосредственных условий.",lambda ns,a,r,p:{v:sorted(r[v]) for v in ns if len(r[v])>1})
graph("branch_points","Показывает развилки влияния с несколькими непосредственными следствиями.",lambda ns,a,r,p:{v:sorted(a[v]) for v in ns if len(a[v])>1})
graph("cyclic_members","Находит узлы, принадлежащие направленным циклам зависимостей.",lambda ns,a,r,p:[v for v in ns if any(v in reach(a,w) for w in a[v])])
graph("shared_predecessors","Находит общие предшествующие факторы пары выбранных событий.",lambda ns,a,r,p:sorted((set(reach(r,p["start"])) & set(reach(r,p["end"])))-{p["start"],p["end"]}))

OPTIONS=dict(options={"fast":[7,3,8],"quiet":[5,8,9],"bright":[3,2,6]},weights=[.3,.5,.2],minima=[4,3,6],axis=1,target=[6,7,8])
def opt(k,d,f):
    def run(p):
        opts=p["options"];w=p["weights"]
        if not opts or not w or any(len(v)!=len(w) for v in opts.values()):raise ValueError("options must match weight count")
        if any(k<0 for k in w) or sum(w)<=0:raise ValueError("weights must be nonnegative with positive sum")
        return f(opts,w,p)
    add(k,d,OPTIONS,run)

def dominates(a,b):return all(x>=y for x,y in zip(a,b)) and any(x>y for x,y in zip(a,b))
def scores(o,w):return {k:weighted(v,w) for k,v in o.items()}
def argmax(d):return sorted(k for k,v in d.items() if v==max(d.values()))
def regret(o):
    best=[max(v[i] for v in o.values()) for i in range(len(next(iter(o.values()))))]
    return {k:max(a-b for a,b in zip(best,v)) for k,v in o.items()}
opt("weighted_preference","Ранжирует варианты по взвешенной полезности при сопоставимых шкалах.",lambda o,w,p:sorted(scores(o,w).items(),key=lambda i:(-i[1],i[0])))
opt("pareto_options","Выделяет недоминируемые варианты для критериев с предпочтением большего.",lambda o,w,p:[k for k,v in o.items() if not any(dominates(u,v) for u in o.values())])
opt("dominance_witness","Показывает для каждого слабого варианта, какие альтернативы превосходят его.",lambda o,w,p:{k:[j for j,u in o.items() if dominates(u,v)] for k,v in o.items()})
opt("maximin_option","Выбирает варианты с наиболее сильным худшим показателем.",lambda o,w,p:argmax({k:min(v) for k,v in o.items()}))
opt("scenario_regret","Оценивает максимальную упущенную полезность при смене главного критерия.",lambda o,w,p:regret(o))
opt("feasible_options","Отбирает варианты, одновременно выполняющие все минимальные требования.",lambda o,w,p:[k for k,v in o.items() if len(p["minima"])==len(v) and all(x>=m for x,m in zip(v,p["minima"]))])
opt("criterion_leaders","Находит лучшие варианты отдельно по каждому критерию с учётом ничьих.",lambda o,w,p:[argmax({k:v[i] for k,v in o.items()}) for i in range(len(w))])
opt("goal_distance","Оценивает расстояние до заданного целевого профиля в пространстве критериев.",lambda o,w,p:{k:math.dist(v,p["target"]) for k,v in o.items()})
opt("weight_omission","Проверяет, изменится ли победитель, если снять вес отдельного критерия.",lambda o,w,p:[argmax(scores(o,[v if j!=i else 0 for j,v in enumerate(w)])) if sum(w)-w[i]>0 else [] for i in range(len(w))])
opt("criterion_disagreement","Находит пары критериев, меняющие предпочтение между одними и теми же вариантами.",lambda o,w,p:[dict(a=a,b=b,criteria=[i,j]) for a,b in combinations(o,2) for i,j in combinations(range(len(w)),2) if (o[a][i]-o[b][i])*(o[a][j]-o[b][j])<0])

PROB=dict(prior={"buffer":.6,"synthesis":.4},likelihood={"buffer":.8,"synthesis":.2},predictions=[.1,.3,.6,.8],outcomes=[0,1,1,1],bins=4)
def normalized(d):
    if not d or any(v<0 or not math.isfinite(v) for v in d.values()) or sum(d.values())<=0:raise ValueError("invalid mass")
    return {k:v/sum(d.values()) for k,v in d.items()}
def entropy(d):return -sum(v*math.log2(v) for v in normalized(d).values() if v)
def prior(p):
    if set(p["prior"])!=set(p["likelihood"]) or any(not 0<=v<=1 for v in p["likelihood"].values()):
        raise ValueError("likelihood for each hypothesis must be in [0,1]")
    return normalized(p["prior"])
def post(p):return normalized({k:v*p["likelihood"][k] for k,v in prior(p).items()})
def evidence(p):return sum(v*p["likelihood"][k] for k,v in prior(p).items())
def probs(p):
    a=p["predictions"];b=p["outcomes"]
    if not a or len(a)!=len(b) or any(not 0<=v<=1 for v in a) or any(y not in (0,1) for y in b):raise ValueError("invalid binary prediction data")
    return list(zip(a,b))
def cal(p):
    groups=defaultdict(list);n=int(p["bins"])
    if n<1:raise ValueError("bins must be positive")
    for v,y in probs(p):groups[min(n-1,int(v*n))].append((v,y))
    return [dict(bin=k,n=len(g),predicted=st.mean(x for x,y in g),observed=st.mean(y for x,y in g)) for k,g in sorted(groups.items())]

for k,d,f in [
 ("posterior_hypotheses","Обновляет вероятности конкурирующих объяснений по заданным правдоподобиям.",post),
 ("evidence_probability","Оценивает предсказанную вероятность наблюдения смесью исходных гипотез.",evidence),
 ("information_gain_observed","Измеряет изменение неопределённости гипотез после конкретного свидетельства.",lambda p:entropy(prior(p))-entropy(post(p))),
 ("belief_revision","Показывает величину пересмотра по каждой гипотезе.",lambda p:{k:v-prior(p)[k] for k,v in post(p).items()}),
 ("effective_hypotheses","Оценивает эффективное число правдоподобных версий через энтропию.",lambda p:2**entropy(post(p))),
 ("missing_event_posterior","Пересчитывает распределение гипотез при ненаступлении ожидаемого события.",lambda p:post(dict(p,likelihood={k:1-v for k,v in p["likelihood"].items()}))),
 ("brier_binary","Оценивает качество вероятностных предсказаний бинарного исхода.",lambda p:st.mean((x-y)**2 for x,y in probs(p))),
 ("calibration_bins","Сопоставляет обещанную вероятность с наблюдаемой частотой по группам.",cal),
 ("threshold_confusion","Подсчитывает четыре типа исходов при переводе вероятности в бинарное решение.",lambda p:dict(Counter(("true_" if (x>=p.get("threshold",.5))==bool(y) else "false_")+("positive" if x>=p.get("threshold",.5) else "negative") for x,y in probs(p)))),
 ("uncertainty_order","Выбирает прогнозы, в которых бинарная неопределённость максимальна.",lambda p:sorted(range(len(probs(p))),key=lambda i:abs(p["predictions"][i]-.5)))
]:add(k,d,PROB,f)

SRC=dict(claims=[
 dict(id="a",topic="latency",source="log",origin="run1",stance="pro",date=2,scope="S1",confidence=.9),
 dict(id="b",topic="latency",source="forum",origin="run1",stance="pro",date=3,scope="S1",confidence=.5),
 dict(id="c",topic="latency",source="lab",origin="run2",stance="con",date=5,scope="S2",confidence=.8),
 dict(id="d",topic="voice",source="log",origin="run3",stance="pro",date=6,scope="S1",confidence=.6)],
 scope="S1",topics=["latency","voice","memory"],as_of=4)
def by(rows,key):
    out=defaultdict(list)
    for r in rows:out[r[key]].append(r)
    return dict(out)
def claim(k,d,f):add(k,d,SRC,lambda p:f(p["claims"],p))
def origin_votes(cs):
    out={}
    for topic,g in by(cs,"topic").items():
        origins=by(g,"origin")
        counts=Counter()
        for parts in origins.values():
            tags={s["stance"] for s in parts}
            counts[next(iter(tags)) if len(tags)==1 else "mixed"]+=1
        out[topic]=dict(counts)
    return out
claim("shared_origin_groups","Выявляет публикации, основанные на одном первоначальном наблюдении.",lambda c,p:{k:[v["id"] for v in vs] for k,vs in by(c,"origin").items() if len(vs)>1})
claim("independent_stances","Считает независимые источники за и против тезиса с учётом общего происхождения.",lambda c,p:origin_votes(c))
claim("scope_matched_claims","Отбирает свидетельства, чьи условия точно совпадают с заданными.",lambda c,p:[v["id"] for v in c if v["scope"]==p["scope"]])
claim("disputed_topics","Обнаруживает темы с явно противоположными свидетельствами.",lambda c,p:[k for k,g in by(c,"topic").items() if {"pro","con"}<={r["stance"] for r in g}])
claim("first_attestation","Восстанавливает наиболее раннюю датированную запись по каждому тезису.",lambda c,p:{k:min(g,key=lambda r:r["date"])["id"] for k,g in by(c,"topic").items()})
claim("as_of_evidence","Воссоздаёт набор свидетельств, доступный к заданной дате.",lambda c,p:[v["id"] for v in c if v["date"]<=p["as_of"]])
claim("uncovered_topics","Находит вопросы, для которых в подборке вообще отсутствует свидетельство.",lambda c,p:sorted(set(p["topics"])-{v["topic"] for v in c}))
claim("scope_dependence","Отмечает разные позиции для одного тезиса в разных условиях.",lambda c,p:[dict(topic=a["topic"],left=a["id"],right=b["id"]) for a,b in combinations(c,2) if a["topic"]==b["topic"] and a["scope"]!=b["scope"] and {a["stance"],b["stance"]}=={"pro","con"}])
claim("source_topic_coverage","Сопоставляет каждому источнику охваченные им вопросы.",lambda c,p:{k:sorted({v["topic"] for v in g}) for k,g in by(c,"source").items()})
claim("strongest_counterexample","Ищет самое уверенное явно отрицательное свидетельство по теме.",lambda c,p:{t:max(n,key=lambda v:v["confidence"])["id"] for t,g in by(c,"topic").items() if (n:=[v for v in g if v["stance"]=="con"])})

TRIAL=dict(rows=[
 dict(subject="a",group="A",stratum="mobile",value=7),dict(subject="b",group="A",stratum="desktop",value=9),
 dict(subject="c",group="A",stratum="mobile",value=13),dict(subject="a",group="B",stratum="mobile",value=10),
 dict(subject="b",group="B",stratum="desktop",value=12),dict(subject="d",group="B",stratum="desktop",value=11)],
 baseline="A",candidate="B",threshold=10)
def trial(k,d,f):
    def run(p):
        gs=by(p["rows"],"group")
        return f(gs[p["baseline"]],gs[p["candidate"]],p)
    add(k,d,TRIAL,run)
def avg(g):return st.mean(v["value"] for v in g)
def strata(a,b):
    x,y=by(a,"stratum"),by(b,"stratum")
    return {k:avg(y[k])-avg(x[k]) for k in sorted(x.keys()&y.keys())}
def matched(a,b):
    x,y=by(a,"subject"),by(b,"subject")
    return {k:avg(y[k])-avg(x[k]) for k in sorted(x.keys()&y.keys())}
def unpaired_delta(a,b):
    return avg(b)-avg(a)
def wins(a,b):
    return sum((int(y["value"]>x["value"])+.5*int(y["value"]==x["value"])) for x in a for y in b)/(len(a)*len(b))
def margin(a,b):
    import itertools
    seq=[v["value"] for v in a+b];n=len(a);observed=abs(unpaired_delta(a,b))
    count=math.comb(len(seq),n)
    if count>100000:raise ValueError("exact permutation enumeration exceeds 100000 subsets")
    total=sum(seq);large=0
    for group in itertools.combinations(seq,n):
        s=sum(group)
        large+=abs((total-s)/len(b)-s/n)>=observed-1e-12
    return large/count
trial("between_group_difference","Оценивает разницу средних у двух опытных групп.",lambda a,b,p:unpaired_delta(a,b))
trial("subject_matched_difference","Измеряет эффект отдельно у участников, присутствующих в обеих группах.",lambda a,b,p:matched(a,b))
trial("per_stratum_difference","Показывает эффект внутри сопоставимых подгрупп.",lambda a,b,p:strata(a,b))
trial("balanced_strata_effect","Даёт одинаковый вес представленным в обеих группах слоям.",lambda a,b,p:st.mean(strata(a,b).values()))
trial("case_mix_shift","Измеряет сдвиг состава подгрупп между сравниваемыми выборками.",lambda a,b,p:{k:sum(v["stratum"]==k for v in b)/len(b)-sum(v["stratum"]==k for v in a)/len(a) for k in sorted({v["stratum"] for v in a+b})})
trial("missing_pairs","Находит участников, для которых отсутствует парное наблюдение.",lambda a,b,p:sorted({v["subject"] for v in a}^{v["subject"] for v in b}))
trial("common_language_effect","Оценивает долю превосходящих попарных сравнений с половинным весом ничьей.",lambda a,b,p:wins(a,b))
trial("pass_rate_difference","Сравнивает долю прохождения указанного порога в двух группах.",lambda a,b,p:st.mean(v["value"]>=p["threshold"] for v in b)-st.mean(v["value"]>=p["threshold"] for v in a))
trial("simpson_reversal","Обнаруживает смену направления общего эффекта относительно всех общих слоёв.",lambda a,b,p:bool(strata(a,b)) and all(d*unpaired_delta(a,b)<0 for d in strata(a,b).values()))
trial("permutation_probability","Перебирает допустимые перестановки независимых групп для двусторонней вероятности эффекта.",lambda a,b,p:margin(a,b))

EV=dict(events=[dict(t=0,kind="open",actor="browser"),dict(t=2,kind="request",actor="gateway"),dict(t=4,kind="token",actor="model"),dict(t=6,kind="play",actor="browser"),dict(t=11,kind="request",actor="gateway"),dict(t=14,kind="token",actor="model")],before="request",after="token",cut=5,max_gap=4,window=5,pattern=["request","token"])
def ev(k,d,f):add(k,d,EV,lambda p:f(sorted(p["events"],key=lambda e:e["t"]),p))
def pair_events(es,p):
    wait=deque();out=[]
    for v in es:
        if v["kind"]==p["after"] and wait:
            first=wait.popleft()
            out.append(dict(start=first["t"],end=v["t"],delta=v["t"]-first["t"]))
        if v["kind"]==p["before"]:wait.append(v)
    return out
def burst(es,w):
    if w<=0:raise ValueError("window must be positive")
    if not es:return None
    best=(-1,0)
    j=0
    for i,v in enumerate(es):
        while j<len(es) and es[j]["t"]<v["t"]+w:j+=1
        if j-i>best[0]:best=(j-i,v["t"])
    return dict(start=best[1],events=best[0])
ev("stage_waits","Извлекает интервалы от начала до подтверждения по очереди событий.",pair_events)
ev("long_silences","Находит промежутки между соседними событиями длиннее заданной паузы.",lambda e,p:[dict(start=a["t"],end=b["t"],duration=b["t"]-a["t"]) for a,b in zip(e,e[1:]) if b["t"]-a["t"]>p["max_gap"]])
ev("handoff_counts","Подсчитывает переходы работы между разными участниками цепочки.",lambda e,p:[dict(sender=a,receiver=b,count=n) for (a,b),n in Counter((a["actor"],b["actor"]) for a,b in zip(e,e[1:]) if a["actor"]!=b["actor"]).items()])
ev("peak_event_window","Ищет самый насыщенный событиями интервал фиксированной длины.",lambda e,p:burst(e,p["window"]))
ev("event_pattern_positions","Находит все точные вхождения цепочки типов событий в хронологию.",lambda e,p:[i for i in range(len(e)-len(p["pattern"])+1) if p["pattern"] and [r["kind"] for r in e[i:i+len(p["pattern"])]]==p["pattern"]])
ev("last_actor_observations","Восстанавливает последние видимые действия участников к выбранному моменту.",lambda e,p:{v["actor"]:v for v in e if v["t"]<=p["cut"]})
ev("actor_active_spans","Вычисляет интервалы между первым и последним наблюдением каждого участника.",lambda e,p:{k:g[-1]["t"]-g[0]["t"] for k,g in by(e,"actor").items()})
ev("interarrival_by_type","Показывает интервалы повторения каждого типа события.",lambda e,p:{k:[b["t"]-a["t"] for a,b in zip(g,g[1:])] for k,g in by(e,"kind").items()})
ev("simultaneous_observations","Выделяет моменты, чьи события нельзя упорядочить по имеющимся меткам времени.",lambda e,p:{str(t):g for t,g in by(e,"t").items() if len(g)>1})
ev("event_state_changes","Называет, какие типы появились впервые или исчезли после временной границы.",lambda e,p:dict(only_before=sorted({v["kind"] for v in e if v["t"]<=p["cut"]}-{v["kind"] for v in e if v["t"]>p["cut"]}),only_after=sorted({v["kind"] for v in e if v["t"]>p["cut"]}-{v["kind"] for v in e if v["t"]<=p["cut"]})))

PLAN=dict(tasks=[dict(id="text",duration=2,deps=[],owner="author"),dict(id="voice",duration=4,deps=["text"],owner="actor"),dict(id="sub",duration=2,deps=["text"],owner="editor"),dict(id="mix",duration=1,deps=["voice","sub"],owner="editor")],done=["text"],target="mix",factor=2,task="voice",deadline=9)
def times(p):
    ts={v["id"]:v for v in p["tasks"]}
    if len(ts)!=len(p["tasks"]):raise ValueError("duplicate task")
    if any(v["duration"]<0 or set(v["deps"])-ts.keys() for v in ts.values()):raise ValueError("invalid duration or dependency")
    finish={};start={}
    while len(finish)<len(ts):
        ready=[k for k,v in ts.items() if k not in finish and set(v["deps"])<=finish.keys()]
        if not ready:raise ValueError("cyclic task graph")
        for k in ready:
            start[k]=max((finish[j] for j in ts[k]["deps"]),default=0)
            finish[k]=start[k]+ts[k]["duration"]
    lf={};ls={}
    end=max(finish.values(),default=0)
    for k in reversed(finish):
        lf[k]=min((ls[j] for j,v in ts.items() if k in v["deps"]),default=end)
        ls[k]=lf[k]-ts[k]["duration"]
    return ts,start,finish,{k:ls[k]-start[k] for k in ts}
def schedule(k,d,f):add(k,d,PLAN,lambda p:f(*times(p),p))
def changed(p):
    q=dict(p,tasks=[dict(t,duration=t["duration"]*p["factor"]) if t["id"]==p["task"] else t for t in p["tasks"]])
    return max(times(q)[2].values(),default=0)
schedule("earliest_schedule","Строит ранние начало и завершение шагов по зависимостям без лимитов исполнителей.",lambda t,s,f,l,p:{k:dict(start=s[k],finish=f[k]) for k in t})
schedule("critical_operations","Выделяет операции с нулевым резервом при текущих длительностях.",lambda t,s,f,l,p:[k for k,v in l.items() if abs(v)<1e-12])
schedule("task_slack","Вычисляет запас задержки каждого шага без переноса общего финиша.",lambda t,s,f,l,p:l)
schedule("ready_tasks","Выбирает ещё не завершённые операции, чьи предварительные условия уже выполнены.",lambda t,s,f,l,p:[k for k,v in t.items() if k not in p["done"] and set(v["deps"])<=set(p["done"])])
schedule("deadline_margin","Оценивает запас времени до указанного срока по графу работ.",lambda t,s,f,l,p:p["deadline"]-max(f.values(),default=0))
schedule("duration_sensitivity","Пересчитывает срок завершения после изменения длительности одной операции.",lambda t,s,f,l,p:dict(before=max(f.values(),default=0),after=changed(p)))
schedule("owner_load","Группирует требуемое рабочее время по ответственным.",lambda t,s,f,l,p:{o:sum(v["duration"] for v in g) for o,g in by(t.values(),"owner").items()})
schedule("resource_overlap","Обнаруживает параллельные задачи одного ответственного в раннем расписании.",lambda t,s,f,l,p:[dict(first=a,second=b,overlap=min(f[a],f[b])-max(s[a],s[b])) for a,b in combinations(t,2) if t[a]["owner"]==t[b]["owner"] and min(f[a],f[b])>max(s[a],s[b])])
schedule("parallelism_bound","Оценивает средний требуемый параллелизм для достижения раннего финиша.",lambda t,s,f,l,p:sum(v["duration"] for v in t.values())/max(f.values()) if any(f.values()) else 0)
schedule("remaining_blockers","Показывает непосредственные незавершённые предпосылки выбранной задачи.",lambda t,s,f,l,p:sorted(set(t[p["target"]]["deps"])-set(p["done"])))
