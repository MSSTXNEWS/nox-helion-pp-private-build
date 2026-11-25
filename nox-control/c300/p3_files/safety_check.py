"""ops/draw/safety_check.py (P3): проверка изображения после генерации. Готовые модели: Falconsai/nsfw_image_detection (ViT, Apache-2.0) и nateraw/vit-age-classifier (Apache-2.0).
Печатает JSON-строку {"nsfw":p,"ages":{...},"block":bool,"why":...}. Блок: nsfw>0.5 И возрастная метка 0-2/3-9/10-19 с p>0.30 (признак несовершеннолетнего).
Неотключаемое правило; ошибка модели = сообщение error (вызывающий код при наличии моделей не выдаёт изображение)."""
import sys, json, os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
D = "/workspace/nox/models/flux"
try:
    import torch; torch.set_num_threads(2)
    from transformers import pipeline
    from PIL import Image
    im = Image.open(sys.argv[1]).convert("RGB")
    n = pipeline("image-classification", model=D + "/nsfw_image_detection", device=-1)
    nsfw = {x["label"].lower(): x["score"] for x in n(im)}.get("nsfw", 0.0)
    a = pipeline("image-classification", model=D + "/vit-age-classifier", device=-1)
    ages = {x["label"]: round(x["score"], 3) for x in a(im, top_k=8)}
    minor = sum(v for k, v in ages.items() if k in ("0-2", "3-9", "10-19"))
    block = nsfw > 0.5 and minor > 0.30
    print(json.dumps({"nsfw": round(nsfw, 3), "minor_p": round(minor, 3), "ages": ages, "block": block, "why": "NSFW и признаки несовершеннолетнего" if block else ""}))
except Exception as e:
    print(json.dumps({"error": "%s: %s" % (type(e).__name__, str(e)[:150]), "block": False}))
