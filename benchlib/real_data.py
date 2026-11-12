"""Inspect proposed real-data inventories without downloading or admitting inputs."""
import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from benchlib.io import digest


def inspect_manifest(manifest, project=None):
    """Validate metadata bindings; a successful inspection is not data admission."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(manifest.get('schema_version') == 1, 'Unsupported real-data manifest schema')
    require(manifest.get('status') == 'proposed_not_admitted' and manifest.get('executable') is False,
            'Real-data execution/admission is not implemented; retain proposed_not_admitted')
    require(manifest.get('track') == 'real_single_isolate_long_reads', 'Only single-isolate long reads are supported')
    scope = manifest['scope']
    require(scope.get('hybrid_benchmark_arms') is False and scope.get('metagenomic_samples') is False,
            'Hybrid and metagenomic benchmark arms are outside this track')
    require(manifest['metrics']['benchmark_contiguity'].get('separate_from_paper_recovery') is True,
            'Paper recovery and benchmark contiguity must remain separate')
    isolates = manifest['isolates']
    seen_ids, seen_samples, seen_runs, seen_molecules = set(), set(), set(), set()
    plasmids = small = molecules = download_bytes = 0
    blockers = {}
    for isolate in isolates:
        name, sample = isolate['isolate_id'], isolate['sample_accession']
        require(name not in seen_ids and sample not in seen_samples, 'Duplicate isolate or BioSample')
        seen_ids.add(name)
        seen_samples.add(sample)
        require(isolate['status'] == 'proposed_not_admitted', name + ': isolate is not admitted')
        run = isolate['ont']
        require(run['sample_accession'] == sample, name + ': read/BioSample binding mismatch')
        require(run['platform'] == 'OXFORD_NANOPORE', name + ': non-ONT assembly input')
        require(run['run_accession'] not in seen_runs, 'Duplicate ONT run')
        seen_runs.add(run['run_accession'])
        require(run['read_count'] > 0 and run['base_count'] > 0 and run['files'], name + ': empty read inventory')
        for file in run['files']:
            require(urlparse(file['url']).scheme == 'https', name + ': read URL must use HTTPS')
            require(re.fullmatch(r'[0-9a-f]{32}', file['publisher_md5']) is not None, name + ': invalid publisher MD5')
            require(type(file['compressed_bytes']) is int and file['compressed_bytes'] > 0, name + ': invalid byte count')
            require(file['download_sha256'] is None, name + ': downloaded reads require a separate admission receipt')
            download_bytes += file['compressed_bytes']
        ref = isolate['reference']
        require(ref['sample_accession'] == sample, name + ': reference/BioSample binding mismatch')
        require(re.fullmatch(r'GCA_\d+\.\d+', ref['assembly_accession'] or '') is not None,
                name + ': reference assembly version is unresolved')
        expected = {x['author_contig_id']: x['length_bp'] for x in isolate['paper_plasmids']}
        require(len(expected) == len(isolate['paper_plasmids']), name + ': duplicate author reference contig')
        mapped = {}
        chromosomes = 0
        for molecule in ref['molecules']:
            accession = molecule['accession']
            require(re.fullmatch(r'[A-Z]+\d+\.\d+', accession) is not None, name + ': unversioned molecule')
            require(accession not in seen_molecules, 'Duplicate reference molecule')
            seen_molecules.add(accession)
            require(molecule['sample_accession'] == sample, name + ': molecule/BioSample binding mismatch')
            require(type(molecule['length_bp']) is int and molecule['length_bp'] > 0, name + ': invalid molecule length')
            require(molecule['topology'] == 'circular', name + ': topology needs review')
            require(molecule['sequence_sha256'] is None, name + ': sequence hashes require a separate admission receipt')
            author_id = molecule['paper_ref_contig']
            if author_id:
                require(author_id not in mapped, name + ': duplicate mapping to author plasmid')
                mapped[author_id] = molecule['length_bp']
                require(molecule['proposed_biological_role'] == 'plasmid', name + ': mapped plasmid role is inconsistent')
                plasmids += 1
                small += molecule['length_bp'] < 10000
            else:
                require(molecule['proposed_biological_role'] == 'chromosome', name + ': unmapped molecule role needs review')
                chromosomes += 1
            conflict = molecule['archive_role'] != molecule['proposed_biological_role']
            require((molecule['role_status'] == 'conflict_requires_resolution') == conflict,
                    name + ': archive role conflict must be explicit')
            if conflict:
                require('archive_molecule_roles_conflict_with_paper_and_lengths' in isolate['blockers'],
                        name + ': unresolved role conflict is missing from blockers')
            molecules += 1
        require(mapped == expected, name + ': supplementary plasmid inventory mismatch')
        require(chromosomes == 1, name + ': expected one proposed chromosome')
        require(isolate['blockers'], name + ': unadmitted inventory must state blockers')
        blockers[name] = isolate['blockers']
    measured = {'isolates': len(isolates), 'plasmids': plasmids,
                'small_plasmids_lt_10000bp': small, 'native_molecules': molecules}
    require(measured == manifest['expected_inventory'], 'Expected study inventory differs from metadata')
    if project is not None:
        root = Path(project).resolve()
        for receipt in manifest['source_receipts']:
            if 'file' not in receipt:
                continue
            path = (root / receipt['file']).resolve()
            require(path.is_relative_to(root), 'Evidence receipt escapes project directory')
            require(path.is_file() and path.stat().st_size == receipt['bytes']
                    and digest(path) == receipt['sha256'], 'Evidence receipt changed: ' + receipt['file'])
        _verify_archive_bindings(manifest, root, require)
    return {'dataset_id': manifest['dataset_id'], 'metadata_valid': True,
            'status': 'proposed_not_admitted', 'executable': False,
            'inventory': measured, 'compressed_ont_download_bytes': download_bytes,
            'admission_blockers': blockers,
            'note': 'Metadata bindings only. Read bytes, reference sequences and original subsets have not been admitted.'}


def _verify_archive_bindings(manifest, root, require):
    """Bind declared facts back to the frozen, hash-verified archive responses."""
    receipt_files = {x['file'] for x in manifest['source_receipts'] if 'file' in x}

    def source_path(relative):
        require(relative in receipt_files, 'Archive binding has no hashed source receipt')
        return root / relative

    for isolate in manifest['isolates']:
        name, sample = isolate['isolate_id'], isolate['sample_accession']
        run, ref = isolate['ont'], isolate['reference']
        with source_path(run['metadata_file']).open() as stream:
            rows = [x for x in csv.DictReader(stream, delimiter='\t') if x['run_accession'] == run['run_accession']]
        require(len(rows) == 1, name + ': ONT source metadata is missing or ambiguous')
        row = rows[0]
        require(row['sample_accession'] == sample and row['sample_alias'] == name
                and row['instrument_platform'] == run['platform']
                and row['experiment_accession'] == run['experiment_accession']
                and int(row['base_count']) == run['base_count']
                and int(row['read_count']) == run['read_count'], name + ': ONT source metadata differs')
        files = [('https://' + url, md5, int(size)) for url, md5, size in
                 zip(row['fastq_ftp'].split(';'), row['fastq_md5'].split(';'), row['fastq_bytes'].split(';'))]
        require(files == [(x['url'], x['publisher_md5'], x['compressed_bytes']) for x in run['files']],
                name + ': ONT source file metadata differs')
        with source_path(ref['inventory_metadata_file']).open() as stream:
            inventory = list(csv.DictReader(stream, delimiter='\t'))
        by_accession = {x['accession'] + '.' + x['sequence_version']: x for x in inventory}
        require(set(by_accession) == {x['accession'] for x in ref['molecules']}, name + ': archived molecule inventory differs')
        for molecule in ref['molecules']:
            item = by_accession[molecule['accession']]
            require(item['sample_accession'] == sample and item['assembly_accession'] == ref['assembly_candidate']
                    and int(item['base_count']) == molecule['length_bp']
                    and item['description'] == molecule['archive_description']
                    and item['topology'] == molecule['topology'], name + ': archived molecule metadata differs')
        path = source_path(ref['assembly_metadata_file'])
        if path.suffix == '.xml':
            assembly = ET.parse(path).getroot().find('ASSEMBLY')
            require(assembly.attrib['accession'] == ref['assembly_accession']
                    and assembly.findtext('./SAMPLE_REF/IDENTIFIERS/PRIMARY_ID') == sample,
                    name + ': assembly source/BioSample binding differs')
            require({x.attrib['accession'] for x in assembly.findall('./CHROMOSOMES/CHROMOSOME')}
                    == set(by_accession), name + ': source assembly membership differs')
        else:
            assembly = json.loads(path.read_text())['reports'][0]
            require(assembly['accession'] == ref['assembly_accession']
                    and assembly['assembly_info']['biosample']['accession'] == sample,
                    name + ': assembly source/BioSample binding differs')
