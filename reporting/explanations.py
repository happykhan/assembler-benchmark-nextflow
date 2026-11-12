"""Deterministic descriptions of existing evidence, without sequence analysis."""
import copy
import math
from pathlib import Path
import re
from .common import digest
from diagnostic_core.diagnostics import DEFAULT_POLICY
CONFIDENCES = {'confirmed', 'suspected', 'unresolved'}
LOG_PATTERNS = (('no_chromosome_identified', '\\b(?:no chromosomes?(?: contigs?)?(?: was| were| has been)? (?:identified|found|assembled)|chromosome was not assembled)\\b', 'The tool reported that no chromosome was identified.'), ('no_disjointigs', '\\bno disjointigs were assembled\\b', 'The tool reported that no disjointigs were assembled.'), ('no_contigs', '\\bno contigs were assembled\\b', 'The tool reported that no contigs were assembled.'), ('socket_path_error', '\\bAF_UNIX path too long\\b', 'Execution reported an overlong temporary socket path.'), ('disk_space_error', '\\bno space left on device\\b', 'Execution reported that the device had no space left.'), ('provenance_mismatch', '(?:provenance does not match|fingerprint does not match|input checksum mismatch|allocated slurm cpus do not match)', 'The benchmark reported a provenance, checksum or allocation mismatch.'), ('missing_expected_output', '(?:expected fasta is missing|expected .*fasta was not produced|assembler exited successfully but its expected)', 'The benchmark could not find the expected output after tool execution.'), ('version_check_failed', '(?:assembler version check failed|tool version check failed)', 'The execution version check failed.'))

def _observations(text, source):
    return [{'code': code, 'type': 'execution_log', 'text': description, 'source': source} for code, pattern, description in LOG_PATTERNS if re.search(pattern, text or '', re.IGNORECASE)]

def _finding(kind, summary, symptom, interpretation, evidence, confidence='confirmed', source='recorded_evidence', **extra):
    scope = {'confirmed': 'Recorded observation, not an assembly-internal mechanism', 'suspected': 'Candidate interpretation requiring review', 'unresolved': 'Available evidence does not resolve the explanation'}
    return {'schema_version': 1, 'kind': kind, 'summary': summary, 'symptom': symptom, 'confidence': confidence, 'confidence_scope': scope[confidence], 'interpretation': interpretation, 'evidence': evidence, 'source': source, 'mechanism_confidence': 'unresolved', **extra}

def _review(record, case):
    review = record.get('sequence_review') or {}
    if review.get('status') != 'verified' or not review.get('explanation') or (not review.get('summary')) or (review.get('strict_status') != record.get('status')):
        return None
    for key, expected in (('tool', record.get('tool')), ('scenario_id', record.get('scenario_id') or (case or {}).get('id')), ('batch_id', record.get('batch_id'))):
        if review.get(key) and expected and (review[key] != expected):
            return None
    return _finding('reviewed_finding', review['summary'], review['summary'], review['explanation'], [{'type': 'curated_review', 'text': review['explanation'], 'source': 'sequence_review.explanation'}], source='curated_review', confidence_scope='Checked finding for the exact reviewed artefacts and stated scope', mechanism_confidence=None, source_document=review.get('source_document'), scope=review.get('scope'), authority='Existing checked review; no additional mechanistic claim is inferred')

def _strict_rows(record, case):
    rows = record.get('evaluation', {}).get('replicons', [])
    plasmids = {r['refseq_accession'] for r in (case or {}).get('replicons', []) if r.get('molecule_type') == 'plasmid'}
    plasmids = plasmids or {r['accession'] for r in rows if r.get('molecule_type') == 'plasmid'}
    return [r for r in rows if r.get('accession') in plasmids] if plasmids else [] if record.get('tool') == 'plassembler' else rows

def _number(value):
    return isinstance(value, (int, float)) and (not isinstance(value, bool)) and math.isfinite(value)

def _mapping_rows(record, strict_rows, case):
    diagnostic = record.get('diagnostics') or {}
    if diagnostic.get('status') != 'complete':
        return []
    rows = diagnostic.get('evidence', {}).get('replicons', [])
    expected = {r.get('accession') for r in strict_rows}
    if not expected and case:
        expected = {r['refseq_accession'] for r in case.get('replicons', []) if r.get('molecule_type') == 'plasmid'}
    failed = {r.get('accession') for r in strict_rows if r.get('status') == 'fail'}
    if expected:
        rows = [r for r in rows if r.get('accession') in (failed or expected)]
    elif record.get('tool') == 'plassembler':
        rows = []
    return [r for r in rows if _number(r.get('recovered_fraction')) and 0 <= r['recovered_fraction'] <= 1]

def _mapping_evidence(rows):
    result = []
    for row in rows:
        text = f"{row.get('name') or row['accession']}: {row['recovered_fraction']:.2%} retained reference coverage"
        if _number(row.get('alignment_identity')):
            text += f"; {row['alignment_identity']:.3%} alignment identity"
        text += f"; {row.get('contig_count', 'unknown')} supporting contig(s)."
        result.append({'type': 'mapping', 'text': text, 'source': 'diagnostics.evidence.replicons[' + row['accession'] + ']', 'metrics': {key: row.get(key) for key in ('recovered_fraction', 'alignment_identity', 'contig_count', 'candidate_flags')}})
    return result

def explain_result(record, case=None, stderr_text=None):
    """Describe the recorded symptom; confirmed generic findings do not confirm cause."""
    reviewed = _review(record, case)
    if reviewed:
        return reviewed
    status = record.get('status', 'not_run')
    observations = _observations(stderr_text, 'stderr.log') if stderr_text is not None else copy.deepcopy(record.get('explanation_log', {}).get('observations', []))
    observations += _observations(record.get('error', ''), 'execution.error')
    observations = list({(item['source'], item['code']): item for item in observations}.values())
    evidence = [{'type': 'execution', 'text': 'Recorded outcome: ' + status + '.', 'source': 'status'}]
    if status in ('not_run', 'pending', 'running'):
        return _finding('awaiting_assessment', 'Awaiting completed assessment', 'No completed assembly assessment is available.', 'An unfinished or unsubmitted run has no scientific recovery outcome yet.', evidence, 'unresolved', 'execution_state')
    if status == 'invalid_input':
        return _finding('invalid_input', 'Input was not admitted', 'The run is marked invalid input.', 'This remains outside assembler pass/fail counts; input validation is separate.', evidence + observations, source='execution_state')
    state = record.get('scheduler_state') or ''
    if state:
        evidence.append({'type': 'scheduler', 'text': 'Scheduler state: ' + state + '.', 'source': 'scheduler_state'})
    if status == 'timeout':
        return _finding('time_limit', 'Fail — did not complete', record.get('error') or 'The run did not finish within its time limit.', 'Execution did not complete; no final sequence assessment was made.', evidence + observations, source='execution_state')
    if status == 'error':
        return _execution_error(record, state, evidence, observations)
    if status == 'pass':
        return _finding('exact_pass', 'Recorded exact endpoint passes', 'The recorded exact sequence endpoint passes.', 'This finding applies to the stated endpoint and this input; topology remains separate.', evidence, source='strict_assessment')
    return _sequence_failure(record, case, evidence)

def attach_explanation(record, execution_path=None, case=None):
    """Enrich a copied report record with auditable, bounded log observations."""
    result = copy.deepcopy(record)
    if execution_path is not None:
        path = Path(execution_path)
        if path.name != 'execution.json':
            raise ValueError('Explain stderr beside an execution.json record only')
        stderr = path.parent / 'stderr.log'
        if stderr.is_file():
            size = stderr.stat().st_size
            with stderr.open('rb') as stream:
                head = stream.read(32768)
                if size > 65536:
                    stream.seek(-32768, 2)
                    content = head + b'\n' + stream.read(32768)
                else:
                    content = head + stream.read()
            result['explanation_log'] = {'file': 'stderr.log', 'sha256': digest(stderr), 'bytes': size, 'sample_policy': 'first and last 32 KiB when larger than 64 KiB; otherwise complete', 'observations': _observations(content.decode('utf-8', errors='replace'), 'stderr.log')}
    result['explanation'] = explain_result(result, case)
    return result

def _execution_error(record, state, evidence, observations):
    codes = {item['code'] for item in observations}
    if state.startswith('OUT_OF_MEMORY'):
        return _finding('resource_stop', 'Scheduler memory-limit stop', 'The scheduler reported an out-of-memory stop.', 'No completed sequence comparison follows from this stopped job.', evidence + observations, source='scheduler_state')
    if codes & {'provenance_mismatch', 'missing_expected_output', 'version_check_failed', 'socket_path_error', 'disk_space_error'}:
        return _finding('pipeline_error', 'Execution or evidence-handling error', 'The benchmark could not complete a valid execution record.', 'This concerns execution setup, required output or evidence handling; it does not establish plasmid recovery failure.', evidence + observations, source='execution_evidence')
    if 'no_chromosome_identified' in codes:
        return _finding('tool_stopped', 'Tool reported no chromosome identified', 'The tool stopped with a no-chromosome-identified condition.', 'This is the reported stopping condition. It does not by itself establish insufficient depth, absent chromosome sequence or the cause of a plasmid assembly problem.', evidence + observations, source='execution_log')
    if codes & {'no_disjointigs', 'no_contigs'}:
        return _finding('tool_stopped', 'Tool stopped without assembled contigs', 'The tool reported that it could not produce assembled contigs.', 'The log establishes this stopping condition; the reason it occurred remains unresolved.', evidence + observations, source='execution_log')
    exit_code = record.get('exit_code')
    if isinstance(exit_code, int) and (not isinstance(exit_code, bool)) and (exit_code != 0):
        evidence.append({'type': 'execution', 'text': f'Assembler exit code: {exit_code}.', 'source': 'exit_code'})
        return _finding('tool_stopped', 'Assembler returned an error', 'The assembler process returned a non-zero exit code.', 'No completed sequence assessment is established. The exit code alone does not identify the cause.', evidence + observations, source='execution_record')
    return _finding('execution_error', 'Execution failed; cause unresolved', 'The run ended with an execution error.', 'Available records do not establish whether the tool, scheduler or benchmark stage caused the failure.', evidence + observations, 'unresolved', 'execution_record')

def _sequence_failure(record, case, evidence):
    strict_rows = _strict_rows(record, case)
    score = record.get('evaluation') or {}
    for row in strict_rows:
        exact, embedded = (row.get('exact_contigs', []), row.get('extra_full_copy_contigs', []))
        if row.get('status') == 'fail' and (len(exact) > 1 or embedded):
            detail = {'type': 'strict_sequence', 'text': f"{row.get('name') or row['accession']}: {len(exact)} exact dedicated match(es), {len(embedded)} additional embedded full-copy contig(s).", 'source': 'evaluation.replicons[' + row['accession'] + ']'}
            return _finding('exact_duplicate_or_embedded', 'Exact copy uniqueness failed', 'The exact evaluator found duplicate or embedded full-copy sequence.', 'The recorded output violates the unique dedicated-molecule criterion. This does not identify the assembly stage that produced it.', evidence + [detail], source='strict_assessment')
    if not strict_rows and record.get('tool') == 'plassembler' and (score.get('contig_count', 0) > 0):
        return _finding('unexpected_control_output', 'No-plasmid control produced output', 'The chromosome-only control produced sequence in the final plasmid output.', "This violates the no-plasmid-output criterion; the sequence's origin is not established by that criterion alone.", evidence, source='strict_assessment')
    if case and (not any((r.get('molecule_type') == 'plasmid' for r in case.get('replicons', [])))) and (score.get('contig_count', 0) > 1) and strict_rows and all((r.get('status') == 'pass' for r in strict_rows)):
        return _finding('unexpected_control_output', 'Extra contigs in chromosome-only control', 'The exact chromosome is present alongside additional output contigs.', 'The control requires one exact chromosome-only output. These extra contigs are not automatically identified as plasmids.', evidence, source='strict_assessment')
    assessment = record.get('tolerant_assessment') or {}
    failed = {r.get('accession') for r in strict_rows if r.get('status') == 'fail'}
    assessed = [r for r in assessment.get('replicons', []) if not failed or r.get('accession') in failed]
    ambiguous = [r for r in assessed if r.get('ambiguous_evidence')]
    if ambiguous:
        details = [{'type': 'tolerant_assessment', 'text': row.get('reason', 'Ambiguous assignment recorded.'), 'source': 'tolerant_assessment.replicons[' + row['accession'] + ']'} for row in ambiguous]
        return _finding('ambiguous_assignment', 'Sequence assignment remains ambiguous', 'The supplementary assessment records unresolved sequence or copy assignment.', 'Ambiguous alignments or competing assignments do not establish a unique dedicated molecule or a particular structural cause.', evidence + details, 'unresolved', 'supplementary_assessment')
    copies = [r for r in assessed if r.get('second_copy_evidence')]
    if copies:
        details = [{'type': 'tolerant_assessment', 'text': r.get('reason', 'Additional copy evidence recorded.'), 'source': 'tolerant_assessment.replicons[' + r['accession'] + '].second_copy_evidence'} for r in copies]
        return _finding('candidate_copy', 'Additional copy evidence', 'The supplementary assessment records a competing or embedded near-copy.', 'This is copy-screen evidence at the stated thresholds. It does not by itself identify a join, repeat structure or the assembly stage responsible.', evidence + details, 'suspected', 'supplementary_assessment')
    if record.get('status') == 'fail' and assessment.get('status') == 'pass':
        details = []
        for row in assessed:
            distances = [p['edit_distance'] for c in row.get('dedicated_candidates', []) for p in c.get('placements', []) if _number(p.get('edit_distance'))]
            text = (row.get('name') or row['accession']) + ': tolerant endpoint passes'
            if distances:
                text += '; recorded aligned-window edit distance ' + str(min(distances)) + ('–' + str(max(distances)) if min(distances) != max(distances) else '')
            details.append({'type': 'tolerant_assessment', 'text': text + '.', 'source': 'tolerant_assessment.replicons[' + row['accession'] + ']'})
        return _finding('non_exact_tolerant_recovery', 'Exact match fails; tolerant recovery passes', 'The output meets the separately recorded tolerant endpoint but is not an exact recovery.', 'A small sequence or boundary difference can fail exact recovery. Use the recorded alignment measurements; this result does not establish how the difference arose.', evidence + details, source='supplementary_assessment')
    rows = _mapping_rows(record, strict_rows, case)
    mapping_evidence = _mapping_evidence(rows)
    flags = sorted({flag for row in rows for flag in ('duplicated', 'joined', 'fragmented') if row.get('candidate_flags', {}).get(flag)})
    if flags:
        return _finding('candidate_structure', 'Candidate ' + ', '.join(flags) + ' evidence', 'Retained alignments carry candidate ' + ', '.join(flags) + ' flags.', 'These alignment flags can overlap. They require review before duplication, joining, fragmentation or an internal cause is confirmed.', evidence + mapping_evidence, 'suspected', 'mapping_diagnostics')
    if rows:
        return _mapped_failure(record, rows, evidence, mapping_evidence)
    diagnostic = record.get('diagnostics') or {}
    if diagnostic.get('status'):
        evidence.append({'type': 'diagnostic_state', 'text': 'Recovery diagnostics state: ' + str(diagnostic['status']) + '.', 'source': 'diagnostics.status'})
    return _finding('unresolved_exact_failure', 'Exact failure; explanation unresolved', 'The recorded exact endpoint fails, with no sufficient explanation in the available evidence.', 'The strict failure remains recorded. Missing, unavailable or failed supplementary diagnostics do not establish an additional sequence or mechanistic finding.', evidence, 'unresolved', 'strict_assessment')

def _mapped_failure(record, rows, evidence, mapping_evidence):
    diagnostic = record.get('diagnostics') or {}
    fractions = [row['recovered_fraction'] for row in rows]
    if any((value == 0 for value in fractions)):
        excluded = diagnostic.get('evidence', {}).get('excluded_alignment_counts', {})
        count = sum((excluded.get(key, 0) for key in ('secondary_or_unclassified', 'low_mapq', 'missing_mapq', 'ambiguous_bases')))
        if count:
            mapping_evidence.append({'type': 'mapping_filter', 'text': f'{count} alignment record(s) were excluded for secondary, ambiguous or unavailable/low-confidence evidence.', 'source': 'diagnostics.evidence.excluded_alignment_counts'})
        return _finding('no_retained_alignment', 'No retained alignment for an expected molecule', 'At least one expected molecule has no retained alignment under this mapping policy.', 'Filtering or alignment heuristics can hide sequence. This observation does not prove biological absence or identify where recovery failed.', evidence + mapping_evidence, source='mapping_diagnostics')
    policy = {**diagnostic.get('policy', {}), **diagnostic.get('evidence', {}).get('policy', {})}
    complete_fraction = policy.get('complete_fraction', DEFAULT_POLICY['complete_fraction'])
    if any((value < complete_fraction for value in fractions)):
        return _finding('partial_aligned_recovery', 'Partial aligned recovery', 'Retained alignments cover part of an expected molecule.', 'This measures aligned recovery under the stated filters. Unaligned positions are not automatically physically absent, and the assembly-internal cause remains unresolved.', evidence + mapping_evidence, source='mapping_diagnostics')
    return _finding('near_full_non_exact', 'Near-full mapping; exact recovery failed', 'Retained alignments cover most or all of the expected sequence, but the exact endpoint fails.', 'Mapped coverage does not establish exact sequence, complete boundaries or a unique dedicated copy. Differences and assignment remain unresolved unless separately reviewed.', evidence + mapping_evidence, source='mapping_diagnostics')
