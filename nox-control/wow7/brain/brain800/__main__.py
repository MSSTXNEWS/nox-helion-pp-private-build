"""One JSON request on stdin. Usage: python -m brain800 /path/to/state.sqlite3."""
import json
import sys
import os
from .kernel import Kernel,pack

def main():
    try:
        try:
            import resource
        except ImportError:
            pass
        else:
            resource.setrlimit(resource.RLIMIT_CPU,(7,8))
            cap=512*1024**2
            _,hard=resource.getrlimit(resource.RLIMIT_AS)
            resource.setrlimit(resource.RLIMIT_AS,(min(cap,hard) if hard>=0 else cap,hard))
        raw=sys.stdin.buffer.read(120001)
        if len(raw)>120000:raise ValueError("Запрос слишком большой")
        req=json.loads(raw)
        kernel=Kernel(sys.argv[1])
        from . import life
        scope,token=req.get("scope",""),req.get("token","")
        if "life" in req:
            if not scope or scope=="default" or len(scope)>200:raise ValueError("Нужен идентификатор беседы")
            if req["life"]=="teach":
                os.environ["OPENBLAS_NUM_THREADS"]="1"
                os.environ["OMP_NUM_THREADS"]="1"
            result=life.supervise(kernel,scope,token,req["life"],req.get("data",{}))
        elif "suggest" in req:
            # One BLAS thread on the shared S1; import the optional ML runtime lazily.
            os.environ["OPENBLAS_NUM_THREADS"]="1"
            os.environ["OMP_NUM_THREADS"]="1"
            from .suggest import suggest
            result=suggest(kernel,req["suggest"],req.get("data"),scope)
        elif "find" in req:
            term=req["find"].strip().casefold()
            result=[{"op":k,"description":v} for k,v in kernel.meta.items() if term in (k+" "+v).casefold()][:40]
        else:
            op,data=req["op"],req.get("data",{})
            try:
                result=kernel.run(op,data,scope,token)
            except (ValueError,TypeError,KeyError):
                if op in kernel.meta:life.experience(kernel,scope,token,op,data,None,False)
                raise
            life.experience(kernel,scope,token,op,data,result,True)
        print(pack({"ok":True,"result":result}))
    except Exception as error:
        print(pack({"ok":False,"error":f"{type(error).__name__}: {error}"}))
        return 1
    return 0
if __name__=="__main__":sys.exit(main())
