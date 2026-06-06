(function () {
  'use strict';

  // Palette shared with the vis-network graph viewer so a community keeps a
  // stable colour across both visualisations.
  const COMMUNITY_PALETTE = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#56b6f2',
  ];
  const UNGROUPED_KEY = '__ungrouped__';
  const BASE_LETTERS = ['A', 'A*', 'T', 'G', 'C'];
  const PULSE_MS = 950;
  const RECONNECT_MS = 2500;

  const params = new URLSearchParams(window.location.search);
  const liveMode = params.get('live') === '1';
  const wsPort = params.get('ws') || '8765';
  const graphExplorerLink = document.getElementById('btn-graph-explorer');
  if (graphExplorerLink && window.location.search) {
    graphExplorerLink.href = `graph.html${window.location.search}`;
  }

  /** @type {Map<string, object>} module_id -> module summary */
  const modules = new Map();
  /** @type {{ level: 'communities' | 'modules' | 'helix' | 'structure', communityKey: string | null, moduleId: string | null }} */
  const view = { level: 'communities', communityKey: null, moduleId: null };
  let snapshotId = null;
  /** @type {WebSocket | null} */
  let socket = null;
  /** @type {InstanceType<typeof window.HelixRenderer> | null} */
  let helixRenderer = null;
  let helixLoading = false;
  /** @type {InstanceType<typeof window.StructureMap> | null} */
  let structureMap = null;
  let structureLoading = false;
  const HELIX_PITCH = 16;

  const els = {
    grid: document.getElementById('grid'),
    empty: document.getElementById('empty-state'),
    breadcrumb: document.getElementById('breadcrumb'),
    crumbRoot: document.getElementById('crumb-root'),
    workspace: document.getElementById('workspace-label'),
    liveBadge: document.getElementById('live-badge'),
    toast: document.getElementById('toast'),
    statCommunities: document.getElementById('stat-communities'),
    statModules: document.getElementById('stat-modules'),
    statGenes: document.getElementById('stat-genes'),
    statSnapshot: document.getElementById('stat-snapshot'),
    helixView: document.getElementById('helix-view'),
    helixScroll: document.getElementById('helix-scroll'),
    helixCanvas: document.getElementById('helix-canvas'),
    helixSpacer: document.getElementById('helix-spacer'),
    helixTitle: document.getElementById('helix-module-title'),
    helixPath: document.getElementById('helix-module-path'),
    helixNodeCount: document.getElementById('helix-node-count'),
    helixHealth: document.getElementById('helix-health'),
    helixAlertCount: document.getElementById('helix-alert-count'),
    structureView: document.getElementById('structure-view'),
    structureRoot: document.getElementById('structure-root'),
    structureTitle: document.getElementById('structure-module-title'),
    structurePath: document.getElementById('structure-module-path'),
    structureFileTotal: document.getElementById('structure-file-total'),
    structureVisibleFiles: document.getElementById('structure-visible-files'),
  };

  // ---------------------------------------------------------------- helpers

  function communityKeyOf(module) {
    const id = module.community_id;
    return id === null || id === undefined ? UNGROUPED_KEY : String(id);
  }

  function communityColor(key) {
    if (key === UNGROUPED_KEY) return '#5b6675';
    const idx = Number(key);
    return COMMUNITY_PALETTE[((idx % COMMUNITY_PALETTE.length) + COMMUNITY_PALETTE.length) % COMMUNITY_PALETTE.length];
  }

  function communityLabel(key) {
    return key === UNGROUPED_KEY ? 'Unclustered' : `Chromosome ${key}`;
  }

  function healthColor(score) {
    if (score >= 0.75) return getComputedStyle(document.documentElement).getPropertyValue('--health-good').trim();
    if (score >= 0.5) return getComputedStyle(document.documentElement).getPropertyValue('--health-warn').trim();
    return getComputedStyle(document.documentElement).getPropertyValue('--health-bad').trim();
  }

  function baseCount(module, letter) {
    return (module.base_counts && Number(module.base_counts[letter])) || 0;
  }

  function shortModuleName(moduleId) {
    if (moduleId === '__root__') return '. (root)';
    const parts = moduleId.split('/');
    return parts[parts.length - 1] || moduleId;
  }

  function groupByCommunity() {
    /** @type {Map<string, object[]>} */
    const groups = new Map();
    for (const module of modules.values()) {
      const key = communityKeyOf(module);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(module);
    }
    return groups;
  }

  function aggregateCommunity(members) {
    const agg = { genes: 0, bases: { A: 0, 'A*': 0, T: 0, G: 0, C: 0 }, healthSum: 0 };
    for (const module of members) {
      agg.genes += module.gene_count || 0;
      agg.healthSum += module.health_score || 0;
      for (const letter of BASE_LETTERS) agg.bases[letter] += baseCount(module, letter);
    }
    agg.health = members.length ? agg.healthSum / members.length : 1;
    agg.count = members.length;
    return agg;
  }

  function showToast(message) {
    els.toast.textContent = message;
    els.toast.classList.add('show');
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => els.toast.classList.remove('show'), 2600);
  }

  // ---------------------------------------------------------------- rendering

  function basesMarkup(counts) {
    return (
      '<div class="bases">' +
      BASE_LETTERS.map((letter) => {
        const cssClass = letter === 'A*' ? 'a-star' : letter;
        return (
          `<div class="base ${cssClass}"><span class="letter">${letter}</span>` +
          `<span class="count" data-base="${letter}">${counts[letter] || 0}</span></div>`
        );
      }).join('') +
      '</div>'
    );
  }

  function healthMarkup(score) {
    const pct = Math.round(score * 100);
    return (
      '<div class="health-row"><span>Health</span>' +
      `<span class="health-value">${pct}%</span></div>` +
      '<div class="health-track"><div class="health-fill"></div></div>'
    );
  }

  function paintHealth(card, score) {
    const fill = card.querySelector('.health-fill');
    const value = card.querySelector('.health-value');
    if (fill) {
      fill.style.width = `${Math.round(score * 100)}%`;
      fill.style.backgroundColor = healthColor(score);
    }
    if (value) value.textContent = `${Math.round(score * 100)}%`;
  }

  function communityCard(key, members) {
    const agg = aggregateCommunity(members);
    const color = communityColor(key);
    const card = document.createElement('article');
    card.className = 'card community';
    card.dataset.communityKey = key;
    card.style.setProperty('--community-color', color);
    card.innerHTML =
      '<div class="card-head">' +
      `<span class="card-title">${communityLabel(key)}</span>` +
      `<span class="chip-community">${agg.count} mod</span></div>` +
      `<div class="card-sub">Community of tightly-coupled modules</div>` +
      basesMarkup(agg.bases) +
      healthMarkup(agg.health) +
      `<div class="card-foot"><span><strong>${agg.genes}</strong> genes</span>` +
      `<span><strong>${agg.count}</strong> modules</span></div>`;
    card.addEventListener('click', () => zoomIntoCommunity(key));
    requestAnimationFrame(() => paintHealth(card, agg.health));
    return card;
  }

  function moduleCard(module) {
    const key = communityKeyOf(module);
    const color = communityColor(key);
    const card = document.createElement('article');
    card.className = 'card module';
    card.dataset.moduleId = module.module_id;
    card.style.setProperty('--community-color', color);
    const counts = {};
    for (const letter of BASE_LETTERS) counts[letter] = baseCount(module, letter);
    card.innerHTML =
      '<div class="card-head">' +
      `<span class="card-title">${shortModuleName(module.module_id)}</span>` +
      `<span class="chip-community">${communityLabel(key)}</span></div>` +
      `<div class="card-sub">${module.module_id}</div>` +
      basesMarkup(counts) +
      healthMarkup(module.health_score || 0) +
      `<div class="card-foot"><span><strong class="gene-count">${module.gene_count || 0}</strong> genes</span></div>`;
    card.addEventListener('click', () => zoomIntoHelix(module.module_id));
    requestAnimationFrame(() => paintHealth(card, module.health_score || 0));
    return card;
  }

  function encodeModulePath(moduleId) {
    return String(moduleId)
      .split('/')
      .map((part) => encodeURIComponent(part))
      .join('/');
  }

  function renderBreadcrumb() {
    els.breadcrumb.innerHTML = '';
    const root = document.createElement('button');
    root.type = 'button';
    root.className = 'crumb' + (view.level === 'communities' ? ' active' : '');
    root.textContent = 'Genome';
    root.addEventListener('click', showCommunities);
    els.breadcrumb.appendChild(root);
    if (view.communityKey !== null && view.level !== 'communities') {
      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = '/';
      els.breadcrumb.appendChild(sep);
      const communityCrumb = document.createElement('button');
      communityCrumb.type = 'button';
      communityCrumb.className = 'crumb' + (view.level === 'modules' ? ' active' : '');
      communityCrumb.textContent = communityLabel(view.communityKey);
      communityCrumb.addEventListener('click', () => {
        if (view.level !== 'modules') showModules(view.communityKey);
      });
      els.breadcrumb.appendChild(communityCrumb);
    }
    if ((view.level === 'helix' || view.level === 'structure') && view.moduleId) {
      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = '/';
      els.breadcrumb.appendChild(sep);
      const moduleCrumb = document.createElement('button');
      moduleCrumb.type = 'button';
      moduleCrumb.className = 'crumb' + (view.level === 'helix' ? ' active' : '');
      moduleCrumb.textContent = shortModuleName(view.moduleId);
      moduleCrumb.addEventListener('click', () => {
        if (view.level !== 'helix') zoomIntoHelix(view.moduleId);
      });
      els.breadcrumb.appendChild(moduleCrumb);
    }
    if (view.level === 'structure' && view.moduleId) {
      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = '/';
      els.breadcrumb.appendChild(sep);
      const leaf = document.createElement('button');
      leaf.type = 'button';
      leaf.className = 'crumb active';
      leaf.textContent = 'Structure';
      els.breadcrumb.appendChild(leaf);
    }
  }

  function renderStats() {
    const groups = groupByCommunity();
    let genes = 0;
    for (const module of modules.values()) genes += module.gene_count || 0;
    els.statCommunities.textContent = String(groups.size);
    els.statModules.textContent = String(modules.size);
    els.statGenes.textContent = String(genes);
    els.statSnapshot.textContent = snapshotId === null ? '—' : `#${snapshotId}`;
  }

  function render() {
    renderBreadcrumb();
    renderStats();

    if (view.level === 'helix') {
      els.grid.classList.add('hidden');
      els.helixView.classList.remove('hidden');
      els.structureView.classList.add('hidden');
      els.empty.classList.add('hidden');
      return;
    }

    if (view.level === 'structure') {
      els.grid.classList.add('hidden');
      els.helixView.classList.add('hidden');
      els.structureView.classList.remove('hidden');
      els.empty.classList.add('hidden');
      stopHelix();
      return;
    }

    els.grid.classList.remove('hidden');
    els.helixView.classList.add('hidden');
    els.structureView.classList.add('hidden');
    stopHelix();
    stopStructure();
    els.grid.innerHTML = '';

    if (modules.size === 0) {
      els.empty.classList.remove('hidden');
      return;
    }
    els.empty.classList.add('hidden');

    if (view.level === 'communities') {
      const groups = [...groupByCommunity().entries()].sort((a, b) => {
        if (a[0] === UNGROUPED_KEY) return 1;
        if (b[0] === UNGROUPED_KEY) return -1;
        return Number(a[0]) - Number(b[0]);
      });
      for (const [key, members] of groups) els.grid.appendChild(communityCard(key, members));
      return;
    }

    const members = [...modules.values()]
      .filter((module) => communityKeyOf(module) === view.communityKey)
      .sort((a, b) => a.module_id.localeCompare(b.module_id));
    if (members.length === 0) {
      showCommunities();
      return;
    }
    for (const module of members) els.grid.appendChild(moduleCard(module));
  }

  function showCommunities() {
    view.level = 'communities';
    view.communityKey = null;
    view.moduleId = null;
    sendSubscription('karyotype');
    render();
  }

  function showModules(key) {
    view.level = 'modules';
    view.communityKey = key;
    view.moduleId = null;
    sendSubscription('karyotype');
    render();
  }

  function zoomIntoCommunity(key) {
    showModules(key);
  }

  function stopHelix() {
    if (helixRenderer) {
      helixRenderer.destroy();
      helixRenderer = null;
    }
  }

  function paintHelixMeta(moduleId, graph) {
    const module = modules.get(moduleId);
    els.helixTitle.textContent = shortModuleName(moduleId);
    els.helixPath.textContent = moduleId;
    els.helixNodeCount.textContent = String((graph.nodes || []).length);
    const health = typeof graph.health_score === 'number' ? graph.health_score : module?.health_score || 0;
    els.helixHealth.textContent = `${Math.round(health * 100)}%`;
    const alertNodes = (graph.nodes || []).filter((node) => String(node.base) === 'G!').length;
    const alertList = (graph.alerts || []).length;
    els.helixAlertCount.textContent = String(Math.max(alertNodes, alertList));
  }

  async function loadHelixGraph(moduleId) {
    const path = encodeModulePath(moduleId);
    const res = await fetch(`/genome/${path}/graph`, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function zoomIntoHelix(moduleId) {
    if (helixLoading) return;
    helixLoading = true;
    try {
      const graph = await loadHelixGraph(moduleId);
      view.level = 'helix';
      view.moduleId = moduleId;
      if (view.communityKey === null) {
        const module = modules.get(moduleId);
        if (module) view.communityKey = communityKeyOf(module);
      }
      render();
      paintHelixMeta(moduleId, graph);
      stopHelix();
      if (window.HelixRenderer) {
        helixRenderer = new window.HelixRenderer(els.helixScroll, els.helixCanvas, els.helixSpacer);
        helixRenderer.setData(graph);
        helixRenderer.start();
      }
      sendSubscription('helix', moduleId);
    } catch (err) {
      console.error('Failed to load helix graph', err);
      showToast(`Could not load helix: ${err.message}`);
    } finally {
      helixLoading = false;
    }
  }

  async function refreshHelixGraph() {
    if (view.level !== 'helix' || !view.moduleId || !helixRenderer) return;
    try {
      const graph = await loadHelixGraph(view.moduleId);
      paintHelixMeta(view.moduleId, graph);
      helixRenderer.setData(graph);
    } catch (err) {
      console.error('Helix refresh failed', err);
    }
  }

  function stopStructure() {
    if (structureMap) {
      structureMap.destroy();
      structureMap = null;
    }
  }

  function paintStructureMeta(moduleId, tree) {
    els.structureTitle.textContent = shortModuleName(moduleId);
    els.structurePath.textContent = moduleId;
    const total = (tree.files || []).length;
    const shown = structureMap ? structureMap.renderedCount : Math.min(5, total);
    els.structureFileTotal.textContent = String(total);
    els.structureVisibleFiles.textContent = String(shown);
  }

  function updateStructureVisibleCount() {
    if (!structureMap) return;
    els.structureVisibleFiles.textContent = String(structureMap.renderedCount);
  }

  async function loadStructureTree(moduleId) {
    const path = encodeModulePath(moduleId);
    const res = await fetch(`/genome/${path}/structure`, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function zoomIntoStructure(moduleId, focusFilePath) {
    if (structureLoading) return;
    structureLoading = true;
    try {
      const tree = await loadStructureTree(moduleId);
      view.level = 'structure';
      view.moduleId = moduleId;
      if (view.communityKey === null) {
        const module = modules.get(moduleId);
        if (module) view.communityKey = communityKeyOf(module);
      }
      render();
      stopStructure();
      if (window.StructureMap) {
        structureMap = new window.StructureMap(els.structureRoot, {
          onLoadMore: updateStructureVisibleCount,
        });
        structureMap.setTree(tree, focusFilePath || null);
        paintStructureMeta(moduleId, tree);
      }
      sendSubscription('structure', moduleId);
    } catch (err) {
      console.error('Failed to load structure tree', err);
      showToast(`Could not load structure: ${err.message}`);
    } finally {
      structureLoading = false;
    }
  }

  function filePathsFromGraphDelta(delta) {
    const paths = new Set();
    const fromNodeId = window.StructureMapUtils && window.StructureMapUtils.filePathFromSymbolNodeId;
    for (const key of ['added_nodes', 'removed_nodes', 'modified_nodes']) {
      for (const nodeId of delta[key] || []) {
        const path = fromNodeId ? fromNodeId(nodeId) : null;
        if (path) paths.add(path);
      }
    }
    if (delta.changed_file) paths.add(delta.changed_file);
    return [...paths];
  }

  async function applyStructureDelta(delta) {
    if (view.level !== 'structure' || !view.moduleId || !structureMap) return;
    const affected = filePathsFromGraphDelta(delta);
    const visible = new Set(structureMap.getVisibleFilePaths());
    const patchPaths = affected.filter((path) => visible.has(path));
    if (patchPaths.length === 0) return;
    try {
      const tree = await loadStructureTree(view.moduleId);
      structureMap.patchFromTree(tree, patchPaths);
      paintStructureMeta(view.moduleId, tree);
    } catch (err) {
      console.error('Structure patch failed', err);
    }
  }

  function helixGeneIndexFromClick(event) {
    if (!helixRenderer || !helixRenderer.nodes.length) return -1;
    const rect = els.helixScroll.getBoundingClientRect();
    const y = event.clientY - rect.top + els.helixScroll.scrollTop;
    const index = Math.floor(y / HELIX_PITCH);
    if (index < 0 || index >= helixRenderer.nodes.length) return -1;
    return index;
  }

  function onHelixGeneClick(event) {
    if (view.level !== 'helix' || !view.moduleId) return;
    const index = helixGeneIndexFromClick(event);
    if (index < 0) return;
    const node = helixRenderer.nodes[index];
    const filePath = node && node.file_path;
    zoomIntoStructure(view.moduleId, filePath || null);
  }

  // ----------------------------------------------------- real-time mutations

  function pulse(card) {
    card.classList.remove('pulse');
    // Force reflow so the animation restarts even on rapid consecutive updates.
    void card.offsetWidth;
    card.classList.add('pulse');
    window.setTimeout(() => card.classList.remove('pulse'), PULSE_MS);
  }

  function bumpBaseCounts(card, counts) {
    for (const letter of BASE_LETTERS) {
      const el = card.querySelector(`.count[data-base="${letter}"]`);
      if (!el) continue;
      const next = String(counts[letter] || 0);
      if (el.textContent !== next) {
        el.textContent = next;
        el.classList.add('bump');
        window.setTimeout(() => el.classList.remove('bump'), 700);
      }
    }
  }

  function patchModuleCard(module) {
    const card = els.grid.querySelector(`.card.module[data-module-id="${cssEscape(module.module_id)}"]`);
    if (!card) return false;
    const counts = {};
    for (const letter of BASE_LETTERS) counts[letter] = baseCount(module, letter);
    bumpBaseCounts(card, counts);
    const geneEl = card.querySelector('.gene-count');
    if (geneEl) geneEl.textContent = String(module.gene_count || 0);
    paintHealth(card, module.health_score || 0);
    pulse(card);
    return true;
  }

  function patchCommunityCard(key) {
    const card = els.grid.querySelector(`.card.community[data-community-key="${cssEscape(key)}"]`);
    if (!card) return false;
    const members = [...modules.values()].filter((module) => communityKeyOf(module) === key);
    const agg = aggregateCommunity(members);
    bumpBaseCounts(card, agg.bases);
    const foot = card.querySelector('.card-foot');
    if (foot) {
      foot.innerHTML =
        `<span><strong>${agg.genes}</strong> genes</span>` +
        `<span><strong>${agg.count}</strong> modules</span>`;
    }
    const chip = card.querySelector('.chip-community');
    if (chip) chip.textContent = `${agg.count} mod`;
    paintHealth(card, agg.health);
    pulse(card);
    return true;
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function applyKaryotypeUpdate(message) {
    if (typeof message.snapshot_id === 'number') {
      snapshotId = message.snapshot_id;
      els.statSnapshot.textContent = `#${snapshotId}`;
    }
    const incoming = message.modules || [];
    if (incoming.length === 0) return;

    const touchedCommunities = new Set();
    let structuralChange = false;

    for (const update of incoming) {
      const existing = modules.get(update.module_id);
      const merged = Object.assign({}, existing, update);
      if (!existing) structuralChange = true;
      else if (communityKeyOf(existing) !== communityKeyOf(merged)) structuralChange = true;
      modules.set(update.module_id, merged);
      touchedCommunities.add(communityKeyOf(merged));
    }

    renderStats();

    // A new module or a module that hopped communities changes the grouping,
    // so re-render the whole grid; otherwise patch in place to keep animations.
    if (structuralChange) {
      render();
      flashTouched(incoming, touchedCommunities);
      return;
    }

    if (view.level === 'communities') {
      for (const key of touchedCommunities) patchCommunityCard(key);
    } else {
      for (const update of incoming) {
        if (communityKeyOf(modules.get(update.module_id)) === view.communityKey) {
          patchModuleCard(modules.get(update.module_id));
        }
      }
    }
  }

  function flashTouched(incoming, touchedCommunities) {
    if (view.level === 'communities') {
      for (const key of touchedCommunities) {
        const card = els.grid.querySelector(`.card.community[data-community-key="${cssEscape(key)}"]`);
        if (card) pulse(card);
      }
    } else {
      for (const update of incoming) {
        const card = els.grid.querySelector(`.card.module[data-module-id="${cssEscape(update.module_id)}"]`);
        if (card) pulse(card);
      }
    }
  }

  // ---------------------------------------------------------------- networking

  async function loadGenome() {
    try {
      const res = await fetch('/genome', { headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      snapshotId = typeof data.snapshot_id === 'number' ? data.snapshot_id : null;
      modules.clear();
      for (const module of data.modules || []) modules.set(module.module_id, module);
      if (data.workspace) els.workspace.textContent = data.workspace;
      render();
    } catch (err) {
      console.error('Failed to load /genome', err);
      showToast(`Could not load genome: ${err.message}`);
      render();
    }
  }

  function setLive(online) {
    els.liveBadge.classList.toggle('online', online);
    els.liveBadge.classList.toggle('offline', !online);
    els.liveBadge.querySelector('.live-text').textContent = online ? 'Live' : 'Offline';
  }

  function sendSubscription(level, moduleId) {
    if (!liveMode || !socket || socket.readyState !== WebSocket.OPEN) return;
    const payload = { action: 'subscribe', level };
    if ((level === 'helix' || level === 'structure') && moduleId) payload.module_id = moduleId;
    socket.send(JSON.stringify(payload));
  }

  function connectWebSocket() {
    if (!liveMode) return;
    try {
      socket = new WebSocket(`ws://${window.location.hostname}:${wsPort}`);
    } catch (err) {
      console.error('WebSocket init failed', err);
      window.setTimeout(connectWebSocket, RECONNECT_MS);
      return;
    }

    socket.addEventListener('open', () => {
      setLive(true);
      if (view.level === 'structure' && view.moduleId) {
        sendSubscription('structure', view.moduleId);
      } else if (view.level === 'helix' && view.moduleId) {
        sendSubscription('helix', view.moduleId);
      } else {
        sendSubscription('karyotype');
      }
    });

    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload && payload.type === 'karyotype_update') applyKaryotypeUpdate(payload);
        if (payload && payload.type === 'graph_delta') {
          if (payload.module_id !== view.moduleId) return;
          if (view.level === 'helix') refreshHelixGraph();
          if (view.level === 'structure') applyStructureDelta(payload);
        }
      } catch (err) {
        console.error('Bad WebSocket message', err);
      }
    });

    socket.addEventListener('close', () => {
      setLive(false);
      window.setTimeout(connectWebSocket, RECONNECT_MS);
    });

    socket.addEventListener('error', () => socket.close());
  }

  els.crumbRoot.addEventListener('click', showCommunities);
  els.helixScroll.addEventListener('click', onHelixGeneClick);

  loadGenome().then(connectWebSocket);
})();
