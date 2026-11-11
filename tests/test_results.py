import importlib.util
from contextlib import chdir
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchlib.assessment import outcome, parse_paf, sha256, summarise, write_json
from benchlib.report import export_results

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('assess_cli', ROOT / 'bin/assess-assembly.py')
assess_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assess_cli)


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paf = Path(self.temp.name) / 'alignment.paf'
        self.references = {'reference': 'A' * 1000}
        self.queries = {'contig': 'A' * 2000}

    def parse(self, text):
        self.paf.write_text(text)
        return parse_paf(self.paf, self.references, self.queries)

    def test_contiguity_is_uncapped_and_longest_alignment_selected(self):
        alignments = self.parse('contig\t2000\t0\t1100\t+\treference\t3000\t400\t1500\t1098\t1100\t60\tcg:Z:1100M\n')
        result = summarise(self.references, alignments)[0]
        self.assertAlmostEqual(result['contiguity'], 1.1)
        self.assertTrue(result['complete'])
        self.assertAlmostEqual(result['identity'], 1098 / 1100)
        self.assertEqual(result['max_indel_bp'], 0)

    def test_split_alignments_do_not_establish_completion(self):
        alignments = self.parse('contig\t2000\t0\t500\t+\treference\t3000\t0\t500\t500\t500\t60\tcg:Z:500M\n'
                                'contig\t2000\t500\t1000\t+\treference\t3000\t500\t1000\t500\t500\t60\tcg:Z:500M\n')
        result = summarise(self.references, alignments)[0]
        self.assertEqual(result['contiguity'], .5)
        self.assertEqual(outcome([result], 1), 'incomplete')

    def test_short_alignment_has_no_accuracy_measurement(self):
        alignments = self.parse('contig\t2000\t0\t250\t+\treference\t3000\t0\t250\t250\t250\t60\tcg:Z:250M\n')
        result = summarise(self.references, alignments)[0]
        self.assertFalse(result['identity_measured'])
        self.assertIsNone(result['identity'])
        self.assertIsNone(result['max_indel_bp'])

    def test_invalid_cigar_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CIGAR span'):
            self.parse('contig\t2000\t0\t500\t+\treference\t3000\t0\t500\t500\t500\t60\tcg:Z:499M\n')


class FailureAndExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.reference = self.directory / 'reference.fasta'
        self.reference.write_text('>reference\nACGT\n')
        self.execution = self.directory / 'execution.json'
        self.simulation = self.directory / 'simulation.json'
        self.provenance = self.directory / 'reference-provenance.json'
        write_json(self.execution, {'status': 'software_error', 'assembler': 'flye', 'reads_sha256': 'a' * 64,
                                   'exit_code': 139, 'elapsed_seconds': 1, 'process_tree_peak_rss_bytes': 100})
        self.case = {'id': 'test', 'group': 'read-quality', 'preset': 'quick'}
        write_json(self.simulation, {'status': 'completed', 'case': self.case,
                                    'reference_sha256': sha256(self.reference), 'reads_sha256': 'a' * 64})
        write_json(self.provenance, {'accession': 'test', 'reference_sha256': sha256(self.reference)})
        from argparse import Namespace
        self.args = Namespace(reference=self.reference, assembly=self.directory / 'absent.fasta',
                              execution=self.execution, simulation=self.simulation, reference_provenance=self.provenance,
                              case_json=json.dumps(self.case),
                              assembler='flye', cpus=1, out=self.directory / 'test.result.json')

    def standard_baseline(self, reference_headline_eligible=False):
        self.case.update(preset='standard', purpose='baseline_validation', headline_eligible=False)
        self.args.case_json = json.dumps(self.case)
        write_json(self.provenance, {'accession': 'test', 'reference_sha256': sha256(self.reference),
                                    'mode': 'whole_genome', 'status': 'admitted',
                                    'headline_eligible': reference_headline_eligible})
        write_json(self.simulation, {'status': 'completed', 'case': self.case,
                                    'reference_sha256': sha256(self.reference), 'reads_sha256': 'a' * 64,
                                    'reference_provenance_sha256': sha256(self.provenance)})

    def test_standard_baseline_scope_survives_tsv_roundtrip(self):
        self.standard_baseline()
        result = assess_cli.assess(self.args)
        self.assertIs(result['headline_eligible'], False)
        export_results([self.args.out], self.directory / 'bundle', 1, 'baseline')
        with (self.directory / 'bundle/results.tsv').open() as stream:
            table = csv.DictReader(stream, delimiter='\t')
            self.assertIn('purpose', table.fieldnames)
            self.assertIn('headline_eligible', table.fieldnames)
            rows = list(table)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['preset'], 'standard')
        self.assertEqual(rows[0]['purpose'], 'baseline_validation')
        self.assertEqual(rows[0]['headline_eligible'].lower(), 'false')

    def test_standard_baseline_is_not_promoted_by_preset_or_reference(self):
        self.standard_baseline(reference_headline_eligible=True)
        result = assess_cli.assess(self.args)
        self.assertEqual(result['assessment']['status'], 'not_run')
        self.assertIs(result['headline_eligible'], False)
        self.assertIsNone(result['sequence_outcome'])
        self.assertIn('baseline validation', ' '.join(result['limitations']))
        export_results([self.args.out], self.directory / 'bundle', 1, 'baseline')
        html = (self.directory / 'bundle/index.html').read_text()
        self.assertIn('Standard whole-genome baseline validation', html)
        self.assertIn('excluded from headline comparisons', html)

    def test_standard_preparation_binding_failure_has_no_sequence_verdict(self):
        self.standard_baseline()
        simulation = json.loads(self.simulation.read_text())
        simulation['reference_provenance_sha256'] = 'f' * 64
        write_json(self.simulation, simulation)
        result = assess_cli.assess(self.args)
        self.assertEqual(result['assessment']['status'], 'error')
        self.assertIn('preparation provenance binding differs', result['assessment']['error'])
        self.assertIsNone(result['sequence_outcome'])
        self.assertEqual(result['replicons'], [])
        manifest = export_results([self.args.out], self.directory / 'bundle', 1, 'baseline')
        self.assertFalse(manifest['complete'])

    def test_software_failure_is_accounted_without_sequence_absence(self):
        result = assess_cli.assess(self.args)
        self.assertIsNone(result['sequence_outcome'])
        self.assertEqual(result['replicons'], [])
        self.assertEqual(result['assessment']['status'], 'not_run')
        manifest = export_results([self.args.out], self.directory / 'bundle', 1, 'run')
        self.assertTrue(manifest['complete'])
        for path, expected in manifest['files'].items():
            self.assertEqual(sha256(self.directory / 'bundle' / path), expected)
        html = (self.directory / 'bundle/index.html').read_text()
        self.assertIn('No sequence verdict', html)
        self.assertIn('excluded from headline', html)

    def test_missing_slot_prevents_completion(self):
        assess_cli.assess(self.args)
        manifest = export_results([self.args.out], self.directory / 'bundle', 2, 'run')
        self.assertFalse(manifest['complete'])

    def test_changed_evidence_cannot_be_exported(self):
        assess_cli.assess(self.args)
        (self.directory / 'test.result.evidence' / 'execution.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Evidence hash mismatch'):
            export_results([self.args.out], self.directory / 'bundle', 1, 'run')

    def test_binding_failure_is_assessment_error_not_incomplete_sequence(self):
        write_json(self.simulation, {'status': 'completed', 'case': self.case,
                                    'reference_sha256': 'wrong', 'reads_sha256': 'a' * 64})
        result = assess_cli.assess(self.args)
        self.assertEqual(result['assessment']['status'], 'error')
        self.assertIsNone(result['sequence_outcome'])
        manifest = export_results([self.args.out], self.directory / 'bundle', 1, 'run')
        self.assertFalse(manifest['complete'])

    def test_reference_provenance_and_case_substitution_are_rejected(self):
        for index, field in enumerate(('reference', 'case')):
            with self.subTest(field=field):
                if field == 'reference':
                    write_json(self.provenance, {'reference_sha256': 'b' * 64})
                else:
                    write_json(self.provenance, {'reference_sha256': sha256(self.reference)})
                    simulation = json.loads(self.simulation.read_text())
                    simulation['case'] = dict(self.case, seed=123)
                    write_json(self.simulation, simulation)
                self.args.out = self.directory / f'{index}.result.json'
                result = assess_cli.assess(self.args)
                self.assertEqual(result['assessment']['status'], 'error')
                self.assertIsNone(result['sequence_outcome'])

    def test_software_failure_retains_logs_and_partial_graph_with_hash(self):
        for name in ('stdout.log', 'stderr.log', 'partial.gfa'):
            (self.directory / name).write_text(name + '\n')
        result = assess_cli.assess(self.args)
        evidence = self.directory / result['evidence_directory']
        self.assertTrue((evidence / 'stderr.log').is_file())
        self.assertEqual(result['provenance']['retained_graphs'][0]['role'], 'partial_or_diagnostic_graph')
        manifest = export_results([self.args.out], self.directory / 'bundle', 1, 'run')
        self.assertEqual(manifest['retention']['graphs'], ['assemblies/test/flye/partial.gfa'])

    def test_changed_graph_is_rejected_before_export(self):
        (self.directory / 'partial.gfa').write_text('H\tVN:Z:1.0\n')
        result = assess_cli.assess(self.args)
        (self.directory / result['evidence_directory'] / 'partial.gfa').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Graph hash mismatch'):
            export_results([self.args.out], self.directory / 'bundle', 1, 'run')

    def test_exact_expected_slot_plan_rejects_missing_and_unknown_pairs(self):
        assess_cli.assess(self.args)
        plan = self.directory / 'plan.json'
        for assemblers in (['raven'], ['flye', 'raven']):
            write_json(plan, {'cases': [{'id': 'test'}], 'assemblers': assemblers})
            with self.assertRaisesRegex(ValueError, 'slots differ'):
                export_results([self.args.out], self.directory / 'bundle', len(assemblers), 'run', plan)
            self.assertFalse((self.directory / 'bundle').exists())
        write_json(plan, {'cases': [{'id': 'test'}], 'assemblers': ['flye']})
        manifest = export_results([self.args.out], self.directory / 'bundle', 1, 'run', plan)
        self.assertTrue(manifest['complete'])
        self.assertEqual(manifest['expected_slot_plan'], [{'case_id': 'test', 'assembler': 'flye'}])
        self.assertEqual(manifest['files']['slot-plan.json'], sha256(plan))

    def test_mapper_resources_are_recorded_separately(self):
        assembly = self.directory / 'assembly.fasta'
        assembly.write_text('>contig\nACGT\n')
        execution = json.loads(self.execution.read_text())
        execution.update(status='completed', assembly_sha256=sha256(assembly))
        write_json(self.execution, execution)
        # Nextflow supplies a staged relative path; measured_run changes cwd to evidence.
        self.args.assembly = Path('assembly.fasta')

        def measured(command, stdout, stderr, cwd):
            query = Path(command[-1])
            self.assertTrue(query.is_absolute(), 'Mapper query must survive its working-directory change')
            self.assertEqual(query.read_bytes(), assembly.read_bytes())
            self.assertNotEqual(cwd, assembly.parent)
            self.assertTrue((Path(cwd) / query).is_file())
            stdout.write_text('contig\t4\t0\t4\t+\treference\t12\t0\t4\t4\t4\t60\tcg:Z:4M\n')
            stderr.write_text('mapper diagnostics')
            return {'exit_code': 0, 'elapsed_seconds': .2, 'process_tree_peak_rss_bytes': 12345}

        with chdir(self.directory), patch.object(assess_cli, 'measured_run', side_effect=measured), \
                patch.object(assess_cli.subprocess, 'run') as version:
            version.return_value.stdout = '2.31-r1279\n'
            result = assess_cli.assess(self.args)
        self.assertEqual(result['assessment']['status'], 'completed')
        self.assertEqual(result['resources']['assessment_mapper_process_tree_peak_rss_bytes'], 12345)
        self.assertEqual(result['resources']['assembler_process_tree_peak_rss_bytes'], 100)


if __name__ == '__main__':
    unittest.main()
