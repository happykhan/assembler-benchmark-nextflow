#!/usr/bin/env python3
"""Run pinned Badread with exact base budgets and verified reference bindings."""
import argparse
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.io import digest, fasta_lengths, fastq_records, length_statistics, save


CASE_FIELDS = {'id', 'group', 'reference_id', 'description', 'coverage', 'seed',
               'length_mean', 'length_sd', 'short_fraction', 'short_length_mean',
               'short_length_sd', 'preset', 'purpose', 'headline_eligible'}


def validate_case(case):
    unknown = set(case) - CASE_FIELDS
    if unknown:
        raise ValueError('Unsupported simulation fields: ' + ', '.join(sorted(unknown)))
    for field in ('id', 'group', 'coverage', 'seed', 'length_mean', 'length_sd'):
        if field not in case:
            raise ValueError('Missing simulation field: ' + field)
    for field in ('coverage', 'length_mean', 'length_sd', 'short_length_mean', 'short_length_sd'):
        value = case.get(field, 1)
        if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(field + ' must be finite and numeric')
        if value < 0 or (field in ('coverage', 'length_mean', 'short_length_mean') and value == 0):
            raise ValueError(field + ' is outside its permitted range')
    if not isinstance(case['seed'], int) or isinstance(case['seed'], bool) or not 0 <= case['seed'] < 2**32 - 1:
        raise ValueError('seed must be an integer in [0, 2**32 - 2]')
    fraction = case.get('short_fraction', 0)
    if not isinstance(fraction, (float, int)) or isinstance(fraction, bool) or not 0 <= fraction <= 1:
        raise ValueError('short_fraction must be a base fraction in [0, 1]')


def command_for(reference, bases, mean, sd, seed):
    return ['badread', 'simulate', '--reference', str(reference), '--quantity', str(bases),
            '--length', f'{mean},{sd}', '--identity', '100,100,0',
            '--error_model', 'random', '--qscore_model', 'ideal', '--seed', str(seed),
            '--start_adapter', '0,0', '--end_adapter', '0,0',
            '--junk_reads', '0', '--random_reads', '0', '--chimeras', '0', '--glitches', '0,0,0']


def write_mode(source, output, target, label):
    lengths, total = [], 0
    for index, (name, sequence, quality) in enumerate(fastq_records(source)):
        remaining = target - total
        if remaining <= 0:
            break
        length = min(remaining, len(sequence))
        # Prefix mode prevents duplicate Badread UUIDs across separately seeded modes.
        output.write(f'@{label}_{index} {name[1:]}\n{sequence[:length]}\n+\n{quality[:length]}\n')
        lengths.append(length)
        total += length
    if total != target:
        raise ValueError(f'Badread supplied {total} bases, fewer than requested {target}')
    return lengths


def mix_modes(sources, output, seed):
    """Uniform seeded interleaving preserves each mode's random internal order."""
    generator = random.Random(seed)
    iterators = [iter(fastq_records(path)) for path, _ in sources]
    remaining = [count for _, count in sources]
    while sum(remaining):
        choice = generator.randrange(sum(remaining))
        index = 0
        while choice >= remaining[index]:
            choice -= remaining[index]
            index += 1
        name, sequence, quality = next(iterators[index])
        output.write(f'{name}\n{sequence}\n+\n{quality}\n')
        remaining[index] -= 1


def verify_reference(reference, case, provenance_path=None):
    """Whole-genome baselines cannot silently consume a Quick fragment."""
    if provenance_path is None:
        if case.get('preset') == 'standard':
            raise ValueError('Standard simulation requires verified reference provenance')
        return None
    provenance = json.loads(Path(provenance_path).read_text())
    if provenance.get('reference_sha256') != digest(reference):
        raise ValueError('Simulation reference differs from its preparation hash')
    if provenance.get('id') != case.get('reference_id'):
        raise ValueError('Simulation reference ID differs from the selected case')
    if case.get('preset') == 'standard':
        if provenance.get('mode') != 'whole_genome' or provenance.get('status') != 'admitted':
            raise ValueError('Standard simulation requires an admitted whole-genome reference')
        molecules = provenance.get('molecules', [])
        if len(molecules) != 1 or molecules[0].get('type') != 'chromosome':
            raise ValueError('Initial Standard baseline supports one verified chromosome only')
        if molecules[0].get('topology') != 'circular':
            raise ValueError('Initial Standard baseline requires verified native circular topology')
        records = [line.strip() for line in Path(reference).read_text().splitlines() if line.startswith('>')]
        if len(records) != 1 or 'circular=true' not in records[0].split():
            raise ValueError('Whole-genome FASTA does not declare native circular topology')
    return provenance


def simulate(reference, case, destination, metadata, reference_provenance=None):
    validate_case(case)
    reference = Path(reference).resolve()
    provenance = verify_reference(reference, case, reference_provenance)
    destination = Path(destination).resolve()
    metadata = Path(metadata).resolve()
    if destination.exists() or metadata.exists():
        raise FileExistsError('Refusing to overwrite existing simulation output')
    destination.parent.mkdir(parents=True, exist_ok=True)
    version = subprocess.check_output(['badread', '--version'], text=True, stderr=subprocess.STDOUT).strip()
    if 'Badread v0.4.2' not in version:
        raise ValueError('Badread 0.4.2 is required; found: ' + version)
    genome_bases = sum(fasta_lengths(reference))
    target = round(genome_bases * case['coverage'])
    if target <= 0:
        raise ValueError('Requested read budget rounds to zero bases')
    short = round(target * case.get('short_fraction', 0))
    modes = [('short', short, case.get('short_length_mean', 1000),
              case.get('short_length_sd', 250), case['seed']),
             ('long', target - short, case['length_mean'], case['length_sd'], case['seed'] + 1)]
    commands, lengths, observed_modes = [], [], {}
    pending = destination.with_name(destination.name + '.partial')
    try:
        with tempfile.TemporaryDirectory(prefix='badread-') as temporary, pending.open('w') as output:
            trimmed_modes = []
            for label, bases, mean, sd, seed in modes:
                if not bases:
                    observed_modes[label] = {'target_bases': 0, 'total_bases': 0, 'read_count': 0}
                    continue
                command = command_for(reference, bases, mean, sd, seed)
                raw = Path(temporary) / (label + '.fastq')
                log = metadata.with_name('simulation-' + label + '.log')
                with raw.open('w') as handle, log.open('w') as error:
                    subprocess.run(command, stdout=handle, stderr=error, check=True)
                trimmed = Path(temporary) / (label + '-trimmed.fastq')
                with trimmed.open('w') as mode_output:
                    mode_lengths = write_mode(raw, mode_output, bases, label)
                trimmed_modes.append((trimmed, len(mode_lengths)))
                lengths.extend(mode_lengths)
                observed_modes[label] = dict(length_statistics(mode_lengths), target_bases=bases, seed=seed)
                commands.append(command)
            mix_modes(trimmed_modes, output, case['seed'])
        pending.replace(destination)
        measured = length_statistics(lengths)
        measured['short_mode_base_fraction'] = short / target
        measured['short_mode_read_fraction'] = observed_modes['short']['read_count'] / measured['read_count']
        record = {'schema_version': 1, 'status': 'completed', 'case': case,
                  'workflow_source_sha256': os.environ.get('BENCH_SOURCE_SHA256'),
                  'simulator_source_sha256': digest(Path(__file__)),
                  'reference_sha256': digest(reference), 'reads_sha256': digest(destination),
                  'reference_bases': genome_bases, 'target_bases': target,
                  'reference_provenance_sha256': digest(reference_provenance) if reference_provenance else None,
                  'reference_mode': provenance.get('mode', 'quick_fragment') if provenance else 'quick_fixture',
                  'reference_topology': [m['topology'] for m in provenance.get('molecules', [])] if provenance else [],
                  'observed': measured, 'modes': observed_modes, 'commands': commands,
                  'simulator': 'Badread', 'version': version,
                  'method': 'Error-free uniformly sampled reference reads; separate seeded length modes, uniformly interleaved using the case seed; final read per mode trimmed to exact base budget',
                  'sequencing_bias_modelled': False}
        save(metadata, record)
        return record
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--case-json', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--metadata', required=True)
    parser.add_argument('--reference-provenance')
    args = parser.parse_args()
    simulate(args.reference, json.loads(args.case_json), args.out, args.metadata, args.reference_provenance)
