"""The real runtime wrapper supplies a non-interactive terminal without tool changes."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BatchRuntimeTests(unittest.TestCase):
    def test_missing_terminal_is_dumb_and_explicit_terminal_is_preserved(self):
        for supplied,expected in ((None,'dumb'),('','dumb'),('xterm','xterm')):
            env=dict(os.environ,BENCH_RUNTIME='native')
            env.pop('TERM',None)
            if supplied is not None:env['TERM']=supplied
            observed=subprocess.check_output(['bash',str(ROOT/'bin/bench-run'),'python3','-c',
                'import os; print(os.environ["TERM"])'],env=env,text=True).strip()
            self.assertEqual(observed,expected)
