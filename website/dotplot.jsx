import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, FileUpload, StatusBadge } from '@genomicx/ui';

export function parseNucmerCoords(text) {
  const alignments = [], references = new Map(), queries = new Map();
  let referenceTotal = 0, queryTotal = 0;
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line.trim() || line.startsWith('#')) continue;
    const fields = line.trim().split('\t');
    if (fields.length !== 11) throw Error(`Line ${index + 1}: expected the 11 tab-separated fields from show-coords -THrl.`);
    const values = fields.slice(0, 9).map(Number);
    const [r1, r2, q1, q2, spanR, spanQ, identity, lengthR, lengthQ] = values;
    const [reference, query] = fields.slice(9);
    if (fields.slice(0,9).some(value=>!value.trim()) || !values.every(Number.isFinite) || ![r1,r2,q1,q2,spanR,spanQ,lengthR,lengthQ].every(v => Number.isSafeInteger(v) && v > 0) || identity < 0 || identity > 100 || Math.max(r1,r2) > lengthR || Math.max(q1,q2) > lengthQ || !reference || !query || reference.length > 256 || query.length > 256) throw Error(`Line ${index + 1}: invalid coordinates, lengths or identifiers.`);
    for (const [inventory, name, length] of [[references,reference,lengthR],[queries,query,lengthQ]]) {
      if (inventory.has(name) && inventory.get(name) !== length) throw Error(`Conflicting sequence lengths for ${name}.`);
      if (!inventory.has(name)) {
        const total = (inventory === references ? referenceTotal : queryTotal) + length;
        if (!Number.isSafeInteger(total)) throw Error('Axis lengths exceed the supported coordinate range.');
        if (inventory === references) referenceTotal = total; else queryTotal = total;
      }
      inventory.set(name, length);
      if (inventory.size > 5000) throw Error('The coordinate file exceeds the 5,000 sequences per axis display limit.');
    }
    alignments.push({reference,query,r1,r2,q1,q2,identity,reverse:(r2-r1)*(q2-q1)<0});
    if (alignments.length > 50000) throw Error('The file exceeds the 50,000 alignment display limit; no partial plot was loaded.');
  }
  if (!alignments.length) throw Error('No alignment rows found. No dot plot was loaded.');
  return {alignments,references:[...references].map(([id,length])=>({id,length})),queries:[...queries].map(([id,length])=>({id,length}))};
}

export function coordinateWindow(start, end, total) {
  const first = start === '' ? 1 : Number(start), last = end === '' ? total : Number(end);
  if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 1 || last > total || first >= last) return null;
  return {start:first-1,end:last,span:last-first+1};
}

function axis(items) {
  let total = 0;
  const offsets = new Map();
  for (const item of items) { offsets.set(item.id,total); total += item.length; }
  return {items,total,offsets};
}

export function NucmerDotPlot() {
  const [data,setData] = useState(null), [files,setFiles] = useState([]), [error,setError] = useState('');
  const [reference,setReference] = useState(''), [query,setQuery] = useState('');
  const [bounds,setBounds] = useState({x1:'',x2:'',y1:'',y2:''}), [page,setPage] = useState(0);
  const canvas = useRef(null);
  const x = useMemo(()=>axis((data?.references??[]).filter(r=>!reference||r.id===reference)),[data,reference]);
  const y = useMemo(()=>axis((data?.queries??[]).filter(r=>!query||r.id===query)),[data,query]);
  const rows = useMemo(()=>(data?.alignments??[]).filter(r=>(!reference||r.reference===reference)&&(!query||r.query===query)),[data,reference,query]);
  const windowX = coordinateWindow(bounds.x1,bounds.x2,x.total), windowY = coordinateWindow(bounds.y1,bounds.y2,y.total);
  const validWindow = windowX && windowY;
  function resetWindow() { setBounds({x1:'',x2:'',y1:'',y2:''}); setPage(0); }
  function focusRow(row) {
    setReference(row.reference); setQuery(row.query);
    setBounds({x1:String(Math.max(1,Math.min(row.r1,row.r2)-50)),x2:String(Math.min(data.references.find(r=>r.id===row.reference).length,Math.max(row.r1,row.r2)+50)),y1:String(Math.max(1,Math.min(row.q1,row.q2)-50)),y2:String(Math.min(data.queries.find(r=>r.id===row.query).length,Math.max(row.q1,row.q2)+50))});
    setPage(0);
  }
  useEffect(()=>{
    if (!canvas.current || !data || !validWindow) return;
    const element=canvas.current;
    function draw() {
      const width=Math.max(300,element.getBoundingClientRect().width), height=400, ratio=Math.min(devicePixelRatio||1,2);
      element.width=width*ratio; element.height=height*ratio;
      const context=element.getContext('2d'); context.scale(ratio,ratio);
      const style=getComputedStyle(element), ink=style.color, line=style.getPropertyValue('--gx-border');
      context.clearRect(0,0,width,height); context.strokeStyle=line; context.lineWidth=1;
      const left=58, top=20, plotWidth=width-80, plotHeight=height-85;
      context.strokeRect(left,top,plotWidth,plotHeight);
      const px=value=>left+(value-windowX.start)/windowX.span*plotWidth, py=value=>top+plotHeight-(value-windowY.start)/windowY.span*plotHeight;
      context.font=`11px ${style.fontFamily}`; context.fillStyle=ink;
      for (const [inventory,vertical] of [[x,false],[y,true]]) {
        for (const item of inventory.items) {
          const offset=inventory.offsets.get(item.id), range=vertical?windowY:windowX;
          if (offset+item.length <= range.start || offset >= range.end) continue;
          const middle=(Math.max(offset,range.start)+Math.min(offset+item.length,range.end))/2;
          context.strokeStyle=line; context.beginPath();
          if (vertical) {context.moveTo(left,py(offset));context.lineTo(left+plotWidth,py(offset));}
          else {context.moveTo(px(offset),top);context.lineTo(px(offset),top+plotHeight);}
          context.stroke();
          if (inventory.items.length <= 8) {
            const label=item.id.length>22?item.id.slice(0,20)+'…':item.id;
            if (vertical) {context.save();context.translate(45,py(middle));context.rotate(-Math.PI/2);context.textAlign='center';context.fillText(label,0,0);context.restore();}
            else {context.textAlign='center';context.fillText(label,px(middle),top+plotHeight+18);}
          }
        }
      }
      context.save(); context.beginPath(); context.rect(left,top,plotWidth,plotHeight); context.clip();
      context.lineWidth=1.2;
      for (const row of rows) {
        context.strokeStyle=row.reverse?'#cd812c':'#4f8ed0'; context.beginPath();
        context.moveTo(px(x.offsets.get(row.reference)+row.r1-1),py(y.offsets.get(row.query)+row.q1-1));
        context.lineTo(px(x.offsets.get(row.reference)+row.r2-1),py(y.offsets.get(row.query)+row.q2-1));context.stroke();
      }
      context.restore();
      context.fillStyle=ink; context.textAlign='center';
      context.fillText(`Reference · ${(windowX.start+1).toLocaleString()}–${windowX.end.toLocaleString()} bp`,left+plotWidth/2,height-12);
      context.save();context.translate(13,top+plotHeight/2);context.rotate(-Math.PI/2);context.fillText(`Query · ${(windowY.start+1).toLocaleString()}–${windowY.end.toLocaleString()} bp`,0,0);context.restore();
    }
    draw(); const observer=new ResizeObserver(draw); observer.observe(element);
    const theme=new MutationObserver(draw); theme.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    return ()=>{observer.disconnect();theme.disconnect();};
  },[data,x,y,rows,bounds]);
  async function openFiles(next) {
    setFiles(next);setError('');setData(null);setReference('');setQuery('');resetWindow();
    if (!next.length) return;
    try {
      if (next[0].size>20*1024*1024) throw Error('The coordinate file exceeds 20 MiB. Nothing was loaded.');
      setData(parseNucmerCoords(await next[0].text()));
    } catch (failure) {setError(failure.message);}
  }
  return <div className="nucmer-dotplot">
    <p>No benchmark NUCmer coordinate file has been collected for this result.</p>
    <details><summary>How are small differences shown?</summary><ul><li><strong>Large structure:</strong> a dot plot shows alignment orientation and placement.</li><li><strong>Small coordinate changes:</strong> isolate a reference/contig pair, narrow both axes, and inspect the recorded endpoints below the plot.</li><li><strong>Changed bases:</strong> substitutions, inserted/deleted bases and exact breakpoint sequences require separate base-level difference records. Those records have not been collected here. A straight line or rounded 100% identity does not establish an exact match.</li></ul></details>
    <p>Preview an existing <code>show-coords -THrl</code> table locally. The file stays in your browser and does not become benchmark evidence.</p>
    <FileUpload files={files} onFilesChange={openFiles} multiple={false} accept=".tsv,.coords,text/plain" label="Choose existing NUCmer coordinates" hint="11-column tab-separated coordinates; up to 20 MiB." />
    {error&&<Alert variant="error">{error}</Alert>}
    {data&&<><p><StatusBadge variant="warning">Local preview</StatusBadge> {rows.length.toLocaleString()} of {data.alignments.length.toLocaleString()} recorded alignments</p><div className="graph-controls">
      <label>Reference<select className="gx-input" value={reference} onChange={event=>{setReference(event.target.value);resetWindow();}}><option value="">All reference sequences</option>{data.references.map(r=><option key={r.id}>{r.id}</option>)}</select></label>
      <label>Query<select className="gx-input" value={query} onChange={event=>{setQuery(event.target.value);resetWindow();}}><option value="">All query sequences</option>{data.queries.map(r=><option key={r.id}>{r.id}</option>)}</select></label>
    </div><details open><summary>Inspect a coordinate window</summary><p className="muted">Enter 1-based inclusive positions on the displayed axes. With all sequences selected, positions use the cumulative axes. Select one sequence per axis to use its own coordinates.</p><div className="graph-controls">{[['x1','Reference start'],['x2','Reference end'],['y1','Query start'],['y2','Query end']].map(([key,label])=><label key={key}>{label}<input className="gx-input" type="number" min="1" step="1" value={bounds[key]} placeholder={key.endsWith('1')?'1':String(key.startsWith('x')?x.total:y.total)} onChange={event=>setBounds({...bounds,[key]:event.target.value})} /></label>)}<button className="gx-btn gx-btn-secondary gx-btn-sm" onClick={resetWindow}>Reset window</button></div></details>{!validWindow&&<Alert variant="error">Use integer coordinates within each axis, with start smaller than end.</Alert>}<canvas ref={canvas} className="dotplot-canvas" hidden={!validWindow} role="img" aria-label={`NUCmer coordinate dot plot, ${rows.length} alignments; reference on horizontal axis, query on vertical axis`} /><p className="muted">Blue: same orientation · orange: opposite orientation. Only sequences present in this file are shown. These coordinate spans do not show individual base differences.</p><details open><summary>Recorded alignment coordinates ({rows.length.toLocaleString()})</summary><p>Identity is the value recorded in the coordinate table. It is not a list of changed bases. Focus a row to inspect its alignment with 50 bp of context.</p><div className="table-scroll" role="region" aria-label="Alignment coordinates" tabIndex="0"><table><thead><tr>{['Reference','Reference interval','Query','Query interval','Identity','View'].map(label=><th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.slice(page*25,page*25+25).map((row,index)=><tr key={index}><td>{row.reference}</td><td>{row.r1.toLocaleString()}–{row.r2.toLocaleString()}</td><td>{row.query}</td><td>{row.q1.toLocaleString()}–{row.q2.toLocaleString()}</td><td>{row.identity}%</td><td><button className="gx-btn gx-btn-secondary gx-btn-sm" onClick={()=>focusRow(row)}>Focus alignment {page*25+index+1}</button></td></tr>)}</tbody></table></div><div className="graph-controls"><button className="gx-btn gx-btn-secondary gx-btn-sm" disabled={page===0} onClick={()=>setPage(page-1)}>Previous alignments</button><span>{rows.length ? page*25+1 : 0}–{Math.min(rows.length,page*25+25)} of {rows.length}</span><button className="gx-btn gx-btn-secondary gx-btn-sm" disabled={(page+1)*25>=rows.length} onClick={()=>setPage(page+1)}>Next alignments</button></div></details></>}
  </div>;
}
