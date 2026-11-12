"""Admit exact published read members and whole reference bytes, online or offline."""
from collections import Counter
from contextlib import contextmanager
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

from .io import digest, save
from .references import read_fasta


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


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
    temporary = directory / 'reads.fastq.gz.partial'
    if temporary.exists():
        raise ValueError('Interrupted input preparation exists; inspect ' + str(temporary))
    local_archive = cache / source['name']
    try:
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
        _check_file(temporary, manifest['reads_sha256'], member['size'])
        temporary.replace(reads)
    except Exception:
        # Keep a failed transfer distinct from an admitted read file.
        if temporary.exists():
            temporary.rename(temporary.with_name('reads.fastq.gz.rejected'))
        raise
    return reads


def obtain_reference(manifest, directory, cache, offline):
    reference = directory / 'reference.fasta'
    if reference.exists():
        _check_file(reference, manifest['truth_sha256'])
        return reference
    source = manifest['source_reference_archive']
    archive = cache / source['name']
    with locked(cache / '.reference-archive.lock'):
        if not archive.exists():
            if offline:
                raise ValueError('Offline reference absent: prefill ' + str(reference) + ' or ' + str(archive))
            temporary = archive.with_name(archive.name + '.partial')
            if temporary.exists():
                raise ValueError('Interrupted reference download exists: ' + str(temporary))
            with urllib.request.urlopen(source['download_url'], timeout=120) as response:
                _copy_bounded(response, temporary, source['size'])
            checksum = hashlib.md5()
            with temporary.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    checksum.update(block)
            if checksum.hexdigest() != source['computed_md5']:
                raise ValueError('Reference archive published MD5 differs')
            temporary.replace(archive)
        checksum = hashlib.md5()
        with archive.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                checksum.update(block)
        if archive.stat().st_size != source['size'] or checksum.hexdigest() != source['computed_md5']:
            raise ValueError('Cached reference archive differs from published bytes')
        name = manifest['case']['id'] + '.fasta'
        with tarfile.open(archive, 'r:gz') as stream:
            matches = [row for row in stream if row.isfile() and Path(row.name).name == name]
            if len(matches) != 1:
                raise ValueError('Published reference member missing or duplicated')
            temporary = directory / 'reference.fasta.partial'
            with stream.extractfile(matches[0]) as original:
                _copy_bounded(original, temporary, matches[0].size)
        _check_file(temporary, manifest['truth_sha256'])
        temporary.replace(reference)
    return reference


def decompress_verified(reads, destination, manifest):
    """Preserve every original FASTQ byte while checking CRC, statistics and SHA256."""
    expected = manifest['statistics']
    if destination.exists():
        _check_file(destination, expected['uncompressed_fastq_sha256'])
        return
    temporary = destination.with_name(destination.name + '.partial')
    if temporary.exists():
        raise ValueError('Interrupted decompression exists: ' + str(temporary))
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
    temporary.replace(destination)


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
