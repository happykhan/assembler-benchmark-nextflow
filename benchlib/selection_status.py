"""Selected-slot completeness, separate from independently published results."""
from collections import Counter
from pathlib import Path
import json
import os
import uuid

from .current_results import load_current


def selection_status(root, definitions):
    expected=set(definitions['expected_result_ids'])
    records={row['result_id']:row for row in load_current(root)}
    available=expected & records.keys()
    counts=Counter(records[key]['status'] for key in available)
    return {'schema_version':2,'plan_sha256':definitions['plan_sha256'],
            'expected_result_ids':sorted(expected),'available_result_ids':sorted(available),
            'missing_result_ids':sorted(expected-available),'status_counts':dict(sorted(counts.items())),
            'complete':not (expected-available) and not counts['not_run'],
            'assessment_complete':not (expected-available) and not counts['not_run'] and not counts['assessment_failure'],
            'scope':'Latest selected workload; unrelated current results are retained. Execution failures are terminal outcomes, not evidence of sequence absence.'}


def publish_selection_status(root, definitions):
    result=selection_status(root,definitions);root=Path(root)
    temporary=root/('.selection-'+uuid.uuid4().hex+'.json')
    try:
        temporary.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        os.replace(temporary,root/'selection.json')
    finally:
        temporary.unlink(missing_ok=True)
    return result
