#!/usr/bin/env python3
"""NOX local RU/ES emotion sidecar for the EXISTING CognitiveOverlay.

Optional CPU text classifier: NO remote API, NO auto-download, NO model
weights altered. Requires pre-downloaded approved model weights in local NOX
paths. Emotion labels are observations about text tone, NOT user diagnoses and
NOT claims that the assistant subjectively feels these emotions.
"""
from pathlib import Path
import math

ROOTS=(Path("/root/nox"),Path("/tmp/nox"),Path("/dev/shm/nox"))
ALLOWED={
  "ru": "cointegrated/rubert-tiny2-cedr-emotion-detection",
  "es": "UMUTeam/MarIA-emotion-es",
}
LABELS={
  "joy":"joy","sadness":"sadness","anger":"anger","fear":"fear",
  "surprise":"surprise","disgust":"disgust","neutral":"neutral",
  "no emotion":"neutral","no_emotion":"neutral",
}
MAX_CHARS=2200


def _safe_dir(folder: str)->bool:
    if not isinstance(folder,str) or not folder or not Path(folder).is_absolute():
        return False
    p=Path(folder).resolve(strict=False)
    return (any(root==p or root in p.parents for root in ROOTS)
            and p.is_dir() and (p/"config.json").is_file()
            and not p.is_symlink())


class LocalEmotionClassifier:
    def __init__(self,model_dir:str,*,language:str,source_model_id:str):
        if language not in ALLOWED or source_model_id!=ALLOWED[language]:
            raise ValueError("HOLD_UNAPPROVED_EMOTION_MODEL")
        if not _safe_dir(model_dir):
            raise ValueError("HOLD_EMOTION_MODEL_NOT_LOCAL")
        self.model_dir=model_dir
        self.language=language
        self.source_model_id=source_model_id
        self.model=None
        self.tokenizer=None
        self.torch=None

    def load(self):
        """All model file reads are local_files_only; CPU chosen to protect A100."""
        try:
            import torch
            from transformers import AutoTokenizer,AutoModelForSequenceClassification
        except ImportError:
            raise RuntimeError("HOLD_TORCH_OR_TRANSFORMERS_NOT_INSTALLED")
        self.tokenizer=AutoTokenizer.from_pretrained(self.model_dir,
                local_files_only=True,trust_remote_code=False)
        self.model=AutoModelForSequenceClassification.from_pretrained(self.model_dir,
                local_files_only=True,trust_remote_code=False)
        self.model.to("cpu")
        self.model.eval()
        self.torch=torch
        return self

    def __call__(self,text:str,language:str)->dict:
        if language!=self.language or not isinstance(text,str) or not text.strip():
            return {"label":"uncertain","confidence":0.0,
                    "model_id":self.source_model_id}
        if self.model is None or self.tokenizer is None or self.torch is None:
            return {"label":"uncertain","confidence":0.0,
                    "model_id":self.source_model_id}
        encoded=self.tokenizer(text[:MAX_CHARS],return_tensors="pt",
                               truncation=True,max_length=256)
        with self.torch.no_grad():
            logits=self.model(**encoded).logits[0]
            if language=="ru":
                scores=self.torch.sigmoid(logits)
            else:
                scores=self.torch.softmax(logits,dim=-1)
        probabilities=scores.tolist()
        index=max(range(len(probabilities)),key=probabilities.__getitem__)
        raw=str(self.model.config.id2label.get(index,"")).casefold()
        label=LABELS.get(raw,"uncertain")
        score=float(probabilities[index])
        if not math.isfinite(score) or not 0.0<=score<=1.0:
            label="uncertain";score=0.0
        return {"label":label,"confidence":score,"model_id":self.source_model_id,
                "classification":"text_tone_not_diagnosis"}
