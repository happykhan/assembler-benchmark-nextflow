"""Read-only, sequence-free GFA1 metadata and tool-reported Flye circularity.

Format authority: https://gfa-spec.github.io/GFA-spec/GFA1.html
Graph observations and tool claims do not establish sequence accuracy or physical topology.
"""
import copy
import json
import math
from pathlib import Path
import re
from .common import digest, load
DEFAULT_LIMITS = {'max_source_bytes': 64 * 1024 * 1024, 'max_line_bytes': 16 * 1024 * 1024, 'max_nodes': 10000, 'max_edges': 20000, 'max_paths': 10000, 'max_path_steps': 50000, 'max_identifier_chars': 256, 'max_overlap_chars': 1024, 'max_sidecar_bytes': 8 * 1024 * 1024}
STATUSES = {'available', 'missing', 'unsupported', 'invalid'}
LIMITATIONS = ['Segment sequences and arbitrary optional tags are never exported.', 'A GFA self-link is a graph observation, not proof of a circular molecule.', 'Tool-reported circularity is an assembly-info claim; sequence accuracy and physical topology are not assessed.']
COVERAGE_TAGS = {'RC': 'read_count', 'FC': 'fragment_count', 'KC': 'kmer_count', 'DP': 'tool_specific_coverage_tag', 'dp': 'tool_specific_coverage_tag'}

class Unsupported(ValueError):
    pass

def _limits(limits):
    settings = {**DEFAULT_LIMITS, **(limits or {})}
    if set(settings) != set(DEFAULT_LIMITS) or any((not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in settings.values())):
        raise ValueError('Use recognised positive integer metadata limits')
    return settings

def _identifier(value, settings):
    if len(value) > settings['max_identifier_chars']:
        raise Unsupported('Identifier exceeds metadata limit')
    if not value or value[0] in '*=' or (not all((33 <= ord(c) <= 126 for c in value))) or ('+,' in value) or ('-,' in value):
        raise ValueError('Invalid GFA identifier')
    return value

def _integer(value):
    if not re.fullmatch('[+-]?[0-9]+', value):
        raise ValueError('Invalid integer metadata')
    number = int(value)
    if number < 0:
        raise ValueError('Negative length or count metadata')
    if number > 2 ** 53 - 1:
        raise Unsupported('Integer exceeds exact JSON numeric range')
    return number

def _numeric(value):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid numeric coverage metadata') from error
    if not math.isfinite(number) or number < 0:
        raise ValueError('Invalid numeric coverage metadata')
    return number

def _tags(fields):
    result = {}
    for field in fields:
        parts = field.split(':', 2)
        if len(parts) != 3 or not re.fullmatch('[A-Za-z][A-Za-z0-9]', parts[0]) or parts[1] not in {'A', 'i', 'f', 'Z', 'J', 'H', 'B'} or (parts[0] in result):
            raise ValueError('Invalid or duplicate GFA optional tag')
        result[parts[0]] = (parts[1], parts[2])
    return result

def _overlap(value, settings):
    if len(value) > settings['max_overlap_chars']:
        raise Unsupported('Overlap description exceeds metadata limit')
    if value != '*' and (not re.fullmatch('(?:[0-9]+[MIDNSHPX=])+', value)):
        raise ValueError('Invalid GFA overlap description')
    return value

def _source_unchecked(path, kind, settings):
    if path is None or not Path(path).is_file():
        return ({'filename': Path(path).name if path is not None else None, 'file_sha256': None, 'kind': kind, 'role': 'unspecified'}, 'missing')
    path = Path(path)
    size = path.stat().st_size
    source = {'filename': path.name, 'file_sha256': None, 'kind': kind, 'role': 'unspecified', 'bytes': size}
    if size > settings['max_source_bytes']:
        source['hash_status'] = 'not_computed_size_limit'
        return (source, 'unsupported')
    source['file_sha256'] = digest(path)
    return (source, 'available')

def _source(path, kind, settings):
    try:
        return _source_unchecked(path, kind, settings)
    except OSError:
        return ({'filename': Path(path).name if path is not None else None, 'file_sha256': None, 'kind': kind, 'role': 'unspecified'}, 'invalid')

def _lines(path, settings):
    with Path(path).open('rb') as stream:
        number = 0
        while True:
            raw = stream.readline(settings['max_line_bytes'] + 1)
            if not raw:
                return
            number += 1
            if len(raw) > settings['max_line_bytes']:
                raise Unsupported('Source line exceeds metadata limit')
            try:
                text = raw.decode('ascii').rstrip('\r\n')
            except UnicodeDecodeError as error:
                raise ValueError('GFA metadata must contain ASCII only') from error
            yield (number, text)

def _segment(fields, settings):
    if len(fields) < 3:
        raise ValueError('Incomplete segment record')
    name = _identifier(fields[1], settings)
    sequence = fields[2]
    if sequence != '*' and (not re.fullmatch('[A-Za-z=.]+', sequence)):
        raise ValueError('Invalid segment sequence field')
    tags = _tags(fields[3:])
    length = None if sequence == '*' else len(sequence)
    if 'LN' in tags:
        if tags['LN'][0] != 'i':
            raise ValueError('Segment length tag must be integer')
        reported = _integer(tags['LN'][1])
        if length is not None and length != reported:
            raise ValueError('Segment sequence/length tag disagree')
        length = reported
    coverage = []
    for tag, meaning in COVERAGE_TAGS.items():
        if tag in tags:
            kind, value = tags[tag]
            if kind not in ('i', 'f') or (tag in {'RC', 'FC', 'KC'} and kind != 'i'):
                raise ValueError('Unsupported coverage/count tag type')
            coverage.append({'tag': tag, 'type': kind, 'value': _integer(value) if kind == 'i' else _numeric(value), 'meaning': meaning})
    return {'id': name, 'length_bp': length, 'reported_coverage_tags': coverage}

def _link(fields, settings):
    if len(fields) < 6 or fields[2] not in ('+', '-') or fields[4] not in ('+', '-'):
        raise ValueError('Invalid oriented link record')
    left, right = (_identifier(fields[1], settings), _identifier(fields[3], settings))
    _tags(fields[6:])
    return {'source': left, 'target': right, 'source_orientation': fields[2], 'target_orientation': fields[4], 'overlap': _overlap(fields[5], settings), 'is_self_link': left == right}

def _path(fields, settings):
    if len(fields) < 4:
        raise ValueError('Incomplete path record')
    name = _identifier(fields[1], settings)
    if ';' in fields[2]:
        raise Unsupported('Jump-connected paths are not supported')
    steps = []
    for value in fields[2].split(','):
        if len(steps) >= settings['max_path_steps']:
            raise Unsupported('Path steps exceed metadata limit')
        if not value or value[-1] not in ('+', '-'):
            raise ValueError('Invalid oriented path step')
        steps.append({'segment': _identifier(value[:-1], settings), 'orientation': value[-1]})
    overlaps = None if fields[3] == '*' else [_overlap(v, settings) for v in fields[3].split(',')]
    if overlaps is not None and len(overlaps) != len(steps) - 1:
        raise ValueError('Path overlap count disagrees with steps')
    _tags(fields[4:])
    return {'id': name, 'steps': steps, 'overlaps': overlaps}

def parse_gfa(path, limits=None):
    """Parse GFA1 S/L/P syntax and references without exporting sequences or URIs."""
    settings = _limits(limits)
    source, status = _source(path, 'gfa', settings)
    result = {'status': status, 'source': source, 'format': 'GFA1 S/L/P', 'version': None, 'nodes': [], 'edges': [], 'paths': [], 'self_loop_segment_ids': [], 'complete': False, 'unsupported_record_counts': {}, 'limits': settings, 'limitations': list(LIMITATIONS)}
    if status != 'available':
        result['reason'] = {'missing': 'Source not collected', 'unsupported': 'Source exceeds metadata size limit', 'invalid': 'Source is unreadable'}[status]
        return result
    names, path_names, step_count, line_number = (set(), set(), 0, 0)
    try:
        for line_number, line in _lines(path, settings):
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            record = fields[0]
            if record == 'H':
                tags = _tags(fields[1:])
                if 'VN' in tags:
                    kind, version = tags['VN']
                    if kind != 'Z' or version not in {'1.0', '1.1', '1.2'}:
                        raise Unsupported('Unsupported GFA version')
                    if result['version'] is not None and result['version'] != version:
                        raise ValueError('Conflicting GFA version headers')
                    result['version'] = version
            elif record == 'S':
                node = _segment(fields, settings)
                if node['id'] in names or node['id'] in path_names:
                    raise ValueError('Duplicate segment/path name')
                if len(result['nodes']) >= settings['max_nodes']:
                    raise Unsupported('Segment count exceeds metadata limit')
                result['nodes'].append(node)
                names.add(node['id'])
            elif record == 'L':
                if len(result['edges']) >= settings['max_edges']:
                    raise Unsupported('Link count exceeds metadata limit')
                result['edges'].append(_link(fields, settings))
            elif record == 'P':
                row = _path(fields, settings)
                if row['id'] in names or row['id'] in path_names:
                    raise ValueError('Duplicate segment/path name')
                step_count += len(row['steps'])
                if len(result['paths']) >= settings['max_paths'] or step_count > settings['max_path_steps']:
                    raise Unsupported('Path count/steps exceed metadata limit')
                result['paths'].append(row)
                path_names.add(row['id'])
            else:
                key = record if len(record) == 1 and record.isascii() else 'other'
                result['unsupported_record_counts'][key] = result['unsupported_record_counts'].get(key, 0) + 1
        if any((e['source'] not in names or e['target'] not in names for e in result['edges'])) or any((s['segment'] not in names for p in result['paths'] for s in p['steps'])):
            raise ValueError('Link/path refers to an undefined segment')
        if digest(Path(path)) != source['file_sha256']:
            raise ValueError('Source changed while reading metadata')
        result['self_loop_segment_ids'] = sorted({e['source'] for e in result['edges'] if e['is_self_link']})
        result['status'] = 'unsupported' if result['unsupported_record_counts'] else 'available'
        result['complete'] = result['status'] == 'available'
        if not result['complete']:
            result['reason'] = 'Contains record types outside S/L/P; graph is partial'
    except (ValueError, OSError) as error:
        result.update(status='unsupported' if isinstance(error, Unsupported) else 'invalid', reason=str(error), error_line=line_number, nodes=[], edges=[], paths=[], self_loop_segment_ids=[], complete=False)
    return result

def parse_flye_assembly_info(path, limits=None):
    """Read Flye's reported circ. field; N is not a verified linear molecule."""
    settings = _limits(limits)
    source, status = _source(path, 'flye_assembly_info', settings)
    result = {'status': status, 'source': source, 'format': 'Flye assembly_info.txt', 'contigs': [], 'columns': [], 'limits': settings, 'limitations': list(LIMITATIONS)}
    if status != 'available':
        result['reason'] = {'missing': 'Source not collected', 'unsupported': 'Source exceeds metadata size limit', 'invalid': 'Source is unreadable'}[status]
        return result
    header, seen, line_number = (None, set(), 0)
    try:
        for line_number, line in _lines(path, settings):
            if not line:
                continue
            if line.startswith('#'):
                names = line[1:].split()
                if names and names[0] == 'seq_name':
                    if header is not None:
                        raise ValueError('Repeated Flye assembly-info header')
                    if names[:4] != ['seq_name', 'length', 'cov.', 'circ.'] or any((name not in {'seq_name', 'length', 'cov.', 'circ.', 'repeat', 'mult.', 'alt_group', 'graph_path'} for name in names)) or len(set(names)) != len(names):
                        raise Unsupported('Unsupported assembly-info columns')
                    header = names
                    result['columns'] = names
                continue
            if header is None:
                raise Unsupported('Flye assembly-info header was not found')
            fields = line.split()
            if len(fields) != len(header):
                raise ValueError('Assembly-info row/column count mismatch')
            row = dict(zip(header, fields))
            name = _identifier(row['seq_name'], settings)
            if name in seen:
                raise ValueError('Duplicate assembly-info contig name')
            if len(result['contigs']) >= settings['max_nodes']:
                raise Unsupported('Contig claims exceed metadata limit')
            circ = {'Y': 'circular', 'N': 'not_circular', '*': 'unknown', '?': 'unknown'}.get(row['circ.'])
            if circ is None:
                raise Unsupported('Unsupported tool circularity token')
            item = {'id': name, 'length_bp': _integer(row['length']), 'reported_coverage': None if row['cov.'] == '*' else _numeric(row['cov.']), 'reported_circularity': circ, 'reported_circularity_raw': row['circ.'], 'claim_scope': 'Tool report only; N means not reported circular, not proven linear'}
            if 'graph_path' in row:
                if len(row['graph_path']) > settings['max_overlap_chars']:
                    raise Unsupported('Reported graph path exceeds metadata limit')
                item['reported_graph_path'] = row['graph_path']
            result['contigs'].append(item)
            seen.add(name)
        if header is None:
            raise Unsupported('Flye assembly-info header was not found')
        if digest(Path(path)) != source['file_sha256']:
            raise ValueError('Source changed while reading metadata')
    except (ValueError, OSError) as error:
        result.update(status='unsupported' if isinstance(error, Unsupported) else 'invalid', reason=str(error), error_line=line_number, contigs=[])
    return result

def parse_miniasm_unitig_info(path, limits=None):
    """Miniasm 0.3 names unitigs utgNNNNNNc/l (asm.c ma_ug_print)."""
    graph = parse_gfa(path, limits)
    source = {**graph['source'], 'kind': 'miniasm_gfa_unitig_names'}
    result = {'status': graph['status'], 'source': source, 'format': 'Miniasm unitig identifiers in GFA', 'contigs': [], 'limits': graph['limits'], 'limitations': []}
    if graph['status'] != 'available':
        result['reason'] = graph.get('reason', 'GFA unavailable')
        return result
    for node in graph['nodes']:
        match = re.fullmatch('utg[0-9]+([lc])', node['id'])
        token = match.group(1) if match else '?'
        depth = next((tag['value'] for tag in node['reported_coverage_tags'] if tag['tag'] == 'dp'), None)
        result['contigs'].append({'id': node['id'], 'length_bp': node['length_bp'], 'reported_coverage': depth, 'reported_circularity_raw': token, 'reported_circularity': {'c': 'circular', 'l': 'not_circular', '?': 'unknown'}[token], 'claim_scope': 'Miniasm unitig identifier suffix from ma_ug_print; coverage from a dp tag when present.'})
    return result

def _partial_role(role):
    return isinstance(role, str) and bool(re.fullmatch('(?:initial_[A-Za-z0-9_-]+|partial_[A-Za-z0-9_-]+|[A-Za-z0-9_-]+_component)', role))

def build_graph_artifacts(execution_path, assembly_path, gfa_path=None, assembly_info_path=None, source_role='final', limits=None, assembly_info_kind='flye', allow_failed=False):
    """Collect existing topology only; failed runs require explicit partial provenance.

    Default scored-run calls retain full assembly-byte verification. Opt-in error/
    timeout collection never represents its graph as a verified primary assembly.
    """
    settings = _limits(limits)
    if not re.fullmatch('[A-Za-z0-9_-]{1,64}', source_role):
        raise ValueError('Use a simple source role label')
    execution_path = Path(execution_path)
    execution_hash = digest(execution_path)
    execution = load(execution_path)
    if digest(execution_path) != execution_hash:
        raise ValueError('Execution changed while reading its state')
    state = execution.get('status')
    failed = state in {'error', 'timeout'} and allow_failed is True
    assembly_hash = None
    if state in {'pass', 'fail'}:
        if assembly_path is None:
            raise ValueError('A scored execution requires its primary assembly bytes')
        assembly_path = Path(assembly_path)
        assembly_hash = digest(assembly_path)
        if not execution.get('assembly_sha256') or execution['assembly_sha256'] != assembly_hash:
            raise ValueError('Assembly checksum does not match the execution record')
    elif failed:
        if assembly_path is not None or not _partial_role(source_role):
            raise ValueError('Failed-run metadata requires no primary assembly and an explicit partial/component role')
    else:
        raise ValueError('Only scored runs or explicitly admitted terminal error/timeout metadata can be collected')
    graph = parse_gfa(gfa_path, settings)
    if assembly_info_kind not in {'flye', 'plassembler', 'miniasm'}:
        raise ValueError('Unsupported assembly-information source kind')
    parser = {'flye': parse_flye_assembly_info, 'plassembler': parse_plassembler_summary, 'miniasm': parse_miniasm_unitig_info}[assembly_info_kind]
    info = parser(assembly_info_path, settings)
    for item in (graph, info):
        item['source']['role'] = source_role
    states = {graph['status'], info['status']}
    status = next((value for value in ('invalid', 'unsupported', 'available') if value in states), 'missing')
    result = {'schema_version': 1, 'status': status, 'input_hashes': {'execution_sha256': execution_hash, 'assembly_sha256': assembly_hash}, 'graph': graph, 'assembly_info': info, 'limits': settings, 'limitations': list(LIMITATIONS), 'source_relationship': 'Artefacts from this execution; graph segment IDs need not equal final FASTA contig IDs', 'validation': {'execution_record_verified': True, 'assembly_bytes_verified': not failed}}
    if failed:
        result['failed_execution_provenance'] = {'execution_status': state, 'execution_sha256': execution_hash, 'primary_assembly_status': 'unavailable_or_unverified', 'recorded_primary_assembly_sha256': execution.get('assembly_sha256'), 'source_role': source_role}
        result['source_relationship'] = 'Partial/component artefacts retained by a stopped execution; no verified primary or final assembly is established'
        result['limitations'].append('The execution stopped with ' + state + '; retained artefact claims are partial and no primary assembly hash is verified.')
    if failed:
        _failed_metadata(result)
    if len(json.dumps(result, sort_keys=True).encode()) > settings['max_sidecar_bytes']:
        result['status'] = 'unsupported'
        result['reason'] = 'Serialized metadata exceeds sidecar limit'
        graph.update(status='unsupported', reason=result['reason'], nodes=[], edges=[], paths=[], self_loop_segment_ids=[], complete=False)
        info.update(status='unsupported', reason=result['reason'], contigs=[])
    if digest(execution_path) != execution_hash or (not failed and digest(assembly_path) != assembly_hash):
        raise ValueError('Execution or assembly changed during metadata collection')
    for path, metadata in ((gfa_path, graph), (assembly_info_path, info)):
        sha = metadata['source'].get('file_sha256')
        if sha and digest(Path(path)) != sha:
            raise ValueError('Source artefact changed during metadata collection')
    return result

def _keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('Unsupported topology metadata schema')

def _source_metadata(source):
    _keys(source, {'filename', 'file_sha256', 'kind', 'role', 'bytes', 'hash_status'}, {'kind'})
    filename = source.get('filename')
    if filename is not None and (not isinstance(filename, str) or not filename or len(filename) > 256 or ('/' in filename) or ('\\' in filename)):
        raise ValueError('Source filename is not a basename')
    sha = source.get('file_sha256')
    if sha is not None and (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)):
        raise ValueError('Invalid source hash')
    if source['kind'] not in {'gfa', 'flye_assembly_info', 'plassembler_summary', 'miniasm_gfa_unitig_names'} or not re.fullmatch('[A-Za-z0-9_-]{1,64}', source.get('role', 'unspecified')):
        raise ValueError('Unsupported source kind/role')
    if 'bytes' in source and (not isinstance(source['bytes'], int) or isinstance(source['bytes'], bool) or source['bytes'] < 0):
        raise ValueError('Invalid source size')

def _length(value, nullable=True):
    if value is None and nullable:
        return
    if not isinstance(value, int) or isinstance(value, bool) or (not 0 <= value <= 2 ** 53 - 1):
        raise ValueError('Invalid segment/contig length')

def _validate_metadata(document):
    """Reject unknown payload fields, including injected sequence fields, before publication."""
    settings = DEFAULT_LIMITS

    def no_sequence_fields(value):
        if isinstance(value, dict):
            if any((str(key).lower() in {'sequence', 'sequences', 'seq', 'dna', 'bases', 'fasta', 'nucleotide_sequence', 'sequence_data'} for key in value)):
                raise ValueError('Sequence payloads are outside topology metadata')
            for child in value.values():
                no_sequence_fields(child)
        elif isinstance(value, list):
            for child in value:
                no_sequence_fields(child)
    no_sequence_fields(document)
    if 'collection' in document:
        collection = document['collection']
        _keys(collection, {'source_role', 'candidate_files', 'batch_id', 'execution_relative_path', 'collected_at', 'source_reads_modified', 'sequence_exported', 'checkpoint_policy', 'recorded_primary_assembly_sha256', 'assembly_hash_verified'})
        for flag in ('source_reads_modified', 'sequence_exported'):
            if flag in collection and collection[flag] is not False:
                raise ValueError('Collection contains a source modification/sequence export claim')
        for key in ('batch_id', 'execution_relative_path', 'collected_at', 'checkpoint_policy'):
            if key in collection and (not isinstance(collection[key], str) or len(collection[key]) > 1024):
                raise ValueError('Invalid scalar collection metadata')
        if collection.get('source_role') is not None and (not isinstance(collection['source_role'], str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', collection['source_role'])):
            raise ValueError('Invalid collection source role')
        if 'assembly_hash_verified' in collection and (not isinstance(collection['assembly_hash_verified'], bool)):
            raise ValueError('Invalid collection hash-verification flag')
        if collection.get('recorded_primary_assembly_sha256') is not None and (not re.fullmatch('[0-9a-f]{64}', collection['recorded_primary_assembly_sha256'])):
            raise ValueError('Invalid recorded assembly hash')
        candidates = collection.get('candidate_files', [])
        if not isinstance(candidates, list) or len(candidates) > 64:
            raise ValueError('Too many source candidates')
        for candidate in candidates:
            _keys(candidate, {'relative_path', 'kind', 'role', 'status'}, {'kind', 'role', 'status'})
            if any((not isinstance(value, str) or len(value) > 512 for value in candidate.values())):
                raise ValueError('Invalid source-candidate metadata')
    for metadata in (document, document.get('graph', {}), document.get('assembly_info', {})):
        if 'limits' in metadata:
            _limits(metadata['limits'])
    _keys(document, {'schema_version', 'status', 'input_hashes', 'graph', 'assembly_info', 'limits', 'limitations', 'source_relationship', 'validation', 'reason', 'availability', 'collection', 'attachment', 'failed_execution_provenance'}, {'schema_version', 'status', 'input_hashes', 'graph', 'assembly_info'})
    if document['schema_version'] != 1 or document['status'] not in STATUSES:
        raise ValueError('Unsupported topology sidecar version/status')
    failed = _failed_metadata(document)
    if 'attachment' in document:
        _keys(document['attachment'], {'sidecar_sha256', 'execution_hash_verified', 'assembly_record_hash_verified', 'failed_execution_state_verified'}, {'sidecar_sha256', 'execution_hash_verified', 'assembly_record_hash_verified'})
        attachment = document['attachment']
        if not isinstance(attachment['sidecar_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', attachment['sidecar_sha256']) or attachment['execution_hash_verified'] is not True or (attachment['assembly_record_hash_verified'] is not (not failed)) or (failed and attachment.get('failed_execution_state_verified') is not True):
            raise ValueError('Invalid topology attachment audit')
    if 'validation' in document:
        _keys(document['validation'], {'execution_record_verified', 'assembly_bytes_verified'})
        if any((not isinstance(value, bool) for value in document['validation'].values())):
            raise ValueError('Invalid source-validation flags')
    if document['status'] == 'available' and document.get('validation') != {'execution_record_verified': True, 'assembly_bytes_verified': not failed}:
        raise ValueError('Available topology is missing verified input provenance')
    _keys(document['input_hashes'], {'execution_sha256', 'assembly_sha256'}, {'execution_sha256', 'assembly_sha256'})
    for key, value in document['input_hashes'].items():
        if value is None and key == 'assembly_sha256' and failed:
            continue
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('Invalid input hash')
    graph, info = (document['graph'], document['assembly_info'])
    _keys(graph, {'status', 'source', 'format', 'version', 'nodes', 'edges', 'paths', 'self_loop_segment_ids', 'complete', 'unsupported_record_counts', 'limits', 'limitations', 'reason', 'error_line'}, {'status'})
    _keys(info, {'status', 'source', 'format', 'contigs', 'columns', 'limits', 'limitations', 'reason', 'error_line'}, {'status'})
    if graph.get('format') not in {None, 'GFA1 S/L/P'} or info.get('format') not in {None, 'Flye assembly_info.txt', 'Plassembler summary.tsv', 'Miniasm unitig identifiers in GFA'}:
        raise ValueError('Unsupported source metadata format label')
    for metadata in (graph, info):
        if metadata['status'] not in STATUSES:
            raise ValueError('Invalid metadata source status')
        if 'source' in metadata:
            _source_metadata(metadata['source'])
        if metadata['status'] == 'available' and (not metadata.get('source', {}).get('file_sha256')):
            raise ValueError('Available metadata has no source hash')
    nodes, edges, paths = (graph.get('nodes', []), graph.get('edges', []), graph.get('paths', []))
    if not all((isinstance(value, list) for value in (nodes, edges, paths, info.get('contigs', [])))) or len(nodes) > settings['max_nodes'] or len(edges) > settings['max_edges'] or (len(paths) > settings['max_paths']) or (len(info.get('contigs', [])) > settings['max_nodes']):
        raise ValueError('Topology payload exceeds metadata bounds')
    names, path_names, step_count = (set(), set(), 0)
    for node in nodes:
        _keys(node, {'id', 'length_bp', 'reported_coverage_tags'}, {'id', 'length_bp'})
        name = _identifier(node['id'], settings)
        if name in names:
            raise ValueError('Duplicate metadata segment name')
        names.add(name)
        _length(node['length_bp'])
        tags = node.get('reported_coverage_tags', [])
        if not isinstance(tags, list) or len(tags) > len(COVERAGE_TAGS):
            raise ValueError('Invalid coverage metadata list')
        for tag in tags:
            _keys(tag, {'tag', 'type', 'value', 'meaning'}, {'tag', 'type', 'value', 'meaning'})
            if tag['tag'] not in COVERAGE_TAGS or tag['meaning'] != COVERAGE_TAGS[tag['tag']] or tag['type'] not in {'i', 'f'} or (not isinstance(tag['value'], (int, float))) or isinstance(tag['value'], bool) or (not math.isfinite(tag['value'])) or (tag['value'] < 0):
                raise ValueError('Invalid numeric coverage tag')
    for edge in edges:
        _keys(edge, {'source', 'target', 'source_orientation', 'target_orientation', 'overlap', 'is_self_link'}, {'source', 'target', 'source_orientation', 'target_orientation', 'overlap', 'is_self_link'})
        if edge['source'] not in names or edge['target'] not in names or edge['source_orientation'] not in {'+', '-'} or (edge['target_orientation'] not in {'+', '-'}) or (edge['is_self_link'] is not (edge['source'] == edge['target'])):
            raise ValueError('Invalid topology link')
        _overlap(edge['overlap'], settings)
    for row in paths:
        _keys(row, {'id', 'steps', 'overlaps'}, {'id', 'steps', 'overlaps'})
        name = _identifier(row['id'], settings)
        if name in names or name in path_names or (not isinstance(row['steps'], list)):
            raise ValueError('Invalid metadata path name/steps')
        path_names.add(name)
        step_count += len(row['steps'])
        if step_count > settings['max_path_steps']:
            raise ValueError('Topology path steps exceed metadata bounds')
        for step in row['steps']:
            _keys(step, {'segment', 'orientation'}, {'segment', 'orientation'})
            if step['segment'] not in names or step['orientation'] not in {'+', '-'}:
                raise ValueError('Invalid metadata path step')
        overlaps = row['overlaps']
        if overlaps is not None:
            if not isinstance(overlaps, list) or len(overlaps) != len(row['steps']) - 1:
                raise ValueError('Invalid metadata path overlaps')
            for value in overlaps:
                _overlap(value, settings)
    self_links = sorted({edge['source'] for edge in edges if edge['is_self_link']})
    if 'self_loop_segment_ids' in graph and graph['self_loop_segment_ids'] != self_links:
        raise ValueError('Self-link labels disagree with recorded links')
    if graph['status'] == 'available' and graph.get('complete') is not True:
        raise ValueError('Available graph metadata must state complete parsing')
    if graph['status'] in {'missing', 'invalid'} and (nodes or edges or paths):
        raise ValueError('Unavailable graph contains untrusted topology')
    if graph.get('source', {}).get('role') and info.get('source', {}).get('role') and (graph['source']['role'] != info['source']['role']):
        raise ValueError('Graph and circularity claims refer to different source stages')
    info_names = set()
    for row in info.get('contigs', []):
        _keys(row, {'id', 'length_bp', 'reported_coverage', 'reported_circularity', 'reported_circularity_raw', 'claim_scope', 'reported_graph_path'}, {'id', 'length_bp', 'reported_circularity'})
        _identifier(row['id'], settings)
        if row['id'] in info_names:
            raise ValueError('Duplicate contig claim')
        info_names.add(row['id'])
        _length(row['length_bp'], False)
        raw = row.get('reported_circularity_raw')
        known = {'Y': 'circular', 'N': 'not_circular', '*': 'unknown', '?': 'unknown', 'circular': 'circular', 'linear': 'not_circular', 'not_circular': 'not_circular', 'unknown': 'unknown', 'NA': 'unknown'}
        known.update({'c': 'circular', 'l': 'not_circular'})
        if raw is not None and known.get(raw) != row['reported_circularity']:
            raise ValueError('Raw circularity token disagrees with the tool-claim label')
        if row['reported_circularity'] not in {'circular', 'not_circular', 'unknown'}:
            raise ValueError('Unknown tool circularity claim')
        if row.get('reported_coverage') is not None:
            _numeric(row['reported_coverage'])
    return document

def attach_graph_artifacts(record, execution_path=None):
    """Attach only a checked existing sidecar. Reporting never parses raw artefacts."""
    result = copy.deepcopy(record)

    def unavailable(reason):
        result['graph_artifacts'] = {'status': 'not_collected', 'reason': reason}
        return result
    if execution_path is None:
        return unavailable('An execution record path is required to verify collected topology metadata')
    execution_path = Path(execution_path)
    if execution_path.name != 'execution.json' or not execution_path.is_file():
        return unavailable('Execution record is unavailable for topology verification')
    path = execution_path.parent / 'graph_artifacts.json'
    if not path.is_file():
        return unavailable('Graph metadata has not been collected for this execution')
    if path.stat().st_size > DEFAULT_LIMITS['max_sidecar_bytes']:
        return unavailable('Collected topology metadata exceeds the publication size limit')
    try:
        document = _validate_metadata(load(path))
        hashes = document['input_hashes']
        execution = load(execution_path)
        failed = _failed_metadata(document)
        if hashes['execution_sha256'] != digest(execution_path):
            return unavailable('Collected topology metadata does not match this execution')
        if failed:
            proof = document['failed_execution_provenance']
            if execution.get('status') != proof['execution_status'] or record.get('status') != proof['execution_status'] or execution.get('assembly_sha256') != proof['recorded_primary_assembly_sha256'] or (record.get('assembly_sha256') != proof['recorded_primary_assembly_sha256']):
                return unavailable('Failed topology metadata does not match the actual execution state')
        elif execution.get('status') not in {'pass', 'fail'} or hashes['assembly_sha256'] != record.get('assembly_sha256') or execution.get('assembly_sha256') != record.get('assembly_sha256'):
            return unavailable('Collected topology metadata does not match this scored execution and assembly')
        result['graph_artifacts'] = document
        result['graph_artifacts']['attachment'] = {'sidecar_sha256': digest(path), 'execution_hash_verified': True, 'assembly_record_hash_verified': not failed}
        if failed:
            result['graph_artifacts']['attachment']['failed_execution_state_verified'] = True
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        return unavailable('Collected topology metadata is invalid or outside the supported schema')
    return result

def parse_plassembler_summary(path, limits=None):
    """Read only final Plassembler contig/length/circularity claims, never sequences."""
    import csv
    settings = _limits(limits)
    source, status = _source(path, 'plassembler_summary', settings)
    result = {'status': status, 'source': source, 'format': 'Plassembler summary.tsv', 'contigs': [], 'columns': ['contig', 'length', 'circularity'], 'limits': settings, 'limitations': list(LIMITATIONS)}
    if status != 'available':
        result['reason'] = {'missing': 'Source not collected', 'unsupported': 'Source exceeds metadata size limit', 'invalid': 'Source is unreadable'}[status]
        return result
    seen, line_number = (set(), 0)
    try:
        lines = _lines(path, settings)
        header = None
        for line_number, line in lines:
            if not line:
                continue
            fields = next(csv.reader([line], delimiter='\t'))
            if header is None:
                header = fields
                if len(set(header)) != len(header) or not {'contig', 'length', 'circularity'}.issubset(header):
                    raise Unsupported('Required Plassembler summary columns were not found')
                continue
            if len(fields) != len(header):
                raise ValueError('Plassembler summary row/column count mismatch')
            row = dict(zip(header, fields))
            name = _identifier(row['contig'], settings)
            if name in seen:
                raise ValueError('Duplicate Plassembler summary contig name')
            if len(result['contigs']) >= settings['max_nodes']:
                raise Unsupported('Contig claims exceed metadata limit')
            raw = row['circularity']
            claim = {'circular': 'circular', 'linear': 'not_circular', 'not_circular': 'not_circular', 'unknown': 'unknown', 'NA': 'unknown', '*': 'unknown', '?': 'unknown'}.get(raw)
            if claim is None:
                raise Unsupported('Unsupported Plassembler circularity token')
            result['contigs'].append({'id': name, 'length_bp': _integer(row['length']), 'reported_circularity': claim, 'reported_circularity_raw': raw, 'claim_scope': 'Final tool summary claim only; physical topology and sequence accuracy are not established'})
            seen.add(name)
        if header is None:
            raise Unsupported('Plassembler summary header was not found')
        if digest(Path(path)) != source['file_sha256']:
            raise ValueError('Source changed while reading metadata')
    except (ValueError, OSError) as error:
        result.update(status='unsupported' if isinstance(error, Unsupported) else 'invalid', reason=str(error), error_line=line_number, contigs=[])
    return result

def _failed_metadata(document):
    if 'failed_execution_provenance' not in document:
        return False
    proof = document['failed_execution_provenance']
    _keys(proof, {'execution_status', 'execution_sha256', 'primary_assembly_status', 'recorded_primary_assembly_sha256', 'source_role'}, {'execution_status', 'execution_sha256', 'primary_assembly_status', 'recorded_primary_assembly_sha256', 'source_role'})
    hashes = document.get('input_hashes') or {}
    if proof['execution_status'] not in {'error', 'timeout'} or proof['execution_sha256'] != hashes.get('execution_sha256') or hashes.get('assembly_sha256') is not None or (proof['primary_assembly_status'] != 'unavailable_or_unverified') or (not _partial_role(proof['source_role'])):
        raise ValueError('Invalid failed-execution topology provenance')
    recorded = proof['recorded_primary_assembly_sha256']
    if recorded is not None and (not isinstance(recorded, str) or not re.fullmatch('[0-9a-f]{64}', recorded)):
        raise ValueError('Invalid unverified assembly record hash')
    if document.get('validation') != {'execution_record_verified': True, 'assembly_bytes_verified': False}:
        raise ValueError('Failed-execution topology cannot claim primary assembly verification')
    for key in ('graph', 'assembly_info'):
        source = document.get(key, {}).get('source', {})
        if source and source.get('role') != proof['source_role']:
            raise ValueError('Failed artefact source role disagrees with provenance')
    collection = document.get('collection') or {}
    if collection.get('assembly_hash_verified') is True or (collection.get('source_role') is not None and collection['source_role'] != proof['source_role']):
        raise ValueError('Failed collection cannot claim verified primary/final assembly')
    return True
