"""Archive admission and standalone-render regression tests.

Full historical verification is opt-in with BENCHMARK_HISTORICAL_BUNDLE and
BENCHMARK_HISTORICAL_SITE, pointing to already frozen evidence, never a run.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reporting.archive import import_archive, render_website, validate_archive
from reporting.common import digest
from reporting.site_gate import check_site


def seal(root):
    record = {'case': {'id': 'fixture'}, 'assembler': 'fixture-v1',
              'assessment': {'status': 'not_run', 'identity': None},
              'execution': {'status': 'software_error'}}
    (root / 'results.json').write_text(json.dumps({'schema_version': 1, 'run_id': 'fixture', 'results': [record]}))
    (root / 'results.tsv').write_text('case\tidentity\tstatus\nfixture\t\tsoftware_error\n')
    (root / 'index.html').write_text('<html><head><title>Fixture</title></head><body><main><h1>Fixture</h1><a href="results.tsv">TSV</a><a href="results.json">JSON</a></main></body></html>')
    manifest = {'schema_version': 1, 'run_id': 'fixture', 'expected_slots': 1, 'result_count': 1,
                'complete': True, 'expected_slot_plan': [{'case_id': 'fixture', 'assembler': 'fixture-v1'}],
                'files': {p.name: digest(p) for p in root.iterdir()}}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return record


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.record = seal(self.source)

    def tearDown(self):
        self.temporary.cleanup()

    def test_import_retains_all_bytes_and_unknowns(self):
        output = self.root / 'admitted'
        receipt = import_archive(self.source, output)
        for source in self.source.iterdir():
            self.assertEqual(source.read_bytes(), (output / source.name).read_bytes())
        self.assertTrue((self.root / 'admitted.import.json').is_file())
        self.assertEqual(receipt['manifest_sha256'], digest(output / 'manifest.json'))
        self.assertIsNone(json.loads((output / 'results.json').read_text())['results'][0]['assessment']['identity'])

    def test_import_is_immutable(self):
        output = self.root / 'admitted'
        import_archive(self.source, output)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            import_archive(self.source, output)

    def test_changed_record_is_rejected(self):
        (self.source / 'results.tsv').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            import_archive(self.source, self.root / 'admitted')
        self.assertFalse((self.root / 'admitted').exists())

    def test_unsealed_file_is_rejected(self):
        (self.source / 'extra.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'unmanifested'):
            validate_archive(self.source)

    def test_parent_symlink_is_rejected(self):
        (self.source / 'results.tsv').unlink()
        (self.source / 'results.tsv').symlink_to(self.source / 'results.json')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            validate_archive(self.source)

    def test_frozen_slot_mismatch_is_rejected(self):
        path = self.source / 'manifest.json'
        value = json.loads(path.read_text())
        value['expected_slot_plan'][0]['assembler'] = 'different'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'slot plan'):
            validate_archive(self.source)

    def test_render_survives_original_source_removal_without_analysis(self):
        archive, site = self.root / 'admitted', self.root / 'website'
        import_archive(self.source, archive)
        self.source.rename(self.root / 'unavailable-source')
        before = digest(archive / 'manifest.json')
        with patch('subprocess.run', side_effect=AssertionError('No external analysis during rendering')):
            render_website(archive, site)
        self.assertEqual(before, digest(archive / 'manifest.json'))
        self.assertEqual((archive / 'results.tsv').read_bytes(), (site / 'results.tsv').read_bytes())
        self.assertNotIn('href="results.json"', (site / 'index.html').read_text())
        self.assertFalse(check_site(site)['errors'])

    def test_render_rejects_non_generated_destination(self):
        output = self.root / 'website'
        output.mkdir()
        (output / 'precious.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'destination'):
            render_website(self.source, output)
        self.assertEqual((output / 'precious.txt').read_text(), 'keep')


@unittest.skipUnless(os.environ.get('BENCHMARK_HISTORICAL_BUNDLE'), 'Full frozen archive not configured')
class HistoricalParity(unittest.TestCase):
    def test_lossless_import_and_complete_standalone_render(self):
        source = Path(os.environ['BENCHMARK_HISTORICAL_BUNDLE']).resolve()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, output = root / 'admitted', root / 'website'
            import_archive(source, archive)
            manifest, kind = validate_archive(archive)
            self.assertEqual(kind, 'historical')
            # The original source is inaccessible to the renderer, which receives
            # only admitted files and this repository's presentation code/assets.
            original_open = Path.open
            def independent_open(path, *args, **kwargs):
                if path.resolve().is_relative_to(source):
                    raise AssertionError('Renderer accessed original evidence source')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', independent_open), patch('subprocess.run', side_effect=AssertionError('Unexpected analysis process')):
                render_website(archive, output)
            self.assertEqual(digest(source / 'manifest.json'), digest(archive / 'manifest.json'))
            performance = json.loads((archive / 'performance/model.json').read_text())
            self.assertEqual(len(performance['results']), 200)
            for name in ('index.html', 'performance.html', 'aggregate.html', 'diagnostic-plots.html', 'scenarios/s5.html', 'scenarios/s7.html', 'data/read-order/runs.tsv'):
                self.assertTrue((output / name).is_file(), name)
            self.assertEqual((output / 'data/summary.tsv').read_bytes(), (archive / 'summary.tsv').read_bytes())
            self.assertFalse(check_site(output)['errors'])
            reference = os.environ.get('BENCHMARK_HISTORICAL_SITE')
            if reference:
                reference = Path(reference)
                source_files = {p.relative_to(reference).as_posix() for p in reference.rglob('*') if p.is_file()}
                output_files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
                # Gate receipts contain output paths and are administrative.
                ignore = {'site-receipt.json', '.results-render.json', '.site-files.json', 'site-manifest.json', '.vercel/project.json'}
                self.assertEqual(source_files - ignore, output_files - ignore)
                for name in sorted(source_files - ignore):
                    self.assertEqual(digest(reference / name), digest(output / name), name)


if __name__ == '__main__':
    unittest.main()
