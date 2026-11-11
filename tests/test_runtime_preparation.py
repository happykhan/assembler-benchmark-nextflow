"""Serial environment startup is distinct from assembler job concurrency."""
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchlib.planning import build_plan, plan_digest
from benchlib.runtime import EnvironmentPreparationError, prepare_environments


ROOT = Path(__file__).resolve().parents[1]


class RuntimePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        for name in ('assets', 'environments'):
            shutil.copytree(ROOT / name, self.project / name, ignore=shutil.ignore_patterns('.pixi'))
        self.plan = build_plan(self.project)

    def test_default_then_selected_named_environments_are_installed_once_in_order(self):
        with patch('benchlib.runtime.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='ready', stderr='')) as run:
            receipt = prepare_environments(self.project, self.plan, '/tools/pixi')
        environments = [call.args[0][-1] for call in run.call_args_list]
        self.assertEqual(environments, ['default', 'flye-2-9-6', 'raven-1-8-3'])
        self.assertEqual(len(set(environments)), len(environments))
        self.assertTrue(all('--locked' in call.args[0] for call in run.call_args_list))
        self.assertEqual(receipt['status'], 'prepared')
        self.assertEqual(receipt['plan_sha256'], self.plan['plan_sha256'])
        self.assertTrue(all(len(row['lock_sha256']) == 64 for row in receipt['environments']))

    def test_only_selected_assembler_environment_is_provisioned(self):
        plan = build_plan(self.project, assemblers='raven')
        with patch('benchlib.runtime.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
            prepare_environments(self.project, plan)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], ['default', 'raven-1-8-3'])

    def test_duplicate_or_modified_plan_is_rejected_before_installation(self):
        plan = copy.deepcopy(self.plan)
        plan['selection']['assemblers'].append(plan['selection']['assemblers'][0])
        plan['plan_sha256'] = plan_digest(plan)
        with patch('benchlib.runtime.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                prepare_environments(self.project, plan)
        run.assert_not_called()

    def test_installation_failure_stops_before_later_environments_without_retry(self):
        failure = subprocess.CalledProcessError(101, ['pixi'], output='partial', stderr='path_resolver panic')
        with patch('benchlib.runtime.subprocess.run', side_effect=[SimpleNamespace(returncode=0, stdout='', stderr=''), failure]) as run:
            with self.assertRaises(EnvironmentPreparationError) as caught:
                prepare_environments(self.project, self.plan)
        self.assertEqual(run.call_count, 2)
        receipt = caught.exception.receipt
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['environments'][-1]['exit_code'], 101)
        self.assertIn('path_resolver', receipt['environments'][-1]['stderr'])
        self.assertEqual(receipt['automatic_retries'], 0)

    def test_changed_lock_is_rejected_before_installation(self):
        (self.project / 'environments/pixi.lock').write_text('changed')
        with patch('benchlib.runtime.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'differs'):
                prepare_environments(self.project, self.plan)
        run.assert_not_called()
