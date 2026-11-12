// Keep the full comparison on desktop; phones show a complete selected column.
export function selectMatrixColumn(table, column) {
  for (const row of table.rows) {
    [...row.cells].forEach((cell, index) => cell.classList.toggle('matrix-mobile-selected', index === column));
  }
}

export function enhanceMobileMatrices(root = document) {
  let ordinal = 0;
  for (const table of root.querySelectorAll('.overview-heatmap')) {
    if (table.classList.contains('matrix-mobile-ready')) continue;
    const headers = [...(table.tHead?.rows[0]?.cells ?? [])];
    if (headers.length < 2) continue;
    const label = document.createElement('label');
    label.className = 'overview-matrix-controls';
    label.textContent = 'Assembler';
    const select = document.createElement('select');
    select.className = 'gx-input';
    select.setAttribute('aria-label', `Assembler shown in ${table.dataset.matrixLabel ?? 'scenario matrix'}`);
    if (!table.id) table.id = `scenario-matrix-${++ordinal}`;
    select.setAttribute('aria-controls', table.id);
    headers.slice(1).forEach((header, index) => {
      const option = document.createElement('option');
      option.value = String(index + 1);
      option.textContent = header.textContent.trim();
      select.append(option);
    });
    label.append(select);
    const scroller = table.closest('.table-scroll');
    (scroller ?? table).before(label);
    select.addEventListener('change', () => selectMatrixColumn(table, Number(select.value)));
    selectMatrixColumn(table, 1);
    table.classList.add('matrix-mobile-ready');
    scroller?.classList.add('matrix-mobile-ready');
  }
}
