import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const baseDir=process.argv[2],output=process.argv[3];
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
const records=[];
for(const cohort of process.argv.slice(4)) {
 const root=resolve(baseDir,cohort);
 const server=createServer(async(req,res)=>{try {
   let path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
   if(path!==root&&!path.startsWith(root+'/'))throw Error('escaped');
   if((await stat(path)).isDirectory())path=resolve(path,'index.html');
   const types={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.tsv':'text/tab-separated-values'};
   res.setHeader('Content-Type',types[extname(path)]||'application/octet-stream');res.end(await readFile(path));
 } catch {res.writeHead(404);res.end('missing');}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port;
 for(const [label,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
   const page=await browser.newPage({viewport});const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   let exampleResult=null;
   const routes=['/index.html',cohort==='read-order'?'/scenarios/s7.html':cohort==='quick'?'/simulated.html':cohort==='linear'?'/scenarios/s5.html':'/performance.html'];
   if(cohort==='general')routes.push('/aggregate.html');
   for(const [index,route] of routes.entries()) {
      const response=await page.goto(base+route,{waitUntil:'networkidle'});
      if(response.status()!==200)throw Error(route+' '+response.status());
      if(!exampleResult && await page.locator('a[href^="/results/"]').count())exampleResult=await page.locator('a[href^="/results/"]').first().getAttribute('href');
      const downloads=await page.locator('a[href$=".tsv"]').evaluateAll(nodes=>nodes.map(n=>n.href));
      for(const link of new Set(downloads)){ const fetched=await page.request.get(link); if(fetched.status()!==200 || !(await fetched.body()).length)throw Error('Failed TSV download: '+link); }
      const figures=await page.locator('img[src]').evaluateAll(nodes=>nodes.map(n=>n.src));
      for(const link of new Set(figures)){ const fetched=await page.request.get(link); if(fetched.status()!==200 || !(await fetched.body()).length)throw Error('Failed figure: '+link); }
      const wide=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
      records.push({cohort,viewport:label,route,status:response.status(),overflow:wide.scroll>wide.viewport+1,dimensions:wide,errors:[...errors],tsvDownloads:downloads.length,figures:figures.length});
      await page.screenshot({path:resolve(output,`${cohort}-${label}-${index}.png`),fullPage:true});
   }
   const href=exampleResult;
   if(!href)throw Error('No execution detail link in cohort '+cohort);
   const response=await page.goto(base+href,{waitUntil:'networkidle'});
   const graphs=await page.locator('[data-assembly-graph]').count();
   const rendered=await page.locator('svg.graph-canvas').count();
   if(rendered){ await page.getByRole('button',{name:'Zoom in',exact:true}).first().click(); await page.getByRole('button',{name:'Fit graph',exact:true}).first().click(); }
   const artifacts=await page.locator('a[href$=".tsv"],img[src]').evaluateAll(nodes=>nodes.map(n=>n.href||n.src));
   for(const link of new Set(artifacts)){ const fetched=await page.request.get(link); if(fetched.status()!==200 || !(await fetched.body()).length)throw Error('Failed result artifact: '+link); }
   const resultWidth=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
   records.push({cohort,viewport:label,overflow:resultWidth.scroll>resultWidth.viewport+1,route:href,status:response.status(),graphs,renderedGraphs:rendered,errors:[...errors]});
   await page.screenshot({path:resolve(output,`${cohort}-${label}-result.png`),fullPage:true});
   await page.close();
 }
 await new Promise(r=>server.close(r));
}
await browser.close();
await writeFile(resolve(output,'qa.json'),JSON.stringify(records,null,2));
console.log(JSON.stringify(records));
if(records.some(r=>r.errors.length||r.status!==200||r.overflow||(r.graphs&&!r.renderedGraphs)))process.exitCode=1;
