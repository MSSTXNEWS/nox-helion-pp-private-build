#!/bin/bash
find /root/nox/dl/hf/piper_ru /root/nox -name '*.onnx' 2>/dev/null | grep -iE "ru_RU|/ru/" | head; echo ==; grep -rn "NOX_PIPER_MODEL_RU" /root/nox/boot_s1.sh /root/onstart.sh /root/nox/*.sh 2>/dev/null | cut -c1-200
