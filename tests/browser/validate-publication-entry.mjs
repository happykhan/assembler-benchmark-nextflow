import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const [input,output]=process.argv.slice(2),base=input.replace(/\/$/,'');await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});const checks=[];
try{
 for(const [device,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]])for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport,colorScheme:theme}),errors=[];page.on('pageerror',error=>errors.push(error.message));await page.addInitScript(t=>localStorage.setItem('gx-theme',t),theme);
  await page.goto(base+'/',{waitUntil:'networkidle'});
  const entry=page.locator('#nextflow-pilot-entry');await entry.waitFor({state:'visible'});
  if(!(await entry.innerText()).includes('Not a full panel'))throw Error('Homepage pilot scope missing');
  if(!(await page.locator('main').innerText()).includes('200 of 200 results recorded'))throw Error('Established benchmark summary missing');
  await page.screenshot({path:resolve(output,device+'-'+theme+'-entry.png'),fullPage:true});
  await entry.getByRole('link',{name:'Nextflow pilot reports',exact:true}).click();await page.waitForLoadState('networkidle');
  const notice=page.locator('.pilot-notice');await notice.waitFor({state:'visible'});
  if(!(await notice.innerText()).includes('7 measured results')||!(await notice.innerText()).includes('3 inputs'))throw Error('Pilot totals missing');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  await page.screenshot({path:resolve(output,device+'-'+theme+'-pilot.png'),fullPage:true});checks.push({device,theme,url:page.url(),overflow,errors});await page.close();
 }
}finally{await browser.close();}
await writeFile(resolve(output,'qa.json'),JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));if(checks.some(x=>x.overflow||x.errors.length))process.exitCode=1;
