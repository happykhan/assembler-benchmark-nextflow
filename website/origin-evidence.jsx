import React from 'react';
import { StatusBadge } from '@genomicx/ui';

export function originEvidenceClass(match) {
  if (match?.status === 'ambiguous') return 'ambiguous';
  if (match?.status !== 'supported') return 'unresolved';
  if (['verified_whole_segment', 'path_inferred'].includes(match.evidence_class)) return match.evidence_class;
  if (match.evidence?.some(item => item.association_kind === 'whole_segment_sequence_identity')) return 'verified_whole_segment';
  return match.evidence?.some(item => item.path_id && item.exact_source) ? 'path_inferred' : 'unresolved';
}

export const originLabels = {verified_whole_segment: 'Verified whole-segment identity', path_inferred: 'Inferred through contig path', ambiguous: 'Ambiguous reference association', unresolved: 'Unresolved origin'};
export const originShortLabels = {verified_whole_segment: 'Identity verified', path_inferred: 'Via contig path', ambiguous: 'Ambiguous', unresolved: 'Unresolved'};
const spanLabel = span => Array.isArray(span) && span.length === 2 ? span.map(value => value.toLocaleString()).join('–') : 'Not recorded';

export function OriginEvidence({ origin, node, origins, selectedInterval, onSelectInterval }) {
  if (nodeOriginChunks(node.id, origins).length) return <NodeIntervalEvidence node={node} origins={origins} selectedInterval={selectedInterval} onSelectInterval={onSelectInterval} />;
  const kind = originEvidenceClass(origin.match);
  const evidence = origin.match?.evidence ?? [];
  const identity = evidence.find(item => item.association_kind === 'whole_segment_sequence_identity');
  return <div className="origin-evidence" style={{'--reference-colour':origin.reference?.colour,'--reference-light':origin.reference?.light_colour}}>
    <h4>Reference origin: {origin.reference?.name ?? 'Unresolved'}</h4>
    <p><StatusBadge variant={kind === 'verified_whole_segment' ? 'success' : kind === 'path_inferred' ? 'info' : 'muted'}>{originLabels[kind]}</StatusBadge></p>
    {kind === 'verified_whole_segment' && identity && <>
      <div className="origin-track">Whole segment · {origin.reference?.name}</div>
      <div className="origin-axis"><span>0 bp</span><span>{identity.length_bp.toLocaleString()} bp</span></div>
      <p>Segment and contig cover the same full interval: {spanLabel([0,identity.length_bp])} bp, 0-based and end excluded.</p>
    </>}
    {kind === 'path_inferred' && <p>Reference association comes from an exact-matching contig's recorded path. Segment-to-reference coordinates are not recorded.</p>}
    {kind === 'ambiguous' && <p>Saved evidence associates this segment with multiple references.</p>}
    {kind === 'unresolved' && <p>{origins?.unassigned_reason ?? 'No saved reference association is available.'}</p>}
    {evidence.length > 0 && <ul className="origin-proof-list">{evidence.map((item,index) => {
      const saved = origins?.contig_alignments?.[item.contig_id];
      const rows = saved?.rows?.filter(row => row.reference_id === item.reference_id) ?? [];
      return <li key={index}>
        <p><strong>{item.association_kind === 'whole_segment_sequence_identity' ? 'Verified sequence identity' : 'Recorded path association'}</strong></p>
        <p>Segment <code>{node.id}</code> → contig <code>{item.contig_id}</code> → reference <code>{item.reference_id}</code> (saved exact match).</p>
        {item.association_kind === 'whole_segment_sequence_identity' ? <>
          <p>Segment and contig have identical sequence hashes across {item.length_bp.toLocaleString()} bp, orientation {item.orientation}.</p>
          <details><summary>Identity evidence</summary><p>Source: <code>{item.identity_source}</code></p><code>{item.sequence_sha256}</code></details>
        </> : <p>GFA path <code>{item.path_id}</code> contains segment <code>{node.id}{item.orientation}</code>.</p>}
        {rows.length > 0 ? <details className="origin-coordinates"><summary>Saved contig/reference coordinates ({rows.length} displayed)</summary>
          <p>These spans describe the output contig. Coordinates are 0-based; the end is excluded.{kind === 'path_inferred' ? ' A position for this graph segment within the contig is not recorded.' : ''}</p>
          <div className="table-scroll"><table><thead><tr><th>Contig interval (bp)</th><th>Reference interval (bp)</th><th>Strand</th></tr></thead><tbody>{rows.map((row,i)=><tr key={i}><td>{spanLabel(row.query_interval)}</td><td>{spanLabel(row.reference_interval)}</td><td>{row.strand}</td></tr>)}</tbody></table></div>
          {saved.total_rows > saved.rows.length && <p>Showing a subset of {saved.total_rows} saved rows. Full coordinates remain in the alignment downloads.</p>}
        </details> : <p className="muted">Contig/reference coordinates: not recorded in this origin summary.</p>}
      </li>;
    })}</ul>}
  </div>;
}

export function nodeOriginChunks(nodeId, origins) {
  return origins?.node_intervals?.[nodeId]?.intervals ?? [];
}

export function NodeIntervalEvidence({ node, origins, selectedInterval = 0, onSelectInterval }) {
  const saved = origins.node_intervals[node.id];
  const index = Math.min(selectedInterval ?? 0, saved.intervals.length - 1);
  const interval = saved.intervals[index];
  const rows = saved.alignments.filter(row => interval.alignment_ids.includes(row.id));
  const reference = id => origins.references.find(item => item.id === id);
  const label = chunk => chunk.status === 'supported' ? reference(chunk.reference_id)?.name ?? chunk.reference_id : chunk.status === 'ambiguous' ? 'Ambiguous' : 'No recorded support';
  return <section className="origin-evidence node-interval-evidence" aria-label="Recorded origin intervals">
    <h4>Origin within segment</h4>
    <p>Recorded node-to-reference matches. Positions are 0-based, with the end excluded. Boundaries mark alignment spans.</p>
    <div className="node-interval-track" aria-label="Choose an origin interval">{saved.intervals.map((chunk, i) => {
      const ref = chunk.status === 'supported' ? reference(chunk.reference_id) : null;
      return <button key={i} type="button" className="node-interval-chunk" aria-pressed={index === i} aria-label={`${spanLabel(chunk.node_interval)} bp: ${label(chunk)}`} title={`${spanLabel(chunk.node_interval)} bp: ${label(chunk)}`} style={{flexGrow:chunk.node_interval[1]-chunk.node_interval[0], '--reference-colour':ref?.colour, '--reference-light':ref?.light_colour}} onClick={() => onSelectInterval(i)} />;
    })}</div>
    <div className="origin-axis"><span>0 bp</span><span>{saved.length_bp.toLocaleString()} bp</span></div>
    <label className="node-interval-picker">Inspect interval<select className="gx-input" value={index} onChange={event => onSelectInterval(Number(event.target.value))}>{saved.intervals.map((chunk,i)=><option key={i} value={i}>{spanLabel(chunk.node_interval)} bp · {label(chunk)}</option>)}</select></label>
    <h4>{spanLabel(interval.node_interval)} bp · {label(interval)}</h4>
    {interval.status === 'ambiguous' && <p>Candidate origins: {interval.candidate_reference_ids.map(id => reference(id)?.name ?? id).join(', ')}. Matching evidence does not assign a unique origin.</p>}
    {interval.status === 'unresolved' && <p>No saved node-to-reference match supports this interval.</p>}
    {rows.length > 0 && <div className="table-scroll" role="region" aria-label="Matching interval evidence" tabIndex="0"><table><thead><tr><th scope="col">Reference</th><th scope="col">Node match (bp)</th><th scope="col">Reference match (bp)</th><th scope="col">Strand</th><th scope="col">Recorded quality</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{reference(row.reference_id)?.name ?? row.reference_id}<small>{row.reference_id}</small></td><td>{spanLabel(row.node_interval)}</td><td>{spanLabel(row.reference_interval)}</td><td>{row.strand}</td><td>{Object.entries(row.match_quality).map(([key,value])=>`${key}: ${value}`).join('; ')}</td></tr>)}</tbody></table></div>}
    {rows.length > 0 && <p className="muted">Rows retain their original spans; a selected chunk may be part of a longer match.</p>}
    <details><summary>Interval evidence source</summary><p>{saved.source.name}</p><code className="checksum">{saved.source.sha256}</code></details>
  </section>;
}
