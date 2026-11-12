"""Supplementary tolerant assessment without changing archived exact scores."""
import argparse
import importlib.metadata
from pathlib import Path
from .common import ROOT, load, save, digest, fingerprint, fasta
CONTINUOUS_MODE = 'continuous-evidence-v1'

def assessment_mode(config):
    mode = config.get('assessment_mode', 'small-plasmid-tolerant-v1')
    if mode not in {'small-plasmid-tolerant-v1', CONTINUOUS_MODE}:
        raise ValueError('Unsupported supplementary assessment mode')
    return mode

def continuous_assessment(case):
    reason = 'Tolerant pass/fail is unscored for this panel; continuous alignment measurements are reported separately.'
    return {'schema_version': 1, 'endpoint_version': CONTINUOUS_MODE, 'status': 'unscored', 'endpoint': 'Continuous alignment evidence; no tolerant pass/fail endpoint.', 'reason': reason, 'binary_endpoint_validated': False, 'replicons': [{'accession': row['refseq_accession'], 'name': row['replicon_name'], 'length_bp': row['length_bp'], 'status': 'unscored', 'reason': reason} for row in case['replicons'] if row['molecule_type'] == 'plasmid'], 'limitations': 'Coverage, identity and continuity are reported in the source-bound mapping diagnostics; exact scores remain separate.'}
