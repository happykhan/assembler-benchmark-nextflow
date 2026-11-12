import assert from 'node:assert/strict';
import { build } from 'esbuild';
const {outputFiles}=await build({entryPoints:[new URL('./dotplot.jsx',import.meta.url).pathname],bundle:true,write:false,format:'esm',platform:'browser',jsx:'automatic',loader:{'.css':'empty'},define:{'process.env.NODE_ENV':'"production"'}});
const {parseNucmerCoords,coordinateWindow}=await import('data:text/javascript;base64,'+Buffer.from(outputFiles[0].contents).toString('base64'));
const fixture='1\t100\t1\t100\t100\t100\t100\t1000\t1000\ttoy-reference\ttoy-query\n101\t200\t400\t301\t100\t100\t99\t1000\t1000\ttoy-reference\ttoy-query\n';
const parsed=parseNucmerCoords(fixture);
assert.equal(parsed.alignments.length,2);
assert.deepEqual(parsed.alignments.map(r=>r.reverse),[false,true]);
assert.deepEqual(parsed.references,[{id:'toy-reference',length:1000}]);
assert.equal(parsed.alignments[0].r1,1,'Keep original 1-based inclusive coordinates in parsed records');
for(const text of ['', '1\t2\t3\n',fixture.replace('1\t100\t1\t100','0\t100\t1\t100'),fixture.replace('\t1000\t1000\t','\t50\t1000\t'),fixture.replace('\t99\t','\t101\t'),fixture+fixture.replaceAll('\t1000\t1000\t','\t1001\t1000\t')]) assert.throws(()=>parseNucmerCoords(text));
assert.throws(()=>parseNucmerCoords(Array(50002).fill(fixture.split('\n')[0]).join('\n')),/no partial plot/);
console.log('NUCmer coordinate parser tests passed: both orientations, lengths, coordinates, conflicts and bounds.');

assert.deepEqual(coordinateWindow('101','113',1000),{start:100,end:113,span:13});
assert.deepEqual(coordinateWindow('','',1000),{start:0,end:1000,span:1000});
for (const [start,end] of [['0','13'],['14','13'],['1','1001'],['1.5','13']]) assert.equal(coordinateWindow(start,end,1000),null);
