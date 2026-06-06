(function () {
  'use strict';

  /**
   * 3D double-helix canvas renderer with a scroll-synced virtual window.
   * Only bases whose helix Y intersects the viewport are projected and drawn.
   */
  const BASE_COLORS = {
    A: '#9b59b6',
    'A*': '#c39bd3',
    T: '#20b2aa',
    G: '#ff7f50',
    C: '#4e79a7',
    'G!': '#ff2244',
  };

  const PITCH = 16;
  const RADIUS = 72;
  const TWIST = 0.42;
  const BASE_RADIUS = 5.5;
  const OVERSCAN = 24;
  const ROTATION_SPEED = 0.004;
  const POOL_CAPACITY = 512;

  function normalizeBase(letter) {
    const raw = String(letter || 'A').trim();
    if (raw === 'G!' || raw.toUpperCase() === 'G!') return 'G!';
    if (raw === 'A*' || raw.toUpperCase() === 'A*') return 'A*';
    return raw.toUpperCase();
  }

  function baseColor(letter) {
    const key = normalizeBase(letter);
    return BASE_COLORS[key] || BASE_COLORS.A;
  }

  function isAlertBase(letter) {
    return normalizeBase(letter) === 'G!';
  }

  function isAbstractBase(letter) {
    return normalizeBase(letter) === 'A*';
  }

  function drawBaseLabel(ctx, letter, sx, sy) {
    const base = normalizeBase(letter);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    if (base === 'A*') {
      ctx.font = 'bold 6px Segoe UI, system-ui, sans-serif';
      ctx.fillText('A*', sx, sy);
      return;
    }
    if (base === 'G!') {
      ctx.font = 'bold 7px Segoe UI, system-ui, sans-serif';
      ctx.fillText('G', sx, sy);
      return;
    }
    ctx.font = 'bold 7px Segoe UI, system-ui, sans-serif';
    ctx.fillText(base, sx, sy);
  }

  class HelixRenderer {
    /**
     * @param {HTMLElement} scrollEl Scroll container tracking viewport position.
     * @param {HTMLCanvasElement} canvas Overlay canvas (viewport-sized).
     * @param {HTMLElement} spacerEl Inner spacer setting total scroll height.
     */
    constructor(scrollEl, canvas, spacerEl) {
      this.scrollEl = scrollEl;
      this.canvas = canvas;
      this.spacerEl = spacerEl;
      this.ctx = canvas.getContext('2d', { alpha: true });
      this.nodes = [];
      this.rotation = 0;
      this.running = false;
      this.rafId = 0;
      this.visibleStart = 0;
      this.visibleEnd = 0;
      this._pool = Array.from({ length: POOL_CAPACITY }, () => ({
        index: -1,
        sx: 0,
        sy: 0,
        depth: 0,
        color: BASE_COLORS.A,
        alert: false,
        abstract: false,
        strand: 0,
      }));
      this._onScroll = () => this._updateVisibleRange();
      this._onResize = () => this._resizeCanvas();
      scrollEl.addEventListener('scroll', this._onScroll, { passive: true });
      window.addEventListener('resize', this._onResize);
    }

    /** @param {{ nodes: object[], edges?: object[], health_score?: number, alerts?: string[] }} graph */
    setData(graph) {
      this.nodes = (graph && graph.nodes) || [];
      const totalHeight = Math.max(this.nodes.length * PITCH, this.scrollEl.clientHeight);
      this.spacerEl.style.height = `${totalHeight}px`;
      this.scrollEl.scrollTop = 0;
      this._updateVisibleRange();
      this._resizeCanvas();
    }

    start() {
      if (this.running) return;
      this.running = true;
      this._loop();
    }

    stop() {
      this.running = false;
      if (this.rafId) {
        cancelAnimationFrame(this.rafId);
        this.rafId = 0;
      }
    }

    destroy() {
      this.stop();
      this.scrollEl.removeEventListener('scroll', this._onScroll);
      window.removeEventListener('resize', this._onResize);
      this.nodes = [];
    }

    _resizeCanvas() {
      const rect = this.scrollEl.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, Math.floor(rect.width));
      const h = Math.max(1, Math.floor(rect.height));
      this.canvas.width = Math.floor(w * dpr);
      this.canvas.height = Math.floor(h * dpr);
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._updateVisibleRange();
    }

    _updateVisibleRange() {
      const scrollTop = this.scrollEl.scrollTop;
      const viewH = this.scrollEl.clientHeight;
      const start = Math.max(0, Math.floor(scrollTop / PITCH) - OVERSCAN);
      const end = Math.min(
        this.nodes.length - 1,
        Math.ceil((scrollTop + viewH) / PITCH) + OVERSCAN,
      );
      this.visibleStart = start;
      this.visibleEnd = Math.max(start, end);
    }

    _helixPoint(index, strandOffset, scrollTop, viewW, viewH) {
      const angle = index * TWIST + this.rotation + strandOffset;
      const x = RADIUS * Math.cos(angle);
      const z = RADIUS * Math.sin(angle);
      const worldY = index * PITCH;
      const screenY = worldY - scrollTop + viewH * 0.08;
      const tilt = 0.55;
      const screenX = viewW * 0.5 + x - z * tilt;
      const depth = z;
      return { sx: screenX, sy: screenY, depth };
    }

    _loop() {
      if (!this.running) return;
      this.rotation += ROTATION_SPEED;
      this._drawFrame();
      this.rafId = requestAnimationFrame(() => this._loop());
    }

    _drawFrame() {
      const ctx = this.ctx;
      const viewW = this.canvas.width / (window.devicePixelRatio || 1);
      const viewH = this.canvas.height / (window.devicePixelRatio || 1);
      const scrollTop = this.scrollEl.scrollTop;

      ctx.clearRect(0, 0, viewW, viewH);

      const start = this.visibleStart;
      const end = this.visibleEnd;
      if (end < start || this.nodes.length === 0) return;

      const slots = Math.min((end - start + 1) * 3, POOL_CAPACITY);
      let slotIdx = 0;

      for (let i = start; i <= end; i++) {
        const node = this.nodes[i];
        if (!node) continue;
        const letter = normalizeBase(node.base);
        const color = baseColor(letter);
        const alert = isAlertBase(letter);
        const abstract = isAbstractBase(letter);

        const p1 = this._helixPoint(i, 0, scrollTop, viewW, viewH);
        const p2 = this._helixPoint(i, Math.PI, scrollTop, viewW, viewH);

        if (p1.sy < -BASE_RADIUS * 2 || p1.sy > viewH + BASE_RADIUS * 2) continue;

        const midY = (p1.sy + p2.sy) * 0.5;
        if (midY < -BASE_RADIUS * 2 || midY > viewH + BASE_RADIUS * 2) continue;

        if (slotIdx < slots) {
          const s1 = this._pool[slotIdx++];
          s1.index = i;
          s1.sx = p1.sx;
          s1.sy = p1.sy;
          s1.depth = p1.depth;
          s1.color = '#3d4f66';
          s1.alert = false;
          s1.abstract = false;
          s1.strand = 0;
        }

        if (slotIdx < slots) {
          const s2 = this._pool[slotIdx++];
          s2.index = i;
          s2.sx = p2.sx;
          s2.sy = p2.sy;
          s2.depth = p2.depth;
          s2.color = '#3d4f66';
          s2.alert = false;
          s2.abstract = false;
          s2.strand = 1;
        }

        if (slotIdx < slots) {
          const base = this._pool[slotIdx++];
          base.index = i;
          base.sx = p1.sx;
          base.sy = p1.sy;
          base.depth = p1.depth + 0.01;
          base.color = color;
          base.alert = alert;
          base.abstract = abstract;
          base.strand = 2;
        }
      }

      const visible = this._pool.slice(0, slotIdx);
      const backbones = visible.filter((item) => item.strand === 0 || item.strand === 1);
      const bases = visible.filter((item) => item.strand === 2);
      backbones.sort((a, b) => a.depth - b.depth);
      bases.sort((a, b) => a.depth - b.depth);

      for (let i = start; i <= end; i++) {
        const s1 = backbones.find((slot) => slot.index === i && slot.strand === 0);
        const s2 = backbones.find((slot) => slot.index === i && slot.strand === 1);
        if (!s1 || !s2) continue;
        ctx.strokeStyle = 'rgba(86, 182, 242, 0.22)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(s1.sx, s1.sy);
        ctx.lineTo(s2.sx, s2.sy);
        ctx.stroke();
      }

      for (const item of backbones) {
        ctx.fillStyle = item.color;
        ctx.beginPath();
        ctx.arc(item.sx, item.sy, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const item of bases) {
        const r = BASE_RADIUS;
        ctx.fillStyle = item.color;
        ctx.beginPath();
        ctx.arc(item.sx, item.sy, r, 0, Math.PI * 2);
        ctx.fill();

        drawBaseLabel(ctx, this.nodes[item.index].base, item.sx, item.sy);

        if (item.abstract) {
          ctx.strokeStyle = 'rgba(195, 155, 211, 0.9)';
          ctx.lineWidth = 1.5;
          ctx.setLineDash([2, 2]);
          ctx.beginPath();
          ctx.arc(item.sx, item.sy, r + 2.5, 0, Math.PI * 2);
          ctx.stroke();
          ctx.setLineDash([]);
        }

        if (item.alert) {
          const pulse = 0.6 + 0.4 * Math.sin(this.rotation * 6);
          ctx.strokeStyle = `rgba(255, 34, 68, ${0.35 + pulse * 0.45})`;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(item.sx, item.sy, r + 3 + pulse * 2, 0, Math.PI * 2);
          ctx.stroke();

          ctx.fillStyle = '#ff2244';
          ctx.font = 'bold 9px Segoe UI, system-ui, sans-serif';
          ctx.fillText('!', item.sx + r + 4, item.sy - r - 2);
        }
      }
    }
  }

  window.HelixRenderer = HelixRenderer;
})();
