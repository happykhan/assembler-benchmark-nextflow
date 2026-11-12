"""Cohort separation, result routes and static-publication budgets."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reporting.archive import render_website
from reporting.common import digest
from reporting.native_site import result_route
from reporting.site_gate import check_site


def record(case_id, track, outcome, group='baseline'):
    return {'case': {'id': case_id, 'group': group, 'category': group},
            'assembler': 'tool-v1', 'preset': 'standard', 'track': track,
            'headline_eligible': track == 'general', 'sequence_outcome': outcome,
            'execution': {'status': 'completed'}, 'assessment': {'status': 'completed', 'method': 'exact-dedicated-molecule-v1' if track == 'diagnostic' else 'wick-longest-alignment-v1', 'query_count': 1},
            'evidence_directory': 'evidence/' + case_id,
            'resources': {'workflow_wall_seconds': 10, 'assembler_process_tree_peak_rss_bytes': 1024},
            'replicons': []}


def seal(root, records, prepared=None):
    root.mkdir()
    (root / 'results.json').write_text(json.dumps({'schema_version': 1, 'run_id': 'mixed-test', 'results': records}))
    (root / 'index.html').write_text('<html><head><title>Producer</title></head><body><main>Prepared results</main></body></html>')
    with (root / 'results.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['case_id', 'assembler', 'sequence_outcome'])
        writer.writerows((r['case']['id'], r['assembler'], r['sequence_outcome']) for r in records)
    if prepared is not None:
        (root / 'presentation').mkdir(exist_ok=True)
        (root / 'presentation/index.json').write_text(json.dumps({'results': prepared}))
    manifest = {'schema_version': 1, 'run_id': 'mixed-test', 'result_count': len(records), 'expected_slots': len(records), 'complete': True,
                'files': {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*') if p.is_file()}}
    (root / 'manifest.json').write_text(json.dumps(manifest))


class NativeRoutes(unittest.TestCase):
    def test_mixed_cohorts_have_independent_pages_and_tsvs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = [record('general-only-case', 'general', 'fully_complete'),
                       record('diagnostic-only-case', 'diagnostic', 'fail', 'S7'),
                       record('real-only-case', 'real', 'incomplete'),
                       record('simulated-only-case', 'simulated', 'empty')]
            records[1]['agreement'] = {'status': 'No order effect observed'}
            records[1]['secondary_reference_status'] = 'fail'
            seal(root / 'bundle', records)
            with patch('subprocess.run', side_effect=AssertionError('No analysis during rendering')):
                render_website(root / 'bundle', root / 'site')
            site = root / 'site'
            for name in ('index.html', 'performance.html', 'aggregate.html', 'real.html', 'simulated.html', 'scenarios/index.html', 'scenarios/s3.html', 'scenarios/s5.html', 'scenarios/s7.html'):
                self.assertTrue((site / name).is_file(), name)
            performance = (site / 'performance.html').read_text()
            self.assertIn('general-only-case', performance)
            for name in ('diagnostic-only-case', 'real-only-case', 'simulated-only-case'):
                self.assertNotIn(name, performance)
            diagnostic = (site / 'scenarios/s7.html').read_text()
            self.assertIn('No order effect observed', diagnostic)
            self.assertIn('Secondary reference verdict', diagnostic)
            self.assertNotIn('99%', diagnostic)
            self.assertNotIn('general-only-case', diagnostic)
            self.assertIn('/data/cohorts/s7.tsv', diagnostic)
            self.assertNotIn('general-only-case', (site / 'data/cohorts/s7.tsv').read_text())
            self.assertNotIn('diagnostic-only-case', (site / 'data/cohorts/general.tsv').read_text())
            for r in records:
                self.assertTrue((site / result_route(r)).is_file())
            self.assertFalse(check_site(site)['errors'])

    def test_graphs_are_per_result_and_home_stays_under_file_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = [record('case-' + str(i), 'general', 'fully_complete') for i in range(3)]
            # More than 5 MiB in total would break an index-embedded design.
            model = {'graph': {'status': 'not_collected'}, 'reason': 'x' * (2 * 1024 * 1024)}
            prepared = [{'case_id': r['case']['id'], 'assembler': r['assembler'], 'graphs': [{'file': f'presentation/graph-{i}.json'}]} for i, r in enumerate(records)]
            seal(root / 'bundle', records, prepared)
            for i in range(3):
                (root / f'bundle/presentation/graph-{i}.json').write_text(json.dumps(model))
            path = root / 'bundle/manifest.json'
            manifest = json.loads(path.read_text())
            manifest['files'].update({f'presentation/graph-{i}.json': digest(root / f'bundle/presentation/graph-{i}.json') for i in range(3)})
            path.write_text(json.dumps(manifest))
            render_website(root / 'bundle', root / 'site')
            site = root / 'site'
            self.assertLess((site / 'index.html').stat().st_size, 100000)
            self.assertNotIn('data-assembly-graph', (site / 'performance.html').read_text())
            for r in records:
                self.assertIn('data-assembly-graph', (site / result_route(r)).read_text())
                self.assertLess((site / result_route(r)).stat().st_size, 5 * 1024 * 1024)
            self.assertFalse(check_site(site)['errors'])


if __name__ == '__main__':
    unittest.main()
