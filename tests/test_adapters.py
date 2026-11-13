from pathlib import Path
import unittest
from benchlib.adapters import ADAPTERS

class AdapterTests(unittest.TestCase):
    def test_adapter_arguments_preserve_paths_without_shell_interpretation(self):
        reads = Path('/reads/a file;echo injected.fastq')
        for adapter in ADAPTERS.values():
            command = adapter.command(reads, 3)
            self.assertIn(str(reads), command)
            if adapter.executable != 'miniasm':
                self.assertIn('3', command)
            self.assertEqual(command[0], adapter.executable)

    def test_configuration_modes_are_explicit_and_checked(self):
        from benchlib.adapters import validate_options
        command = ADAPTERS['flye'].command('reads.fastq', 4, {'flye_input_mode': 'nano-hq', 'flye_meta': True, 'deterministic': True})
        self.assertIn('--nano-hq', command)
        self.assertIn('--meta', command)
        self.assertIn('--deterministic', command)
        command = ADAPTERS['plassembler'].command('reads.fastq', 4, {'plassembler_raw_flag': True})
        self.assertIn('--keep_chromosome', command)
        self.assertIn('--raw_flag', command)
        self.assertNotIn('--no_chromosome', command)
        for invalid in ({'tune': 5}, {'deterministic': 'true'}, {'flye_input_mode': 'anything'}, {'plassembler_chromosome_threshold': 0}):
            with self.assertRaises(ValueError):
                validate_options(invalid)

    def test_unimplemented_configuration_cannot_be_recorded_as_executed(self):
        from benchlib.workflow_options import workflow_options
        for tool,options in [('raven',{'threads':8}),('skesa',{'kmer':31}),('miniasm',{'mode':'tuned'}),('flye',{'plassembler_raw_flag':True})]:
            with self.subTest(tool=tool),self.assertRaises(ValueError):workflow_options(tool,options)
        self.assertEqual(workflow_options('flye',{'mode':'default','flye_input_mode':'nano-hq','deterministic':True}),{'flye_input_mode':'nano-hq','deterministic':True})
