import React, { useId, useMemo, useRef, useState } from 'react';
import { Alert, StatusBadge } from '@genomicx/ui';
import './graph.css';
import { OriginEvidence, originEvidenceClass, originLabels, originShortLabels, nodeOriginChunks } from './origin-evidence.jsx';
export { originEvidenceClass, nodeOriginChunks } from './origin-evidence.jsx';

export const GRAPH_LIMITS = { segments: 5000, links: 5000, bytes: 20 * 1024 * 1024 };

// Local inspection deliberately retains topology metadata only, never segment bases.
export function parseLocalGfa(text, source = {}) {
  if (/[^\x00-\x7f]/.test(text)) throw Error("GFA1 metadata must contain ASCII only.");
  const nodes = [], edges = [], paths = [], seen = new Set(), pathNames = new Set(), warnings = new Set();
  let pathSteps = 0;
  const validId = id => Boolean(id && id.length <= 256 && !/^[*=]|\s|[\x00-\x20]|\+,|-,/.test(id));
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line || line.startsWith('#')) continue;
    const fields = line.split('\t'), type = fields[0];
    if (type === 'H') {
      if (fields.some(value => /^VN:Z:2/.test(value))) throw Error('GFA2 is not supported by this local inspector. Use a GFA1 file.');
    } else if (type === 'S') {
      const id = fields[1], sequence = fields[2];
      if (!validId(id) || seen.has(id) || pathNames.has(id) || !sequence) throw Error(`Invalid or duplicate segment on line ${index + 1}.`);
      if (sequence !== '*' && !/^[A-Za-z=.]+$/.test(sequence)) throw Error(`Unsupported GFA1 segment on line ${index + 1}.`);
      const lengthTag = fields.slice(3).find(value => /^LN:i:\d+$/.test(value));
      const taggedLength = lengthTag ? Number(lengthTag.slice(5)) : null;
      if (taggedLength !== null && (!Number.isSafeInteger(taggedLength) || taggedLength < 0)) throw Error(`Unsupported LN length on line ${index + 1}.`);
      const length = sequence === '*' ? taggedLength : sequence.length;
      if (taggedLength !== null && sequence !== '*' && taggedLength !== length) throw Error(`Sequence and LN length disagree on line ${index + 1}.`);
      const coverage = Object.fromEntries(fields.slice(3).filter(value => /^(?:dp|DP|KC|RC):[if]:/.test(value)).map(value => [value.slice(0, 2), value.split(':').slice(2).join(':')]));
      nodes.push({ id, length_bp: length, reported_coverage_tags: coverage }); seen.add(id);
    } else if (type === 'L') {
      if (fields.length < 6 || !validId(fields[1]) || !validId(fields[3]) || !['+', '-'].includes(fields[2]) || !['+', '-'].includes(fields[4]) || !(fields[5] === '*' || /^(?:[0-9]+[MIDNSHPX=])+$/.test(fields[5]))) throw Error(`Invalid link on line ${index + 1}.`);
      edges.push({ source: fields[1], source_orientation: fields[2], target: fields[3], target_orientation: fields[4], overlap: fields[5], is_self_link: fields[1] === fields[3] });
    } else if (type === 'P') {
      if (!validId(fields[1]) || !fields[2] || fields[2] === "*" || fields[2].includes(";") || fields.length < 4 || seen.has(fields[1]) || pathNames.has(fields[1])) throw Error(`Invalid or unsupported path on line ${index + 1}.`);
      if (paths.length >= 1000 || fields[2].length > 50_000 * 257) throw Error("Path data exceed the local inspection limit; nothing was partially displayed.");
      const steps = fields[2].split(',').map(step => {
        if (++pathSteps > 50_000) throw Error("Path steps exceed the local inspection limit; nothing was partially displayed.");
        if (!/[+-]$/.test(step)) throw Error(`Unsupported path step on line ${index + 1}.`);
        return { segment: step.slice(0, -1), orientation: step.slice(-1) };
      });
      if (fields[3] !== '*' && (fields[3].split(',').length !== steps.length - 1 || fields[3].split(',').some(value => !/^(?:[0-9]+[MIDNSHPX=])+$/.test(value)))) throw Error(`Invalid path overlap list on line ${index + 1}.`);
      pathNames.add(fields[1]);
      paths.push({ id: fields[1], steps, overlaps: fields[3] ?? '*' });
    } else warnings.add(`Record type ${type || '(empty)'} is not drawn by this inspector.`);
    if (nodes.length > GRAPH_LIMITS.segments || edges.length > GRAPH_LIMITS.links) throw Error(`This inspector supports at most ${GRAPH_LIMITS.segments} segments and ${GRAPH_LIMITS.links} links. The file was not partially displayed.`);
  }
  if (!nodes.length) throw Error('No GFA1 segment records were found. No graph is displayed.');
  if (edges.some(edge => !seen.has(edge.source) || !seen.has(edge.target)) || paths.some(path => path.steps.some(step => !seen.has(step.segment)))) throw Error('A link or path refers to an unknown segment. No graph is displayed.');
  return { status: 'available', nodes, edges, paths, self_loop_segment_ids: [...new Set(edges.filter(edge => edge.is_self_link).map(edge => edge.source))], complete: !warnings.size,
    warnings: [...warnings], source: { ...source, kind: 'gfa', role: 'local inspection only; not benchmark provenance' } };
}

export function schematicLayout(nodes) {
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  return { width: Math.max(400, columns * 180 + 80), height: Math.max(300, Math.ceil(nodes.length / columns) * 140 + 80),
    positions: new Map(nodes.map((node, index) => [node.id, { x: 110 + index % columns * 180, y: 90 + Math.floor(index / columns) * 140 }])) };
}

// Bounded, deterministic springs/repulsion; all source records stay untouched.
// Large graphs retain the full inventory using the cheaper grid layout.
export function forceLayout(nodes, edges) {
  if (!nodes.length || nodes.length > 300) return { ...schematicLayout(nodes), mode: 'grid' };
  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const radius = Math.max(100, Math.sqrt(nodes.length) * 55);
  const points = nodes.map((_, i) => ({ x: nodes.length === 1 ? 0 : radius * Math.cos(i * 2 * Math.PI / nodes.length), y: nodes.length === 1 ? 0 : radius * Math.sin(i * 2 * Math.PI / nodes.length), vx: 0, vy: 0 }));
  const seen = new Set(), links = [];
  for (const edge of edges) {
    const a = index.get(edge.source), b = index.get(edge.target);
    if (a == null || b == null || a === b) continue;
    const key = [Math.min(a, b), Math.max(a, b)].join(':');
    if (!seen.has(key)) { seen.add(key); links.push([a, b]); }
  }
  for (let tick = 0; tick < 100; tick++) {
    const forces = points.map(p => ({ x: -p.x * .001, y: -p.y * .001 }));
    for (let a = 0; a < points.length; a++) for (let b = a + 1; b < points.length; b++) {
      const dx = points[b].x - points[a].x, dy = points[b].y - points[a].y;
      const distance = Math.max(1, Math.hypot(dx, dy)), force = Math.min(20, 28000 / (distance * distance));
      const x = dx / distance * force, y = dy / distance * force;
      forces[a].x -= x; forces[a].y -= y; forces[b].x += x; forces[b].y += y;
    }
    for (const [a, b] of links) {
      const dx = points[b].x - points[a].x, dy = points[b].y - points[a].y;
      const distance = Math.max(1, Math.hypot(dx, dy)), force = (distance - 170) * .025;
      const x = dx / distance * force, y = dy / distance * force;
      forces[a].x += x; forces[a].y += y; forces[b].x -= x; forces[b].y -= y;
    }
    points.forEach((p, i) => {
      p.vx = (p.vx + forces[i].x * .5) * .8; p.vy = (p.vy + forces[i].y * .5) * .8;
      const speed = Math.max(1, Math.hypot(p.vx, p.vy) / 12);
      p.x += p.vx / speed; p.y += p.vy / speed;
    });
  }
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const width = Math.max(400, maxX - minX + 200), height = Math.max(300, maxY - minY + 240);
  return { width, height, mode: 'force', positions: new Map(nodes.map((node, i) => [node.id, { x: points[i].x - (minX + maxX) / 2 + width / 2, y: points[i].y - (minY + maxY) / 2 + height / 2 + 15 }])) };
}

export function coverageDescription(tags) {
  if (Array.isArray(tags)) return tags.map(tag => `${tag.tag}=${tag.value} (${String(tag.meaning ?? 'reported tag').replaceAll('_', ' ')})`).join(', ');
  return Object.entries(tags ?? {}).map(([key, value]) => `${key}=${value}`).join(', ');
}

function edgePath(edge, positions) {
  const start = positions.get(edge.source), end = positions.get(edge.target);
  if (!start || !end) return '';
  if (edge.source === edge.target) return `M ${start.x - 30} ${start.y - 32} C ${start.x - 110} ${start.y - 105}, ${start.x + 110} ${start.y - 105}, ${start.x + 30} ${start.y - 32}`;
  const dx = end.x - start.x, dy = end.y - start.y;
  const boundary = 1 / Math.max(Math.abs(dx) / 68, Math.abs(dy) / 32);
  return `M ${start.x + dx * boundary} ${start.y + dy * boundary} L ${end.x - dx * boundary} ${end.y - dy * boundary}`;
}

export function GraphViewer({ artifact = {} }) {
  const [selected, setSelected] = useState(''), [view, setView] = useState(null), [showLabels, setShowLabels] = useState(true);
  const [selectedInterval, setSelectedInterval] = useState(0);
  const [movedNodes, setMovedNodes] = useState(new Map());
  const svg = useRef(null), pan = useRef(null), nodeDrag = useRef(null), suppressClick = useRef(false), marker = useId().replace(/:/g, '');
  const graph = artifact.graph ?? {}, nodes = graph.nodes ?? [], edges = graph.edges ?? [];
  const layout = useMemo(() => forceLayout(nodes, edges), [nodes, edges]);
  const positions = useMemo(() => new Map([...layout.positions, ...[...movedNodes].filter(([id]) => layout.positions.has(id))]), [layout, movedNodes]);
  const activeView = view ?? { x: 0, y: 0, width: layout.width, height: layout.height };
  const origins = artifact.reference_origins;
  const originFor = id => {
    const match = origins?.nodes?.[id];
    const kind = originEvidenceClass(match);
    const reference = match?.status === "supported" && kind !== "unresolved" ? origins.references.find(r => r.id === match.reference_id) : null;
    return { match, reference, kind };
  };
  const selectedOrigin = originFor(selected);
  const selectedNode = nodes.find(node => node.id === selected);
  const tooLarge = nodes.length > GRAPH_LIMITS.segments || edges.length > GRAPH_LIMITS.links;
  const ready = graph.status === 'available' && nodes.length > 0 && !tooLarge;
  const related = edges.filter(edge => edge.source === selected || edge.target === selected);
  function reset() { setView(null); setSelected(''); setMovedNodes(new Map()); }
  function fit() {
    if (!positions.size) return;
    const points = [...positions.values()], xs = points.map(p => p.x), ys = points.map(p => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const width = Math.max(400, maxX - minX + 200), height = Math.max(300, maxY - minY + 240);
    setView({ x: (minX + maxX - width) / 2, y: (minY + maxY - height) / 2 - 15, width, height });
  }
  function zoom(factor) {
    const width = Math.min(layout.width * 20, Math.max(80, activeView.width * factor)), ratio = width / activeView.width;
    setView({ x: activeView.x + activeView.width * (1 - ratio) / 2, y: activeView.y + activeView.height * (1 - ratio) / 2, width, height: activeView.height * ratio });
  }
  function select(id, intervalIndex = 0) {
    setSelected(id); setSelectedInterval(intervalIndex);
    if (!id) { setView(null); return; }
    const point = positions.get(id);
    if (point) {
      const width = Math.min(560, layout.width, Math.max(240, svg.current?.getBoundingClientRect().width ?? 560));
      const height = width * 360 / 560;
      setView({ x: point.x - width / 2, y: point.y - height / 2, width, height });
    }
  }
  function pointerDown(event) {
    if (event.button !== 0 || event.target.closest('[data-graph-node]')) return;
    pan.current = { clientX: event.clientX, clientY: event.clientY, view: activeView };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event) {
    if (nodeDrag.current) {
      const matrix = svg.current.getScreenCTM();
      if (!matrix) return;
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      const start = nodeDrag.current;
      if (Math.hypot(event.clientX - start.clientX, event.clientY - start.clientY) > 3) suppressClick.current = true;
      setMovedNodes(previous => new Map(previous).set(start.id, { x: point.x - start.offsetX, y: point.y - start.offsetY }));
      return;
    }
    if (!pan.current) return;
    const bounds = svg.current.getBoundingClientRect(), start = pan.current;
    if (!bounds.width || !bounds.height) return;
    setView({ ...start.view, x: start.view.x - (event.clientX - start.clientX) * start.view.width / bounds.width, y: start.view.y - (event.clientY - start.clientY) * start.view.height / bounds.height });
  }
  function dragNode(event, id) {
    if (event.button !== 0) return;
    event.stopPropagation();
    const matrix = svg.current.getScreenCTM();
    if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse()), position = positions.get(id);
    nodeDrag.current = { id, clientX: event.clientX, clientY: event.clientY, offsetX: point.x - position.x, offsetY: point.y - position.y };
    suppressClick.current = false; setSelected(id);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function endPointer() { pan.current = null; nodeDrag.current = null; }
  function keyboard(event) {
    if (['+', '='].includes(event.key)) { event.preventDefault(); zoom(.8); }
    if (event.key === '-') { event.preventDefault(); zoom(1.25); }
    const shifts = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (shifts[event.key]) { event.preventDefault(); const [x, y] = shifts[event.key]; setView({ ...activeView, x: activeView.x + x * activeView.width / 10, y: activeView.y + y * activeView.height / 10 }); }
  }
  return <div className="assembly-graph" role="region" aria-label="Assembly graph viewer">
    {!ready && <Alert variant="info">{tooLarge ? 'This graph exceeds the interactive display limit; no partial graph is drawn.' : graph.status === 'available' && !nodes.length ? 'The collected GFA contains no segment records. This is an empty recorded graph, not missing graph data.' : artifact.availability ? `${artifact.availability.title}. ${artifact.availability.description}` : artifact.reason || graph.reason || 'No assembly graph was collected for this result.'}</Alert>}
    {ready && <>
      <p><StatusBadge variant="info">Recorded GFA</StatusBadge> {nodes.length.toLocaleString()} segments · {edges.length.toLocaleString()} link records. Source: {graph.source?.filename ?? 'not recorded'}; role: {graph.source?.role ?? 'not recorded'}.</p>
      {graph.complete === false && <Alert variant="warning">The source graph includes unsupported or omitted records. This view is not a complete representation of the source file.</Alert>}
      {graph.warnings?.length > 0 && <details><summary>Graph parsing notes</summary><ul>{graph.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
      <><div className="origin-legend" aria-label="Reference colour key">{origins?.references?.map(reference => <span key={reference.id} style={{'--reference-colour':reference.colour,'--reference-light':reference.light_colour}}><i aria-hidden="true" />{reference.name}</span>)}<span><i aria-hidden="true" />Ambiguous / unassigned</span></div><p className="muted">Coloured portions show recorded reference support. Grey portions are ambiguous or have no recorded support; select a segment to inspect its evidence.</p></>
      <div className="graph-controls">
        <button className="gx-btn gx-btn-secondary gx-btn-sm" onClick={() => zoom(.8)}>Zoom in</button>
        <button className="gx-btn gx-btn-secondary gx-btn-sm" onClick={() => zoom(1.25)}>Zoom out</button>
        <button className="gx-btn gx-btn-secondary gx-btn-sm" onClick={fit}>Fit graph</button>
        <button className="gx-btn gx-btn-secondary gx-btn-sm" onClick={reset}>Reset layout</button>
        <label>Select segment<select className="gx-input" value={selected} onChange={event => select(event.target.value)}><option value="">Whole graph</option>{nodes.map(node => <option key={node.id} value={node.id}>{node.id}</option>)}</select></label>
        <label className="graph-checkbox"><input type="checkbox" checked={showLabels} onChange={event => setShowLabels(event.target.checked)} /> Show labels</label>
      </div>
      <p className="muted">{layout.mode === 'force' ? 'Force-directed layout.' : 'Grid layout for large graphs.'} Drag segments to rearrange; drag the background to pan.</p>
      <svg ref={svg} className="graph-canvas" viewBox={`${activeView.x} ${activeView.y} ${activeView.width} ${activeView.height}`} role="group" aria-label="Schematic GFA topology" tabIndex="0" onKeyDown={keyboard} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={endPointer} onPointerCancel={endPointer}>
        <defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="currentColor" /></marker></defs>
        {edges.map((edge, index) => <path key={index} className={`graph-edge ${selected && (edge.source === selected || edge.target === selected) ? 'selected' : ''}`} d={edgePath(edge, positions)} markerEnd={`url(#${marker})`}><title>{`${edge.source}${edge.source_orientation} → ${edge.target}${edge.target_orientation}; overlap ${edge.overlap}`}</title></path>)}
        {nodes.map(node => { const point = positions.get(node.id); const origin = originFor(node.id); return <g key={node.id} className={`graph-node ${node.id === selected ? 'selected' : ''}`} style={{'--reference-colour':origin.reference?.colour,'--reference-light':origin.reference?.light_colour}} data-graph-node={node.id} role="button" tabIndex="0" aria-label={`Segment ${node.id}; ${node.length_bp == null ? 'length unknown' : `${node.length_bp} bases`}; ${nodeOriginChunks(node.id, origins).length ? "recorded internal origin intervals" : origin.reference?.name ?? "origin unresolved"}; ${nodeOriginChunks(node.id, origins).length ? "select a portion to inspect evidence" : originLabels[origin.kind]}`} aria-pressed={node.id === selected} onPointerDown={event => dragNode(event, node.id)} onClick={() => { if (suppressClick.current) { suppressClick.current = false; return; } select(node.id); }} onKeyDown={event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); event.stopPropagation(); select(node.id); } }}>
          <rect x={point.x - 58} y={point.y - 30} width="116" height="64" rx="4" />
          {nodeOriginChunks(node.id, origins).length ? nodeOriginChunks(node.id, origins).map((chunk, index) => {
            const ref = chunk.status === 'supported' ? origins.references.find(r => r.id === chunk.reference_id) : null;
            const length = origins.node_intervals[node.id].length_bp;
            return <rect key={index} className="node-origin-chunk" x={point.x - 54 + 108 * chunk.node_interval[0] / length} y={point.y + 24} width={108 * (chunk.node_interval[1]-chunk.node_interval[0]) / length} height="6" style={{'--reference-colour':ref?.colour ?? '#92969d','--reference-light':ref?.light_colour ?? '#686c73'}} onPointerDown={event => {event.stopPropagation(); suppressClick.current=false;}} onClick={event => {event.stopPropagation(); if (suppressClick.current) {suppressClick.current=false; return;} select(node.id, index);}}><title>{`${chunk.node_interval.join('–')} bp · ${ref?.name ?? (chunk.status === 'ambiguous' ? 'Ambiguous' : 'No recorded support')}`}</title></rect>;
          }) : <rect className="origin-strip" x={point.x - 54} y={point.y + 24} width="108" height="6" rx="1" />}
          {showLabels && <text x={point.x} y={point.y - 13} textAnchor="middle">{node.id.length > 16 ? node.id.slice(0, 14) + '…' : node.id}</text>}
          {showLabels && <text className="origin-node-label" x={point.x} y={point.y + 1} textAnchor="middle">{(nodeOriginChunks(node.id, origins).length ? "Recorded intervals" : origin.reference?.name ?? "Unresolved").slice(0,18)}</text>}
          {showLabels && <text className="origin-node-evidence" x={point.x} y={point.y + 15} textAnchor="middle">{nodeOriginChunks(node.id, origins).length ? "Select a portion" : originShortLabels[origin.kind]}</text>}
          <title>{`${node.id}; ${node.length_bp == null ? 'length unknown' : node.length_bp + ' bp'}`}</title>
        </g>; })}
      </svg>
      {selectedNode && <div className="graph-selection" aria-live="polite"><h3>Segment {selectedNode.id}</h3><p>Length: {selectedNode.length_bp == null ? 'not reported' : `${selectedNode.length_bp.toLocaleString()} bp`}. Recorded GFA coverage/count tags: {coverageDescription(selectedNode.reported_coverage_tags) || 'none collected'}.</p>
        <OriginEvidence origin={selectedOrigin} node={selectedNode} origins={origins} selectedInterval={selectedInterval} onSelectInterval={setSelectedInterval} />
        <p>{graph.self_loop_segment_ids?.includes(selectedNode.id) ? 'An explicit GFA self-link was recorded for this segment.' : 'No explicit GFA self-link was recorded for this segment.'}</p>
        <details open><summary>Incident link records ({related.length})</summary>{related.length ? <ul>{related.map((edge, index) => <li key={index}><code>{edge.source}{edge.source_orientation} → {edge.target}{edge.target_orientation}</code>; overlap {edge.overlap}</li>)}</ul> : <p>No incident link records.</p>}</details>
      </div>}
      {graph.paths?.length > 0 && <details><summary>Recorded GFA paths ({graph.paths.length})</summary><ul>{graph.paths.map((path, index) => <li key={index}><strong>{path.id}</strong>: <code>{path.steps.map(step => step.segment + step.orientation).join(', ')}</code></li>)}</ul></details>}
    </>}
  </div>;
}
