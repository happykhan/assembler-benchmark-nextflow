import React from 'react';
import { createRoot } from 'react-dom/client';
import { Router, createPath } from 'react-router-dom';
import { NavBar, StatusBadge } from '@genomicx/ui';
import '@genomicx/ui/styles/tokens.css';
import '@genomicx/ui/styles/components.css';
import './site.css';
import { GraphViewer } from './graph.jsx';

const batchPrefix = window.location.pathname.match(/^\/batches\/[^/]+/)?.[0] ?? '';
const address = (to) => {
  const href = typeof to === 'string' ? to : createPath(to);
  return href === '/about' ? `${batchPrefix}/about.html` : href;
};
const normalise = (path) => path.replace(/\/index(\.html)?$/, '/').replace(/\.html$/, '').replace(/\/$/, '') || '/';
// Native GenomicX links navigate between real static pages, not an empty SPA route.
const navigator = {
  createHref: address,
  go: (delta) => window.history.go(delta),
  push: (to) => window.location.assign(address(to)),
  replace: (to) => window.location.replace(address(to)),
};
const links = [
  ['/index.html', 'Results'],
  ['/scenarios/index.html', 'Scenarios'],
  ['/aggregate.html', 'Aggregate plots'],
  ['/methods.html', 'Methods'],
];
const actions = (mobile = false) => links.map(([href, label]) => (
  <a key={href} href={href === '/aggregate.html' ? href : batchPrefix + href} className={mobile ? 'gx-nav-dropdown-link' : 'gx-nav-link'}
    aria-current={normalise(window.location.pathname) === normalise(batchPrefix + href)
      || (label === 'Scenarios' && window.location.pathname.startsWith(batchPrefix + '/scenarios/')) ? 'page' : undefined}>
    {label}
  </a>
));

const mount = document.getElementById('genomicx-nav');
if (mount) createRoot(mount).render(
  <Router location={window.location} navigator={navigator}>
    <NavBar appName="Ploptimizer" appSubtitle="Long-read assembly benchmark"
      githubUrl="https://github.com/SPREAD-Hackathon/ploptimizer/tree/main/assembly-benchmark"
      actions={actions()} mobileActions={actions(true)} />
  </Router>
);

const variants = {pass: 'success', fail: 'error', error: 'error', timeout: 'error',
  invalid_input: 'warning', pending: 'warning', running: 'info', not_run: 'muted'};
for (const element of document.querySelectorAll('[data-benchmark-status]')) {
  const status = element.dataset.benchmarkStatus;
  const label = element.textContent;
  createRoot(element).render(<StatusBadge variant={variants[status] ?? 'muted'}>{label}</StatusBadge>);
}

const category = document.getElementById('category-filter');
const species = document.getElementById('species-filter');
function filterRows() {
  let count = 0;
  const totals = {};
  for (const row of document.querySelectorAll('tr[data-category]')) {
    row.hidden = Boolean((category?.value && row.dataset.category !== category.value)
      || (species?.value && row.dataset.species !== species.value));
    if (!row.hidden) {
      count++;
      for (const cell of row.querySelectorAll('[data-tool]')) {
        const tool = cell.dataset.tool;
        totals[tool] ??= {pass: 0, fail: 0, unscored: 0};
        const status = cell.dataset.status;
        totals[tool][status === 'pass' || status === 'fail' ? status : 'unscored']++;
      }
    }
  }
  const message = document.getElementById('filter-count');
  if (message) message.textContent = `${count} scenarios shown`;
  for (const summary of document.querySelectorAll('[data-summary-tool]')) {
    const total = totals[summary.dataset.summaryTool] ?? {pass: 0, fail: 0, unscored: 0};
    summary.textContent = `${total.pass} pass · ${total.fail} fail · ${total.unscored} unscored`;
  }
}
if (category) category.disabled = false;
if (species) species.disabled = false;
category?.addEventListener('change', filterRows);
species?.addEventListener('change', filterRows);
if (category || species) filterRows();

for (const element of document.querySelectorAll('[data-assembly-graph]')) {
  const source = document.getElementById(element.dataset.assemblyGraph);
  try {
    const artifact = source ? JSON.parse(source.textContent) : {};
    createRoot(element).render(<GraphViewer artifact={artifact} />);
  } catch {
    element.textContent = 'The collected graph data could not be read. No topology view is available.';
  }
}

import { enhanceTables } from './table-controls.js';
enhanceTables();

import { enhanceMobileMatrices } from './mobile-matrix.js';
enhanceMobileMatrices();

// Reveal saved result details when an individual execution link targets them.
function revealHashDetails() {
  let target;
  try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { return; }
  if (!target) return;
  let parent = target;
  let revealed = false;
  while (parent) {
    if (parent.tagName === 'DETAILS' && !parent.open) { parent.open = true; revealed = true; }
    parent = parent.parentElement;
  }
  if (revealed) target.scrollIntoView({block:'start'});
}
window.addEventListener('hashchange', revealHashDetails);
revealHashDetails();
