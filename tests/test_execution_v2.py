"""Fragmentation metrics and explicit failures stay distinct."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from benchlib.assembly import assemble
from benchlib.measurement import assess,n50,union_breadth
from benchlib.io import digest


class ExecutionV2Tests(unittest.TestCase):
    def test_fragmented_breadth_is_not_single_alignment_completion(self):
        rows=[{'reference_start':0,'reference_end':500},{'reference_start':500,'reference_end':1000}]
        self.assertEqual(union_breadth(rows,1000),1)
        self.assertEqual(n50([500,500]),500)
        self.assertIsNone(n50([100,100],1000))

    def test_union_counts_overlap_and_wrap_once(self):
        self.assertEqual(union_breadth([{'reference_start':950,'reference_end':1050}],1000),.1)
        self.assertEqual(union_breadth([{'reference_start':0,'reference_end':700},{'reference_start':200,'reference_end':900}],1000),.9)
        self.assertEqual(union_breadth([{'reference_start':900,'reference_end':2100}],1000),1)
        self.assertEqual(union_breadth([],1000),0)

    def test_nonzero_exit_is_failure_without_sequence_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared=root/'prepared';prepared.mkdir()
            (prepared/'reads.fastq').write_text('@r\nACGT\n+\nIIII\n')
            (prepared/'reference.fasta').write_text('>REF.1\nACGT\n')
            (prepared/'reference.json').write_text(json.dumps({'reference_sha256':digest(prepared/'reference.fasta'),'molecules':[]}))
            inp={'id':'input-test','layout':'long_single','files':['reads.fastq'],'file_sha256':{'reads.fastq':digest(prepared/'reads.fastq')},
                 'reference':'reference.fasta','reference_metadata':'reference.json','observed':{}}
            (prepared/'input.json').write_text(json.dumps(inp))
            workflow={'id':'raven-default','tool':'raven','adapter':'raven','version':'1.8.3','version_order':10803,
                      'resources':{'cpus':1,'memory_gb':2},'configuration':{}}
            def failed(command,stdout,stderr,cwd):
                stdout.write_text('');stderr.write_text('failed')
                return {'exit_code':139,'elapsed_seconds':.01,'process_tree_peak_rss_bytes':1}
            with patch('subprocess.check_output',return_value='Raven 1.8.3'),patch('benchlib.assembly.measured_run',side_effect=failed):
                result=assemble(prepared,workflow,root/'execution',root)
            self.assertEqual(result['status'],'execution_failure');self.assertEqual(result['exit_code'],139);self.assertEqual(result['failure_kind'],'software')
            case={'id':'test','read_technology':'long','recipe':{}}
            with patch('benchlib.measurement.measured_run',side_effect=AssertionError('No mapping after failure')):
                measured=assess(prepared,root/'execution',{'case':case,'workflow':workflow},root/'assessment')
            self.assertEqual(measured['status'],'execution_failure');self.assertIsNone(measured['sequence_outcome'])
            self.assertFalse(any(m['name']=='reference_breadth' for m in measured['metrics']))

    def test_wrong_input_binding_is_assessment_failure_without_sequence_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared=root/'prepared';prepared.mkdir();execution=root/'execution';execution.mkdir()
            (prepared/'input.json').write_text(json.dumps({'id':'input-a','reference_metadata':'reference.json','layout':'long_single','observed':{}}))
            (prepared/'reference.json').write_text('{}')
            (execution/'execution.json').write_text(json.dumps({'status':'completed','input_id':'input-b','input_sha256':'wrong'}))
            slot={'case':{'id':'test','recipe':{},'read_technology':'long'},'workflow':{}}
            with patch('benchlib.measurement.measured_run',side_effect=AssertionError('Must not map mismatched input')):
                result=assess(prepared,execution,slot,root/'assessment')
            self.assertEqual(result['status'],'assessment_failure')
            self.assertIsNone(result['sequence_outcome'])
            self.assertIn('binding differs',result['reason'])
