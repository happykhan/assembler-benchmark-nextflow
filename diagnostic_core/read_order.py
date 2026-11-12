"""S7: frozen FASTQ permutations and reference-independent output comparisons."""
import collections
import copy
import gzip
import hashlib
import os
import platform
import struct
import sys
from pathlib import Path
from .common import digest, fasta, fingerprint, load, save
VERSION = 'read-order-sha256-sort-v1'
COMPLETED = {'pass', 'fail'}
DNA = 'ACGTRYMKBDHVSWN'
COMPLEMENT = str.maketrans(DNA, 'TGCAYRKMVHDBSWN')

def records(path):
    """Read complete, unwrapped FASTQ records, preserving all four original lines."""
    with gzip.open(path, 'rb') as stream:
        while True:
            header = stream.readline()
            if not header:
                return
            sequence, plus, quality = [stream.readline() for _ in range(3)]
            if not header.startswith(b'@') or not plus.startswith(b'+') or (not all((x.endswith(b'\n') for x in (header, sequence, plus, quality)))):
                raise ValueError('Expected complete four-line FASTQ records')
            if not sequence.rstrip(b'\r\n') or len(sequence.rstrip(b'\r\n')) != len(quality.rstrip(b'\r\n')):
                raise ValueError('FASTQ sequence/quality lengths differ or are empty')
            yield (header + sequence + plus + quality)

def record_fingerprints(items):
    """Duplicates and qualities participate in both multiset and order fingerprints."""
    ordered, content, hashes = (hashlib.sha256(), hashlib.sha256(), [])
    total_bytes = 0
    for item in items:
        h = hashlib.sha256(item).digest()
        ordered.update(h)
        content.update(item)
        hashes.append(h)
        total_bytes += len(item)
    return {'record_count': len(hashes), 'record_multiset_sha256': hashlib.sha256(b''.join(sorted(hashes))).hexdigest(), 'record_order_sha256': ordered.hexdigest(), 'uncompressed_sha256': content.hexdigest(), 'uncompressed_bytes': total_bytes}

def permutation(count, seed):
    """Portable seeded permutation; independent of Python's random module version."""
    if type(seed) is not int or seed < 0:
        raise ValueError('Shuffle seed must be a nonnegative integer')
    prefix = (VERSION + ':' + str(seed) + ':').encode('ascii')
    return sorted(range(count), key=lambda i: (hashlib.sha256(prefix + struct.pack('>Q', i)).digest(), i))

def write_order(path, items, indices):
    with Path(path).open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as stream:
            for index in indices:
                stream.write(items[index])

def build_cases(source_case, config):
    result = []
    for order in config['read_order']['orders']:
        for repeat in range(1, config['read_order']['repeats_per_order'] + 1):
            case = copy.deepcopy(source_case)
            case.pop('fingerprint', None)
            case.update(id=f"s7-se11-{order['id']}-repeat-{repeat}", category='S7', title=f"SE11 · {order['id']} · repeat {repeat}", read_order={'order_id': order['id'], 'repeat': repeat})
            case['fingerprint'] = fingerprint(case)
            result.append(case)
    return result

def least_rotation(sequence):
    """Booth's linear-time algorithm; no reference or read input is consulted."""
    size = len(sequence)
    if not size:
        return sequence
    doubled = sequence + sequence
    left, right, offset = (0, 1, 0)
    while left < size and right < size and (offset < size):
        a, b = (doubled[left + offset], doubled[right + offset])
        if a == b:
            offset += 1
            continue
        if a > b:
            left += offset + 1
            if left <= right:
                left = right + 1
        else:
            right += offset + 1
            if right <= left:
                right = left + 1
        offset = 0
    begin = min(left, right)
    return doubled[begin:begin + size]

def sequence_fingerprint(parts, circularity=None):
    """Preserve sequence/copy differences; ignore names, strand and output order."""
    circularity = circularity or {}
    end_sensitive, circular = ([], [])
    unknown = []
    for identifier, sequence in parts:
        if not sequence or set(sequence) - set(DNA):
            raise ValueError('Assembly contains empty or unsupported DNA records')
        reverse = sequence.translate(COMPLEMENT)[::-1]
        end = min(sequence, reverse)
        row = {'length_bp': len(sequence), 'sha256': hashlib.sha256(end.encode()).hexdigest()}
        end_sensitive.append(row)
        topology = circularity.get(identifier)
        if topology is None:
            unknown.append(identifier)
        normal = min(least_rotation(sequence), least_rotation(reverse)) if topology is True else end
        circular.append({'length_bp': len(sequence), 'sha256': hashlib.sha256(normal.encode()).hexdigest(), 'reported_topology': 'circular' if topology is True else 'linear' if topology is False else 'unknown'})
    end_sensitive.sort(key=lambda r: (r['length_bp'], r['sha256']))
    circular.sort(key=lambda r: (r['length_bp'], r['sha256'], r['reported_topology']))
    return {'schema_version': 1, 'method': 'reference-independent-contig-multiset-v1', 'end_sensitive_sha256': fingerprint(end_sensitive), 'contigs': end_sensitive, 'circular_representation_sha256': fingerprint(circular) if not unknown else None, 'circularity_unknown_contigs': unknown, 'contig_count': len(end_sensitive), 'total_length_bp': sum((r['length_bp'] for r in end_sensitive)), 'end_sensitive_policy': 'Names/order/strand ignored; ends, sequence and duplicate copies retained.', 'circular_policy': 'Rotations ignored only for tool-reported circular contigs; unavailable when any contig topology is unknown.'}

def assess_tool(rows, orders, repeats, field):
    by_order = {}
    expected = len(orders) * repeats
    for order in orders:
        selected = [r for r in rows if r['order_id'] == order]
        hashes = [r.get('signature', {}).get(field) for r in selected]
        complete = len(selected) == repeats and len({r['repeat'] for r in selected}) == repeats and all((r['status'] in COMPLETED for r in selected)) and all(hashes)
        by_order[order] = {'complete': bool(complete), 'variants': len(set((h for h in hashes if h))), 'identical': len(set(hashes)) == 1 if complete else None}
    versions = {r.get('version') for r in rows}
    complete = len(rows) == expected and all((r['complete'] for r in by_order.values())) and (len(versions) == 1) and (None not in versions)
    if not complete:
        verdict = 'Not assessed — incomplete executions or comparison evidence'
    elif any((not r['identical'] for r in by_order.values())):
        verdict = 'Within-order variability — order-specific effect not established'
    elif len({r['signature'][field] for r in rows}) > 1:
        verdict = 'Order-associated output difference'
    else:
        verdict = 'No order effect observed'
    return {'verdict': verdict, 'complete': complete, 'expected_runs': expected, 'observed_runs': sum((r['status'] in COMPLETED and bool(r.get('signature', {}).get(field)) for r in rows)), 'within_order': by_order, 'variants': len({r['signature'][field] for r in rows if r.get('signature', {}).get(field)})}
