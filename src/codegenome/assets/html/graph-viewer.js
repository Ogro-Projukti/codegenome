(function () {
  'use strict';

  const SEARCH_DEBOUNCE_MS = 180;
  const LIVE_POLL_MS = 1500;
  const MAX_FILE_NODES = 500;
  const MAX_FULL_NODES = 2500;
  const MAX_FULL_EDGES = 6000;
  const HIGHLIGHT_DURATION_MS = 8000;

  const COMMUNITY_PALETTE = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
  ];

  const EDGE_COLORS = {
    imports: '#60a5fa',
    calls: '#c084fc',
    contains: '#6b7280',
    default: '#4b5563',
  };

  const config = Object.assign(
    {
      workspaceName: 'Workspace',
      liveJsonUrl: null,
      livePollMs: LIVE_POLL_MS,
      maxFileNodes: MAX_FILE_NODES,
      maxFullNodes: MAX_FULL_NODES,
      maxFullEdges: MAX_FULL_EDGES,
    },
    window.WATCHER_GRAPH_CONFIG || {},
  );

  const params = new URLSearchParams(window.location.search);
  const liveMode = params.get('live') === '1' || Boolean(config.liveJsonUrl);
  const liveJsonUrl = config.liveJsonUrl || '/graph.json';

  /** @type {GraphDocument | null} */
  let graphDocument = null;
  /** @type {Map<string, GraphNode>} */
  let nodeById = new Map();
  /** @type {Set<string>} */
  let deadCodeSet = new Set();
  /** @type {Map<string, number>} */
  let godNodeScores = new Map();
  /** @type {import('vis').Network | null} */
  let network = null;
  /** @type {import('vis').DataSet | null} */
  let visNodes = null;
  /** @type {import('vis').DataSet | null} */
  let visEdges = null;
  /** @type {GraphDocument | null} */
  let previousDocument = null;
  /** @type {GraphDelta | undefined} */
  let lastDelta = undefined;
  /** @type {Set<string>} */
  let highlightedNodeIds = new Set();
  /** @type {number | undefined} */
  let searchTimer = undefined;
  /** @type {number | undefined} */
  let highlightTimer = undefined;
  /** @type {number | undefined} */
  let pollTimer = undefined;
  /** @type {string | null} */
  let liveEtag = null;
  /** @type {string | null} */
  let selectedNodeId = null;
  /** @type {boolean} */
  let fileLevelView = true;
  /** @type {boolean | null} */
  let lastRenderedViewMode = null;

  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');
  const detailContent = document.getElementById('detail-content');
  const graphContainer = document.getElementById('graph-container');
  const liveBadge = document.getElementById('live-badge');
  const toast = document.getElementById('toast');
  const statNodes = document.getElementById('stat-nodes');
  const statEdges = document.getElementById('stat-edges');
  const statCommunities = document.getElementById('stat-communities');
  const statUpdated = document.getElementById('stat-updated');
  const workspaceLabel = document.getElementById('workspace-label');
  const btnFit = document.getElementById('btn-fit');
  const btnViewMode = document.getElementById('btn-view-mode');

  if (workspaceLabel) {
    workspaceLabel.textContent = config.workspaceName;
  }

  if (liveMode) {
    liveBadge?.classList.remove('hidden');
    setLivePending(true);
  }

  searchInput?.addEventListener('input', () => {
    scheduleSearch(searchInput.value);
  });

  searchInput?.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      searchResults?.classList.add('hidden');
      searchInput.blur();
    }
  });

  btnFit?.addEventListener('click', () => {
    network?.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
  });

  btnViewMode?.addEventListener('click', () => {
    fileLevelView = !fileLevelView;
    btnViewMode.textContent = fileLevelView ? 'Switch to full graph' : 'Switch to file graph';
    btnViewMode.classList.toggle('active', fileLevelView);
    btnViewMode.title = fileLevelView
      ? 'Show files, symbols, and call/import relationships'
      : 'Show aggregated file-level dependencies';
    if (graphDocument) {
      rebuildGraph(graphDocument);
    }
  });
  if (btnViewMode) {
    btnViewMode.textContent = 'Switch to full graph';
    btnViewMode.title = 'Show files, symbols, and call/import relationships';
  }

  document.addEventListener('click', (event) => {
    if (!searchResults || !searchInput) {
      return;
    }
    const target = event.target;
    if (target instanceof Node && !searchResults.contains(target) && target !== searchInput) {
      searchResults.classList.add('hidden');
    }
  });

  init();

  async function init() {
    const embedded = readEmbeddedGraph();
    if (embedded) {
      applyGraphDocument(embedded, false);
    }

    if (!liveMode) {
      if (!embedded) {
        showToast('No graph data embedded in this export.');
      }
      return;
    }

    if (window.location.protocol === 'file:') {
      setLivePending(false);
      showToast('Open via Watcher extension for live updates.');
      return;
    }

    await pollLiveGraph(true);
    
    const ws = new WebSocket('ws://localhost:8765');
    ws.onopen = () => {
      console.log('WebSocket connected for live updates');
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'graph_delta') {
          // Trigger a fast HTTP fetch to get the full updated JSON and apply vis.js diffs
          void pollLiveGraph(false);
        }
      } catch (e) {
        console.error('WebSocket message parse error', e);
      }
    };
    ws.onclose = () => {
      console.log('WebSocket disconnected, falling back to polling');
      pollTimer = window.setInterval(() => {
        void pollLiveGraph(false);
      }, config.livePollMs || LIVE_POLL_MS);
    };
  }

  function readEmbeddedGraph() {
    const element = document.getElementById('watcher-graph-data');
    if (!element || !element.textContent) {
      return null;
    }
    try {
      return normalizeDocument(JSON.parse(element.textContent));
    } catch {
      return null;
    }
  }

  /** @param {boolean} initial */
  async function pollLiveGraph(initial) {
    try {
      setLivePending(true);
      const headers = liveEtag ? { 'If-None-Match': liveEtag } : {};
      const response = await fetch(liveJsonUrl, { cache: 'no-store', headers });
      if (response.status === 304) {
        setLivePending(false);
        return;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const nextEtag = response.headers.get('ETag');
      if (nextEtag) {
        liveEtag = nextEtag;
      }

      const payload = normalizeDocument(await response.json());
      if (!initial && previousDocument && !computeGraphDelta(previousDocument, payload)) {
        setLivePending(false);
        return;
      }

      applyGraphDocument(payload, !initial);
      setLivePending(false);
    } catch (error) {
      setLivePending(false);
      if (initial && !graphDocument) {
        showToast('Could not load live graph data.');
      }
    }
  }

  /** @param {unknown} raw */
  function normalizeDocument(raw) {
    const doc = raw && typeof raw === 'object' ? /** @type {Record<string, unknown>} */ (raw) : {};
    const nodes = Array.isArray(doc.nodes) ? doc.nodes.map(normalizeNode) : [];
    const edges = Array.isArray(doc.edges) ? doc.edges.map(normalizeEdge) : [];
    const metadata = doc.metadata && typeof doc.metadata === 'object'
      ? /** @type {Record<string, unknown>} */ (doc.metadata)
      : {};
    const intelligence = doc.intelligence && typeof doc.intelligence === 'object'
      ? /** @type {Record<string, unknown>} */ (doc.intelligence)
      : null;

    return {
      metadata,
      nodes,
      edges,
      intelligence,
    };
  }

  /** @param {Record<string, unknown>} node */
  function normalizeNode(node) {
    const id = String(node.id ?? node.node_id ?? '');
    return { ...node, id };
  }

  /** @param {Record<string, unknown>} edge */
  function normalizeEdge(edge) {
    return {
      source: String(edge.source ?? edge.from ?? ''),
      target: String(edge.target ?? edge.to ?? ''),
      edge_type: edge.edge_type ? String(edge.edge_type) : undefined,
    };
  }

  /** @param {GraphDocument} document @param {boolean} computeDelta */
  function applyGraphDocument(document, computeDelta) {
    const delta = computeDelta && previousDocument
      ? computeGraphDelta(previousDocument, document)
      : undefined;

    lastDelta = delta;
    graphDocument = document;
    previousDocument = document;
    nodeById = new Map(document.nodes.map((node) => [node.id, node]));

    const intelligence = document.intelligence || {};
    deadCodeSet = new Set(Array.isArray(intelligence.dead_code) ? intelligence.dead_code : []);
    godNodeScores = new Map(
      (Array.isArray(intelligence.god_nodes) ? intelligence.god_nodes : []).map((entry) => {
        if (entry && typeof entry === 'object') {
          const record = /** @type {Record<string, unknown>} */ (entry);
          return [String(record.node ?? ''), Number(record.score ?? 0)];
        }
        return [String(entry), 0];
      }),
    );

    updateStats(document);
    rebuildGraph(document);

    if (delta) {
      applyDeltaHighlights(delta);
      showDeltaToast(delta);
    }

    if (selectedNodeId && nodeById.has(selectedNodeId)) {
      renderNodeDetail(nodeById.get(selectedNodeId));
    }
  }

  /** @param {GraphDocument} document */
  function updateStats(document) {
    const stats = document.metadata?.statistics || computeStatistics(document);
    statNodes.textContent = `${Number(stats.node_count || document.nodes.length).toLocaleString()} nodes`;
    statEdges.textContent = `${Number(stats.edge_count || document.edges.length).toLocaleString()} edges`;
    statCommunities.textContent = `${Number(stats.community_count || countCommunities(document.nodes)).toLocaleString()} communities`;
    statUpdated.textContent = `Updated ${formatTimestamp(new Date().toISOString())}`;
  }

  /** @param {GraphDocument} document */
  function rebuildGraph(document) {
    if (typeof vis === 'undefined') {
      showToast('Graph library failed to load.');
      return;
    }

    const payload = fileLevelView
      ? buildFileLevelVisPayload(document)
      : buildFullVisPayload(document);

    if (!payload.nodes.length) {
      showToast('No nodes to display in this view.');
      return;
    }

    if (payload.sampled && viewChanged) {
      showToast(
        `Showing ${payload.nodes.length.toLocaleString()} of ${payload.totalNodes.toLocaleString()} nodes` +
          (payload.totalEdges > payload.edges.length
            ? ` and ${payload.edges.length.toLocaleString()} of ${payload.totalEdges.toLocaleString()} edges`
            : ''),
        3200,
      );
    }

    const viewChanged = lastRenderedViewMode !== fileLevelView;
    lastRenderedViewMode = fileLevelView;
    const nodeCount = payload.nodes.length;
    const physicsEnabled = nodeCount <= 900;

    if (network && viewChanged) {
      network.destroy();
      network = null;
      visNodes = null;
      visEdges = null;
    }

    if (!network) {
      visNodes = new vis.DataSet(payload.nodes);
      visEdges = new vis.DataSet(payload.edges);
      network = new vis.Network(graphContainer, { nodes: visNodes, edges: visEdges }, {
        physics: {
          enabled: physicsEnabled,
          stabilization: {
            iterations: fileLevelView ? 80 : Math.min(160, Math.max(60, Math.floor(nodeCount / 8))),
          },
          barnesHut: {
            gravitationalConstant: fileLevelView ? -2400 : -1800,
            springLength: fileLevelView ? 110 : 95,
          },
        },
        interaction: { hover: true, navigationButtons: true, keyboard: true, tooltipDelay: 120 },
        nodes: {
          shape: 'dot',
          size: fileLevelView ? 12 : 8,
          font: { color: '#e8eaed', size: fileLevelView ? 10 : 9, face: 'Segoe UI' },
          borderWidth: 2,
        },
        edges: {
          arrows: 'to',
          color: { color: '#4b5563', highlight: '#c084fc' },
          width: 1,
          smooth: { type: 'continuous' },
        },
      });

      network.on('click', (params) => {
        if (params.nodes.length) {
          focusNode(String(params.nodes[0]));
        }
      });

      if (physicsEnabled) {
        network.once('stabilizationIterationsDone', () => {
          network?.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
        });
      } else {
        window.setTimeout(() => {
          network?.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
        }, 0);
      }
    } else if (visNodes && visEdges) {
      syncVisDataSet(visNodes, payload.nodes, 'id');
      syncVisDataSet(visEdges, payload.edges, 'id');
      network.setOptions({
        physics: {
          enabled: physicsEnabled,
          stabilization: {
            iterations: fileLevelView ? 80 : Math.min(160, Math.max(60, Math.floor(nodeCount / 8))),
          },
        },
      });
      if (physicsEnabled) {
        network.stabilize();
        network.once('stabilizationIterationsDone', () => {
          network?.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
        });
      } else {
        network.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
      }
    }

    refreshNodeStyles();
  }

  /** @param {GraphDocument} document */
  function buildFileLevelVisPayload(document) {
    const fileNodes = document.nodes.filter((node) => node.node_type === 'file');
    const fileIds = new Set(fileNodes.map((node) => node.id));
    const limitedFiles = fileNodes.slice(0, config.maxFileNodes || MAX_FILE_NODES);

    /** @type {Map<string, string>} */
    const symbolToFile = new Map();
    for (const edge of document.edges) {
      if (edge.edge_type !== 'contains') {
        continue;
      }
      const target = nodeById.get(edge.target);
      if (target?.node_type === 'symbol') {
        symbolToFile.set(edge.target, edge.source);
      }
    }

    const resolveFileId = (nodeId) => {
      if (fileIds.has(nodeId)) {
        return nodeId;
      }
      return symbolToFile.get(nodeId);
    };

    const visNodeIds = new Set(limitedFiles.map((node) => node.id));
    /** @type {Array<{ id: string; from: string; to: string }>} */
    const visEdgeList = [];
    const edgeSeen = new Set();

    for (const edge of document.edges) {
      if (edge.edge_type !== 'imports' && edge.edge_type !== 'calls') {
        continue;
      }
      const fromFile = resolveFileId(edge.source);
      const toFile = resolveFileId(edge.target);
      if (!fromFile || !toFile || fromFile === toFile) {
        continue;
      }
      if (!visNodeIds.has(fromFile) || !visNodeIds.has(toFile)) {
        continue;
      }
      const key = `${fromFile}|${toFile}|${edge.edge_type || ''}`;
      if (edgeSeen.has(key)) {
        continue;
      }
      edgeSeen.add(key);
      visEdgeList.push({ id: key, from: fromFile, to: toFile, edge_type: edge.edge_type || 'imports' });
    }

    const nodes = limitedFiles.map((node) => styleVisNode(node));
    return {
      nodes,
      edges: visEdgeList.map((edge) => styleVisEdge(edge)),
      sampled: limitedFiles.length < fileNodes.length,
      totalNodes: fileNodes.length,
      totalEdges: visEdgeList.length,
    };
  }

  /** @param {GraphDocument} document */
  function buildFullVisPayload(document) {
    const maxNodes = config.maxFullNodes || MAX_FULL_NODES;
    const maxEdges = config.maxFullEdges || MAX_FULL_EDGES;
    const selected = selectFullViewNodes(document, maxNodes);
    const nodeIds = new Set(selected.keys());
    const visEdges = [];

    for (const edge of document.edges) {
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
        continue;
      }
      if (edge.edge_type !== 'imports' && edge.edge_type !== 'calls' && edge.edge_type !== 'contains') {
        continue;
      }
      const key = `${edge.source}|${edge.target}|${edge.edge_type || ''}`;
      visEdges.push(styleVisEdge({
        id: key,
        from: edge.source,
        to: edge.target,
        edge_type: edge.edge_type || '',
        label: edge.edge_type === 'contains' ? '' : (edge.edge_type || ''),
      }));
      if (visEdges.length >= maxEdges) {
        break;
      }
    }

    const nodes = [...selected.values()].map((node) => styleVisNode(node));
    return {
      nodes,
      edges: visEdges,
      sampled: selected.size < document.nodes.length || visEdges.length >= maxEdges,
      totalNodes: document.nodes.length,
      totalEdges: document.edges.length,
    };
  }

  /** @param {GraphDocument} document @param {number} maxNodes */
  function selectFullViewNodes(document, maxNodes) {
    /** @type {Map<string, GraphNode>} */
    const selected = new Map();
    const addNode = (node) => {
      if (!node?.id || selected.has(node.id) || selected.size >= maxNodes) {
        return false;
      }
      selected.set(node.id, node);
      return true;
    };

    const buckets = {
      file: [],
      symbol: [],
      import: [],
      external: [],
      other: [],
    };

    for (const node of document.nodes) {
      const type = node.node_type || 'other';
      if (type in buckets) {
        buckets[type].push(node);
      } else {
        buckets.other.push(node);
      }
    }

    for (const node of buckets.file) {
      addNode(node);
    }
    for (const node of buckets.symbol) {
      if (selected.size >= maxNodes) {
        break;
      }
      addNode(node);
    }
    for (const node of buckets.import) {
      if (selected.size >= maxNodes) {
        break;
      }
      addNode(node);
    }
    for (const node of buckets.other) {
      if (selected.size >= maxNodes) {
        break;
      }
      addNode(node);
    }

    for (const edge of document.edges) {
      if (selected.size >= maxNodes) {
        break;
      }
      if (edge.edge_type !== 'imports' && edge.edge_type !== 'calls') {
        continue;
      }
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      if (source?.node_type === 'external' && selected.has(edge.target)) {
        addNode(source);
      }
      if (target?.node_type === 'external' && selected.has(edge.source)) {
        addNode(target);
      }
    }

    return selected;
  }

  /** @param {{ id: string; from: string; to: string; edge_type?: string; label?: string }} edge */
  function styleVisEdge(edge) {
    const edgeType = edge.edge_type || 'default';
    const color = EDGE_COLORS[edgeType] ?? EDGE_COLORS.default;
    return {
      id: edge.id,
      from: edge.from,
      to: edge.to,
      label: edge.label,
      color: { color, highlight: EDGE_COLORS.calls, hover: EDGE_COLORS.calls },
    };
  }

  /** @param {GraphNode} node */
  function styleVisNode(node) {
    const communityId = node.community_id ?? -1;
    const color = communityId >= 0
      ? COMMUNITY_PALETTE[communityId % COMMUNITY_PALETTE.length]
      : '#888888';
    const label = nodeLabel(node);
    return {
      id: node.id,
      label: shortLabel(label),
      title: label,
      color: {
        background: color,
        border: color,
        highlight: { background: '#c084fc', border: '#c084fc' },
      },
    };
  }

  /** @param {import('vis').DataSet} dataSet @param {Array<Record<string, unknown>>} nextItems @param {string} idKey */
  function syncVisDataSet(dataSet, nextItems, idKey) {
    const nextIds = new Set(nextItems.map((item) => String(item[idKey])));
    const stale = dataSet.get({ filter: (item) => !nextIds.has(String(item[idKey])) }).map((item) => item[idKey]);
    if (stale.length) {
      dataSet.remove(stale);
    }
    dataSet.update(nextItems);
  }

  function refreshNodeStyles() {
    if (!visNodes || !graphDocument) {
      return;
    }

    const added = new Set(lastDelta?.addedNodeIds ?? []);
    const changed = new Set(lastDelta?.changedNodeIds ?? []);
    const highlight = highlightedNodeIds.size ? highlightedNodeIds : new Set([...added, ...changed]);

    for (const node of visNodes.get()) {
      const nodeId = String(node.id);
      let border = node.color?.background ?? '#888888';
      let borderWidth = 2;
      let size = fileLevelView ? 12 : 8;

      if (added.has(nodeId) || (highlight.has(nodeId) && added.has(nodeId))) {
        border = '#34d399';
        borderWidth = 4;
        size = fileLevelView ? 16 : 12;
      } else if (changed.has(nodeId) || highlight.has(nodeId)) {
        border = '#fbbf24';
        borderWidth = 3;
        size = fileLevelView ? 14 : 10;
      } else if (deadCodeSet.has(nodeId)) {
        border = '#f87171';
      }

      visNodes.update({
        id: node.id,
        size,
        borderWidth,
        color: {
          background: node.color?.background ?? border,
          border,
          highlight: { background: '#c084fc', border: '#c084fc' },
        },
      });
    }
  }

  /** @param {GraphDelta} delta */
  function applyDeltaHighlights(delta) {
    highlightedNodeIds = new Set([...delta.addedNodeIds, ...delta.changedNodeIds]);
    if (highlightTimer) {
      clearTimeout(highlightTimer);
    }
    highlightTimer = window.setTimeout(() => {
      highlightedNodeIds = new Set();
      refreshNodeStyles();
    }, HIGHLIGHT_DURATION_MS);
  }

  /** @param {GraphDelta} delta */
  function showDeltaToast(delta) {
    const parts = [];
    if (delta.addedNodeIds.length) {
      parts.push(`+${delta.addedNodeIds.length} node${delta.addedNodeIds.length === 1 ? '' : 's'}`);
    }
    if (delta.removedNodeIds.length) {
      parts.push(`-${delta.removedNodeIds.length} node${delta.removedNodeIds.length === 1 ? '' : 's'}`);
    }
    if (delta.changedNodeIds.length) {
      parts.push(`${delta.changedNodeIds.length} changed`);
    }
    if (delta.addedEdgeCount) {
      parts.push(`+${delta.addedEdgeCount} edge${delta.addedEdgeCount === 1 ? '' : 's'}`);
    }
    if (parts.length) {
      showToast(`Graph evolved: ${parts.join(', ')}`, 3500);
    }
  }

  /** @param {GraphDocument} previous @param {GraphDocument} current */
  function computeGraphDelta(previous, current) {
    const previousNodeIds = new Set(previous.nodes.map((node) => node.id));
    const previousFingerprints = new Map(previous.nodes.map((node) => [node.id, fingerprintNode(node)]));
    const currentNodeIds = new Set(current.nodes.map((node) => node.id));

    const addedNodeIds = current.nodes
      .filter((node) => !previousNodeIds.has(node.id))
      .map((node) => node.id);
    const changedNodeIds = current.nodes
      .filter((node) => previousNodeIds.has(node.id) && previousFingerprints.get(node.id) !== fingerprintNode(node))
      .map((node) => node.id);
    const removedNodeIds = [...previousNodeIds].filter((nodeId) => !currentNodeIds.has(nodeId));

    const previousEdgeKeys = new Set(previous.edges.map(edgeKey));
    const currentEdgeKeys = new Set(current.edges.map(edgeKey));
    let addedEdgeCount = 0;
    let removedEdgeCount = 0;
    for (const key of currentEdgeKeys) {
      if (!previousEdgeKeys.has(key)) {
        addedEdgeCount += 1;
      }
    }
    for (const key of previousEdgeKeys) {
      if (!currentEdgeKeys.has(key)) {
        removedEdgeCount += 1;
      }
    }

    if (!addedNodeIds.length && !removedNodeIds.length && !changedNodeIds.length && !addedEdgeCount && !removedEdgeCount) {
      return undefined;
    }

    return { addedNodeIds, removedNodeIds, changedNodeIds, addedEdgeCount, removedEdgeCount };
  }

  /** @param {GraphNode} node */
  function fingerprintNode(node) {
    return JSON.stringify({
      node_type: node.node_type,
      name: node.name,
      qualified_name: node.qualified_name,
      file_path: node.file_path,
      community_id: node.community_id,
      complexity: node.complexity,
      churn: node.churn,
      is_bridge: node.is_bridge,
    });
  }

  /** @param {GraphEdge} edge */
  function edgeKey(edge) {
    return `${edge.source}|${edge.target}|${edge.edge_type || ''}`;
  }

  /** @param {string} nodeId */
  function focusNode(nodeId) {
    selectedNodeId = nodeId;
    network?.selectNodes([nodeId]);
    network?.focus(nodeId, { scale: 1.15, animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
    const node = nodeById.get(nodeId);
    if (node) {
      renderNodeDetail(node);
    }
  }

  /** @param {GraphNode | undefined} node */
  function renderNodeDetail(node) {
    if (!node || !detailContent) {
      return;
    }

    const label = node.qualified_name || node.name || node.id;
    const subtitle = node.file_path || node.node_type || '';
    const badges = [];
    if (deadCodeSet.has(node.id)) {
      badges.push('<span class="badge dead">DEAD</span>');
    }
    if (godNodeScores.has(node.id)) {
      badges.push('<span class="badge god">GOD</span>');
    }
    if (node.is_bridge) {
      badges.push('<span class="badge bridge">BRIDGE</span>');
    }

    const metaRows = Object.entries(node)
      .filter(([key]) => !['id', 'node_id'].includes(key))
      .slice(0, 16)
      .map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(formatValue(value))}</td></tr>`)
      .join('');

    detailContent.innerHTML = `
      <div class="detail-title">${escapeHtml(String(label))}</div>
      <div class="detail-subtitle">${escapeHtml(String(subtitle))}</div>
      ${badges.length ? `<div class="badge-row">${badges.join('')}</div>` : ''}
      <div class="metric-grid">
        <div class="metric"><div class="value">${node.complexity ?? '—'}</div><div class="key">Complexity</div></div>
        <div class="metric"><div class="value">${node.churn ?? '—'}</div><div class="key">Churn</div></div>
      </div>
      <table class="meta-table">${metaRows}</table>
    `;
  }

  /** @param {string} query */
  function scheduleSearch(query) {
    if (searchTimer) {
      clearTimeout(searchTimer);
    }
    searchTimer = window.setTimeout(() => {
      renderSearchResults(query.trim().toLowerCase());
    }, SEARCH_DEBOUNCE_MS);
  }

  /** @param {string} query */
  function renderSearchResults(query) {
    if (!searchResults) {
      return;
    }
    if (!query) {
      searchResults.classList.add('hidden');
      searchResults.replaceChildren();
      return;
    }

    const matches = (graphDocument?.nodes ?? [])
      .filter((node) => nodeMatches(node, query))
      .slice(0, 24);

    searchResults.classList.remove('hidden');
    if (!matches.length) {
      searchResults.innerHTML = '<div class="search-item"><span class="label">No matches</span></div>';
      return;
    }

    searchResults.replaceChildren();
    for (const match of matches) {
      const item = document.createElement('div');
      item.className = 'search-item';
      const label = document.createElement('span');
      label.className = 'label';
      label.textContent = nodeLabel(match);
      const meta = document.createElement('span');
      meta.className = 'meta';
      meta.textContent = match.node_type || '';
      item.append(label, meta);
      item.addEventListener('click', () => {
        searchResults.classList.add('hidden');
        if (searchInput) {
          searchInput.value = '';
        }
        focusNode(match.id);
      });
      searchResults.appendChild(item);
    }
  }

  /** @param {GraphNode} node @param {string} query */
  function nodeMatches(node, query) {
    const haystack = [
      node.id,
      node.name,
      node.qualified_name,
      node.file_path,
      node.node_type,
    ].filter(Boolean).join(' ').toLowerCase();
    return haystack.includes(query);
  }

  /** @param {GraphNode} node */
  function nodeLabel(node) {
    if (node.node_type === 'file') {
      return node.file_path || node.name || node.id;
    }
    if (node.node_type === 'symbol') {
      return node.qualified_name || node.name || node.id;
    }
    return node.name || node.id;
  }

  /** @param {string} label */
  function shortLabel(label) {
    const parts = label.split(/[/\\]/);
    const tail = parts[parts.length - 1] || label;
    return tail.length > 28 ? `${tail.slice(0, 25)}…` : tail;
  }

  /** @param {GraphDocument} document */
  function computeStatistics(document) {
    const communities = new Set();
    for (const node of document.nodes) {
      if (node.community_id !== undefined && node.community_id !== null) {
        communities.add(Number(node.community_id));
      }
    }
    return {
      node_count: document.nodes.length,
      edge_count: document.edges.length,
      community_count: communities.size,
    };
  }

  /** @param {GraphNode[]} nodes */
  function countCommunities(nodes) {
    const communities = new Set();
    for (const node of nodes) {
      if (node.community_id !== undefined && node.community_id !== null) {
        communities.add(Number(node.community_id));
      }
    }
    return communities.size;
  }

  /** @param {boolean} pending */
  function setLivePending(pending) {
    liveBadge?.classList.toggle('pending', pending);
  }

  /** @param {string} message @param {number} [duration] */
  function showToast(message, duration = 2500) {
    if (!toast) {
      return;
    }
    toast.textContent = message;
    toast.classList.remove('hidden');
    window.setTimeout(() => toast.classList.add('hidden'), duration);
  }

  /** @param {unknown} value */
  function formatValue(value) {
    if (value === null || value === undefined) {
      return '—';
    }
    if (typeof value === 'object') {
      return JSON.stringify(value);
    }
    return String(value);
  }

  /** @param {string} value */
  function escapeHtml(value) {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** @param {string} iso */
  function formatTimestamp(iso) {
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '—';
    }
  }

  /** @typedef {{ id: string; node_type?: string; name?: string; qualified_name?: string; file_path?: string; community_id?: number; complexity?: number; churn?: number; is_bridge?: boolean; [key: string]: unknown }} GraphNode */
  /** @typedef {{ source: string; target: string; edge_type?: string }} GraphEdge */
  /** @typedef {{ metadata?: { statistics?: Record<string, number> }; nodes: GraphNode[]; edges: GraphEdge[]; intelligence?: Record<string, unknown> | null }} GraphDocument */
  /** @typedef {{ addedNodeIds: string[]; removedNodeIds: string[]; changedNodeIds: string[]; addedEdgeCount: number; removedEdgeCount: number }} GraphDelta */
})();
