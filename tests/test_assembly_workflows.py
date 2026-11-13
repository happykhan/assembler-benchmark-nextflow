"""Multi-stage failure and sequence-source provenance without scientific jobs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchlib.adapters import verify_version, environment_versions
from benchlib.io import digest
from benchlib.miniasm import run

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {'minimap2':'2.31', 'miniasm':'0.3', 'minipolish':'0.2.1', 'racon':'1.5.0'}
RAW = 'S\tutg1\tACGT\tLN:i:4\n' + 'a\tutg1\t0\tread1\t+\t0\t4\n'
POLISHED = 'S\tutg1\tACGTA\n'


class MiniasmWorkflowTests(unittest.TestCase):
    def fake_tools(self, polish_exit=0, bad_version=None):
        def invoke(command, **kwargs):
            binary = command[0]
            if command[1] in ('--version','-V'):
                versions = dict(VERSIONS, minimap2='2.31-r1302', miniasm='0.3-r179')
                return subprocess.CompletedProcess(command,0,stdout=bad_version if binary=='miniasm' and bad_version else versions[binary],stderr='')
            if binary=='minimap2':
                kwargs['stdout'].write('overlap\n')
            elif binary=='miniasm':
                kwargs['stdout'].write(RAW)
            elif binary=='minipolish':
                kwargs['stdout'].write(POLISHED if not polish_exit else 'partial polished output')
                return subprocess.CompletedProcess(command,polish_exit)
            return subprocess.CompletedProcess(command,0)
        return invoke

    def test_polished_result_keeps_bound_raw_phase_and_all_dependency_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reads=root/'reads.fastq';reads.write_text('@r\nACGT\n+\nIIII\n')
            with patch('benchlib.miniasm.subprocess.run',side_effect=self.fake_tools()):
                result=run(reads,root/'result',4,True,VERSIONS)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(set(result['versions']),set(VERSIONS))
            self.assertEqual((root/'result/assembly.fasta').read_text(),'>utg1\nACGTA\n')
            self.assertEqual((root/'result/raw-phase/assembly.fasta').read_text(),'>utg1\nACGT\n')
            self.assertEqual((root/'result/raw-phase/assembly.raw.gfa').read_text(),RAW)
            raw=json.loads((root/'result/raw-phase/execution.json').read_text())
            self.assertEqual(raw['reads_sha256'],digest(reads))
            self.assertEqual(len(raw['steps']),2)
            self.assertEqual(raw['conversion']['raw_annotation_records'],{'a':1})
            self.assertFalse(result['raw_phase_reported_outcome'])
            self.assertEqual(result['raw_phase_execution_sha256'],digest(root/'result/raw-phase/execution.json'))
            self.assertEqual(result['steps'][-1]['command'][1:5],['--threads','4','--rounds','2'])

    def test_polishing_failure_preserves_raw_phase_without_reporting_raw_as_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reads=root/'reads';reads.write_text('@r\nACGT\n+\nIIII\n')
            with patch('benchlib.miniasm.subprocess.run',side_effect=self.fake_tools(polish_exit=139)):
                with self.assertRaisesRegex(RuntimeError,'139'):
                    run(reads,root/'result',4,True,VERSIONS)
            record=json.loads((root/'result/workflow.json').read_text())
            raw=root/'result/raw-phase'
            self.assertEqual(record['status'],'software_error')
            self.assertEqual(record['steps'][-1]['exit_code'],139)
            self.assertEqual((raw/'assembly.fasta').read_text(),'>utg1\nACGT\n')
            self.assertEqual(record['raw_phase_execution_sha256'],digest(raw/'execution.json'))
            self.assertIn('assembly.polished.gfa',record['retained_file_sha256'])

    def test_version_drift_stops_before_any_assembly_and_is_infrastructure_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reads=root/'reads';reads.write_text('input')
            with patch('benchlib.miniasm.subprocess.run',side_effect=self.fake_tools(bad_version='0.30-r179')) as call:
                with self.assertRaisesRegex(ValueError,'Pinned version mismatch'):
                    run(reads,root/'result',4,False,VERSIONS)
            self.assertEqual(call.call_count,2)
            record=json.loads((root/'result/workflow.json').read_text())
            self.assertEqual(record['status'],'infrastructure_error')
            self.assertFalse((root/'result/assembly.raw.gfa').exists())
