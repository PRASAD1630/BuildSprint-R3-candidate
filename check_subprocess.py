"""Verify that the deterministic subprocess path does not require an LLM SDK."""
import os
import subprocess
import sys

code = """
from workmate.llm import complete_json
result, usage = complete_json('system', 'user')
assert result is None
assert usage['input_tokens'] == 0
import workmate.engine
print('Optional model adapter import successful')
print('Deterministic no-provider path successful')
"""
env = dict(os.environ)
env['MODEL_PROVIDER'] = 'none'
p = subprocess.run(
    [sys.executable, '-c', code],
    capture_output=True,
    text=True,
    env=env,
)
print(p.stdout, end='')
if p.stderr:
    print(p.stderr, file=sys.stderr, end='')
sys.exit(p.returncode)
