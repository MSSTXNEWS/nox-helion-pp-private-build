/workspace/nox/venv/bin/python -c "
import sys,torch,numpy,typing_extensions;print(torch.__file__,numpy.__file__,typing_extensions.__file__);print([p for p in sys.path][:8])"
/workspace/nox/invoke/bin/python -c "import sys;print(sys.path)"
ls /workspace/nox/venv/lib/python3.10/site-packages | head -3; cat /workspace/nox/venv/pyvenv.cfg
