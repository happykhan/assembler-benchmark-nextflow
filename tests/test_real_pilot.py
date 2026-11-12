"""Full-read admission and two scientifically distinct recovery endpoints."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from benchlib.planning import build_plan, validate_plan
from benchlib.real_inputs import prepare_reads, unpack_fastq
from benchlib.paper_recovery import summarise_paper

ROOT = Path(__file__).resolve().parents[1]


class RealPlanTests(unittest.TestCase):
    def test_real_plan_binds_one_sample_five_molecules_and_two_versions(self):
        plan = build_plan(ROOT, 'standard', track='real')
        self.assertEqual(plan['expected_slots'], 2)
        self.assertEqual(plan['track'], 'real')
        self.assertFalse(plan['headline_eligible'])
        self.assertEqual(len(plan['references']['johnson-atcc25922-native']['molecules']), 5)
        self.assertEqual(plan['read_inputs']['johnson-atcc25922-full']['read_count'], 165764)
        self.assertEqual(validate_plan(ROOT, plan), plan)
        with self.assertRaisesRegex(ValueError, 'Quick remains simulated'):
            build_plan(ROOT, track='real')
        with self.assertRaisesRegex(ValueError, 'Unknown real-data'):
            build_plan(ROOT, 'standard', cases='other-isolate', track='real')

    def test_same_biosample_and_archive_bindings_cannot_be_relaxed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            shutil.copytree(ROOT / 'assets', project / 'assets')
            shutil.copytree(ROOT / 'evidence/real-data', project / 'evidence/real-data')
            (project / 'environments').mkdir()
            for name in ('pixi.toml', 'pixi.lock'):
                shutil.copyfile(ROOT / 'environments' / name, project / 'environments' / name)
            path = project / 'assets/real-pilot.json'
            data = json.loads(path.read_text())
            data['read_inputs']['johnson-atcc25922-full']['sample_accession'] = 'SAMN00000000'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'BioSample binding'):
                build_plan(project, 'standard', track='real')


class RealReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = b'@r1 original header\nACGT\n+\n!!!!\n@r2\nGGC\n+\nABC\n'
        source = self.root / 'SRR123.fastq.gz'
        source.write_bytes(gzip.compress(self.original, mtime=0))
        self.definition = {'run_accession': 'SRR123', 'compressed_bytes': source.stat().st_size,
            'publisher_md5': hashlib.md5(source.read_bytes()).hexdigest(),
            'download_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'reads_sha256': hashlib.sha256(self.original).hexdigest(), 'read_count': 2,
            'total_bases': 7, 'decompressed_bytes': len(self.original)}

    def test_offline_preparation_preserves_all_bytes_and_detects_cache_change(self):
        reads, stats = prepare_reads(self.definition, self.root, offline=True)
        self.assertEqual(reads.read_bytes(), self.original)
        self.assertEqual(stats['read_count'], 2)
        self.assertEqual(stats['n50'], 4)
        reads.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'reads changed'):
            prepare_reads(self.definition, self.root, offline=True)

    def test_failed_read_count_and_publisher_checksum_do_not_establish_admission(self):
        altered = dict(self.definition, read_count=3)
        with self.assertRaisesRegex(ValueError, 'read_count differs'):
            prepare_reads(altered, self.root, offline=True)
        altered = dict(self.definition, publisher_md5='0' * 32)
        with self.assertRaisesRegex(ValueError, 'publisher MD5'):
            prepare_reads(altered, self.root, offline=True)

    def test_truncated_fastq_is_rejected_without_inventing_reads(self):
        source = self.root / 'truncated.gz'
        source.write_bytes(gzip.compress(b'@read\nACGT\n+\n!!!\n'))
        with self.assertRaisesRegex(ValueError, 'Invalid or truncated'):
            unpack_fastq(source, self.root / 'output.fastq')


class PaperRuleTests(unittest.TestCase):
    def measure(self, hits):
        with tempfile.TemporaryDirectory() as directory:
            paf = Path(directory) / 'test.paf'
            references = {'p': 'A' * 1000}
            assembly = {name: 'A' * size for name, size, block in hits}
            paf.write_text(('p\t1000\t0\t0\t*\t*\t0\t0\t0\t0\t0\t0\n' if not hits else '') + ''.join(f'p\t1000\t0\t{block}\t+\t{name}\t{size}\t0\t{block}\t{block}\t{block}\t60\n' for name,size,block in hits))
            return summarise_paper(paf, references, assembly, {'p': 'plasmid'})[0]

    def test_threshold_is_strict_not_99_percent_contiguity(self):
        self.assertFalse(self.measure([('a',1000,900)])['recovered'])
        self.assertTrue(self.measure([('a',1000,901)])['recovered'])

    def test_fragmented_recovery_is_sum_not_longest_alignment(self):
        row = self.measure([('a',1000,500),('b',1000,450)])
        self.assertTrue(row['recovered'])
        self.assertTrue(row['fragmented_recovery'])
        self.assertFalse(row['duplicate_recovering_contigs'])

    def test_duplicates_and_length_heuristic_remain_distinct(self):
        row = self.measure([('a',1000001,950),('b',1000,950)])
        self.assertTrue(row['duplicate_recovering_contigs'])
        self.assertTrue(row['chromosome_incorporation_heuristic'])
        self.assertEqual(row['summed_block_fraction'], 1.9)

    def test_explicit_no_hit_is_measured_below_threshold(self):
        row = self.measure([])
        self.assertFalse(row['recovered'])
        self.assertEqual(row['status'], 'measured')


class PaperMissingMeasurementTests(unittest.TestCase):
    def test_empty_paf_is_an_error_when_no_hit_records_were_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            paf = Path(directory) / 'empty.paf'
            paf.write_text('')
            with self.assertRaisesRegex(ValueError, 'explicit alignment or no-hit'):
                summarise_paper(paf, {'p': 'A' * 1000}, {}, {'p': 'plasmid'})


class ReadSupportTests(unittest.TestCase):
    def test_union_breadth_and_summed_depth_are_distinct(self):
        from benchlib.read_diagnostics import summarise_read_paf
        with tempfile.TemporaryDirectory() as directory:
            paf = Path(directory) / 'reads.paf'
            paf.write_text('r1\t80\t0\t80\t+\tp\t100\t0\t80\t80\t80\t60\n'
                           'r2\t80\t0\t80\t+\tp\t100\t20\t100\t80\t80\t60\n')
            rows = summarise_read_paf(paf, {'p': 'A' * 100, 'unmapped': 'C' * 50})
        self.assertEqual(rows[0]['reference_breadth'], 1)
        self.assertEqual(rows[0]['mean_aligned_target_depth'], 1.6)
        self.assertEqual(rows[0]['distinct_mapped_read_ids'], 2)
        self.assertEqual(rows[1]['covered_reference_bases'], 0)


class ArchiveTransportTests(unittest.TestCase):
    def test_truncated_valid_range_resumes_from_actual_received_offset(self):
        import io
        from unittest.mock import patch
        from benchlib.real_inputs import download_archive
        payload = b'0123456789abcdefghij'
        calls = []
        def response(request, timeout):
            start,end = map(int,request.get_header('Range').split('=')[1].split('-'))
            calls.append((start,end))
            body = payload[start:end+1]
            if start == 0: body = body[:4]
            result = io.BytesIO(body)
            result.status = 206
            result.headers = {'Content-Range':f'bytes {start}-{end}/{len(payload)}'}
            return result
        definition = {'url':'https://example.test/data','compressed_bytes':len(payload),
            'publisher_md5':hashlib.md5(payload).hexdigest(),'download_sha256':hashlib.sha256(payload).hexdigest()}
        with tempfile.TemporaryDirectory() as directory, patch('urllib.request.urlopen', side_effect=response):
            target = Path(directory)/'archive'
            receipt = download_archive(definition,target,chunk_bytes=8,use_curl=False)
            self.assertEqual(target.read_bytes(),payload)
        self.assertEqual(calls,[(0,7),(4,11),(12,19)])
        self.assertEqual(receipt['verified_bytes'],len(payload))

    def test_wrong_content_range_is_rejected_before_admission(self):
        import io
        from unittest.mock import patch
        from benchlib.real_inputs import download_archive
        response = io.BytesIO(b'abc')
        response.status=206;response.headers={'Content-Range':'bytes 1-3/3'}
        with tempfile.TemporaryDirectory() as directory, patch('urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'range binding'):
                download_archive({'url':'https://example.test/data','compressed_bytes':3},Path(directory)/'archive',use_curl=False)

    def test_same_size_corrupt_curl_stream_cannot_bypass_hash_admission(self):
        import subprocess
        from unittest.mock import patch
        from benchlib.real_inputs import download_archive
        correct = b'correct'; corrupt = b'changed'
        def run(command, **kwargs):
            target = Path(command[command.index('--output')+1])
            target.write_bytes(corrupt)
            return subprocess.CompletedProcess(command,0,stdout='',stderr='')
        definition = {'url':'https://example.test/data','compressed_bytes':len(correct),
            'publisher_md5':hashlib.md5(correct).hexdigest(),'download_sha256':hashlib.sha256(correct).hexdigest()}
        with tempfile.TemporaryDirectory() as directory, patch('shutil.which',return_value='/curl'), patch('subprocess.run',side_effect=run):
            with self.assertRaisesRegex(ValueError,'publisher MD5'):
                download_archive(definition,Path(directory)/'archive')
