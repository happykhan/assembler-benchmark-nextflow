import unittest
import tempfile
from pathlib import Path
from benchlib.paper_recovery import summarise_paper

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
