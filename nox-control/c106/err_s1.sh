#!/bin/bash
sed -n 8,22p /root/nox/logs/build_llama.log | cut -c1-260
