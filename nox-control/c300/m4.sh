#!/bin/bash
sed -n 415,500p /root/nox/web_server.py | cut -c1-260
sed -n 136,145p /root/nox/repo/nox-control/qs6/memory_layer.py | cut -c1-200; sed -n 38,50p /root/nox/repo/nox-control/qs6/memory_layer.py | cut -c1-200
