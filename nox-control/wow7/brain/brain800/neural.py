"""A 10,000-parameter local action router, with an optional low-rank head.

Rows of X are encoder features in the exact order identified by the encoder
fingerprint. Labels index the ordered operation catalog. The output is a
proposal; callers enforce authorization and argument validation separately.
NumPy is the only dependency. No model server or network connection is used.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np


INPUT_DIM = 119
HIDDEN_DIM = 10
OUTPUT_DIM = 800
PARAM_COUNT = INPUT_DIM * HIDDEN_DIM + HIDDEN_DIM + HIDDEN_DIM * OUTPUT_DIM + OUTPUT_DIM
FORMAT_VERSION = 1
_SHAPES = {"W1": (INPUT_DIM, HIDDEN_DIM), "b1": (HIDDEN_DIM,),
           "W2": (HIDDEN_DIM, OUTPUT_DIM), "b2": (OUTPUT_DIM,)}


def _fingerprint(obj):
    data = json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def catalog_fingerprint(ordered_ids):
    """Catalog order is part of the identity: neuron i means ordered_ids[i]."""
    ids = list(ordered_ids)
    if (len(ids) != OUTPUT_DIM or not all(isinstance(i, str) and i for i in ids)
            or len(set(ids)) != OUTPUT_DIM):
        raise ValueError("The catalog must have 800 unique nonempty string identifiers")
    return _fingerprint({"kind": "brain800.action-order.v1", "ids": ids})


def encoder_fingerprint(config):
    """Hash the encoder's version, vocabulary, feature layout and preprocessing."""
    return _fingerprint({"kind": "brain800.feature-order.v1", "config": config})


def _features(x):
    try:
        source = np.asarray(x)
        if source.dtype.kind not in "iuf":
            raise ValueError("Features must contain real numbers")
        values = source.astype(np.float64, copy=False)
    except (TypeError, OverflowError) as exc:
        raise ValueError("Features must contain real numbers") from exc
    if values.ndim == 1:
        values = values[None, :]
    if (values.ndim != 2 or values.shape[1] != INPUT_DIM or values.shape[0] == 0
            or not np.isfinite(values).all()):
        raise ValueError("Expected nonempty finite feature matrix of shape (N,119)")
    return values


def _mask(allowed, n):
    if allowed is None:
        return None
    mask = np.asarray(allowed)
    if mask.dtype.kind != "b":
        raise ValueError("Allowed operations must be a boolean mask")
    if mask.shape == (OUTPUT_DIM,):
        mask = np.broadcast_to(mask, (n, OUTPUT_DIM))
    if mask.shape != (n, OUTPUT_DIM) or not mask.any(axis=1).all():
        raise ValueError("Every row must allow at least one of the 800 operations")
    return mask


def _learning_rate(lr):
    if isinstance(lr, (bool, np.bool_)) or not isinstance(lr, (float, int, np.number)):
        raise ValueError("Learning rate must be a positive finite real number")
    try:
        lr = float(lr)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid learning rate") from exc
    if not np.isfinite(lr) or lr <= 0:
        raise ValueError("Learning rate must be positive and finite")
    return lr


def _targets(y, n):
    labels = np.asarray(y)
    if labels.ndim == 0:
        labels = labels.reshape(1)
    if labels.shape != (n,) or labels.dtype.kind not in "iu":
        raise ValueError("Labels must be N integer indices")
    if (labels < 0).any() or (labels >= OUTPUT_DIM).any():
        raise ValueError("Label outside action catalog")
    return labels.astype(np.intp)


def _row_weights(sample_weight, n):
    if sample_weight is None:
        return np.full(n, 1.0 / n)
    raw = np.asarray(sample_weight)
    if raw.dtype.kind not in "iuf":
        raise ValueError("Weights must be numeric")
    values = raw.astype(np.float64, copy=False)
    if (values.shape != (n,) or not np.isfinite(values).all() or (values < 0).any()
            or not (values > 0).any()):
        raise ValueError("Expected N finite nonnegative weights with positive total")
    scaled = values / values.max()
    return scaled / scaled.sum()


def _stored_array(archive, name, shape):
    array = archive[name]
    if array.dtype != np.dtype("float64") or array.shape != shape or not np.isfinite(array).all():
        raise ValueError("Invalid checkpoint tensor: " + name)
    return array.copy()


def _identity(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Catalog and encoder fingerprints must be nonempty strings")
    return value


class Router:
    """119 input features -> 10 tanh features -> 800 logits, including biases."""
    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, np.sqrt(2 / (INPUT_DIM + HIDDEN_DIM)), _SHAPES["W1"])
        self.b1 = np.zeros(HIDDEN_DIM)
        self.W2 = rng.normal(0, np.sqrt(2 / (HIDDEN_DIM + OUTPUT_DIM)), _SHAPES["W2"])
        self.b2 = np.zeros(OUTPUT_DIM)
        self.A = None
        self.B = None
        self.alpha = None
        self.steps = 0

    @property
    def lora_rank(self):
        return 0 if self.A is None else self.A.shape[1]

    @property
    def trainable_parameters(self):
        return PARAM_COUNT if self.A is None else self.A.size + self.B.size

    def _head(self):
        if self.A is None:
            return self.W2
        return self.W2 + (self.alpha / self.lora_rank) * (self.A @ self.B)

    def _forward(self, x):
        with np.errstate(over="raise", invalid="raise"):
            hidden = np.tanh(x @ self.W1 + self.b1)
            logits = hidden @ self._head() + self.b2
        if not np.isfinite(logits).all():
            raise ValueError("Non-finite activations")
        return hidden, logits

    def logits(self, X, allowed=None):
        x = _features(X)
        mask = _mask(allowed, len(x))
        _, scores = self._forward(x)
        return scores if mask is None else np.where(mask, scores, -np.inf)

    def predict(self, X, allowed=None):
        """Return one allowed index per input row. Ties use the first index."""
        return self.logits(X, allowed).argmax(axis=1)

    def _objective(self, X, y, allowed, sample_weight):
        x = _features(X)
        n = len(x)
        rows = np.arange(n)
        labels, mask = _targets(y, n), _mask(allowed, n)
        if mask is not None and not mask[rows, labels].all():
            raise ValueError("A training label is excluded by its allowed mask")
        weights = _row_weights(sample_weight, n)
        h, raw = self._forward(x)
        scores = raw if mask is None else np.where(mask, raw, -np.inf)
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            shifted = scores - scores.max(axis=1, keepdims=True)
            exp = np.exp(shifted)
            sums = exp.sum(axis=1)
            losses = np.log(sums) - shifted[rows, labels]
            loss = float(weights @ losses)
            grad = exp / sums[:, None]
            grad[rows, labels] -= 1
            grad *= weights[:, None]
        if not np.isfinite(loss):
            raise ValueError("Non-finite cross-entropy")
        return loss, x, h, grad

    def loss(self, X, y, allowed=None, sample_weight=None):
        return self._objective(X, y, allowed, sample_weight)[0]

    def _apply(self, gradients, lr):
        # Stage all tensors so arithmetic failure never applies half an update.
        updated = {}
        with np.errstate(over="raise", invalid="raise"):
            for key, grad in gradients.items():
                value = getattr(self, key) - lr * grad
                if not np.isfinite(value).all():
                    raise ValueError("Non-finite gradient update")
                updated[key] = value
        for key, value in updated.items():
            setattr(self, key, value)
        self.steps += 1

    def train_batch(self, X, y, lr=.05, allowed=None, sample_weight=None):
        """One mean-cross-entropy SGD step over all 10,000 base parameters."""
        if self.A is not None:
            raise ValueError("An adapter is active; use train_lora_batch or merge_lora")
        lr = _learning_rate(lr)
        loss, x, h, grad = self._objective(X, y, allowed, sample_weight)
        with np.errstate(over="raise", invalid="raise"):
            pre = (grad @ self.W2.T) * (1 - h * h)
            gradients = {"W1": x.T @ pre, "b1": pre.sum(axis=0),
                         "W2": h.T @ grad, "b2": grad.sum(axis=0)}
        self._apply(gradients, lr)
        return loss

    def enable_lora(self, rank=4, alpha=None, seed=0):
        """Initialize W_eff = W2 + alpha/r * A@B; zero B preserves logits."""
        if self.A is not None:
            raise ValueError("An adapter is already active")
        if type(rank) is not int or not 1 <= rank <= HIDDEN_DIM:
            raise ValueError("LoRA rank must be an integer in [1,10]")
        scale = rank if alpha is None else _learning_rate(alpha)
        a = np.random.default_rng(seed).normal(0, HIDDEN_DIM ** -.5, (HIDDEN_DIM, rank))
        self.A, self.B, self.alpha = a, np.zeros((rank, OUTPUT_DIM)), float(scale)
        return self

    def train_lora_batch(self, X, y, lr=.05, allowed=None, sample_weight=None):
        """One SGD step on A and B only. W1,b1,W2,b2 remain bit-identical."""
        if self.A is None:
            raise ValueError("Enable a LoRA adapter first")
        lr = _learning_rate(lr)
        loss, _, h, grad = self._objective(X, y, allowed, sample_weight)
        with np.errstate(over="raise", invalid="raise"):
            head_grad = (h.T @ grad) * (self.alpha / self.lora_rank)
            gradients = {"A": head_grad @ self.B.T, "B": self.A.T @ head_grad}
        self._apply(gradients, lr)
        return loss

    def merge_lora(self):
        if self.A is None:
            raise ValueError("No adapter to merge")
        with np.errstate(over="raise", invalid="raise"):
            merged = self._head()
        if not np.isfinite(merged).all():
            raise ValueError("Non-finite merged weights")
        self.W2 = merged
        self.A = self.B = self.alpha = None
        return self

    def save(self, path, catalog_fingerprint, encoder_fingerprint):
        """Atomically replace the named npz checkpoint in its destination directory."""
        manifest = {"format": "nox.brain800.router", "version": FORMAT_VERSION,
                    "catalog": _identity(catalog_fingerprint), "encoder": _identity(encoder_fingerprint),
                    "steps": self.steps, "rank": self.lora_rank, "alpha": self.alpha}
        tensors = {k: getattr(self, k) for k in _SHAPES}
        if self.A is not None:
            tensors.update(A=self.A, B=self.B)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="." + path.name + ".", suffix=".tmp",
                                         dir=path.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                np.savez_compressed(tmp, metadata=np.array(json.dumps(manifest)), **tensors)
                tmp.flush()
                os.fsync(tmp.fileno())
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        try:
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)

    @classmethod
    def load(cls, path, catalog_fingerprint, encoder_fingerprint):
        """Refuse mismatched operation order, encoder identity or incompatible shapes."""
        catalog = _identity(catalog_fingerprint)
        encoder = _identity(encoder_fingerprint)
        with np.load(path, allow_pickle=False) as store:
            raw = store["metadata"]
            if raw.shape != () or raw.dtype.kind != "U":
                raise ValueError("Invalid checkpoint metadata")
            meta = json.loads(raw.item())
            if (not isinstance(meta, dict) or meta.get("format") != "nox.brain800.router"
                    or meta.get("version") != FORMAT_VERSION):
                raise ValueError("Unsupported checkpoint format/version")
            if meta.get("catalog") != catalog or meta.get("encoder") != encoder:
                raise ValueError("Checkpoint catalog or encoder fingerprint mismatch")
            rank, steps = meta.get("rank"), meta.get("steps")
            if type(rank) != int or not 0 <= rank <= HIDDEN_DIM or type(steps) != int or steps < 0:
                raise ValueError("Invalid adapter rank or training step")
            expected_keys = set(_SHAPES) | {"metadata"} | ({"A", "B"} if rank else set())
            if set(store.files) != expected_keys:
                raise ValueError("Checkpoint tensors disagree with its metadata")
            result = cls()
            for name, shape in _SHAPES.items():
                setattr(result, name, _stored_array(store, name, shape))
            if rank:
                result.alpha = _learning_rate(meta.get("alpha"))
                result.A = _stored_array(store, "A", (HIDDEN_DIM, rank))
                result.B = _stored_array(store, "B", (rank, OUTPUT_DIM))
            elif meta.get("alpha") is not None:
                raise ValueError("Unexpected scaling on a checkpoint without LoRA")
            result.steps = steps
        return result
