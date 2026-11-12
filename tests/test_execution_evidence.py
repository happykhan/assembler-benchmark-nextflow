"""Phase retention and frozen experiment binding without scientific execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from benchlib.evidence import retain_workflow_evidence
from benchlib.io import digest
from benchlib.planning import build_plan
from benchlib.report import verify_plan_binding

ROOT = Path(__file__).resolve().parents[1]


class ExecutionEvidenceTests(unittest.TestCase):
    def test_raw_phase_is_portable_even_when_polishing_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / 'tool-output/raw-phase'
            raw.mkdir(parents=True)
            (raw / 'assembly.fasta').write_text('>unitig\nACGT\n')
            (raw / 'assembly.raw.gfa').write_text('S\tunitig\tACGT\tLN:i:4\n')
            (raw / 'execution.json').write_text('{"status":"complete"}')
            workflow = root / 'tool-output/workflow.json'
            files = {p.relative_to(workflow.parent).as_posix(): digest(p) for p in raw.iterdir()}
            workflow.write_text(json.dumps({'status': 'software_error', 'retained_file_sha256': files}))
            execution = {'status': 'software_error', 'assembly_workflow': json.loads(workflow.read_text()),
                         'assembly_workflow_sha256': digest(workflow)}
            out = root / 'evidence'
            out.mkdir()
            retained, graphs = retain_workflow_evidence(execution, root, out)
            self.assertEqual(len(retained), 4)
            self.assertEqual(len(graphs), 1)
            for row in retained:
                self.assertEqual(digest(out / row['file']), row['sha256'])
            (raw / 'assembly.fasta').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'binding differs'):
                retain_workflow_evidence(execution, root, out)

    def test_matching_slot_id_does_not_allow_changed_science_or_software(self):
        plan = build_plan(ROOT)
        definition = next(iter(plan['assembler_definitions'].values()))
        record = {'case': copy.deepcopy(plan['cases'][0]), 'assembler': definition['id'],
                  'execution': {'assembler': definition['id'], 'tool': definition['tool'],
                    'expected_version': definition['version'], 'environment': definition['environment'],
                    'manifest': definition['manifest'],
                    'environment_manifest_sha256': plan['source_file_sha256'][definition['manifest']],
                    'environment_lock_sha256': plan['source_file_sha256']['environments/pixi.lock']}}
        verify_plan_binding(record, plan)
        for field in ('coverage', 'seed'):
            changed = copy.deepcopy(record)
            changed['case'][field] += 1
            with self.assertRaisesRegex(ValueError, 'scientific selection'):
                verify_plan_binding(changed, plan)
        changed = copy.deepcopy(record)
        changed['execution']['environment_lock_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'software locks'):
            verify_plan_binding(changed, plan)

    def test_s7_defaults_preserve_48_and_modes_compare_separately(self):
        from diagnostic_core.comparison import compare_results
        plan = build_plan(ROOT, preset='standard', track='diagnostic', groups='S7')
        self.assertEqual(plan['expected_slots'], 48)
        comparison = compare_results([], plan)
        self.assertEqual(len(comparison['groups']), 4)
        self.assertTrue(all(g['expected_runs'] == 12 for g in comparison['groups']))
        self.assertEqual({g['configuration_id'] for g in comparison['groups']},
                         {'flye--default', 'flye-meta--default', 'raven--default', 'plassembler--default'})
        self.assertFalse(comparison['complete'])
        expanded = build_plan(ROOT, preset='standard', track='diagnostic', groups='S7', assemblers='miniasm-plus')
        self.assertEqual(expanded['expected_slots'], 12)

    def test_homepage_does_not_merge_failure_classes_with_sequence_outcomes(self):
        from reporting.native_site import outcome_label
        for status, label in [('software_error','Software error'), ('resource_error','Did not complete'), ('infrastructure_error','Infrastructure error')]:
            self.assertEqual(outcome_label({'execution':{'status':status},'sequence_outcome':None}),label)
        self.assertEqual(outcome_label({'assessment':{'status':'error'},'sequence_outcome':None}),'Assessment error')
        self.assertEqual(outcome_label({'sequence_outcome':'incomplete'}),'incomplete')

    def test_plassembler_prefixed_empty_final_graph_is_retained_as_plasmid_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'tool-output').mkdir()
            graph=root/'tool-output/benchmark_plasmids.gfa'
            graph.write_text('')
            out=root/'evidence';out.mkdir()
            files,graphs=retain_workflow_evidence({'tool':'plassembler','status':'completed'},root,out)
            self.assertEqual(len(files),1)
            self.assertEqual(graphs[0]['role'],'final_plasmid_graph')
            self.assertEqual(graphs[0]['sha256'],digest(graph))
            self.assertEqual((out/graphs[0]['file']).read_bytes(),b'')
            failed=root/'failed-evidence';failed.mkdir()
            self.assertEqual(retain_workflow_evidence({'tool':'plassembler','status':'software_error'},root,failed),([],[]))
