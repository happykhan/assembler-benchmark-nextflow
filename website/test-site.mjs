import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, stat, readdir } from 'node:fs/promises';
import { dirname, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(process.argv[2] ?? resolve(project, 'dist'));
const backendRoot = process.argv[3] ? resolve(process.argv[3]) : null;
const bundleManifest = backendRoot ? JSON.parse(await readFile(resolve(backendRoot, 'manifest.json'), 'utf8')) : null;
const cohortConfig = bundleManifest ? {...bundleManifest.cohort, root_batch: bundleManifest.primary_batch} : JSON.parse(await readFile(resolve(project, 'config/overview.json'), 'utf8'));
const deploymentConfig = JSON.parse(await readFile(resolve(root, 'vercel.json'), 'utf8'));
for (const source of ['/history', '/history.html', '/batches/:batch/history', '/batches/:batch/history.html']) {
  assert.ok(deploymentConfig.redirects.some(rule => rule.source === source && rule.destination === '/' && rule.permanent === true), `${source}: legacy navigation redirect required`);
}
const types = {'.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json'};
const server = createServer(async (request, response) => {
  try {
    const path = resolve(root, '.' + new URL(request.url, 'http://localhost').pathname);
    if (!path.startsWith(root + '/') && path !== root) throw Error('Invalid path');
    const file = (await stat(path)).isDirectory() ? resolve(path, 'index.html') : path;
    response.setHeader('content-type', types[extname(file)] ?? 'application/octet-stream');
    response.end(await readFile(file));
  } catch { response.writeHead(404); response.end('Not found'); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const statusCache = new Map();
const checkedPages = new Set();
const compact = value => value.replace(/\s+/g, ' ').trim();
const escaped = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#x27;');
const slug = row => [row.scenario_id, row.tool, row.run_id].filter(Boolean).join('--');
const titleCase = value => value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());

async function httpStatus(url) {
  if (!statusCache.has(url)) statusCache.set(url, (async () => {
    const response = await fetch(url);
    await response.body?.cancel();
    return response.status;
  })());
  return statusCache.get(url);
}

async function textAt(route) {
  const response = await fetch(base + route);
  assert.equal(response.status, 200, route);
  statusCache.set(base + route, Promise.resolve(response.status));
  return response.text();
}

async function jsonRoute(route) {
  return await httpStatus(base + route + '.gz') === 200 ? route + '.gz' : route;
}

async function jsonAt(route) {
  const download = await jsonRoute(route);
  const response = await fetch(base + download);
  assert.equal(response.status, 200, download);
  const bytes = Buffer.from(await response.arrayBuffer());
  return JSON.parse((download.endsWith('.gz') ? gunzipSync(bytes) : bytes).toString('utf8'));
}

async function checkPage(route) {
  const html = await textAt(route);
  if (!checkedPages.has(route)) {
    checkedPages.add(route);
    assert.ok(html.includes('genomicx-nav'), route);
    assert.ok(html.includes('assets/genomicx.js'), route);
    for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
      const url = new URL(match[1], base + route);
      if (url.origin === base) {
        assert.ok(!/\.(?:gfa|fasta|fastq|cereal)(?:\.gz)?$/i.test(url.pathname), `${route}: raw sequence artefact must not be published`);
        assert.equal(await httpStatus(url.href), 200, `${route}: ${url.pathname}`);
      }
    }
  }
  return html;
}

function noSequenceFields(value) {
  if (Array.isArray(value)) value.forEach(noSequenceFields);
  else if (value && typeof value === 'object') for (const [key, item] of Object.entries(value)) {
    assert.ok(!['sequence', 'sequences', 'segment_sequence', 'raw_sequence'].includes(key), `Unexpected sequence payload: ${key}`);
    noSequenceFields(item);
  }
}

function assertCohortCounts(model, records, context) {
  const countsFor = rows => {
    const counts = {total: rows.length, pass: 0, fail: 0, errors: 0, unscored: 0, denominator: 0};
    for (const row of rows) {
      const key = row.execution_outcome === 'did_not_complete' ? 'fail' : ['pass', 'fail'].includes(row.status) ? row.status : ['error', 'timeout', 'invalid_input'].includes(row.status) ? 'errors' : 'unscored';
      counts[key]++;
    }
    counts.denominator = counts.pass + counts.fail;
    counts.pass_fraction = counts.denominator ? counts.pass / counts.denominator : null;
    return counts;
  };
  for (const record of records) assert.ok(['primary', 'supplementary'].includes(record.cohort_role), `${context}: explicit reporting role required`);
  assert.deepEqual(model.counts, countsFor(records.filter(row => row.cohort_role === 'primary')), `${context}: headline counts include primary records only`);
  assert.deepEqual(model.supplementary_counts, countsFor(records.filter(row => row.cohort_role === 'supplementary')), `${context}: supplementary records retain separate counts`);
  assert.deepEqual(model.all_counts, countsFor(records), `${context}: all source records remain represented`);
}

function repeatabilityCounts(groups) {
  const counts = {identical: 0, different: 0, not_assessed: 0, total: groups.length};
  for (const group of groups) {
    const assessed = group.complete === true && group.inputs_identical === true;
    const key = assessed && group.normalised_sequence_identical === true ? 'identical' : assessed && group.normalised_sequence_identical === false ? 'different' : 'not_assessed';
    counts[key]++;
  }
  return counts;
}

async function checkOverview(prefix) {
  const overview = await jsonAt(prefix + '/data/overview.json');
  const home = await checkPage(prefix + '/');
  assert.equal(overview.endpoint, 'recorded_exact_status');
  assert.ok(home.includes('overview-heatmap'));
  assert.ok(!home.includes('data-assembly-graph'), 'Graphs belong on individual result pages');
  assert.ok(!home.includes('assembler-result'), 'Per-run diagnoses must stay off the headline');
  assert.ok(!home.includes('class="matrix"'), 'The headline must aggregate families, not individual cases');
  assert.ok(![...home.matchAll(/href="([^"]+)"/g)].some(match => /(?:^|\/)results\//.test(match[1])), 'Headline links should open a family');
  const diagnosticMatrix = (home.match(/<table class="overview-heatmap">[\s\S]*?<\/table>/)?.[0] ?? '').replace(/<tr data-read-order="true">[\s\S]*?<\/tr>/g, '');
  const cells = [...diagnosticMatrix.matchAll(/<td\b[^>]*class="([^"]*\boverview-cell\b[^"]*)"[^>]*>[\s\S]*?<\/td>/g)];
  const displayedFamilies = overview.scope === 'archived_batch' ? overview.families.filter(family => family.counts.total > 0) : overview.families;
  assert.equal(cells.length, displayedFamilies.length * overview.tools.length);
  let index = 0;
  const identities = new Set();
  for (const family of overview.families) {
    for (const tool of (displayedFamilies.includes(family) ? family.tools : [])) {
      const cell = cells[index++];
      const repeat = tool.repeatability;
      const numerator = repeat ? repeat.identical : tool.pass;
      const denominator = repeat ? repeat.identical + repeat.different : tool.denominator;
      const fields = repeat ? {identical: repeat.identical, different: repeat.different, denominator} : {pass: tool.pass, fail: tool.fail, denominator};
      for (const [key, value] of Object.entries(fields)) assert.ok(cell[0].includes(`data-${key}="${value}"`), `${prefix}/${family.id}/${tool.id}: ${key}`);
      if (repeat) {
        if (repeat.total) assert.ok(cell[0].includes(`${repeat.identical} identical · ${repeat.different} different`));
        else assert.ok(cell[0].includes('Not assessed'), 'Unassessed primary repeatability must stay explicit');
        if (repeat.not_assessed) assert.ok(compact(cell[0]).includes(`${repeat.not_assessed} not assessed`));
      } else {
        if (tool.errors) assert.ok(compact(cell[0]).includes(`${tool.errors} errors`));
        if (tool.unscored) assert.ok(compact(cell[0]).includes(`${tool.unscored} unscored`));
      }
      assert.equal(cell[1].split(/\s+/).includes('neutral'), denominator === 0, 'Unassessed cells must be neutral');
      if (denominator > 0) {
        const heat = Math.min(4, Math.floor(numerator / denominator * 5));
        assert.ok(cell[1].split(/\s+/).includes(`heat-${heat}`), 'Heat bin must use its assessed endpoint');
      }
    }
    const route = prefix + '/' + family.href;
    const html = await checkPage(route);
    assert.ok(html.includes('Assembler / version'), route);
    assert.ok(html.includes('Exact status'), route);
    assert.ok(!html.includes('data-assembly-graph'), 'Family page lists runs; graphs are third level');
    const tableRows = [...html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/g)].map(match => match[0]);
    for (const record of family.records) {
      const expected = (overview.scope === 'primary_cohort' && record.batch !== cohortConfig.root_batch ? `batches/${record.batch}/` : '') + `results/${slug(record)}.html`;
      assert.equal(record.href, expected, 'Result link must retain its batch and repeat identity');
      const identity = JSON.stringify([record.batch, record.scenario_id, record.tool, record.run_id]);
      assert.ok(!identities.has(identity), `Duplicate family record: ${identity}`);
      identities.add(identity);
      const matches = tableRows.filter(row => row.includes(`href="../${escaped(record.href)}"`));
      assert.equal(matches.length, 1, `${route}: missing or duplicated run link ${record.href}`);
      assert.ok(compact(matches[0]).includes(compact(escaped(record.version))), `${route}: version absent from its run row`);
      assert.ok(matches[0].includes(titleCase(record.status)), `${route}: status absent from its run row`);
      assert.ok(matches[0].includes(escaped(record.run_id ?? 'Single run')), `${route}: repeat identity missing`);
      if (overview.scope === 'primary_cohort') assert.ok(record.version && record.version !== 'Version not recorded', 'Completed cohort rows require recorded software versions');
      if (family.id === 'S3') {
        const repeat = record.run_id.match(/^(?:mode-(?:default|deterministic)-)?threads-(\d+)-repeat-(\d+)$/);
        assert.ok(repeat, 'Repeat identity must preserve its explicit mode, threads and replicate');
        assert.equal(record.threads, Number(repeat[1]));
        assert.ok(Number(repeat[2]) > 0);
      }
      const result = new URL('../' + record.href, base + route);
      assert.equal(await httpStatus(result.href), 200, `${route}: ${result.pathname}`);
    }
    assertCohortCounts(family, family.records, `${prefix}/${family.id}`);
    for (const tool of family.tools) {
      assert.equal(tool.total, family.records.filter(row => row.cohort_role === 'primary' && row.tool === tool.id).length);
    }
    if (family.id === 'S3') {
      const primaryGroups = family.repeatability_groups.filter(group => group.comparison === 'within_thread' && group.cohort_role === 'primary');
      assert.deepEqual(family.repeatability, repeatabilityCounts(primaryGroups), 'Headline repeatability excludes supplementary groups');
      for (const tool of family.tools) assert.deepEqual(tool.repeatability, repeatabilityCounts(primaryGroups.filter(group => group.tool === tool.id)));
    }
  }
  assert.equal(identities.size, overview.all_counts.total);
  assertCohortCounts(overview, overview.families.flatMap(family => family.records), prefix || '/');
  return overview;
}

try {
  const primary = await checkOverview('');
  assert.equal(primary.scope, 'primary_cohort');
  const expected = {total: 0, pass: 0, fail: 0, errors: 0, unscored: 0, denominator: 0};
  let supplementary = 0;
  for (const batch of cohortConfig.primary_batches) {
    const source = JSON.parse(await readFile(resolve(project, 'published', batch + '.json'), 'utf8'));
    const cases = new Map(source.scenarios.map(row => [row.id, row]));
    for (const row of source.results) {
      const scenario = cases.get(row.scenario_id);
      const family = source.config.determinism ? 'S3' : scenario.category;
      if (!cohortConfig.families.includes(family) || !cohortConfig.tools.includes(row.tool)) continue;
      const policy = cohortConfig.baseline_policy;
      const molecules = scenario.replicons ?? [];
      const plasmids = molecules.filter(m => m.molecule_type === 'plasmid');
      const scoped = policy && (policy.families ?? ['S1', 'S2', 'S3']).includes(family);
      const eligible = !scoped || (family === 'S5'
        ? (policy.linear_assemblies ?? []).includes(scenario.assembly_accession) &&
          molecules.filter(m => m.molecule_type === 'chromosome').length === 1 && molecules.every(m => m.topology === 'linear')
        : molecules.filter(m => m.molecule_type === 'chromosome').length === 1 &&
          (family === 'S1' || plasmids.length > 0) &&
          plasmids.every(m => Number.isInteger(m.length_bp) && m.length_bp >= policy.minimum_plasmid_bp));
      if (!eligible) { supplementary++; continue; }
      expected.total++;
      expected[row.execution_outcome === 'did_not_complete' ? 'fail' : ['pass', 'fail'].includes(row.status) ? row.status : ['error', 'timeout', 'invalid_input'].includes(row.status) ? 'errors' : 'unscored']++;
    }
  }
  expected.denominator = expected.pass + expected.fail;
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map(key => [key, primary.counts[key]])), expected, 'Headline counts must match the frozen source cohort');
  assert.equal(primary.all_counts.total, expected.total + supplementary);
  assert.equal(primary.supplementary_counts.total, supplementary);
  assert.deepEqual(primary.included_batches, cohortConfig.primary_batches);
  for (const batch of cohortConfig.excluded_historical_batches ?? []) assert.ok(!primary.included_batches.includes(batch));
  const prefixes = ['', ...(await readdir(resolve(root, 'batches')).catch(() => [])).map(id => `/batches/${id}`)];
  assert.ok(!prefixes.includes('/batches/' + cohortConfig.root_batch), 'The primary report must not be duplicated in its own archive');
  let batchViews = 0;
  let resultViews = 0;
  for (const prefix of prefixes) {
    const batchId = prefix ? prefix.split('/').at(-1) : cohortConfig.root_batch;
    if (!backendRoot && await httpStatus(base + await jsonRoute(prefix + '/data/results.json')) !== 200) continue;
    const data = backendRoot ? JSON.parse(await readFile(resolve(backendRoot, 'batches', batchId + '.json'), 'utf8')) : await jsonAt(prefix + '/data/results.json');
    const repeats = data.config.determinism;
    const taskCount = repeats ? repeats.repeats * repeats.threads.length * data.config.tools.reduce((sum, tool) => sum + (repeats.modes?.[tool]?.length ?? 1), 0) : data.config.tools.length;
    assert.equal(data.results.length, data.scenarios.length * taskCount);
    const frozen = JSON.parse(await readFile(resolve(project, 'published', data.batch + '.json'), 'utf8'));
    assert.deepEqual(data.config, frozen.config, 'Presentation must preserve the frozen configuration');
    const sourceRows = new Map(frozen.results.map(row => [JSON.stringify([row.scenario_id, row.tool, row.run_id]), row]));
    for (const row of data.results) {
      const original = sourceRows.get(JSON.stringify([row.scenario_id, row.tool, row.run_id]));
      assert.ok(original, 'The hierarchy cannot invent scientific executions');
      for (const field of ['status', 'evaluation', 'version', 'threads', 'repeat', 'elapsed_seconds', 'peak_memory_kb', 'assembly_sha256', 'reads_sha256', 'truth_sha256']) {
        assert.deepEqual(row[field], original[field], `${prefix}/${slug(row)}: changed scientific field ${field}`);
      }
    }
    if (prefix) {
      const archived = await checkOverview(prefix);
      assert.equal(archived.scope, 'archived_batch');
      assert.deepEqual(archived.included_batches, [data.batch], 'Archived views cannot pool the primary cohort');
      assert.equal(archived.all_counts.total, data.results.length);
    }
    for (const route of ['/methods.html', '/about.html', '/scenarios/index.html', '/batch-details.html', ...data.scenarios.map(scenario => `/scenarios/${scenario.id}.html`)]) {
      await checkPage(prefix + route);
    }
    for (const record of data.results) {
      const route = prefix + `/results/${slug(record)}.html`;
      const html = await checkPage(route);
      assert.ok(html.includes('Tool version'), `${route}: tool version fact missing`);
      assert.ok(html.includes('id="assembly-graph"'), `${route}: graph section missing`);
      assert.ok(html.includes('id="assembly-graph-data"'), `${route}: graph data missing`);
      if (record.assembly_sha256) assert.ok(html.includes(record.assembly_sha256), `${route}: assembly provenance missing`);
      const execution = backendRoot ? record : await jsonAt(prefix + `/data/results/${slug(record)}.json`);
      assert.equal(execution.status, record.status, `${route}: download changed status`);
      assert.equal(execution.assembly_sha256, record.assembly_sha256, `${route}: download changed assembly provenance`);
      const artifact = backendRoot ? JSON.parse(html.match(/<script type="application\/json" id="assembly-graph-data">(.*?)<\/script>/s)[1]) : await jsonAt(prefix + `/data/results/${slug(record)}-graph.json`);
      noSequenceFields(artifact);
      if (artifact.input_hashes?.assembly_sha256 && record.assembly_sha256) assert.equal(artifact.input_hashes.assembly_sha256, record.assembly_sha256, `${route}: graph belongs to another assembly`);
      if (artifact.graph?.status === 'available') assert.match(artifact.graph.source.file_sha256, /^[0-9a-f]{64}$/);
      resultViews++;
    }
    batchViews++;
  }
  const assetInfo = await jsonAt('/assets/build.json');
  assert.equal(assetInfo.packages['@genomicx/ui'], '0.10.1');
  const bundle = await textAt('/assets/genomicx.js');
  for (const marker of ['gx-theme-toggle', 'gx-nav-logo', 'gx-badge']) assert.ok(bundle.includes(marker));
  console.log(`HTTP end-to-end checks passed: ${checkedPages.size} routes, ${resultViews} result views across ${batchViews} batch views; ${primary.counts.total} primary and ${primary.supplementary_counts.total} supplementary executions; family/run/graph hierarchy and scientific metrics preserved.`);
} finally { await new Promise(resolve => server.close(resolve)); }
