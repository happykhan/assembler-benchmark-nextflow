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
