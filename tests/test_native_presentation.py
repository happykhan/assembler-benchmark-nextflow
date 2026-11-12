"""Presentation export preserves source graph and raw-coordinate meanings."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from reporting.common import digest
from reporting.native_prepare import prepare_presentation
from reporting.native_diagnostics import render_diagnostics
from reporting.archive import render_website
from benchlib.report import record_complete


class NativePresentationTests(unittest.TestCase):
    def test_retained_graph_and_coordinates_render_without_source_reads_or_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'bundle'
            source.mkdir()
            evidence = source / 'evidence'
            evidence.mkdir()
            assembly = source / 'assemblies/case/tool'
            assembly.mkdir(parents=True)
            gfa = assembly / 'assembly.gfa'
            gfa.write_text('H\tVN:Z:1.0\nS\tx\tACGT\nL\tx\t+\tx\t+\t0M\n')
            paf = evidence / 'alignment.paf'
            paf.write_text('x\t4\t0\t4\t+\tref\t12\t0\t4\t4\t4\t60\n')
            record = {'case': {'id': 'case'}, 'assembler': 'tool', 'evidence_directory': 'evidence',
                      'execution': {'status': 'completed'}, 'assessment': {'paf_sha256': digest(paf)},
                      'provenance': {'assembly_sha256': 'a' * 64}}
            prepare_presentation(source, [record])
            model = json.loads((source / 'presentation/graphs/0-assembly.json').read_text())
            self.assertEqual(model['graph']['self_loop_segment_ids'], ['x'])
            self.assertNotIn('ACGT', json.dumps(model))
            self.assertEqual(model['reference_origins']['nodes'], {})
            (source / 'index.html').write_text('<html><head><title>Test</title></head><body><main><h1>Test</h1></main></body></html>')
            (source / 'results.json').write_text(json.dumps({'run_id': 'test', 'results': [record]}))
            (source / 'results.tsv').write_text('case_id\tassembler\ncase\ttool\n')
            manifest = {'schema_version': 1, 'run_id': 'test', 'result_count': 1, 'expected_slots': 1,
                        'complete': True, 'files': {p.relative_to(source).as_posix(): digest(p) for p in source.rglob('*') if p.is_file()}}
            (source / 'manifest.json').write_text(json.dumps(manifest))
            # Validation hashes every source, then rendering must only consume
            # sealed presentation models, never parse GFA or PAF again.
            with patch('reporting.native_prepare.parse_gfa', side_effect=AssertionError('Parser during render')), patch('subprocess.run', side_effect=AssertionError('Analysis during render')):
                render_website(source, root / 'site')
            from reporting.native_site import result_route
            html = (root / 'site' / result_route(record)).read_text()
            self.assertNotIn('data-assembly-graph', (root / 'site/index.html').read_text())
            self.assertIn('data-assembly-graph', html)
            self.assertIn('tripled references remain tripled', html)
            self.assertEqual((root / 'site/presentation/alignments/0.tsv').read_bytes(), (source / 'presentation/alignments/0.tsv').read_bytes())

    def test_s7_secondary_reference_failure_is_not_output_disagreement(self):
        record = {'case': {'id': 's7', 'group': 'reproducibility', 'category': 'S7'},
                  'track': 'diagnostic', 'assembler': 'tool', 'execution': {'status': 'completed'},
                  'assessment': {'status': 'completed', 'method': 'exact-dedicated-molecule-v1'},
                  'sequence_outcome': 'fail', 'secondary_reference_status': 'fail', 'replicons': []}
        html = render_diagnostics([record], 1, 'test')
        self.assertIn('Not assessed across runs', html)
        self.assertIn('does not determine agreement', html)
        self.assertNotIn('99%', html)

    def test_terminal_resource_failure_is_accounted_without_sequence_verdict(self):
        self.assertTrue(record_complete({'assessment': {'status': 'not_run'}, 'execution': {'status': 'resource_error'}}))


if __name__ == '__main__':
    unittest.main()
