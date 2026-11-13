import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const [input,output]=process.argv.slice(2),root=resolve(input);await mkdir(output,{recursive:true});
const server=createServer(async(req,res)=>{try{let path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));if(path!==root&&!path.startsWith(root+'/'))throw Error('escape');if((await stat(path)).isDirectory())path=resolve(path,'index.html');const types={'.html':'text/html','.css':'text/css','.js':'application/javascript','.svg':'image/svg+xml','.json':'application/json','.woff2':'font/woff2','.tsv':'text/tab-separated-values'};res.setHeader('Content-Type',types[extname(path)]||'application/octet-stream');res.end(await readFile(path));}catch{res.writeHead(404);res.end('missing')}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})}),checks=[];
try{
 const catalogue=JSON.parse(await readFile(resolve(root,'catalogue.json'),'utf8'));let first=catalogue.results[0];for(const entry of catalogue.results){const r=JSON.parse(await readFile(resolve(root,entry.record),'utf8'));if(Object.values(r.artifacts||{}).some(a=>a.role==='graph_model')){first=entry;break;}}
 const collection=Object.keys(catalogue.collections).find(k=>k==='mixed')||Object.keys(catalogue.collections)[0];
 for(const [device,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]])for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport,colorScheme:theme}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(value=>localStorage.setItem('gx-theme',value),theme);
  for(const [name,path] of [['home','/index.html'],['comparison','/broad/'+collection+'.html'],['detail','/'+first.report]]){
   const response=await page.goto(base+path,{waitUntil:'networkidle'});if(response.status()!==200)throw Error('Unavailable '+path);
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);if(overflow)console.log('OVERFLOW',device,path,await page.evaluate(()=>[...document.querySelectorAll('main > *, .filters > *, .plot-grid > *, .table-scroll')].map(n=>({tag:n.tagName,cls:n.className,x:n.getBoundingClientRect().x,width:n.getBoundingClientRect().width})).filter(r=>r.x+r.width>innerWidth+1)));
   for(const url of await page.locator('a[href$=".tsv"],a[href$=".json"],img[src]').evaluateAll(nodes=>nodes.map(n=>n.href||n.src))){const r=await page.request.get(url);if(r.status()!==200)throw Error('Missing artifact '+url);}
   if(name==='comparison'){
    const search=page.getByLabel('Search cases',{exact:true});await search.fill('NO_MATCH_FIXTURE_ef51');if(await page.locator('tbody tr[data-result-id]:visible').count())throw Error('Search filter failed');await search.fill('');
    await page.getByLabel('Read technology',{exact:true}).selectOption('short');const values=await page.locator('tbody tr[data-result-id]:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.technology));if(values.some(v=>v!=='short'))throw Error('Technology filter failed');await page.getByLabel('Read technology',{exact:true}).selectOption('');
    await page.getByLabel('Data source',{exact:true}).selectOption('real');const sources=await page.locator('tbody tr[data-result-id]:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.source));if(sources.some(v=>v!=='real'))throw Error('Source filter failed');await page.getByLabel('Data source',{exact:true}).selectOption('');
   }
   if(name==='detail'&&await page.locator('[data-graph]').count()){await page.getByRole('button',{name:'Zoom in',exact:true}).click();if(!(await page.locator('[data-graph-transform]').getAttribute('transform')).includes('1.3'))throw Error('Graph zoom failed');await page.getByRole('button',{name:'Fit graph',exact:true}).click();}
   await page.screenshot({path:resolve(output,device+'-'+theme+'-'+name+'.png'),fullPage:true});checks.push({device,theme,route:path,status:response.status(),overflow,errors:[...errors]});
  }
  await page.close();
 }
}finally{await browser.close();await new Promise(r=>server.close(r));}
await writeFile(resolve(output,'qa.json'),JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));if(checks.some(c=>c.errors.length||c.overflow))process.exitCode=1;
