#!/bin/bash
cat /root/nox/logs/mtp_ab.log; tail -2 /root/nox/logs/mtp_build.log | cut -c1-120
