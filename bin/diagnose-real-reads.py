#!/usr/bin/env python3
"""Read-support diagnostics, independent of assembly recovery verdicts."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.assessment import read_fasta, sha256, write_json
from benchlib.process import measured_run
from benchlib.read_diagnostics import summarise_read_paf

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--reference', type=Path, required=True)
p.add_argument('--reads', type=Path, required=True)
p.add_argument('--input-provenance', type=Path, required=True)
p.add_argument('--cpus', type=int, default=4)
a = p.parse_args()
metadata = json.loads(a.input_provenance.read_text())
if sha256(a.reads) != metadata['reads_sha256'] or sha256(a.reference) != metadata['reference_sha256']:
    raise ValueError('Diagnostic input hash binding differs')
output = Path('read-diagnostics'); output.mkdir()
refs = read_fasta(a.reference)
paf = output / 'read-alignment.paf'
command = ['minimap2', '-t', str(a.cpus), '-x', 'map-ont', '--secondary=no', str(a.reference.resolve()), str(a.reads.resolve())]
measurement = measured_run(command, paf, output / 'minimap2.stderr.log', output)
if measurement['exit_code']:
    raise ValueError('Read mapper failed; coverage is unresolved')
rows = summarise_read_paf(paf, refs)
write_json(output/'read-diagnostics.json', {'schema_version':1,'case_id':metadata['case']['id'],
    'run_accession':metadata['run_accession'],'reads_sha256':metadata['reads_sha256'],
    'reference_sha256':metadata['reference_sha256'],'status':'completed','command':command,
    'paf_sha256':sha256(paf),'measurement':measurement,'molecules':rows,
    'scope':'Native-reference mapping; secondary mappings suppressed, split mappings retained. Depth sums aligned target spans; breadth is interval union. Read support is not assembly recovery, independent truth, or structural correctness.'})
