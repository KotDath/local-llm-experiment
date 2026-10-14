"""Launch the measured selection with its actual native context per slot."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
selection = json.loads((ROOT/'configs/selected.json').read_text())
profile = selection['profile']
quant = selection['quant']
if profile not in {'baseline', 'optimized'} or quant not in {'Q8', 'Q4'}:
    raise SystemExit('Invalid measured selection')
settings = json.loads((ROOT/'configs'/f'{profile}.json').read_text())
env = os.environ.copy()
# An inherited explicit MODEL must not silently override the measured quantization.
env.pop('MODEL', None)
env.update(QUANT=quant, CTX_PER_SLOT=str(settings['context']))
env.setdefault('PARALLEL', '3')
os.chdir(ROOT)
print(f"Launching Tiel Coder {quant}/{profile}, {settings['context']} context/slot, {env['PARALLEL']} slots", flush=True)
os.execvpe('bash', ['bash', str(ROOT/'run_model.sh')], env)
