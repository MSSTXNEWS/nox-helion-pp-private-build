echo "C300: ac_liger1"
D=/workspace/nox/tmp/liger_ab; mkdir -p $D
V=/workspace/nox/venv/bin/python
$V -m pip install -q --no-deps --target $D liger-kernel 2>&1 | tail -2
du -sh $D; ls $D | head
cat > $D/bench.py <<'PY'
import sys,time,torch
sys.path.insert(0,'/workspace/nox/tmp/liger_ab')
import warnings; warnings.filterwarnings('ignore')
from unsloth.kernels import fast_cross_entropy_loss
from liger_kernel.transformers.functional import liger_cross_entropy
from liger_kernel.transformers.rms_norm import LigerRMSNorm
import liger_kernel; print('liger',getattr(liger_kernel,'__version__','?'))
torch.manual_seed(0); N,V,H=2048,151936,2048
lg=torch.randn(N,V,device='cuda',dtype=torch.float16,requires_grad=True); y=torch.randint(0,V,(N,),device='cuda')
def t(f,n=10):
    for _ in range(3): f()
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); s=time.time()
    for _ in range(n): f()
    torch.cuda.synchronize(); return (time.time()-s)/n*1000, torch.cuda.max_memory_allocated()/2**20
def uns():
    l=fast_cross_entropy_loss(lg.view(1,N,V),y.view(1,N)); l.backward()
def lig():
    l=liger_cross_entropy(lg,y)[0] if isinstance(liger_cross_entropy(lg,y),tuple) else liger_cross_entropy(lg,y); l.backward()
def torchce():
    l=torch.nn.functional.cross_entropy(lg.float(),y); l.backward()
for n,f in (('unsloth_ce',uns),('liger_ce',lig),('torch_ce',torchce)):
    try: print(n,'ms %.2f peakMiB %.0f'%t(f))
    except Exception as e: print(n,'ERR',str(e)[:150])
x=torch.randn(8192,H,device='cuda',dtype=torch.float16,requires_grad=True)
from unsloth.kernels import fast_rms_layernorm
class W(torch.nn.Module):
    def __init__(s): super().__init__(); s.weight=torch.nn.Parameter(torch.ones(H,device='cuda',dtype=torch.float16)); s.variance_epsilon=1e-6
w=W(); lr=LigerRMSNorm(H).cuda().half()
print('unsloth_rms','ms %.3f peakMiB %.0f'%t(lambda: fast_rms_layernorm(w,x,gemma=False).sum().backward()))
print('liger_rms','ms %.3f peakMiB %.0f'%t(lambda: lr(x).sum().backward()))
PY
nvidia-smi --query-gpu=memory.used --format=csv,noheader
$V $D/bench.py 2>&1 | grep -vE "Warn|warn|xformers|🦥|fla\.|W11" | tail -14
