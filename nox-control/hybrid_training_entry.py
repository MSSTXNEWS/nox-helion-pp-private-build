#!/usr/bin/env python3
"""Bounded continuation of the existing t866u trainer on the original GPU1.

Keeps its native HF loader and training corpus. Fixes adapter precision after
TRL construction, uses one optimizer lineage, and never merges/promotes a model.
The existing Supervisor remains the only process supervisor.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import sys
import tempfile
import time
import types

ROOT = Path('/root/nox')
NATIVE = ROOT / 'scripts/train_qlora_35b_t866u.py'
OUTPUT = ROOT / 'lora/qlora_t866u/runs_owner_hybrid'
STOP_PATHS = (ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag', ROOT / '.stop',
              Path('/workspace/NOX_STOP'), ROOT / 'program/STOP',
              ROOT / 'state/TRAIN_HOLD.flag', ROOT / 'state/TRAIN_PAUSE_REQUEST.flag')
SHA = re.compile(r'^[0-9a-f]{64}$')
SCHEMA = 'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1'
STOP_REQUESTED = False


def atomic_json(path: Path, data: dict) -> None:
    if path.is_symlink():
        raise RuntimeError('HOLD_OUTPUT_SYMLINK')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.owner-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as file:
            os.chmod(tmp, 0o600)
            json.dump(data, file, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
            file.write('\n'); file.flush(); os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as file:
        for part in iter(lambda: file.read(4 * 1024 * 1024), b''): h.update(part)
    return h.hexdigest()


def json_sha(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stop_active() -> bool:
    return STOP_REQUESTED or any(p.exists() or p.is_symlink() for p in STOP_PATHS)


def check_stop() -> None:
    if stop_active(): raise RuntimeError('HOLD_TRAINING_STOP_REQUESTED')


def signal_stop(signum, frame) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def cpu_threads() -> int:
    count = min(4, len(os.sched_getaffinity(0)))
    try:
        quota, period = Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if quota != 'max': count = min(count, max(1, int(quota) // int(period)))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    try: count = min(count, max(1, int(os.environ.get('OMP_NUM_THREADS', '4'))))
    except ValueError: pass
    return max(1, count)


def load_native(path: Path, expected: str):
    if path != NATIVE or path.is_symlink() or not path.is_file() or not SHA.fullmatch(expected):
        raise RuntimeError('HOLD_NATIVE_TRAINER_PATH_OR_SHA')
    if file_sha(path) != expected: raise RuntimeError('HOLD_NATIVE_TRAINER_SOURCE_CHANGED')
    spec = importlib.util.spec_from_file_location('nox_existing_t866u', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if file_sha(path) != expected: raise RuntimeError('HOLD_NATIVE_TRAINER_SOURCE_CHANGED')
    return module


def fp32_adapters(model, torch, *, convert: bool) -> dict:
    """Never cast the NF4 base or replace Parameter objects after optimizer init."""
    names, count = [], 0
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad: continue
        if 'lora_' not in name:
            raise RuntimeError('HOLD_UNEXPECTED_TRAINABLE_BASE_PARAMETER')
        if parameter.device.type != 'cuda':
            raise RuntimeError('HOLD_TRAINABLE_ADAPTER_NOT_ON_GPU1')
        if parameter.dtype != torch.float32:
            if not convert: raise RuntimeError('HOLD_ADAPTER_DTYPE_CHANGED')
            parameter.data = parameter.data.to(dtype=torch.float32)
        if parameter.grad is not None and parameter.grad.dtype != torch.float32:
            raise RuntimeError('HOLD_ADAPTER_GRADIENT_NOT_FP32')
        names.append((name, list(parameter.shape)))
        count += parameter.numel()
    if not names: raise RuntimeError('HOLD_NO_TRAINABLE_ADAPTERS')
    return {'trainable_tensors': len(names), 'trainable_parameters': count,
            'target_schema_sha256': json_sha(names), 'trainable_dtype': 'float32'}


def tensor_sha(model, torch) -> str:
    result = hashlib.sha256()
    for name, parameter in sorted(model.named_parameters(), key=lambda x: x[0]):
        if not parameter.requires_grad: continue
        value = parameter.detach().to(device='cpu', dtype=torch.float32).contiguous()
        if not bool(torch.isfinite(value).all().item()):
            raise RuntimeError('HOLD_NONFINITE_ADAPTER_TENSOR')
        result.update(name.encode()); result.update(json_sha(list(value.shape)).encode())
        result.update(value.numpy().tobytes())
    return result.hexdigest()


def optimizer_fp32(trainer, torch) -> None:
    if trainer.optimizer is None: raise RuntimeError('HOLD_OPTIMIZER_NOT_CREATED')
    count = 0
    for group in trainer.optimizer.param_groups:
        for p in group['params']:
            if not p.requires_grad: continue
            count += 1
            if p.dtype != torch.float32 or (p.grad is not None and p.grad.dtype != torch.float32):
                raise RuntimeError('HOLD_OPTIMIZER_PARAMETER_OR_GRAD_NOT_FP32')
    if count == 0: raise RuntimeError('HOLD_OPTIMIZER_HAS_NO_TRAINABLE_PARAMETERS')


def base_identity(path: Path) -> dict:
    if not path.is_dir(): raise RuntimeError('HOLD_ORIGINAL_HF_BASE_MISSING')
    files = {}
    for name in ('config.json', 'tokenizer_config.json', 'tokenizer.json',
                 'model.safetensors.index.json'):
        p = path / name
        if p.is_file(): files[name] = file_sha(p)
    if 'config.json' not in files or 'tokenizer_config.json' not in files:
        raise RuntimeError('HOLD_ORIGINAL_HF_CONFIG_MISSING')
    shards = sorted(path.glob('*.safetensors'))
    if not shards: raise RuntimeError('HOLD_ORIGINAL_HF_SHARDS_MISSING')
    # Stable file metadata detects local mutation on continuation; this is not
    # mislabeled as a cryptographic proof of the full 35B base tensor contents.
    return {'path': str(path), 'metadata_sha256': files,
            'shards': [{'name': p.name, 'bytes': p.stat().st_size,
                        'mtime_ns': p.stat().st_mtime_ns} for p in shards],
            'full_base_tensor_sha_verified': False}


def complete_checkpoint(path: Path) -> int:
    if path.is_symlink() or not path.is_dir(): raise RuntimeError('HOLD_CHECKPOINT_PATH')
    for name in ('trainer_state.json', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt',
                 'adapter_config.json', 'adapter_model.safetensors'):
        p = path / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size <= 0:
            raise RuntimeError('HOLD_INCOMPLETE_OPTIMIZER_CHECKPOINT')
    data = json.loads((path / 'trainer_state.json').read_text())
    step = data.get('global_step')
    if type(step) is not int or step < 1 or path.name != f'checkpoint-{step}':
        raise RuntimeError('HOLD_CHECKPOINT_GLOBAL_STEP')
    return step


def checkpoint_record(path: Path) -> dict:
    step = complete_checkpoint(path)
    names = ('trainer_state.json', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt',
             'adapter_config.json', 'adapter_model.safetensors')
    return {'path': str(path), 'global_step': step,
            'files_sha256': {name: file_sha(path / name) for name in names}}


def select_resume(output: Path, requested: bool) -> tuple[Path | None, int]:
    existing = list(output.glob('checkpoint-*')) if output.exists() else []
    if existing and not requested: raise RuntimeError('HOLD_RESUME_REQUIRED_EXISTING_CHECKPOINT')
    if not requested: return None, 0
    if not existing: raise RuntimeError('HOLD_RESUME_CHECKPOINT_MISSING')
    steps = [(complete_checkpoint(p), p) for p in existing]
    step, path = max(steps)
    return path, step


def build_existing_trainer(native, model, tokenizer, dataset, planned: int, torch):
    """Retain native TRL compatibility path; override its configuration only."""
    import trl
    # SFTTrainer must retain its real module-level config class for isinstance
    # checks. Returning that class also keeps training_args.bin pickleable.
    import trl.trainer.sft_trainer as sft_module
    _ = trl.SFTTrainer
    original_config = trl.SFTConfig
    if sft_module.SFTConfig is not original_config:
        raise RuntimeError('HOLD_NATIVE_SFT_CONFIG_CLASS_MISMATCH')
    bounded = dict(output_dir=str(OUTPUT), per_device_train_batch_size=1,
                   gradient_accumulation_steps=1, max_length=256,
                   max_steps=planned, fp16=True, bf16=False, packing=False,
                   gradient_checkpointing=True,
                   gradient_checkpointing_kwargs={'use_reentrant': False},
                   dataloader_num_workers=0, logging_steps=1,
                   save_steps=planned, save_total_limit=None,
                   warmup_steps=3, learning_rate=1e-4,
                   optim='paged_adamw_8bit', lr_scheduler_type='cosine',
                   report_to=[])
    def bounded_config(*args, **kwargs):
        kwargs.update(bounded)
        return original_config(*args, **kwargs)
    try:
        trl.SFTConfig = bounded_config
        trainer = native.build_trainer(model, tokenizer, dataset, False, planned)
    finally:
        trl.SFTConfig = original_config
    if (type(trainer.args) is not original_config or any(
            getattr(trainer.args, key, object()) != value for key, value in bounded.items())):
        raise RuntimeError('HOLD_NATIVE_TRAINER_CONFIG_NOT_APPLIED')
    # TRL may cast adapters during SFTTrainer construction even with fp16=True.
    fp32_adapters(trainer.model, torch, convert=True)
    original_create = trainer.create_optimizer
    def create_optimizer(self):
        fp32_adapters(self.model, torch, convert=False)
        result = original_create()
        optimizer_fp32(self, torch)
        return result
    trainer.create_optimizer = types.MethodType(create_optimizer, trainer)
    if trainer.optimizer is not None: optimizer_fp32(trainer, torch)
    original_compute_loss = trainer.compute_loss
    def compute_loss(self, *args, **kwargs):
        result = original_compute_loss(*args, **kwargs)
        loss = result[0] if isinstance(result, tuple) else result
        if not bool(torch.isfinite(loss.detach()).all().item()):
            raise RuntimeError('HOLD_NONFINITE_MICROBATCH_LOSS')
        return result
    trainer.compute_loss = types.MethodType(compute_loss, trainer)
    return trainer


def run(args) -> dict:
    check_stop()
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '1':
        raise RuntimeError('HOLD_PHYSICAL_GPU1_VISIBILITY_REQUIRED')
    if not 1 <= args.max_steps <= args.planned_steps <= 50000:
        raise RuntimeError('HOLD_BOUNDED_STEP_PLAN')
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    threads = cpu_threads()
    os.environ['OMP_NUM_THREADS'] = str(threads)
    os.environ['MKL_NUM_THREADS'] = str(threads)
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    lockpath = ROOT / 'state/forge_training.lock'
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    lock = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    # Keep fd alive until process exit; duplicates fail before loading Torch/base.
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM, signal_stop); signal.signal(signal.SIGINT, signal_stop)
    native = load_native(Path(args.native_script), args.native_sha)
    parent = native.OUT
    if OUTPUT.parent != parent: raise RuntimeError('HOLD_NATIVE_OUTPUT_ROOT_CHANGED')
    output_existed = OUTPUT.exists()
    if OUTPUT.is_symlink(): raise RuntimeError('HOLD_OUTPUT_SYMLINK')
    resume, start_step = select_resume(OUTPUT, args.resume)
    if args.max_steps <= start_step: raise RuntimeError('HOLD_REQUESTED_STEP_ALREADY_COMPLETE')
    lineage_path = OUTPUT / 'owner_lineage.json'
    if output_existed and not args.resume and not args.recover_unstarted:
        raise RuntimeError('HOLD_EXISTING_RUN_USE_VERIFIED_RESUME')
    before_base = base_identity(native.HF)
    preparation_path = OUTPUT / 'owner_preparation.json'
    preparation = {'schema': SCHEMA, 'native_sha256': args.native_sha,
                   'base': before_base, 'planned_steps': args.planned_steps}
    previous_preparation = None
    if args.recover_unstarted:
        if args.resume: raise RuntimeError('HOLD_RECOVERY_MODE_CONFLICT')
        allowed = {'owner_preparation.json', 'training_text.jsonl', 'owner_lineage.json'}
        if any(p.name not in allowed or not p.is_file() or p.is_symlink()
               for p in OUTPUT.iterdir()):
            raise RuntimeError('HOLD_RECOVERY_HAS_TRAINING_OR_UNKNOWN_ARTIFACTS')
        if preparation_path.is_file():
            previous_preparation = json.loads(preparation_path.read_text())
            if {k: previous_preparation.get(k) for k in preparation} != preparation:
                raise RuntimeError('HOLD_RECOVERY_PREPARATION_CHANGED')
        elif any(OUTPUT.iterdir()):
            raise RuntimeError('HOLD_RECOVERY_PREPARATION_MISSING')
    OUTPUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not args.resume and previous_preparation is None:
        atomic_json(preparation_path, preparation)
    random.seed(42)
    # Freeze the existing selected training corpus on this private server for an
    # exact continuation. It is not exported into receipts, source, or chat.
    dataset_path = OUTPUT / 'training_text.jsonl'
    old = json.loads(lineage_path.read_text()) if args.resume else None
    if args.recover_unstarted and lineage_path.is_file():
        old = json.loads(lineage_path.read_text())
    if args.resume:
        if not dataset_path.is_file() or file_sha(dataset_path) != old.get('dataset_sha256'):
            raise RuntimeError('HOLD_CONTINUATION_DATASET_CHANGED')
        if old.get('base') != before_base or old.get('native_sha256') != args.native_sha:
            raise RuntimeError('HOLD_CONTINUATION_BASE_OR_SOURCE_CHANGED')
    check_stop()
    import torch
    if (not torch.cuda.is_available() or torch.cuda.device_count() != 1 or
        tuple(torch.cuda.get_device_capability(0)) != (7, 0)):
        raise RuntimeError('HOLD_V100_RUNTIME')
    torch.set_num_threads(threads)
    torch.manual_seed(42)
    # Retain original native.main's allocator cap, which load_model alone omits.
    torch.cuda.set_per_process_memory_fraction(0.91, 0)
    native.write_hb({'phase': 'loading_owner_hybrid', 'step': start_step,
                     'loss': None, 'training_mode': 'QLORA_NF4_FP16',
                     'output': str(OUTPUT), 'max_steps': args.max_steps})
    model, tokenizer = native.load_model(12)
    check_stop()
    fp32_adapters(model, torch, convert=True)
    model.config.use_cache = False
    from datasets import Dataset
    if args.resume or (args.recover_unstarted and dataset_path.is_file()):
        expected_dataset_sha = (old or previous_preparation or {}).get('dataset_sha256')
        if file_sha(dataset_path) != expected_dataset_sha:
            raise RuntimeError('HOLD_RECOVERY_DATASET_CHANGED')
        texts = [json.loads(line) for line in dataset_path.read_text().splitlines()]
    else:
        rows = native.load_train_rows()
        if len(rows) < 50: raise RuntimeError('HOLD_NATIVE_TRAINING_DATA_TOO_SMALL')
        texts = [{'text': tokenizer.apply_chat_template(row['messages'], tokenize=False,
                                                        add_generation_prompt=False)}
                 for row in rows]
        with dataset_path.open('x', encoding='utf8') as file:
            os.chmod(dataset_path, 0o600)
            for row in texts: file.write(json.dumps(row, ensure_ascii=False) + '\n')
            file.flush(); os.fsync(file.fileno())
        atomic_json(preparation_path, {**preparation, 'dataset_sha256': file_sha(dataset_path)})
    trainer = build_existing_trainer(native, model, tokenizer, Dataset.from_list(texts),
                                      args.planned_steps, torch)
    targets = fp32_adapters(trainer.model, torch, convert=False)
    if getattr(trainer.accelerator, 'scaler', None) is None:
        raise RuntimeError('HOLD_FP16_GRADSCALER_NOT_PRESENT')
    config = {'gpu_weight_budget_gib': 12, 'max_length': 256, 'micro_batch': 1,
              'accumulation': 1, 'planned_steps': args.planned_steps,
              'learning_rate': 1e-4, 'warmup_steps': 3, 'scheduler': 'cosine',
              'optimizer': 'paged_adamw_8bit', 'precision': 'fp16',
              'amp_scaler_state_required': True,
              'adapter_parameter_dtype': 'float32', 'allocator_fraction': 0.91, 'seed': 42}
    lineage = {'schema': SCHEMA, 'native_sha256': args.native_sha,
               'base': before_base, 'dataset_sha256': file_sha(dataset_path),
               'targets': targets, 'training_config': config}
    if old is not None:
        if old != lineage: raise RuntimeError('HOLD_CONTINUATION_LINEAGE_CHANGED')
        # The Trainer resumes adapter/optimizer/scheduler/RNG itself before
        # on_train_begin. This initial hash is superseded there after restore.
    else:
        atomic_json(lineage_path, lineage)
    from transformers import TrainerCallback
    state = {'before_tensor_sha256': None, 'loss': None, 'successful_optimizer_steps': 0,
             'skipped_optimizer_steps': 0, 'last_save_at': time.monotonic(),
             'checkpoint': None, 'stop_requested': False}
    class Progress(TrainerCallback):
        def on_train_begin(self, a, s, c, **kw):
            check_stop(); fp32_adapters(trainer.model, torch, convert=False)
            optimizer_fp32(trainer, torch)
            state['before_tensor_sha256'] = tensor_sha(trainer.model, torch)
            return c
        def on_step_begin(self, a, s, c, **kw):
            state['stop_requested'] |= stop_active()
            fp32_adapters(trainer.model, torch, convert=False)
            return c
        def on_substep_end(self, a, s, c, **kw):
            state['stop_requested'] |= stop_active()
            optimizer_fp32(trainer, torch); return c
        def on_pre_optimizer_step(self, a, s, c, **kw):
            state['stop_requested'] |= stop_active()
            optimizer_fp32(trainer, torch); return c
        def on_step_end(self, a, s, c, **kw):
            skipped = bool(trainer.accelerator.optimizer_step_was_skipped)
            state['skipped_optimizer_steps' if skipped else 'successful_optimizer_steps'] += 1
            # Finish at most the current accumulation=1 optimizer step, then
            # persist optimizer/scheduler/RNG before ending a graceful STOP.
            stop = stop_active() or state['stop_requested']
            if s.global_step == start_step + 1 or s.global_step >= args.max_steps or stop or time.monotonic()-state['last_save_at'] >= 300:
                c.should_save = True
            if s.global_step >= args.max_steps or stop:
                c.should_training_stop = True
                state['stop_requested'] = stop
            return c
        def on_log(self, a, s, c, logs=None, **kw):
            value = (logs or {}).get('loss')
            if value is not None:
                value = float(value)
                if not math.isfinite(value): raise RuntimeError('HOLD_NONFINITE_TRAINING_LOSS')
                state['loss'] = value
            native.write_hb({'phase': 'train_owner_hybrid', 'step': s.global_step,
                             'loss': state['loss'], 'max_steps': args.max_steps,
                             'successful_optimizer_steps': state['successful_optimizer_steps'],
                             'skipped_optimizer_steps': state['skipped_optimizer_steps'],
                             'trainable_dtype': 'float32', 'output': str(OUTPUT)})
            return c
        def on_save(self, a, s, c, **kw):
            checkpoint = OUTPUT / f'checkpoint-{s.global_step}'
            state['checkpoint'] = checkpoint_record(checkpoint)
            state['last_save_at'] = time.monotonic()
            receipt = {'schema': SCHEMA, 'native_sha256': args.native_sha,
                       'lineage_sha256': json_sha(lineage), 'start_step': start_step,
                       'global_step': s.global_step, 'loss': state['loss'],
                       'successful_optimizer_steps': state['successful_optimizer_steps'],
                       'skipped_optimizer_steps': state['skipped_optimizer_steps'],
                       'before_tensor_sha256': state['before_tensor_sha256'],
                       'after_tensor_sha256': tensor_sha(trainer.model, torch),
                       'checkpoint': state['checkpoint'], 'merged': False,
                       'live_promoted': False, 'external_restore_verified': False}
            receipt['adapter_delta_verified'] = receipt['before_tensor_sha256'] != receipt['after_tensor_sha256']
            atomic_json(OUTPUT / f'owner_receipt_step_{s.global_step}.json', receipt)
            return c
    trainer.add_callback(Progress())
    check_stop()
    trainer.train(resume_from_checkpoint=str(resume) if resume else None)
    final_step = int(trainer.state.global_step)
    checkpoint = OUTPUT / f'checkpoint-{final_step}'
    complete_checkpoint(checkpoint)
    receipt_path = OUTPUT / f'owner_receipt_step_{final_step}.json'
    result = json.loads(receipt_path.read_text())
    if (result['successful_optimizer_steps'] < 1 or result['loss'] is None or
        not result['adapter_delta_verified'] or final_step <= start_step):
        raise RuntimeError('HOLD_NO_FINITE_VERIFIED_OPTIMIZER_DELTA')
    result['state'] = 'CHECKPOINTED_OWNER_STOP' if state['stop_requested'] else 'VERIFIED_BOUNDED_ADAPTER_UPDATE'
    result['requested_step'] = args.max_steps
    native.write_hb({'phase': result['state'], 'step': final_step,
                     'loss': result['loss'], 'max_steps': args.max_steps,
                     'checkpoint': str(checkpoint), 'adapter_delta_verified': True,
                     'live_promoted': False})
    atomic_json(OUTPUT / 'owner_last_result.json', result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-script', default=str(NATIVE))
    parser.add_argument('--native-sha', required=True)
    parser.add_argument('--max-steps', type=int, default=5)
    parser.add_argument('--planned-steps', type=int, default=1000)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--recover-unstarted', action='store_true',
                        help='Reuse verified preparation only when no checkpoint/optimizer artifact exists')
    args = parser.parse_args()
    try:
        result = run(args)
        print('NOX_HYBRID_RESULT=' + json.dumps(result, separators=(',', ':')), flush=True)
        return 0
    except Exception as exc:
        code = str(exc)
        reason = code if re.fullmatch(r'HOLD_[A-Z0-9_]+', code) else type(exc).__name__
        # The existing wrapper also latches HOLD to suppress dispatcher storms.
        print('NOX_HYBRID_FAILURE=' + reason, flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
