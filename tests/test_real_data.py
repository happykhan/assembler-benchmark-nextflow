import json
from pathlib import Path
import unittest

from benchlib.real_data import inspect_manifest

PROJECT = Path(__file__).resolve().parents[1]


class RealDataManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PROJECT / 'assets/real-data/small-plasmids-paper.json').read_text())

    def test_frozen_metadata_and_source_receipts(self):
        result = inspect_manifest(self.manifest, PROJECT)
        self.assertEqual(result['inventory'], {'isolates': 14, 'plasmids': 33,
                                             'small_plasmids_lt_10000bp': 11, 'native_molecules': 47})
        self.assertEqual(result['compressed_ont_download_bytes'], 10933444482)
        self.assertFalse(result['executable'])

    def test_mismatched_run_sample_is_rejected(self):
        self.manifest['isolates'][0]['ont']['sample_accession'] = 'SAMN00000000'
        with self.assertRaisesRegex(ValueError, 'read/BioSample'):
            inspect_manifest(self.manifest)

    def test_mismatched_reference_sample_is_rejected(self):
        self.manifest['isolates'][0]['reference']['molecules'][0]['sample_accession'] = 'SAMN00000000'
        with self.assertRaisesRegex(ValueError, 'molecule/BioSample'):
            inspect_manifest(self.manifest)

    def test_missing_plasmid_is_rejected(self):
        isolate = self.manifest['isolates'][0]
        isolate['reference']['molecules'] = [x for x in isolate['reference']['molecules'] if not x['paper_ref_contig']]
        with self.assertRaisesRegex(ValueError, 'supplementary plasmid'):
            inspect_manifest(self.manifest)

    def test_archive_role_conflict_cannot_be_silently_resolved(self):
        isolate = next(x for x in self.manifest['isolates'] if x['isolate_id'] == '2022NG-0076')
        isolate['reference']['molecules'][0]['role_status'] = 'archive_and_supplement_agree'
        with self.assertRaisesRegex(ValueError, 'role conflict'):
            inspect_manifest(self.manifest)

    def test_metadata_cannot_enable_execution(self):
        self.manifest['executable'] = True
        with self.assertRaisesRegex(ValueError, 'not implemented'):
            inspect_manifest(self.manifest)

    def test_short_reads_cannot_become_assembly_input(self):
        self.manifest['isolates'][0]['ont']['platform'] = 'ILLUMINA'
        with self.assertRaisesRegex(ValueError, 'non-ONT'):
            inspect_manifest(self.manifest)

    def test_tampered_evidence_receipt_is_rejected(self):
        receipt = next(x for x in self.manifest['source_receipts'] if 'file' in x)
        receipt['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Evidence receipt changed'):
            inspect_manifest(self.manifest, PROJECT)

    def test_self_consistent_false_metadata_still_fails_source_binding(self):
        isolate = self.manifest['isolates'][0]
        molecule = next(x for x in isolate['reference']['molecules'] if x['paper_ref_contig'])
        molecule['length_bp'] += 1
        author = next(x for x in isolate['paper_plasmids'] if x['author_contig_id'] == molecule['paper_ref_contig'])
        author['length_bp'] += 1
        with self.assertRaisesRegex(ValueError, 'archived molecule metadata differs'):
            inspect_manifest(self.manifest, PROJECT)

    def test_changed_download_url_fails_source_binding(self):
        self.manifest['isolates'][0]['ont']['files'][0]['url'] = 'https://example.org/unrelated.fastq.gz'
        with self.assertRaisesRegex(ValueError, 'ONT source file metadata differs'):
            inspect_manifest(self.manifest, PROJECT)

    def test_missing_md5_is_rejected(self):
        self.manifest['isolates'][0]['ont']['files'][0]['publisher_md5'] = ''
        with self.assertRaisesRegex(ValueError, 'publisher MD5'):
            inspect_manifest(self.manifest)


if __name__ == '__main__':
    unittest.main()
