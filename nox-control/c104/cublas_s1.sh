#!/bin/bash
echo "== find"; find / -xdev \( -name "cublas_v2.h" -o -name "libcublas.so*" \) 2>/dev/null | head -5
ls /usr/local/cuda/include | head -3; ls /usr/local/cuda/lib64 | grep -c .
echo "== apt"; apt-cache policy libcublas-dev-12-9 2>/dev/null | head -4; ls /etc/apt/sources.list.d | head; grep -rh nvidia /etc/apt/sources.list.d 2>/dev/null | head -2
