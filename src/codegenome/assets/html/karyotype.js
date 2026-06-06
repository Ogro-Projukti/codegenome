(function () {
  'use strict';

  // Palette shared with the vis-network graph viewer so a community keeps a
  // stable colour across both visualisations.
  const COMMUNITY_PALETTE = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#56b6f2',
  ];
  const UNGROUPED_KEY = '__ungrouped__';
  const BASE_LETTERS = ['A', 'T', 'G', 'C'];
  const PULSE_MS = 950;
  const RECONNECT_MS = 2500;

  const params = new URLSearchParams(window.location.search);
  const liveMode = params.get('live') === '1';
  const wsPort = params.get('ws') || '8765';

  /** @type {Map<string, object>} module_id -> module summary */
  const modules = new Map();
  /** @type {{ level: 'communities' | 'modules', communityKey: string | null }} */
  const view = { level: 'communities', communityKey: null };
  let snapshotId = null;

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
    const agg = { genes: 0, bases: { A: 0, T: 0, G: 0, C: 0 }, healthSum: 0 };
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
      BASE_LETTERS.map(
        (letter) =>
          `<div class="base ${letter}"><span class="letter">${letter}</span>` +
          `<span class="count" data-base="${letter}">${counts[letter] || 0}</span></div>`,
      ).join('') +
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
    requestAnimationFrame(() => paintHealth(card, module.health_score || 0));
    return card;
  }

  function renderBreadcrumb() {
    els.breadcrumb.innerHTML = '';
    const root = document.createElement('button');
    root.type = 'button';
    root.className = 'crumb' + (view.level === 'communities' ? ' active' : '');
    root.textContent = 'Genome';
    root.addEventListener('click', showCommunities);
    els.breadcrumb.appendChild(root);
    if (view.level === 'modules' && view.communityKey !== null) {
      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = '/';
      els.breadcrumb.appendChild(sep);
      const leaf = document.createElement('button');
      leaf.type = 'button';
      leaf.className = 'crumb active';
      leaf.textContent = communityLabel(view.communityKey);
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
    render();
  }

  function zoomIntoCommunity(key) {
    view.level = 'modules';
    view.communityKey = key;
    render();
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

  function connectWebSocket() {
    if (!liveMode) return;
    let socket;
    try {
      socket = new WebSocket(`ws://${window.location.hostname}:${wsPort}`);
    } catch (err) {
      console.error('WebSocket init failed', err);
      window.setTimeout(connectWebSocket, RECONNECT_MS);
      return;
    }

    socket.addEventListener('open', () => {
      setLive(true);
      socket.send(JSON.stringify({ action: 'subscribe', level: 'karyotype' }));
    });

    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload && payload.type === 'karyotype_update') applyKaryotypeUpdate(payload);
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

  loadGenome().then(connectWebSocket);
})();
