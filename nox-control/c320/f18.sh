#!/bin/bash
cat /root/nox/state/flash_bench/rt.out | cut -c1-330; tail -n 3 /root/nox/state/flash_bench/driver.log | cut -c1-200
