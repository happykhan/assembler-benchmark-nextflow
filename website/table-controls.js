// Progressive enhancement: rows and result links remain usable without JavaScript.
const collator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
export function compareTableValues(a, b, direction = 1) {
  const missing = value => !value || /^(not recorded|not measured|not reported|not available|not collected|unknown|—)$/i.test(value);
  if (missing(a) !== missing(b)) return missing(a) ? 1 : -1;
  const numeric = value => /^-?[\d,.]+(?:\s*(?:bp|s))?$/.test(value.trim()) ? Number(value.replaceAll(',', '').replace(/\s*(bp|s)$/, '')) : null;
  const x = numeric(a), y = numeric(b);
  return direction * (x !== null && y !== null ? x - y : collator.compare(a, b));
}
export function matchesTableFilters(text, values, query, filters) {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return terms.every(term => text.toLocaleLowerCase().includes(term)) && Object.entries(filters).every(([key, value]) => !value || values[key] === value);
}
const layouts = {
  'performance-runs': {label:'General performance results', filters:[['dataset','Dataset',0],['assembler','Assembler',1],['completion','Completion',2]]},
  'performance-inputs': {label:'Broad input datasets', filters:[['organism','Organism',1],['plasmids','Plasmid count',2]]},
  runs: {label:'Individual runs', filters:[['genome','Genome',0],['assembler','Assembler',1],['status','Exact status',3],['threads','Threads',2]]},
  case: {label:'Runs for this case', filters:[['assembler','Assembler',0],['status','Exact status',2],['threads','Threads',1]]},
  contigs: {label:'Output contigs', minimum:8, filters:[['origin','Reference origin',1],['topology','Reported circularity',3]]},
  lengths: {label:'Individual lengths', minimum:8, filters:[]},
  repeats: {label:'Repeatability groups', filters:[['assembler','Assembler',1],['mode','Mode',2],['threads','Threads',3]]},
};
function cellText(cell) {
  if (!cell) return '';
  const copy = cell.cloneNode(true);
  copy.querySelectorAll('small,details').forEach(item => item.remove());
  return copy.textContent.replace(/\s+/g, ' ').trim();
}
export function enhanceTables(root = document) {
  let ordinal = 0;
  for (const table of root.querySelectorAll('table[data-table-kind]')) {
    if (table.dataset.enhanced) continue;
    const config = layouts[table.dataset.tableKind];
    const body = table.tBodies[0];
    const rows = [...(body?.rows ?? [])].filter(row => !row.querySelector('[colspan]'));
    if (!config || rows.length < (config.minimum ?? 1)) continue;
    table.dataset.enhanced = 'true';
    const id = `table-controls-${++ordinal}`;
    if (!table.id) table.id = `${id}-table`;
    const controls = document.createElement('div'); controls.className = 'table-controls';
    controls.setAttribute('role','group'); controls.setAttribute('aria-label',`${config.label} controls`);
    const records = rows.map((row,index) => ({row,index,text:row.textContent,sortValues:[...row.cells].map(cell=>cell.textContent.replace(/\s+/g,' ').trim()),values:Object.fromEntries(config.filters.map(([key,,column]) => {
      let value = cellText(row.cells[column]);
      if (key === 'threads') value = value.match(/^\d+/)?.[0] ?? 'Not recorded';
      if (key === 'topology') value = value.split(' (')[0];
      return [key,value];
    }))}));
    function field(label, input, name) {
      const wrapper = document.createElement('label'); wrapper.textContent = label;
      input.id = `${id}-${name}`; input.className = 'gx-input'; input.setAttribute('aria-controls',table.id);
      wrapper.append(input); controls.append(wrapper); return input;
    }
    const search = field('Search',document.createElement('input'),'search'); search.type='search'; search.placeholder='Search this table';
    const filters = {};
    for (const [key,label] of config.filters) {
      const choices = [...new Set(records.map(record=>record.values[key]))].sort(collator.compare);
      if (choices.length < 2) continue;
      const select = field(label,document.createElement('select'),key);
      for (const [value,text] of [['','All'],...choices.map(value=>[value,value])]) {const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
      filters[key]=select;
    }
    const reset=document.createElement('button');reset.type='button';reset.className='gx-btn gx-btn-secondary gx-btn-sm';reset.textContent='Reset';controls.append(reset);
    const count=document.createElement('p');count.className='table-result-count';count.setAttribute('role','status');
    const empty=document.createElement('p');empty.className='table-empty';empty.textContent='No rows match. Change the search or reset the filters.';empty.hidden=true;
    const scroll=table.closest('.table-scroll') ?? table;scroll.before(controls,count,empty);
    let sortColumn=null,sortDirection=1;
    const heads=[...(table.tHead?.rows[0]?.cells ?? [])];
    const buttons=[];
    heads.forEach((head,column) => {
      if (/^(result|view)$/i.test(head.textContent.trim())) return;
      const label=head.textContent.trim();const button=document.createElement('button');button.type='button';button.className='table-sort';button.textContent=label;
      const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 12 14');icon.setAttribute('aria-hidden','true');
      const path=document.createElementNS(icon.namespaceURI,'path');path.setAttribute('d','M3 6 6 3 9 6 M3 9 6 12 9 9');icon.append(path);button.append(icon);
      button.setAttribute('aria-label',`${label}: sort ascending`);head.replaceChildren(button);head.setAttribute('aria-sort','none');buttons.push([head,button,label,column]);
      button.addEventListener('click',()=>{sortDirection=sortColumn===column?-sortDirection:1;sortColumn=column;apply();});
    });
    function apply() {
      const selected=Object.fromEntries(Object.entries(filters).map(([key,select])=>[key,select.value]));let shown=0;
      const ordered=[...records].sort((a,b)=>sortColumn===null?a.index-b.index:compareTableValues(a.sortValues[sortColumn],b.sortValues[sortColumn],sortDirection)||a.index-b.index);
      for(const record of ordered){record.row.hidden=!matchesTableFilters(record.text,record.values,search.value,selected);if(!record.row.hidden)shown++;body.append(record.row);}
      count.textContent=`${shown.toLocaleString()} of ${records.length.toLocaleString()} rows`;empty.hidden=shown>0;
      for(const [head,button,label,column] of buttons){head.setAttribute('aria-sort',sortColumn===column?(sortDirection===1?'ascending':'descending'):'none');button.setAttribute('aria-label',`${label}: sort ${sortColumn===column&&sortDirection===1?'descending':'ascending'}`);}
    }
    search.addEventListener('input',apply);Object.values(filters).forEach(select=>select.addEventListener('change',apply));
    reset.addEventListener('click',()=>{search.value='';Object.values(filters).forEach(select=>select.value='');sortColumn=null;sortDirection=1;apply();});
    apply();
  }
}
