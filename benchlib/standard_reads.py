"""Beta error-free native-molecule sampling with exact per-replicon budgets."""
from decimal import Decimal, ROUND_HALF_UP
import random
from pathlib import Path

from .io import digest, length_statistics, save
from .references import read_fasta


def budget(length, coverage):
    return int((Decimal(length) * Decimal(str(coverage))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def sample_records(sequence, accession, case, depth):
    """Separate streams keep the lower-depth single-mode arm a baseline prefix."""
    target = budget(len(sequence), depth)
    circular_sequence = sequence + sequence
    short = budget(target, case.get('short_fraction', 0))
    modes = [('short', short, case.get('short_length_mean', 1000), case.get('short_length_sd', 250)),
             ('long', target-short, case['length_mean'], case['length_sd'])]
    for label, bases, mean, sd in modes:
        rng = random.Random(f"native-error-free-v1:{case['seed']}:{accession}:{label}")
        total = 0
        index = 0
        while total < bases:
            sampled = max(1, round(rng.gammavariate((mean / sd)**2, sd**2 / mean))) if sd else round(mean)
            length = min(sampled, len(sequence), bases-total)
            start = rng.randrange(len(sequence))
            fragment = circular_sequence[start:start+length]
            strand = '-' if rng.getrandbits(1) else '+'
            if strand == '-':
                fragment = fragment.translate(str.maketrans('ACGT','TGCA'))[::-1]
            header = f'@{accession}:{label}:{index} start={start} length={length} strand={strand} mode={label}'
            yield label, header, fragment, sampled > length
            total += length
            index += 1


def simulate_standard(reference, case, destination, metadata, provenance):
    reference, destination, metadata = map(Path, (reference, destination, metadata))
    if destination.exists() or metadata.exists():
        raise FileExistsError('Refusing to overwrite existing simulation output')
    sequences = read_fasta(reference.read_text())
    molecules = provenance['molecules']
    if set(sequences) != {m['accession'] for m in molecules}:
        raise ValueError('Standard sequence inventory differs from prepared molecules')
    paths = []
    lengths, replicons, observed_modes = [], [], {}
    pending = destination.with_name(destination.name+'.partial')
    destination.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    try:
        with tempfile.TemporaryDirectory(prefix='standard-reads-') as temporary:
            for i, molecule in enumerate(molecules):
                accession = molecule['accession']
                sequence = sequences[accession]
                depth = case['coverage'] * (case.get('plasmid_relative_depth', 1) if molecule['type']=='plasmid' else 1)
                file = Path(temporary)/str(i)
                emitted, capped, local_lengths = 0, 0, []
                with file.open('w') as stream:
                    for label, header, fragment, trimmed in sample_records(sequence, accession, case, depth):
                        stream.write(f'{header}\n{fragment}\n+\n'+('I'*len(fragment))+'\n')
                        local_lengths.append(len(fragment)); emitted += len(fragment); capped += trimmed
                        mode = observed_modes.setdefault(label, {'total_bases':0,'read_count':0})
                        mode['total_bases'] += len(fragment); mode['read_count'] += 1
                if emitted != budget(len(sequence), depth):
                    raise ValueError('Per-molecule base budget mismatch')
                lengths.extend(local_lengths)
                replicons.append({'accession':accession,'type':molecule['type'],'target_bases':emitted,
                    'observed_bases':emitted,'coverage':emitted/len(sequence),'read_count':len(local_lengths),
                    'native_length_or_terminal_budget_trim_count':capped})
                paths.append((file,len(local_lengths)))
            # Uniformly interleave complete records; source coordinates stay in headers.
            rng = random.Random(f"native-error-free-v1:{case['seed']}:interleave")
            streams = [p.open() for p,_ in paths]
            remaining = [n for _,n in paths]
            try:
                with pending.open('w') as out:
                    while sum(remaining):
                        choice = rng.randrange(sum(remaining)); index = 0
                        while choice >= remaining[index]:
                            choice -= remaining[index]; index += 1
                        out.write(''.join(next(streams[index]) for _ in range(4)))
                        remaining[index] -= 1
            finally:
                for stream in streams: stream.close()
        pending.replace(destination)
        measured = length_statistics(lengths)
        short = observed_modes.get('short', {'total_bases':0,'read_count':0})
        measured.update(short_mode_base_fraction=short['total_bases']/measured['total_bases'],
                        short_mode_read_fraction=short['read_count']/measured['read_count'])
        record = {'schema_version':1,'status':'completed','case':case,'simulator':'Native error-free sampler',
            'version':'native-error-free-v1','simulator_source_sha256':digest(Path(__file__)),
            'reference_sha256':digest(reference),'reads_sha256':digest(destination),
            'reference_mode':'whole_genome','reference_bases':sum(map(len,sequences.values())),
            'target_bases':sum(r['target_bases'] for r in replicons),'observed':measured,
            'replicons':replicons,'modes':observed_modes,'commands':[],
            'method':'Uniform circular starts; gamma fragment lengths capped at native molecule length; exact per-molecule budgets; error-free sequence; synthetic Q40 qualities.',
            'sequencing_bias_modelled':False}
        save(metadata,record)
        return record
    finally:
        pending.unlink(missing_ok=True)
