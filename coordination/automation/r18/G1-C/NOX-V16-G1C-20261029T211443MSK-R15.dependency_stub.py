"""Only a narrow, explicitly labelled test substitute for repo train_qlora.py.
This file is not a production dependency nor official code and does not attest QLoRA.
"""
PROFILES = {"ECO": {}, "BALANCED": {}, "INTENSIVE": {}}
def nvidia_smi(): raise AssertionError('nvidia_smi must be mocked')
def gpu_inventory(exe): raise AssertionError('gpu_inventory must be mocked')
def gpu_temperature(exe, uuid): raise AssertionError('gpu_temperature must be mocked')
def gpu_vram_headroom(exe, uuid, profile): raise AssertionError('gpu_vram_headroom must be mocked')
