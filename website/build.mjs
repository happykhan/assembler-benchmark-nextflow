import { build } from 'esbuild';
import { mkdir, readFile, writeFile, readdir, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const output = join(root, 'generated');
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await build({
  absWorkingDir: root,
  entryPoints: ['shell.jsx'],
  outfile: join(output, 'genomicx.js'),
  bundle: true, minify: true, format: 'iife', jsx: 'automatic', target: 'es2022',
  assetNames: '[name]-[hash]', loader: { '.woff': 'file', '.woff2': 'file' },
  define: { 'process.env.NODE_ENV': '"production"' },
  legalComments: 'linked',
});
const packages = ['@genomicx/ui', 'react', 'react-dom', 'react-router-dom'];
const versions = {};
for (const name of packages) {
  versions[name] = JSON.parse(await readFile(join(root, 'node_modules', name, 'package.json'), 'utf8')).version;
}
const files = {};
for (const name of await readdir(output)) {
  files[name] = createHash('sha256').update(await readFile(join(output, name))).digest('hex');
}
const sources = {};
for (const name of ['package.json', 'shell.jsx', 'site.css', 'graph.jsx', 'graph.css', 'origin-evidence.jsx', 'table-controls.js', 'mobile-matrix.js', 'dotplot.jsx', 'build.mjs']) {
  sources[name] = createHash('sha256').update(await readFile(join(root, name))).digest('hex');
}
await writeFile(join(output, 'build.json'), JSON.stringify({packages: versions, sha256: files, source_sha256: sources}, null, 2) + '\n');
await writeFile(join(output, 'NOTICE.txt'),
  '@genomicx/ui 0.10.1: GPL-3.0; source https://www.npmjs.com/package/@genomicx/ui\n' +
  'React and React DOM: MIT. React Router: MIT. IBM Plex fonts: SIL Open Font License.\n' +
  'Bundled notices are retained in genomicx.js.LEGAL.txt.\n' +
  'Benchmark source: https://github.com/SPREAD-Hackathon/ploptimizer/tree/main/assembly-benchmark\n');
console.log(`Built GenomicX interface assets (${versions['@genomicx/ui']})`);
