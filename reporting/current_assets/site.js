(() => {
  const root=document.documentElement,toggle=document.querySelector('[data-theme-toggle]');
  const theme=()=>root.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  function label(){if(toggle)toggle.textContent=theme()==='dark'?'Light theme':'Dark theme';}
  label();toggle?.addEventListener('click',()=>{root.dataset.theme=theme()==='dark'?'light':'dark';try{localStorage.setItem('gx-theme',root.dataset.theme)}catch{}label();});
  for(const section of document.querySelectorAll('[data-comparison]')){
    const rows=[...section.querySelectorAll('tbody tr[data-result-id]')],controls=[...section.querySelectorAll('[data-filter]')];
    const points=[...section.querySelectorAll('[data-plot-result]')],count=section.querySelector('[data-result-count]'),empty=section.querySelector('.empty-filter');
    let page=0;const pageSize=25;
    const pagination=document.createElement('div');pagination.className='table-pagination';
    const previous=document.createElement('button'),next=document.createElement('button'),pageLabel=document.createElement('p');
    previous.type=next.type='button';previous.textContent='Previous';next.textContent='Next';pageLabel.setAttribute('aria-live','polite');
    pagination.append(previous,pageLabel,next);section.querySelector('.table-scroll')?.after(pagination);
    function filter(reset=true){
      if(reset)page=0;
      const selections=Object.fromEntries(controls.map(c=>[c.dataset.filter,c.value.toLowerCase()]));
      const matching=rows.filter(row=>Object.entries(selections).every(([key,value])=>!value||(key==='search'?row.dataset.search.includes(value):row.dataset[key]===value)));
      page=Math.min(page,Math.max(0,Math.ceil(matching.length/pageSize)-1));const shown=new Set(matching.slice(page*pageSize,(page+1)*pageSize));
      const visibleIds=new Set(matching.map(row=>row.dataset.resultId));
      for(const row of rows)row.hidden=!shown.has(row);
      for(const point of points)point.classList.toggle('filtered-out',!visibleIds.has(point.dataset.plotResult));
      for(const figure of section.querySelectorAll('.metric-plot')){const blank=figure.querySelector('.plot-empty');if(blank)blank.hidden=[...figure.querySelectorAll('[data-plot-result]')].some(p=>!p.classList.contains('filtered-out'));}
      if(count)count.textContent=matching.length+' of '+rows.length+' current results';
      if(empty)empty.hidden=matching.length>0;
      pagination.hidden=matching.length<=pageSize;previous.disabled=page===0;next.disabled=(page+1)*pageSize>=matching.length;
      pageLabel.textContent='Rows '+(matching.length?page*pageSize+1:0)+'–'+Math.min((page+1)*pageSize,matching.length)+' of '+matching.length;
    }
    for(const control of controls)control.addEventListener(control.tagName==='INPUT'?'input':'change',()=>filter());
    previous.addEventListener('click',()=>{page--;filter(false)});next.addEventListener('click',()=>{page++;filter(false)});filter();
  }
  for(const graph of document.querySelectorAll('[data-graph]')){
    const svg=graph.querySelector('svg'),group=graph.querySelector('[data-graph-transform]'),select=graph.querySelector('[data-graph-select]');
    let scale=1,x=0,y=0,drag=null;
    function draw(){const v=svg.viewBox.baseVal,cx=v.width/2,cy=v.height/2;group?.setAttribute('transform',`translate(${x} ${y}) translate(${cx} ${cy}) scale(${scale}) translate(${-cx} ${-cy})`);}
    for(const button of graph.querySelectorAll('[data-graph-action]'))button.addEventListener('click',()=>{
      if(button.dataset.graphAction==='reset'){scale=1;x=y=0;}else scale=Math.max(.2,Math.min(10,scale*(button.dataset.graphAction==='in'?1.3:1/1.3)));draw();
    });
    select?.addEventListener('change',()=>{for(const node of graph.querySelectorAll('[data-node-id]'))node.classList.toggle('selected',!!select.value&&node.dataset.nodeId===select.value);});
    svg?.addEventListener('pointerdown',event=>{drag={px:event.clientX,py:event.clientY,x,y};svg.setPointerCapture(event.pointerId);});
    svg?.addEventListener('pointermove',event=>{if(!drag)return;const box=svg.getBoundingClientRect();x=drag.x+(event.clientX-drag.px)*svg.viewBox.baseVal.width/box.width;y=drag.y+(event.clientY-drag.py)*svg.viewBox.baseVal.height/box.height;draw();});
    svg?.addEventListener('pointerup',()=>{drag=null});svg?.addEventListener('pointercancel',()=>{drag=null});
  }
})();
