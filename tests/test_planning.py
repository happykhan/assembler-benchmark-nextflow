"""Frozen selections reject silent omissions, aliases and changed evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from benchlib.planning import build_plan, catalogue, plan_digest, validate_plan

ROOT = Path(__file__).resolve().parents[1]


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        for name in ('assets/quick.json', 'assets/groups.json', 'assets/references.json', 'assets/assemblers.json'):
            target = self.project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        environments = self.project / 'environments'
        environments.mkdir()
        (environments / 'pixi.toml').write_bytes((ROOT / 'environments/pixi.toml').read_bytes())
        (environments / 'pixi.lock').write_text('frozen fixture lock\n')

    def change_cases(self, modify):
        path = self.project / 'assets/quick.json'
        rows = json.loads(path.read_text())
        modify(rows)
        path.write_text(json.dumps(rows))

    def test_default_plan_is_exact_deterministic_and_binds_versions(self):
        first, second = build_plan(self.project), build_plan(self.project)
        self.assertEqual(first, second)
        self.assertEqual(first['expected_slots'], 4)
        self.assertEqual(first['assemblers'], ['flye-2.9.6', 'raven-1.8.3'])
        self.assertEqual(len({(row['case_id'], row['assembler']) for row in first['slots']}), 4)
        self.assertFalse(first['headline_eligible'])
        self.assertEqual(first['plan_sha256'], plan_digest(first))
        self.assertEqual(validate_plan(self.project, first), first)

    def test_selected_case_and_alias_produce_one_explicit_slot(self):
        plan = build_plan(self.project, groups='read-quality', cases='quick-bimodal', assemblers='raven')
        self.assertEqual(plan['slots'], [{'case_id': 'quick-bimodal', 'assembler': 'raven-1.8.3'}])
        self.assertEqual(plan['reference_ids'], ['bsub-168-quick'])

    def test_unknown_or_unimplemented_selections_fail_instead_of_silently_dropping(self):
        for argument in ({'groups': 'read-quality,typo'}, {'cases': 'quick-baseline,typo'},
                         {'groups': 'read-quality,plasmids'}, {'assemblers': 'raven-99.0'}):
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                build_plan(self.project, **argument)

    def test_duplicate_alias_version_selection_is_not_an_extra_execution(self):
        with self.assertRaisesRegex(ValueError, 'same immutable'):
            build_plan(self.project, assemblers='raven,raven-1.8.3')

    def test_duplicate_case_or_invalid_reference_is_rejected(self):
        self.change_cases(lambda rows: rows.append(copy.deepcopy(rows[0])))
        with self.assertRaisesRegex(ValueError, 'Duplicate case'):
            build_plan(self.project)
        self.change_cases(lambda rows: (rows.pop(), rows[0].update(reference_id='missing')))
        with self.assertRaisesRegex(ValueError, 'unknown reference'):
            build_plan(self.project)

    def test_invalid_seed_repeat_and_unsupported_parameters_fail_before_scheduling(self):
        original = (self.project / 'assets/quick.json').read_text()
        for fields in ({'seed': True}, {'seed': -1}, {'seed': 2**32 - 1},
                       {'repeat': 0}, {'repeat_index': False}, {'coverage': float('nan')},
                       {'unexpected_error_rate': .1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                (self.project / 'assets/quick.json').write_text(original)
                self.change_cases(lambda rows: rows[0].update(fields))
                build_plan(self.project)

    def test_changed_source_and_tampered_slot_plan_fail_validation(self):
        plan = build_plan(self.project)
        tampered = copy.deepcopy(plan)
        tampered['slots'].pop()
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_plan(self.project, tampered)
        tampered['plan_sha256'] = plan_digest(tampered)
        with self.assertRaisesRegex(ValueError, 'differs'):
            validate_plan(self.project, tampered)
        (self.project / 'environments/pixi.lock').write_text('changed lock\n')
        with self.assertRaisesRegex(ValueError, 'differs'):
            validate_plan(self.project, plan)

    def test_standard_is_not_admitted_and_catalogue_is_honest(self):
        with self.assertRaisesRegex(ValueError, 'Standard is not admitted'):
            build_plan(self.project, preset='standard')
        data = catalogue(self.project)
        self.assertEqual(len(data['groups']), 5)
        self.assertEqual({row['id'] for row in data['groups'] if row['quick_status'] == 'implemented'}, {'read-quality'})
        self.assertEqual(data['presets']['standard'], 'not_admitted')

    def test_wrong_or_missing_pinned_environment_blocks_plan(self):
        manifest = self.project / 'environments/pixi.toml'
        original = manifest.read_text()
        manifest.write_text(original.replace('==1.8.3', '==1.8.2'))
        with self.assertRaisesRegex(ValueError, 'pin exactly'):
            build_plan(self.project, assemblers='raven')
        manifest.write_text('[workspace]\nname="fixture"\n')
        with self.assertRaisesRegex(ValueError, 'environment is absent'):
            build_plan(self.project, assemblers='raven')

    def test_cli_validates_plan_and_never_overwrites_frozen_output(self):
        plan = self.project / 'selected.json'
        plan.write_text(json.dumps(build_plan(self.project)))
        output = self.project / 'admitted.json'
        command = [sys.executable, str(ROOT / 'bin/plan.py'), '--project', str(self.project),
                   '--validate', str(plan), '--out', str(output)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(second.returncode, 2)
        self.assertIn('refusing to overwrite', second.stderr)
        self.assertEqual(output.read_bytes(), original)
