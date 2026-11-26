#!/bin/bash
G=/workspace/nox/advisors/gateway.py
sed -n 83,92p $G | cut -c1-200; sed -n 135,222p $G | cut -c1-330; sed -n 296,311p $G | cut -c1-200
