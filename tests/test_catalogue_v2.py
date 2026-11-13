"""Common selections, scientific identity, compatibility and input deduplication."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchlib.catalogue import build_plan, canonical_digest, load_catalogue, result_identity, validate_plan

ROOT = Path(__file__).resolve().parents[1]


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'catalogue.json'
        self.document = json.loads((ROOT / 'assets/catalogue.json').read_text())

    def plan(self, change=None, **selection):
        document = copy.deepcopy(self.document)
        if change:
            change(document)
        self.path.write_text(json.dumps(document))
        return build_plan(ROOT, catalogue_path=self.path, **selection)

    def test_quick_is_two_compatible_inputs_with_explicit_not_applicable(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network during selection')):
            plan = build_plan(ROOT)
        self.assertEqual(plan['expected_slots'], 2)
        self.assertEqual(plan['not_applicable_slots'], 2)
        self.assertEqual({(s['case_id'], s['workflow_id']) for s in plan['slots']},
                         {('quick-long', 'raven-default'), ('quick-short', 'skesa-default')})
        self.assertEqual({i['layout'] for i in plan['inputs']}, {'long_single', 'short_paired'})
        self.assertEqual(validate_plan(ROOT, plan), plan)
        self.assertEqual(plan, build_plan(ROOT))
        references = [d for d in plan['dependencies'] if d['kind'] == 'reference']
        self.assertEqual(len(references), 1)

    def test_mixed_collections_keep_published_simulations_scientifically_distinct(self):
        plan = build_plan(ROOT, collections='quick,wick-holt-long-read')
        self.assertEqual(plan['expected_slots'], 52)
        published = [i for i in plan['inputs'] if i['recipe']['method'] == 'published-frozen-reads-v1']
        self.assertEqual(len(published), 50)
        self.assertEqual({i['source_kind'] for i in published}, {'simulated'})
        self.assertEqual({i['dataset']['data_origin'] for i in published}, {'deposited'})
        self.assertNotIn('wick-holt-long-read', plan['scenarios'])

    def test_memberships_do_not_duplicate_or_change_inputs_or_result_slots(self):
        before = self.plan(cases='quick-long')
        def edit(doc):
            row = next(r for r in doc['cases'] if r['id'] == 'quick-long')
            row['scenarios'].append('gc-composition')
        after = self.plan(edit, cases='quick-long', scenarios='gc-composition')
        old = before['slots'][0]
        matching = [r for r in after['slots'] if r['case_id'] == 'quick-long']
        self.assertEqual(len(matching), 1)
        self.assertEqual(old['result_id'], matching[0]['result_id'])
        self.assertEqual(old['input_id'], matching[0]['input_id'])
        self.assertEqual(old['case']['science_key'], matching[0]['case']['science_key'])

    def test_technical_repeats_share_reads_but_have_distinct_current_results(self):
        plan = build_plan(ROOT, collections='quick,reproducibility-validation')
        self.assertEqual(len(plan['inputs']), 2)
        repeats = [s for s in plan['slots'] if s['case_id'] == 'quick-long-repeatability']
        self.assertEqual(len(repeats), 3)
        self.assertEqual(len({s['input_id'] for s in repeats}), 1)
        self.assertEqual(len({s['result_id'] for s in repeats}), 3)
        self.assertEqual({s['case']['scientific_repeat']['kind'] for s in repeats}, {'technical'})

    def test_adding_or_upgrading_workflow_reuses_inputs_and_stable_current_identity(self):
        before = self.plan(cases='quick-long', workflows='raven-default')
        more = self.plan(cases='quick-long', workflows='raven-default,flye-default')
        self.assertEqual(before['inputs'], more['inputs'])
        def upgrade(doc):
            row = next(r for r in doc['workflows'] if r['id'] == 'raven-default')
            row.update(version='1.9.0', version_order=10900)
        newer = self.plan(upgrade, cases='quick-long', workflows='raven-default')
        self.assertEqual(before['inputs'], newer['inputs'])
        self.assertEqual(before['slots'][0]['result_id'], newer['slots'][0]['result_id'])
        self.assertNotEqual(before['slots'][0]['workflow'], newer['slots'][0]['workflow'])

    def test_changed_recipe_requires_explicit_new_scientific_identity(self):
        def edit(doc):
            next(r for r in doc['cases'] if r['id'] == 'quick-long')['recipe']['seed'] += 1
        with self.assertRaisesRegex(ValueError, 'scientific identity changed'):
            self.plan(edit)

    def test_not_applicable_does_not_schedule_preparation_or_software(self):
        plan = build_plan(ROOT, cases='quick-short', workflows='raven-default')
        self.assertEqual(plan['expected_slots'], 0)
        self.assertEqual(plan['inputs'], [])
        self.assertEqual(plan['dependencies'], [])
        self.assertEqual(plan['exclusions'][0]['status'], 'not_applicable')

    def test_unknown_selection_and_invalid_real_sample_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown scenarios'):
            build_plan(ROOT, scenarios='typo')
        def edit(doc):
            next(r for r in doc['datasets'] if r['id'] == 'johnson-atcc25922-local-validation')['reference_sample_id'] = 'another-sample'
        with self.assertRaisesRegex(ValueError, 'matching read/reference sample'):
            self.plan(edit)

    def test_all_is_only_a_metadata_plan_and_resolves_all_declared_configurations(self):
        with patch('subprocess.run', side_effect=AssertionError('No execution during planning')):
            plan = build_plan(ROOT, all_eligible=True)
        self.assertEqual(len(plan['workflows']), 6)
        self.assertEqual(len({s['result_id'] for s in plan['slots']}), len(plan['slots']))
        self.assertTrue(any(s['case']['source_kind'] == 'real' for s in plan['slots']))

    def test_result_identity_and_plan_tamper_guard(self):
        self.assertEqual(result_identity('case', 'config'), result_identity('case', 'config', None))
        self.assertNotEqual(result_identity('case', 'config', 'repeat-1'), result_identity('case', 'config', 'repeat-2'))
        plan = build_plan(ROOT)
        plan['expected_slots'] += 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_plan(ROOT, plan)

    def test_workflow_requires_its_declared_manifest_and_executable_options(self):
        def manifest(doc):doc['workflows'][0]['manifest']='elsewhere/pixi.toml'
        with self.assertRaisesRegex(ValueError,'manifest/environment'):self.plan(manifest)
        def options(doc):next(w for w in doc['workflows'] if w['tool']=='raven')['configuration']={'mode':'ignored-mode'}
        with self.assertRaisesRegex(ValueError,'Unsupported workflow mode'):self.plan(options)

    def test_matching_dataset_labels_cannot_override_reference_sample(self):
        def edit(doc):
            dataset=next(d for d in doc['datasets'] if d['id']=='johnson-atcc25922-local-validation')
            dataset.update(sample_id='WRONG',reference_sample_id='WRONG')
        with self.assertRaisesRegex(ValueError,'reference record'):self.plan(edit)
