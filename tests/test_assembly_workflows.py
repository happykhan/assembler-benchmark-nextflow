"""Multi-stage failure and sequence-source provenance without scientific jobs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchlib.adapters import verify_version, environment_versions, load_registry, resolve_assembler
from benchlib.io import digest
from benchlib.miniasm import run

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('run_assembler', ROOT / 'bin/run-assembler.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
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


class AssemblerRunnerTests(unittest.TestCase):
    def run_plassembler(self, root, no_chromosome=False, version='plassembler, version 1.9.0'):
        reads=root/'reads';reads.write_text('@r\nACGT\n+\nIIII\n')
        def measured(command,stdout,stderr,directory):
            out=directory/'tool-output';out.mkdir()
            (out/'benchmark_plasmids.fasta').write_text('>1\nACGT\n')
            (out/'chromosome.fasta').write_text('>1\nTTTT\n')
            return {'elapsed_seconds':1,'exit_code':0,'peak_memory_kb':100}
        with patch.object(runner.subprocess,'check_output',return_value=version),patch.object(runner,'measured_run',side_effect=measured) as invoke:
            result=runner.run('plassembler',reads,root/'result',4,options={'plassembler_no_chromosome':no_chromosome})
        return result,invoke

    def test_plassembler_uses_final_plasmids_and_actual_chromosome_with_collision_free_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record,invoke=self.run_plassembler(root)
            self.assertEqual(record['status'],'completed')
            self.assertEqual((root/'result/assembly.fasta').read_text(),'>final_plasmids:1\nACGT\n>retained_chromosome:1\nTTTT\n')
            self.assertEqual({r['role'] for r in record['assembly_sources']},{'final_plasmids','retained_chromosome'})
            self.assertEqual(record['retained_chromosome_sha256'],digest(root/'result/tool-output/chromosome.fasta'))
            self.assertEqual(record['assembly_sha256'],digest(root/'result/assembly.fasta'))
            self.assertIn('--keep_chromosome',invoke.call_args.args[0])

    def test_no_chromosome_mode_does_not_admit_incidental_chromosome(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record,invoke=self.run_plassembler(root,no_chromosome=True)
            self.assertEqual(record['status'],'completed')
            self.assertEqual((root/'result/assembly.fasta').read_text(),'>final_plasmids:1\nACGT\n')
            self.assertNotIn('retained_chromosome_sha256',record)
            self.assertIn('--no_chromosome',invoke.call_args.args[0])

    def test_wrong_primary_version_never_invokes_assembler(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record,invoke=self.run_plassembler(root,version='plassembler, version 1.9.00')
            self.assertEqual(record['status'],'infrastructure_error')
            invoke.assert_not_called()
            self.assertIn('Pinned version mismatch',record['error'])

    def test_outer_polishing_failure_exports_failure_with_unchanged_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reads=root/'reads';reads.write_text('@r\nACGT\n+\nIIII\n')
            def measured(command,stdout,stderr,directory):
                try:
                    with patch('benchlib.miniasm.subprocess.run',side_effect=MiniasmWorkflowTests().fake_tools(polish_exit=1)):
                        run(reads,directory/'tool-output',4,True,VERSIONS)
                except RuntimeError:
                    pass
                return {'elapsed_seconds':2,'exit_code':1,'peak_memory_kb':100}
            with patch.object(runner.subprocess,'check_output',return_value='0.2.1'),patch.object(runner,'measured_run',side_effect=measured):
                record=runner.run('miniasm-plus',reads,root/'result',4)
            self.assertEqual(record['status'],'software_error')
            self.assertNotIn('assembly_sha256',record)
            workflow=root/'result/tool-output/workflow.json'
            self.assertEqual(record['assembly_workflow_sha256'],digest(workflow))
            raw=root/'result/tool-output/raw-phase/execution.json'
            self.assertEqual(record['assembly_workflow']['raw_phase_execution_sha256'],digest(raw))
            self.assertEqual(record['reads_sha256'],record['assembly_workflow']['reads_sha256'])
            self.assertEqual((raw.parent/'assembly.fasta').read_text(),'>utg1\nACGT\n')

    def test_version_parser_refuses_embedded_or_multiple_versions(self):
        for observed in ('0.30','unexpected 0.3','error: expected 0.3 but running 0.4','0.3\n0.4'):
            with self.subTest(observed=observed),self.assertRaises(ValueError):
                verify_version(observed,'0.3','miniasm')
        self.assertEqual(verify_version('0.3-r179','0.3','miniasm'),'0.3-r179')
        verify_version('minipolish v0.2.1','0.2.1','minipolish')

    def test_multistage_dependency_versions_come_from_exact_environment_pins(self):
        definition=resolve_assembler(load_registry(ROOT/'assets/assemblers.json'),'miniasm-plus')
        self.assertEqual(environment_versions(definition,ROOT),VERSIONS)


if __name__=='__main__':
    unittest.main()
