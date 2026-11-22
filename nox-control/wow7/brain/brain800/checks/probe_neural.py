"""Check analytic gradients, frozen-base LoRA, masks, NPZ and rejected inputs.

Run: python probe_neural.py /path/to/brain800
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

import numpy as np


def expect_error(fn):
    try:
        fn()
    except (ValueError, FloatingPointError, OverflowError, TypeError):
        return
    raise AssertionError("Invalid input unexpectedly accepted")


def finite_difference(router, x, y, mask, weights, method, keys):
    """Compare independent central differences to actual SGD displacements."""
    epsilon = 1e-5
    points = []
    for name, index in keys:
        tensor = getattr(router, name)
        original = tensor[index]
        tensor[index] = original + epsilon
        high = router.loss(x, y, mask, weights)
        tensor[index] = original - epsilon
        low = router.loss(x, y, mask, weights)
        tensor[index] = original
        points.append((name, index, original, (high - low) / (2 * epsilon)))
    lr = .01
    method(x, y, lr=lr, allowed=mask, sample_weight=weights)
    errors = []
    for name, index, original, numerical in points:
        actual = (original - getattr(router, name)[index]) / lr
        np.testing.assert_allclose(actual, numerical, rtol=2e-5, atol=1e-8)
        errors.append(abs(actual - numerical))
    return max(errors)


def verify(brain_dir):
    sys.path.insert(0, str(brain_dir))
    import neural as nn
    rng = np.random.default_rng(928)
    x = rng.normal(size=(6, nn.INPUT_DIM))
    y = np.array([3, 9, 42, 9, 42, 3])
    mask = np.zeros((6, nn.OUTPUT_DIM), bool)
    mask[:, [3, 9, 42, 70]] = True
    mask[1, 3] = False
    weights = np.array([1, 2, 3, 2, 1, 2])
    cat = nn.catalog_fingerprint([str(i) for i in range(800)])
    enc = nn.encoder_fingerprint({"vocab": ["проект", "правка"], "version": 1})
    assert cat != nn.catalog_fingerprint([str(i) for i in reversed(range(800))])
    assert enc == nn.encoder_fingerprint({"version": 1, "vocab": ["проект", "правка"]})
    router = nn.Router(seed=17)
    assert router.trainable_parameters == sum(getattr(router, k).size for k in ("W1", "b1", "W2", "b2")) == 10000
    assert np.array_equal(router.logits(x), nn.Router(seed=17).logits(x))
    np.testing.assert_array_equal(np.isfinite(router.logits(x, mask)), mask)
    assert mask[np.arange(6), router.predict(x, mask)].all()
    base_error = finite_difference(router, x, y, mask, weights, router.train_batch,
                                   [("W1",(18,2)), ("b1",(3,)), ("W2",(4,9)), ("b2",(42,))])
    start = router.loss(x, y, mask, weights)
    for _ in range(12):
        router.train_batch(x, y, .1, mask, weights)
    end = router.loss(x, y, mask, weights)
    assert end < start

    # Failure must not partially modify parameters or advance the step counter.
    before = router.logits(x)
    steps = router.steps
    expect_error(lambda: router.train_batch(x, [800] * 6))
    expect_error(lambda: router.train_batch(x, [5] * 6, allowed=mask))
    expect_error(lambda: router.train_batch(x, y, lr=float("nan")))
    expect_error(lambda: router.train_batch(x, y, allowed=mask.astype(int)))
    expect_error(lambda: router.train_batch(x, y, sample_weight=[0] * 6))
    expect_error(lambda: router.logits(np.full((1,119), np.nan)))
    expect_error(lambda: router.logits(np.zeros(120)))
    expect_error(lambda: router.logits(x, np.zeros(800, bool)))
    assert router.steps == steps
    np.testing.assert_array_equal(before, router.logits(x))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "router.npz"
        router.save(path, cat, enc)
        np.testing.assert_array_equal(nn.Router.load(path, cat, enc).logits(x), before)
        expect_error(lambda: nn.Router.load(path, cat, "another encoder"))
        expect_error(lambda: nn.Router.load(path, "different action order", enc))
        expect_error(lambda: router.enable_lora(rank=0))
        expect_error(lambda: router.enable_lora(rank=11))
        lora_error = 0.
        merge_error = 0.
        for rank in range(1, 11):
            model = nn.Router(seed=29)
            base = {k: getattr(model, k).copy() for k in ("W1", "b1", "W2", "b2")}
            initial = model.logits(x)
            model.enable_lora(rank, alpha=rank * 2.5, seed=1)
            assert model.trainable_parameters == rank * (10 + 800)
            np.testing.assert_array_equal(initial, model.logits(x))
            expect_error(lambda: model.train_batch(x, y))
            initial_loss = model.loss(x, y, mask)
            model.train_lora_batch(x, y, .1, mask)
            # A starts random and B zero. Check nontrivial gradients after B moves.
            lora_error = max(lora_error, finite_difference(model, x, y, mask, weights,
                    model.train_lora_batch, [("A",(2,0)), ("B",(0,42)), ("B",(0,70))]))
            assert model.loss(x, y, mask) < initial_loss
            for k, v in base.items():
                np.testing.assert_array_equal(v, getattr(model, k))
            model.save(path, cat, enc)
            loaded = nn.Router.load(path, cat, enc)
            assert loaded.lora_rank == rank and loaded.steps == 2
            live = model.logits(x)
            np.testing.assert_array_equal(loaded.logits(x), live)
            # Check the mathematical sum against direct two-branch evaluation.
            h = np.tanh(x @ base["W1"] + base["b1"])
            parallel = initial + (model.alpha / rank) * ((h @ model.A) @ model.B)
            np.testing.assert_allclose(live, parallel, rtol=1e-12, atol=1e-12)
            loaded.merge_lora()
            np.testing.assert_array_equal(loaded.logits(x), live)
            merge_error = max(merge_error, np.max(np.abs(loaded.logits(x) - parallel)))
            assert loaded.trainable_parameters == 10000 and loaded.lora_rank == 0
    return {"pass": True, "base_parameters": nn.PARAM_COUNT, "ranks_checked": 10,
            "cross_entropy_before": start, "cross_entropy_after": end,
            "base_max_gradient_error": base_error, "lora_max_gradient_error": lora_error,
            "merge_max_absolute_error": merge_error}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_directory", type=Path)
    print(json.dumps(verify(parser.parse_args().module_directory.resolve()), indent=2))
