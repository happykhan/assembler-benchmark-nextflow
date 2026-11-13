import json
from pathlib import Path
import tempfile
import unittest
from benchlib.current_results import publish_result,result_identity
from benchlib.selection_status import publish_selection_status
from test_current_results import record


class SelectionStatusTests(unittest.TestCase):
    def test_missing_and_assessment_failure_stay_distinct_from_execution_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'current'
            publish_result(root,record('one',status='execution_failure'))
            publish_result(root,record('unrelated'))
            definitions={'plan_sha256':'a'*64,'expected_result_ids':[result_identity(case,'assembler-default') for case in ['one','two']]}
            missing=publish_selection_status(root,definitions)
            self.assertFalse(missing['complete']);self.assertEqual(len(missing['missing_result_ids']),1)
            self.assertEqual(missing['status_counts'],{'execution_failure':1})
            publish_result(root,record('two',status='assessment_failure'))
            failed=publish_selection_status(root,definitions)
            self.assertTrue(failed['complete']);self.assertFalse(failed['assessment_complete'])
            publish_result(root,record('two'))
            done=publish_selection_status(root,definitions)
            self.assertTrue(done['complete']);self.assertTrue(done['assessment_complete'])
            self.assertEqual(json.loads((root/'selection.json').read_text()),done)
