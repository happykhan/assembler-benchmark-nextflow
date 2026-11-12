"""Verify and cache immutable full-read archive inputs; never simulate or subset."""
from collections import Counter
import fcntl
import gzip
import hashlib
import http.client
import json
import math
import re
from pathlib import Path
import shutil
import tempfile
import subprocess
import urllib.request

from .io import digest


def verify_archive(path, definition):
    path = Path(path)
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(block)
            md5.update(block)
            sha.update(block)
    if size != definition['compressed_bytes'] or md5.hexdigest() != definition['publisher_md5']:
        raise ValueError('Archive byte count or publisher MD5 differs')
    if definition.get('download_sha256') and sha.hexdigest() != definition['download_sha256']:
        raise ValueError('Archive SHA256 differs from admitted bytes')
    return {'compressed_bytes': size, 'publisher_md5': md5.hexdigest(), 'compressed_sha256': sha.hexdigest()}


def download_archive(definition, destination, chunk_bytes=16 * 1024 * 1024, use_curl=True):
    """Bounded HTTP ranges avoid proxy-truncated large responses; hashes decide admission."""
    expected = definition['compressed_bytes']
    # Curl negotiates the server/proxy's streaming protocol when available.
    # Scientific admission depends on the exact hashes, not transport software.
    curl = shutil.which('curl') if use_curl else None
    if curl:
        command = [curl, '--fail', '--location', '--silent', '--show-error',
                   '--connect-timeout', '30', '--max-time', '1800', '--output', str(destination), definition['url']]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode == 0 and Path(destination).stat().st_size == expected:
            verify_archive(destination, definition)
            return {'method': 'curl-verified-stream-v1', 'command': command, 'verified_bytes': expected}
        # Retain the failed transfer intact before a range-based recovery attempt.
        if Path(destination).exists():
            destination = Path(destination)
            shutil.copyfile(destination, destination.with_name(destination.name + '.failed-stream'))
        failures = 0
    requests = []
    maximum = math.ceil(expected / chunk_bytes) + 32
    with Path(destination).open('wb') as stream:
        for attempt in range(maximum):
            offset = stream.tell()
            if offset == expected:
                break
            end = min(offset + chunk_bytes, expected) - 1
            request = urllib.request.Request(definition['url'], headers={
                'Range': f'bytes={offset}-{end}', 'Accept-Encoding': 'identity'})
            row = {'offset': offset, 'requested_end': end}
            requests.append(row)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    status = response.status
                    if status == 206:
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        if not match or int(match[1]) != offset or int(match[3]) != expected or not offset <= int(match[2]) <= end:
                            raise ValueError('Archive HTTP range binding differs')
                        response_end = int(match[2]) + 1
                    elif status == 200 and offset == 0:
                        response_end = expected
                    else:
                        raise ValueError('Archive server did not honour resume range')
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        if stream.tell() + len(block) > response_end:
                            raise ValueError('Archive response exceeds declared range')
                        stream.write(block)
                row['received_bytes'] = stream.tell() - offset
                if stream.tell() == offset:
                    raise OSError('Archive response made no progress')
                failures = 0
            except (OSError, http.client.IncompleteRead) as error:
                row.update(received_bytes=stream.tell() - offset, error=str(error))
                failures += 1
                if failures >= 3:
                    raise
        if stream.tell() != expected:
            raise ValueError('Archive remained incomplete after bounded transport recovery')
    verify_archive(destination, definition)
    return {'method': 'bounded-http-ranges-v1', 'requests': requests, 'verified_bytes': expected}


def unpack_fastq(source, destination):
    """Preserve decompressed bytes and headers; reject malformed or truncated FASTQ."""
    sha, names = hashlib.sha256(), hashlib.sha256()
    counts = Counter()
    byte_count = 0
    with gzip.open(source, 'rb') as stream, Path(destination).open('xb') as out:
        while True:
            header = stream.readline()
            if not header:
                break
            sequence, plus, quality = stream.readline(), stream.readline(), stream.readline()
            seq, qual = sequence.rstrip(b'\r\n'), quality.rstrip(b'\r\n')
            if (not header.startswith(b'@') or not plus.startswith(b'+') or not seq
                    or len(seq) != len(qual) or not quality.endswith(b'\n')
                    or not set(seq.upper()) <= set(b'ACGTRYSWKMBDHVN')
                    or any(x < 33 or x > 126 for x in qual)):
                raise ValueError('Invalid or truncated archive FASTQ')
            record = header + sequence + plus + quality
            out.write(record)
            sha.update(record)
            byte_count += len(record)
            names.update(header.rstrip(b'\r\n') + b'\n')
            counts[len(seq)] += 1
    reads, bases = sum(counts.values()), sum(n * count for n, count in counts.items())
    if not reads:
        raise ValueError('Archive FASTQ is empty')
    cumulative = 0
    for size in sorted(counts, reverse=True):
        cumulative += size * counts[size]
        if cumulative * 2 >= bases:
            n50 = size
            break
    return {'reads_sha256': sha.hexdigest(), 'decompressed_bytes': byte_count,
            'header_lines_sha256': names.hexdigest(), 'read_count': reads, 'total_bases': bases,
            'min_length': min(counts), 'max_length': max(counts), 'n50': n50, 'mean_length': bases / reads}


def prepare_reads(definition, cache, offline=False):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    run = definition['run_accession']
    if not run.startswith('SRR') or not run[3:].isdigit():
        raise ValueError('Invalid admitted run ID')
    archive, reads = cache / (run + '.fastq.gz'), cache / (run + '.fastq')
    with (cache / (run + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not archive.exists():
            if offline:
                raise ValueError('Offline archive missing: ' + run)
            with tempfile.NamedTemporaryFile(dir=cache, suffix='.download', delete=False) as stream:
                temporary = Path(stream.name)
            transport = download_archive(definition, temporary)
            (cache / (run + '.download-receipt.json')).write_text(json.dumps(transport, indent=2) + '\n')
            temporary.replace(archive)
        compressed = verify_archive(archive, definition)
        # A cache receipt never substitutes for checking the consumed bytes.
        with tempfile.NamedTemporaryFile(dir=cache, suffix='.fastq', delete=False) as stream:
            temporary = Path(stream.name)
        temporary.unlink()
        stats = unpack_fastq(archive, temporary)
        for field in ('reads_sha256', 'read_count', 'total_bases', 'decompressed_bytes'):
            if stats[field] != definition[field]:
                raise ValueError('Admitted read ' + field + ' differs')
        if reads.exists():
            if digest(reads) != stats['reads_sha256']:
                raise ValueError('Cached decompressed reads changed')
            temporary.unlink()
        else:
            temporary.replace(reads)
    return reads.resolve(), dict(compressed, **stats)
