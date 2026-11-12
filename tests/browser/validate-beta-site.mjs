import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const [source,output]=process.argv.slice(2);
await mkdir(output,{recursive:true});
let server=null,base=source;
if(!source.startsWith('https://')&&!source.startsWith('http://')){
 const root=resolve(source);
 server=createServer(async(req,res)=>{try{
   let path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));
   if(path!==root&&!path.startsWith(root+'/'))throw Error('escape');
   if((await stat(path)).isDirectory())path=resolve(path,'index.html');
   const types={'.html':'text/html','.css':'text/css','.js':'application/javascript','.svg':'image/svg+xml','.tsv':'text/tab-separated-values','.json':'application/json'};
   res.setHeader('Content-Type',types[extname(path)]||'application/octet-stream');res.end(await readFile(path));
 }catch{res.writeHead(404);res.end('Missing');}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port;
}
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const results=[];
try{
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const response=await page.goto(base+'/beta/',{waitUntil:'networkidle'});
  if(response.status()!==200)throw Error('Beta page unavailable');
  const count=await page.locator('#beta-rows tr').count();if(!count)throw Error('No beta outcomes');
  const downloads=await page.locator('a[href$=".tsv"],a[href$=".json"]').evaluateAll(a=>a.map(n=>n.href));
  for(const link of downloads){const r=await page.request.get(link);if(r.status()!==200||!(await r.body()).length)throw Error('Broken download '+link);}
  const figure=await page.request.get(base+'/beta/contiguity.svg');if(figure.status()!==200)throw Error('Missing figure');
  await page.getByLabel('Search',{exact:true}).fill('NO_MATCH_TEST_7ef0');
  if(await page.locator('#beta-rows tr:visible').count())throw Error('Search filter failed');
  await page.getByLabel('Search',{exact:true}).fill('');
  await page.getByLabel('Scenario',{exact:true}).selectOption('plasmids');
  const groups=await page.locator('#beta-rows tr:visible').evaluateAll(a=>a.map(n=>n.dataset.groups));
  if(groups.some(g=>!g.split(',').includes('plasmids')))throw Error('Group filter failed');
  await page.getByLabel('Scenario',{exact:true}).selectOption('');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  await page.screenshot({path:resolve(output,`beta-${name}.png`),fullPage:true});
  await page.goto(base+'/index.html',{waitUntil:'networkidle'});
  if(!await page.locator('a[href="/beta/"]').count())throw Error('No homepage beta link');
  results.push({viewport:name,status:response.status(),outcomes:count,downloads:downloads.length,search:true,group_filter:true,overflow,errors});
  await page.close();
 }
}finally{await browser.close();if(server)await new Promise(r=>server.close(r));}
await writeFile(resolve(output,'qa.json'),JSON.stringify(results,null,2));
console.log(JSON.stringify(results));
if(results.some(r=>r.overflow||r.errors.length))process.exitCode=1;
