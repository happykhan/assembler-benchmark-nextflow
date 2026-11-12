#!/usr/bin/env python3
"""Internal Nextflow task: admit one frozen full-read input, with no simulation."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.io import digest, save
from benchlib.real_inputs import prepare_reads

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--case-json', required=True)
p.add_argument('--plan', type=Path, required=True)
p.add_argument('--reference', type=Path, required=True)
p.add_argument('--reference-provenance', type=Path, required=True)
p.add_argument('--cache', type=Path, required=True)
p.add_argument('--offline', action='store_true')
a = p.parse_args()
case = json.loads(a.case_json)
plan = json.loads(a.plan.read_text())
if case not in plan['cases'] or plan.get('track') != 'real':
    raise ValueError('Case is not bound to the real-data plan')
definition = plan['read_inputs'][case['id']]
reference = json.loads(a.reference_provenance.read_text())
if reference['reference_sha256'] != digest(a.reference) or reference['biosample'] != definition['sample_accession']:
    raise ValueError('Real input/reference binding differs')
reads, stats = prepare_reads(definition, a.cache, a.offline)
Path('reads.fastq').symlink_to(reads)
save('input.json', dict(stats, schema_version=1, status='completed', track='real', case=case,
    reference_sha256=digest(a.reference), reference_provenance_sha256=digest(a.reference_provenance),
    dataset_id=definition['dataset_id'], run_accession=definition['run_accession'],
    sample_accession=definition['sample_accession'], input_policy='full_archive_reads_no_filtering_no_subsampling',
    archive_url=definition['url'], admission_sha256=definition['admission_sha256']))
