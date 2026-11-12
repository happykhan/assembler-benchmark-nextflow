"""Admit exact published read members and whole reference bytes, online or offline."""
from collections import Counter
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
import socket
import time
import uuid
from pathlib import Path
import tarfile
import urllib.request

from .io import digest, save
from .references import read_fasta


@contextmanager
def locked(path, timeout_seconds=7200, poll_seconds=0.2):
    """Coordinate shared caches with atomic mkdir, including across cluster nodes.

    Advisory flock was observed not to exclude simultaneous GPFS clients. Never
    infer that a remote PID or an old timestamp makes a lock safe to steal.
    A killed owner leaves its directory and metadata for explicit inspection.
    Legacy advisory-lock files remain untouched.
    """
    path = Path(path)
    directory = path.with_name(path.name + '.d')
    directory.parent.mkdir(parents=True, exist_ok=True)
    if timeout_seconds < 0 or poll_seconds <= 0:
        raise ValueError('Invalid cache lock wait interval')
    deadline = time.monotonic() + timeout_seconds
    token = uuid.uuid4().hex
    owner = {'schema_version': 1, 'token': token, 'hostname': socket.gethostname(),
             'pid': os.getpid(), 'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
             'started_unix_seconds': time.time()}
    while True:
        try:
            directory.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                try:
                    evidence = (directory / 'owner.json').read_text()[:2048]
                except OSError:
                    evidence = 'Owner metadata unavailable; creation may have been interrupted.'
                raise TimeoutError('Shared cache lock did not clear: ' + str(directory)
                    + '; owner=' + evidence + '; verify the owner before explicit recovery. No stale lock was removed.')
            time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))
    owner_path = directory / 'owner.json'
    # An interruption here also leaves the lock fail-closed, never unlocked.
    with owner_path.open('x') as stream:
        json.dump(owner, stream, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    try:
        yield owner
    finally:
        current = json.loads(owner_path.read_text())
        if current.get('token') != token:
            raise RuntimeError('Cache lock ownership changed; refusing to remove ' + str(directory))
        owner_path.unlink()
        directory.rmdir()


def _temporary(destination):
    """A transfer never truncates or adopts another attempt's partial bytes."""
    return destination.with_name(destination.name + '.partial-' + uuid.uuid4().hex)


def _publish(temporary, destination, check):
    """Publish verified bytes atomically without replacing an existing input."""
    check(temporary)
    try:
        os.link(temporary, destination)
    except FileExistsError:
        # Even an unexpected competing publisher cannot replace admitted bytes.
        check(destination)
    else:
        check(destination)
    # This removes only the successful temporary name, after verified admission.
    # Every failed or interrupted candidate is retained for inspection.
    temporary.unlink()


def _check_file(path, expected_sha, size=None):
    if not path.is_file() or (size is not None and path.stat().st_size != size) or digest(path) != expected_sha:
        raise ValueError('Published bytes differ from frozen admission: ' + str(path))


def _copy_bounded(source, destination, length):
    count = 0
    with destination.open('xb') as output:
        while count < length:
            block = source.read(min(1024 * 1024, length - count))
            if not block:
                raise ValueError('Truncated published archive transfer')
            output.write(block)
            count += len(block)
        if source.read(1):
            raise ValueError('Published archive transfer exceeds frozen size')


def _range(source, start, length):
    if start < 0 or length < 1 or start + length > source['size']:
        raise ValueError('Range outside pinned archive')
    request = urllib.request.Request(source['download_url'], headers={'Range': f'bytes={start}-{start + length - 1}'})
    response = urllib.request.urlopen(request, timeout=120)
    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{start + length - 1}/{source["size"]}':
        response.close()
        raise ValueError('Server did not honour exact archive range; refusing entire read archive')
    return response


def _validate_header(header, member):
    if len(header) != 512 or hashlib.sha256(header).hexdigest() != member['header_sha256']:
        raise ValueError('Published TAR header checksum differs')
    row = tarfile.TarInfo.frombuf(header, 'utf-8', 'strict')
    if not row.isfile() or row.name != member['name'] or row.size != member['size']:
        raise ValueError('Published TAR member identity differs')


def obtain_reads(manifest, directory, cache, offline):
    reads = directory / 'reads.fastq.gz'
    member, source = manifest['read_archive_member'], manifest['source_read_archive']
    if reads.exists():
        _check_file(reads, manifest['reads_sha256'], member['size'])
        return reads
    temporary = _temporary(reads)
    local_archive = cache / source['name']
    if local_archive.exists():
        if local_archive.stat().st_size != source['size']:
            raise ValueError('Offline read archive size differs')
        with local_archive.open('rb') as stream:
            stream.seek(member['offset'] - 512)
            _validate_header(stream.read(512), member)
            # Reading an exact member from a larger file must not test archive EOF.
            with temporary.open('xb') as output:
                remaining = member['size']
                while remaining:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('Truncated offline TAR member')
                    output.write(block)
                    remaining -= len(block)
    else:
        if offline:
            raise ValueError('Offline published input absent: prefill ' + str(reads) + ' or ' + str(local_archive))
        with _range(source, member['offset'] - 512, 512) as response:
            _validate_header(response.read(513), member)
        with _range(source, member['offset'], member['size']) as response:
            _copy_bounded(response, temporary, member['size'])
    _publish(temporary, reads, lambda path: _check_file(path, manifest['reads_sha256'], member['size']))
    return reads


def _check_reference_archive(path, source):
    checksum = hashlib.md5()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    if path.stat().st_size != source['size'] or checksum.hexdigest() != source['computed_md5']:
        raise ValueError('Reference archive differs from published size/MD5: ' + str(path))


def obtain_reference(manifest, directory, cache, offline):
    reference = directory / 'reference.fasta'
    if reference.exists():
        _check_file(reference, manifest['truth_sha256'])
        return reference
    source = manifest['source_reference_archive']
    archive = cache / source['name']
    with locked(cache / '.reference-archive.lock'):
        if reference.exists():
            _check_file(reference, manifest['truth_sha256'])
            return reference
        if not archive.exists():
            if offline:
                raise ValueError('Offline reference absent: prefill ' + str(reference) + ' or ' + str(archive))
            temporary = _temporary(archive)
            with urllib.request.urlopen(source['download_url'], timeout=120) as response:
                _copy_bounded(response, temporary, source['size'])
            _publish(temporary, archive, lambda path: _check_reference_archive(path, source))
        _check_reference_archive(archive, source)
        name = manifest['case']['id'] + '.fasta'
        with tarfile.open(archive, 'r:gz') as stream:
            matches = [row for row in stream if row.isfile() and Path(row.name).name == name]
            if len(matches) != 1:
                raise ValueError('Published reference member missing or duplicated')
            temporary = _temporary(reference)
            with stream.extractfile(matches[0]) as original:
                _copy_bounded(original, temporary, matches[0].size)
        _publish(temporary, reference, lambda path: _check_file(path, manifest['truth_sha256']))
    return reference


def decompress_verified(reads, destination, manifest):
    """Preserve every original FASTQ byte while checking CRC, statistics and SHA256."""
    expected = manifest['statistics']
    if destination.exists():
        _check_file(destination, expected['uncompressed_fastq_sha256'])
        return
    temporary = _temporary(destination)
    lengths = Counter()
    count = total = 0
    sha = hashlib.sha256()
    with gzip.open(reads, 'rb') as source, temporary.open('xb') as output:
        while True:
            header = source.readline()
            if not header:
                break
            sequence, plus, quality = source.readline(), source.readline(), source.readline()
            size = len(sequence.rstrip(b'\r\n'))
            if not header.startswith(b'@') or not plus.startswith(b'+') or not size or size != len(quality.rstrip(b'\r\n')):
                raise ValueError('Invalid published FASTQ record')
            for line in (header, sequence, plus, quality):
                sha.update(line)
                output.write(line)
            count += 1
            total += size
            lengths[size] += 1
    cumulative = n50 = 0
    for size, frequency in sorted(lengths.items(), reverse=True):
        cumulative += size * frequency
        if cumulative * 2 >= total:
            n50 = size
            break
    actual = {'read_count': count, 'total_read_bases': total, 'read_n50_bp': n50,
              'uncompressed_fastq_sha256': sha.hexdigest()}
    if actual != expected:
        raise ValueError('Published FASTQ statistics or original content checksum differs')
    _publish(temporary, destination, lambda path: _check_file(path, expected['uncompressed_fastq_sha256']))


def _save_identical(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError('Existing published provenance differs: ' + str(path))
    else:
        save(path, value)


def prepare_general_input(case, admission, cache, output=Path('.'), offline=False):
    manifest = admission['manifest']
    if any(case.get(k) != v for k, v in manifest['case'].items() if k not in ('category', 'title', 'fingerprint', 'track')):
        raise ValueError('General case/admitted input binding differs')
    if case.get('track') != 'general' or case.get('input_policy') != 'published_frozen_bytes_no_resimulation':
        raise ValueError('General input policy differs')
    cache, output = Path(cache).resolve(), Path(output)
    directory = cache / case['id']
    directory.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with locked(directory / '.prepare.lock'):
        reference = obtain_reference(manifest, directory, cache, offline)
        records = read_fasta(reference.read_text())
        expected_inventory = {r['refseq_accession']: r['length_bp'] for r in case['replicons']}
        if {n: len(seq) for n, seq in records.items()} != expected_inventory:
            raise ValueError('Reference FASTA differs from published molecule inventory')
        reads_gzip = obtain_reads(manifest, directory, cache, offline)
        reads = directory / 'reads.fastq'
        decompress_verified(reads_gzip, reads, manifest)
    for name, original in (('reference.fasta', reference), ('reads.fastq', reads)):
        target = output / name
        if target.exists():
            _check_file(target, digest(original))
        else:
            target.symlink_to(original)
    provenance = {'schema_version': 1, 'id': case['id'], 'mode': 'whole_genome', 'status': 'admitted',
        'reference_sha256': manifest['truth_sha256'], 'source_archive': manifest['source_reference_archive'],
        'molecules': [dict(r, accession=r['refseq_accession'], type=r['molecule_type']) for r in case['replicons']],
        'molecule_types': {r['refseq_accession']: r['molecule_type'] for r in case['replicons']},
        'topology_scope': 'Original study simulation assumption; not a native-topology claim.'}
    _save_identical(output / 'reference.json', provenance)
    result = {'schema_version': 1, 'status': 'completed', 'track': 'general', 'case': case,
        'input_policy': case['input_policy'], 'reference_sha256': manifest['truth_sha256'],
        'reference_provenance_sha256': digest(output / 'reference.json'),
        'reads_sha256': manifest['statistics']['uncompressed_fastq_sha256'],
        'published_compressed_reads_sha256': manifest['reads_sha256'],
        'source_input_manifest_sha256': admission['source_sha256'], 'original_admission': manifest,
        'statistics': dict(manifest['statistics'], total_bases=manifest['statistics']['total_read_bases'])}
    _save_identical(output / 'input.json', result)
    return result
