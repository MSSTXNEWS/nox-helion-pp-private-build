#!/bin/bash
cd /root/nox/state/flash_bench
grep -E ' E |error|fail|abort|assert' B_mtp3.srv.log | head -6 | cut -c1-260; tail -n 3 B_mtp3.srv.log | cut -c1-200
echo ---; grep -E ' E |error|fail|abort|assert|CUDA' C_np4_kvu_ngl40.srv.log | tail -5 | cut -c1-260
