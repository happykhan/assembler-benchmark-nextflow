"""Automatic setup preserves frozen selections and fails before provisioning."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchlib.bootstrap import prepare_run
from benchlib.planning import build_plan

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_quick_default_prepares_exact_selected_environments(self):
        with patch('benchlib.bootstrap.prepare_environments', return_value={'status': 'prepared'}) as prepare:
            plan, receipt = prepare_run(ROOT, {'preset': 'quick'}, 'pixi')
        self.assertEqual(plan['expected_slots'], 4)
        prepare.assert_called_once_with(ROOT, plan)
        self.assertEqual(receipt['status'], 'prepared')

    def test_unknown_selection_stops_before_installing(self):
        with patch('benchlib.bootstrap.prepare_environments') as prepare:
            with self.assertRaisesRegex(ValueError, 'Unknown case'):
                prepare_run(ROOT, {'cases': 'typo'}, 'pixi')
        prepare.assert_not_called()

    def test_supplied_plan_and_selections_cannot_conflict(self):
        with patch('benchlib.bootstrap.prepare_environments') as prepare:
            with self.assertRaisesRegex(ValueError, 'combined'):
                prepare_run(ROOT, {'cases': 'quick-bimodal'}, 'pixi', 'ignored.json')
        prepare.assert_not_called()

    def test_existing_output_selection_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / 'plan.json'
            existing.write_text(json.dumps(build_plan(ROOT, cases='quick-bimodal')))
            with patch('benchlib.bootstrap.prepare_environments') as prepare:
                with self.assertRaisesRegex(ValueError, 'different selection'):
                    prepare_run(ROOT, {'preset': 'quick'}, 'pixi', existing_plan=existing)
            prepare.assert_not_called()

    def test_explicit_native_runtime_does_not_install_software(self):
        with patch('benchlib.bootstrap.prepare_environments') as prepare:
            plan, receipt = prepare_run(ROOT, {'preset': 'quick'}, 'native')
        prepare.assert_not_called()
        self.assertEqual(receipt['plan_sha256'], plan['plan_sha256'])
        self.assertEqual(receipt['status'], 'externally_prepared')

    def test_supplied_frozen_plan_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan.json'
            original = build_plan(ROOT, cases='quick-bimodal', assemblers='raven')
            path.write_text(json.dumps(original))
            with patch('benchlib.bootstrap.prepare_environments', return_value={'status': 'prepared'}):
                plan, _ = prepare_run(ROOT, {}, 'pixi', path, path)
            self.assertEqual(plan, original)


if __name__ == '__main__':
    unittest.main()
