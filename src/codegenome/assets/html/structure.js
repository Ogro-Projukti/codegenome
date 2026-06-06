(function () {
  'use strict';

  const FILES_PAGE_SIZE = 5;

  function complexityTier(value) {
    if (value === null || value === undefined) return 'na';
    if (value <= 5) return 'low';
    if (value <= 10) return 'med';
    return 'high';
  }

  function complexityBadge(value, size) {
    if (value === null || value === undefined) return '';
    const tier = complexityTier(value);
    const sizeClass = size === 'sm' ? ' complexity-badge-sm' : '';
    return `<span class="complexity-badge${sizeClass} tier-${tier}" title="McCabe complexity">${value}</span>`;
  }

  function classKindLabel(kind) {
    if (kind === 'abstract_class') return 'abstract';
    if (kind === 'interface') return 'interface';
    return 'class';
  }

  function codonPill(symbol) {
    const qn = symbol.qualified_name || symbol.name;
    return (
      `<span class="codon-pill" data-qualified-name="${escapeAttr(qn)}">` +
      `<span class="codon-name">${escapeHtml(symbol.name)}</span>` +
      complexityBadge(symbol.complexity, 'sm') +
      `<span class="codon-lines">L${symbol.start_line}</span>` +
      '</span>'
    );
  }

  function classCard(classNode) {
    const methods = (classNode.methods || [])
      .map((method) => codonPill(method))
      .join('');
    return (
      '<article class="structure-class" data-qualified-name="' + escapeAttr(classNode.qualified_name) + '">' +
      '<div class="structure-class-head">' +
      `<span class="structure-class-name">${escapeHtml(classNode.name)}</span>` +
      `<span class="structure-kind">${classKindLabel(classNode.kind)}</span>` +
      complexityBadge(classNode.complexity) +
      '</div>' +
      `<div class="structure-methods">${methods || '<span class="structure-empty">No methods</span>'}</div>` +
      '</article>'
    );
  }

  function fileCard(fileNode) {
    const classes = (fileNode.classes || []).map((item) => classCard(item)).join('');
    const functions = (fileNode.functions || []).map((item) => codonPill(item)).join('');
    return (
      '<article class="structure-file" data-file-path="' + escapeAttr(fileNode.path) + '">' +
      '<header class="structure-file-head">' +
      `<span class="structure-file-path">${escapeHtml(fileNode.path)}</span>` +
      `<span class="structure-file-meta">${(fileNode.classes || []).length} cls · ${countCodons(fileNode)} fn</span>` +
      '</header>' +
      (classes ? `<div class="structure-classes">${classes}</div>` : '') +
      (functions ? `<div class="structure-functions">${functions}</div>` : '') +
      (!classes && !functions ? '<p class="structure-empty">No symbols</p>' : '') +
      '</article>'
    );
  }

  function countCodons(fileNode) {
    const methods = (fileNode.classes || []).reduce((sum, cls) => sum + (cls.methods || []).length, 0);
    return methods + (fileNode.functions || []).length;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }

  function filePathFromSymbolNodeId(nodeId) {
    const text = String(nodeId);
    if (!text.startsWith('symbol:')) return null;
    const rest = text.slice(7);
    const splitAt = rest.lastIndexOf(':');
    if (splitAt <= 0) return null;
    return rest.slice(0, splitAt);
  }

  class StructureMap {
    /**
     * @param {HTMLElement} rootEl Container for the structural tree.
     * @param {{ onLoadMore?: () => void }} [options]
     */
    constructor(rootEl, options) {
      this.rootEl = rootEl;
      this.options = options || {};
      /** @type {object | null} */
      this.tree = null;
      this.renderedCount = 0;
      this.focusFilePath = null;
    }

    /** @param {object} tree StructureTreeResponse */
    setTree(tree, focusFilePath) {
      this.tree = tree;
      this.focusFilePath = focusFilePath || null;
      this.renderedCount = 0;
      this._renderShell();

      const files = tree.files || [];
      let targetCount = FILES_PAGE_SIZE;
      if (this.focusFilePath) {
        const focusIndex = files.findIndex((file) => file.path === this.focusFilePath);
        if (focusIndex >= 0) {
          targetCount = Math.max(FILES_PAGE_SIZE, focusIndex + 1);
        }
      }

      while (this.renderedCount < targetCount && this.renderedCount < files.length) {
        this.loadNextPage();
      }

      if (this.focusFilePath) this._highlightFile(this.focusFilePath);
    }

    getVisibleFilePaths() {
      if (!this.tree) return [];
      return (this.tree.files || []).slice(0, this.renderedCount).map((file) => file.path);
    }

    totalFileCount() {
      return this.tree && this.tree.files ? this.tree.files.length : 0;
    }

    loadNextPage() {
      if (!this.tree) return 0;
      const files = this.tree.files || [];
      const nextEnd = Math.min(this.renderedCount + FILES_PAGE_SIZE, files.length);
      const slice = files.slice(this.renderedCount, nextEnd);
      const filesEl = this.rootEl.querySelector('.structure-files');
      if (!filesEl) return 0;

      for (const fileNode of slice) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = fileCard(fileNode);
        filesEl.appendChild(wrapper.firstElementChild);
      }

      this.renderedCount = nextEnd;
      this._updateLoadMore();
      return slice.length;
    }

    /**
     * Append new codons to visible file cards without rebuilding the tree.
     * @param {object} tree Fresh structure payload.
     * @param {string[]} filePaths Files to patch.
     */
    patchFromTree(tree, filePaths) {
      if (!tree || !filePaths.length) return;
      const pathSet = new Set(filePaths);
      const previousByPath = new Map();
      if (this.tree) {
        for (const file of this.tree.files || []) previousByPath.set(file.path, file);
      }

      for (const file of tree.files || []) {
        if (!pathSet.has(file.path)) continue;
        const fileEl = this.rootEl.querySelector(
          `.structure-file[data-file-path="${cssEscape(file.path)}"]`,
        );
        if (!fileEl) continue;

        const prev = previousByPath.get(file.path);
        this._patchFileCard(fileEl, prev, file);
      }

      this.tree = tree;
      this._updateLoadMore();
    }

    _patchFileCard(fileEl, prevFile, nextFile) {
      const prevFns = new Set((prevFile && prevFile.functions || []).map((fn) => fn.qualified_name));
      const prevMethods = new Map();
      for (const cls of (prevFile && prevFile.classes) || []) {
        for (const method of cls.methods || []) prevMethods.set(method.qualified_name, cls.qualified_name);
      }

      for (const fn of nextFile.functions || []) {
        if (prevFns.has(fn.qualified_name)) continue;
        const container = fileEl.querySelector('.structure-functions') || this._ensureFunctions(fileEl);
        container.insertAdjacentHTML('beforeend', codonPill(fn));
        this._pulsePill(container.lastElementChild);
      }

      for (const cls of nextFile.classes || []) {
        const classEl = fileEl.querySelector(
          `.structure-class[data-qualified-name="${cssEscape(cls.qualified_name)}"]`,
        );
        if (!classEl) {
          const classesEl = fileEl.querySelector('.structure-classes') || this._ensureClasses(fileEl);
          classesEl.insertAdjacentHTML('beforeend', classCard(cls));
          continue;
        }

        const methodsEl = classEl.querySelector('.structure-methods');
        if (!methodsEl) continue;
        const empty = methodsEl.querySelector('.structure-empty');
        if (empty) empty.remove();

        for (const method of cls.methods || []) {
          if (prevMethods.has(method.qualified_name)) continue;
          methodsEl.insertAdjacentHTML('beforeend', codonPill(method));
          this._pulsePill(methodsEl.lastElementChild);
        }

        const badge = classEl.querySelector('.complexity-badge:not(.complexity-badge-sm)');
        if (badge && cls.complexity !== null && cls.complexity !== undefined) {
          badge.textContent = String(cls.complexity);
          badge.className = `complexity-badge tier-${complexityTier(cls.complexity)}`;
        }
      }

      const meta = fileEl.querySelector('.structure-file-meta');
      if (meta) {
        meta.textContent = `${(nextFile.classes || []).length} cls · ${countCodons(nextFile)} fn`;
      }
    }

    _ensureFunctions(fileEl) {
      let el = fileEl.querySelector('.structure-functions');
      if (!el) {
        el = document.createElement('div');
        el.className = 'structure-functions';
        fileEl.appendChild(el);
      }
      return el;
    }

    _ensureClasses(fileEl) {
      let el = fileEl.querySelector('.structure-classes');
      if (!el) {
        el = document.createElement('div');
        el.className = 'structure-classes';
        const head = fileEl.querySelector('.structure-file-head');
        if (head && head.nextSibling) fileEl.insertBefore(el, head.nextSibling);
        else fileEl.appendChild(el);
      }
      return el;
    }

    _pulsePill(pill) {
      if (!pill) return;
      pill.classList.add('codon-new');
      window.setTimeout(() => pill.classList.remove('codon-new'), 1200);
    }

    _highlightFile(filePath) {
      const fileEl = this.rootEl.querySelector(
        `.structure-file[data-file-path="${cssEscape(filePath)}"]`,
      );
      if (!fileEl) return;
      fileEl.classList.add('structure-file-focus');
      fileEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      window.setTimeout(() => fileEl.classList.remove('structure-file-focus'), 1800);
    }

    _renderShell() {
      const packageLabel = this.tree.package || this.tree.module_id || 'package';
      const total = this.totalFileCount();
      this.rootEl.innerHTML =
        '<article class="structure-package">' +
        '<header class="structure-package-head">' +
        '<span class="structure-level-label">Package</span>' +
        `<h2 class="structure-package-name">${escapeHtml(packageLabel)}</h2>` +
        `<span class="structure-package-meta">${total} file${total === 1 ? '' : 's'}</span>` +
        '</header>' +
        '<div class="structure-files"></div>' +
        '<div class="structure-actions"></div>' +
        '</article>';
    }

    _updateLoadMore() {
      const actions = this.rootEl.querySelector('.structure-actions');
      if (!actions) return;
      const remaining = this.totalFileCount() - this.renderedCount;
      actions.innerHTML = '';
      if (remaining <= 0) return;

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'structure-load-more';
      btn.textContent =
        remaining <= FILES_PAGE_SIZE
          ? `Expand / Load Next ${remaining} File${remaining === 1 ? '' : 's'}`
          : 'Expand / Load Next 5 Files';
      btn.addEventListener('click', () => {
        this.loadNextPage();
        if (typeof this.options.onLoadMore === 'function') this.options.onLoadMore();
      });
      actions.appendChild(btn);
    }

    destroy() {
      this.tree = null;
      this.renderedCount = 0;
      this.rootEl.innerHTML = '';
    }
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, '\\$&');
  }

  window.StructureMap = StructureMap;
  window.StructureMapUtils = {
    FILES_PAGE_SIZE,
    filePathFromSymbolNodeId,
    complexityTier,
  };
})();
