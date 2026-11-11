"""Contracts protect exact read budgets and preserve failed tool executions."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'bin' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


simulate = script('simulate-reads')
assembler = script('run-assembler')


class SimulationContracts(unittest.TestCase):
    def test_mode_interleaving_is_reproducible_and_preserves_every_record(self):
        with tempfile.TemporaryDirectory() as directory:
            sources = []
            for label in ('short', 'long'):
                path = Path(directory) / (label + '.fastq')
                path.write_text(''.join(f'@{label}{i}\nACGT\n+\nIIII\n' for i in range(10)))
                sources.append((path, 10))
            first, second = io.StringIO(), io.StringIO()
            simulate.mix_modes(sources, first, 42)
            simulate.mix_modes(sources, second, 42)
            self.assertEqual(first.getvalue(), second.getvalue())
            names = first.getvalue().splitlines()[::4]
            self.assertEqual(set(names), {f'@{label}{i}' for label in ('short', 'long') for i in range(10)})
            self.assertEqual(len(names), 20)
            self.assertTrue(any(name.startswith('@long') for name in names[:10]))
            self.assertTrue(any(name.startswith('@short') for name in names[10:]))

    def test_last_read_is_trimmed_without_changing_surviving_bases(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.fastq'
            source.write_text('@a\nACGT\n+\nIIII\n@b\nTGCA\n+\nJJJJ\n')
            output = io.StringIO()
            self.assertEqual(simulate.write_mode(source, output, 6, 'short'), [4, 2])
            self.assertEqual(output.getvalue(), '@short_0 a\nACGT\n+\nIIII\n@short_1 b\nTG\n+\nJJ\n')

    def test_insufficient_simulated_bases_are_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.fastq'
            source.write_text('@a\nACGT\n+\nIIII\n')
            with self.assertRaisesRegex(ValueError, 'fewer than requested'):
                simulate.write_mode(source, io.StringIO(), 10, 'long')

    def test_unknown_simulation_parameter_is_rejected(self):
        case = {'id': 'example', 'group': 'reads', 'coverage': 30, 'seed': 42,
                'length_mean': 10000, 'length_sd': 2000, 'unimplemented_error_rate': 0.05}
        with self.assertRaisesRegex(ValueError, 'Unsupported simulation fields'):
            simulate.validate_case(case)


class AssemblerContracts(unittest.TestCase):
    def test_nonzero_tool_exit_is_preserved_without_retry_or_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            reads = path / 'reads.fastq'
            reads.write_text('@a\nACGT\n+\nIIII\n')

            def failed(command, stdout, stderr, cwd):
                stdout.write_text('')
                stderr.write_text('Segmentation fault\n')
                return {'exit_code': 139, 'elapsed_seconds': 1.5, 'process_tree_peak_rss_bytes': 4096}

            with patch.object(assembler.subprocess, 'check_output', return_value='1.8.3'), \
                 patch.object(assembler, 'measured_run', side_effect=failed) as measured, \
                 patch.object(assembler.time, 'monotonic', side_effect=[100, 105]):
                record = assembler.run('raven', reads, path / 'run', 1)
            self.assertEqual(measured.call_count, 1)
            self.assertEqual(record['status'], 'software_error')
            self.assertEqual(record['exit_code'], 139)
            self.assertEqual(record['version'], '1.8.3')
            self.assertEqual(record['elapsed_seconds'], 5)
            self.assertEqual(record['tool_elapsed_seconds'], 1.5)
            self.assertEqual(record['environment_lock_sha256'], assembler.digest(ROOT / 'environments/pixi.lock'))
            self.assertEqual(record['adapter_source_sha256'], assembler.digest(ROOT / 'bin/run-assembler.py'))
            self.assertEqual(record['log_sha256']['stderr.log'], assembler.digest(path / 'run/stderr.log'))
            self.assertNotIn('assembly_sha256', record)
            original = (path / 'run/execution.json').read_bytes()
            with self.assertRaises(FileExistsError):
                assembler.run('raven', reads, path / 'run', 1)
            self.assertEqual((path / 'run/execution.json').read_bytes(), original)

    def test_successful_empty_output_is_a_retained_sequence_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            reads = path / 'reads.fastq'
            reads.write_text('@a\nACGT\n+\nIIII\n')

            def completed(command, stdout, stderr, cwd):
                stdout.write_text('')
                stderr.write_text('No contigs retained\n')
                return {'exit_code': 0, 'elapsed_seconds': 1.5, 'process_tree_peak_rss_bytes': 4096}

            with patch.object(assembler.subprocess, 'check_output', return_value='1.8.3'), \
                 patch.object(assembler, 'measured_run', side_effect=completed):
                record = assembler.run('raven', reads, path / 'run', 1)
            self.assertEqual(record['status'], 'completed')
            self.assertEqual(record['assembly_state'], 'empty')
            self.assertEqual(record['assembly_sha256'], assembler.digest(path / 'run/assembly.fasta'))
            self.assertEqual(record['log_sha256']['stderr.log'], assembler.digest(path / 'run/stderr.log'))

    def test_missing_required_output_remains_software_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            reads = path / 'reads.fastq'
            reads.write_text('@a\nACGT\n+\nIIII\n')
            with patch.object(assembler.subprocess, 'check_output', return_value='2.9.6'), \
                 patch.object(assembler, 'measured_run', return_value={
                     'exit_code': 0, 'elapsed_seconds': 1.5, 'process_tree_peak_rss_bytes': 4096}):
                record = assembler.run('flye', reads, path / 'run', 1)
            self.assertEqual(record['status'], 'software_error')
            self.assertNotIn('assembly_sha256', record)
