#!/bin/bash
grep -nE "error|Error|CMake|CUDA|nvcc|Could not|not found|Built target" /root/nox/logs/build_llama.log | head -25 | cut -c1-200
ls /root/nox/llama.cpp/build/bin | head -20; nvcc --version | tail -2
