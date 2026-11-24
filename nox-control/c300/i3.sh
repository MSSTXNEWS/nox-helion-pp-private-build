grep -v "requires" /workspace/nox/invoke_install.log | cut -c1-250 | tail -25
cat /workspace/nox/invoke/lib/python3.10/site-packages/zz_nox_main.pth; /workspace/nox/invoke/bin/python -c "import numpy;print(numpy.__file__)" 2>&1|tail -1
