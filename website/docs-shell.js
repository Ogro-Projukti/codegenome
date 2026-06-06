/**
 * Codegenome documentation shell — injects header, sidebar, footer, and in-page TOC.
 * Static-friendly: works without a build step; set data-site-root on the script tag.
 */
(function () {
  const script = document.currentScript;
  const siteRoot = (script && script.dataset.siteRoot) || '.';

  function asset(path) {
    const base = siteRoot.endsWith('/') ? siteRoot : siteRoot + '/';
    return base + path.replace(/^\//, '');
  }

  const NAV = [
    {
      id: 'docs',
      label: 'Documentation',
      items: [
        { href: 'docs/index.html', label: 'Documentation home', page: 'docs-index' },
        { href: 'docs/intro/overview.html', label: 'Overview', page: 'overview' },
        { href: 'docs/intro/install.html', label: 'Installation', page: 'install' },
        { href: 'docs/intro/quickstart.html', label: 'Quick start', page: 'quickstart' },
      ],
    },
    {
      id: 'topics',
      label: 'Using Codegenome',
      items: [
        { href: 'docs/topics/knowledge-graph.html', label: 'Knowledge graphs', page: 'knowledge-graph' },
        { href: 'docs/topics/watch-live.html', label: 'Watch & live graph', page: 'watch-live' },
        { href: 'docs/topics/exports.html', label: 'Export formats', page: 'exports' },
        { href: 'docs/topics/tui.html', label: 'Terminal UI (TUI)', page: 'tui' },
        { href: 'docs/topics/ai-agents.html', label: 'AI agents & MCP', page: 'ai-agents' },
      ],
    },
    {
      id: 'howto',
      label: 'How-to guides',
      items: [
        { href: 'docs/howto/cursor-setup.html', label: 'Cursor + MCP setup', page: 'cursor-setup' },
        { href: 'docs/howto/ci-pipeline.html', label: 'CI graph builds', page: 'ci-pipeline' },
      ],
    },
    {
      id: 'reference',
      label: 'Reference',
      items: [
        { href: 'docs/reference/cli.html', label: 'CLI overview', page: 'cli' },
        { href: 'docs/reference/commands.html', label: 'Commands', page: 'commands' },
        { href: 'docs/reference/mcp.html', label: 'MCP server', page: 'mcp' },
        { href: 'docs/reference/mcp-tools.html', label: 'MCP tools', page: 'mcp-tools' },
        { href: 'docs/reference/artifacts.html', label: 'Workspace artifacts', page: 'artifacts' },
        { href: 'docs/reference/legacy-cli.html', label: 'Legacy flag CLI', page: 'legacy-cli' },
        { href: 'docs/reference/troubleshooting.html', label: 'Troubleshooting', page: 'troubleshooting' },
      ],
    },
  ];

  const meta = window.DOC_META || {};
  const currentPage = document.body.dataset.page || meta.page || '';

  function resolveHref(href) {
    return asset(href);
  }

  function isActive(item) {
    return item.page === currentPage;
  }

  function buildSidebar() {
    const nav = document.createElement('nav');
    nav.className = 'doc-sidebar-nav';
    nav.setAttribute('aria-label', 'Documentation');

    NAV.forEach((section) => {
      const sectionEl = document.createElement('section');
      sectionEl.className = 'doc-nav-section';

      const heading = document.createElement('h2');
      heading.className = 'doc-nav-heading';
      heading.textContent = section.label;
      sectionEl.appendChild(heading);

      const list = document.createElement('ul');
      list.className = 'doc-nav-list';

      section.items.forEach((item) => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = resolveHref(item.href);
        a.textContent = item.label;
        if (isActive(item)) {
          a.classList.add('is-active');
          a.setAttribute('aria-current', 'page');
        }
        li.appendChild(a);
        list.appendChild(li);
      });

      sectionEl.appendChild(list);
      nav.appendChild(sectionEl);
    });

    return nav;
  }

  function buildHeader() {
    const header = document.createElement('header');
    header.className = 'doc-site-header';
    header.innerHTML = `
      <div class="doc-header-inner">
        <a href="${asset('index.html')}" class="doc-brand">
          <img src="${asset('logo.png')}" alt="Codegenome logo" width="28" height="28" style="border-radius:6px;opacity:0.85;">
          <span class="doc-brand-text">Codegenome</span>
          <span style="font-size:0.65rem;font-weight:500;color:#9CA3AF;background:#EFECE4;border:1px solid #E8E5DE;padding:0.12rem 0.45rem;border-radius:20px;letter-spacing:0.04em;margin-left:0.2rem;font-family:var(--doc-mono, monospace);">docs</span>
        </a>
        <div class="doc-header-links">
          <a href="${asset('docs/index.html')}" class="doc-header-link">Docs</a>
          <a href="${asset('docs/intro/quickstart.html')}" class="doc-header-link">Quick Start</a>
          <a href="${asset('index.html')}" class="doc-header-link">Home</a>
          <a href="https://github.com/Ogro-Projukti/codegenome" class="doc-header-link" target="_blank" rel="noopener">GitHub ↗</a>
        </div>
        <button type="button" class="doc-menu-toggle" aria-expanded="false" aria-controls="doc-sidebar">
          <span class="sr-only">Toggle menu</span>
          <span aria-hidden="true">☰ Menu</span>
        </button>
      </div>
    `;
    return header;
  }

  function buildFooter() {
    const footer = document.createElement('footer');
    footer.className = 'doc-site-footer';
    footer.innerHTML = `
      <p>Codegenome documentation · <a href="https://github.com/Ogro-Projukti/codegenome">Source on GitHub</a> · MIT License</p>
    `;
    return footer;
  }

  function buildToc(content) {
    const headings = content.querySelectorAll('h2[id], h3[id]');
    if (!headings.length) return null;

    const aside = document.createElement('aside');
    aside.className = 'doc-toc';
    aside.setAttribute('aria-label', 'On this page');

    const title = document.createElement('p');
    title.className = 'doc-toc-title';
    title.textContent = 'On this page';
    aside.appendChild(title);

    const list = document.createElement('ul');
    list.className = 'doc-toc-list';

    headings.forEach((h) => {
      const li = document.createElement('li');
      li.className = h.tagName === 'H3' ? 'doc-toc-h3' : 'doc-toc-h2';
      const a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent.replace(/\s*¶\s*$/, '');
      li.appendChild(a);
      list.appendChild(li);
    });

    aside.appendChild(list);
    return aside;
  }

  function buildPager() {
    const flat = NAV.flatMap((s) => s.items);
    const idx = flat.findIndex((i) => i.page === currentPage);
    if (idx < 0) return null;

    const nav = document.createElement('nav');
    nav.className = 'doc-pager';
    nav.setAttribute('aria-label', 'Page navigation');

    if (idx > 0) {
      const prev = flat[idx - 1];
      nav.innerHTML += `<a class="doc-pager-prev" href="${resolveHref(prev.href)}"><span class="doc-pager-label">Previous</span><span class="doc-pager-title">${prev.label}</span></a>`;
    }
    if (idx < flat.length - 1) {
      const next = flat[idx + 1];
      nav.innerHTML += `<a class="doc-pager-next" href="${resolveHref(next.href)}"><span class="doc-pager-label">Next</span><span class="doc-pager-title">${next.label}</span></a>`;
    }
    return nav.innerHTML ? nav : null;
  }

  function init() {
    const content = document.querySelector('.doc-main-content');
    if (!content) return;

    document.body.classList.add('has-doc-shell');

    const shell = document.createElement('div');
    shell.className = 'doc-layout';

    const sidebar = document.createElement('aside');
    sidebar.className = 'doc-sidebar';
    sidebar.id = 'doc-sidebar';
    sidebar.appendChild(buildSidebar());

    const main = document.createElement('div');
    main.className = 'doc-main';

    const article = document.createElement('article');
    article.className = 'doc-article';

    if (meta.title) {
      const h1 = content.querySelector('h1');
      if (!h1) {
        const titleEl = document.createElement('h1');
        titleEl.textContent = meta.title;
        content.insertBefore(titleEl, content.firstChild);
      }
    }

    if (meta.lead) {
      const existing = content.querySelector('.doc-lead');
      if (!existing) {
        const lead = document.createElement('p');
        lead.className = 'doc-lead';
        lead.textContent = meta.lead;
        const h1 = content.querySelector('h1');
        if (h1 && h1.nextSibling) {
          content.insertBefore(lead, h1.nextSibling);
        } else {
          content.prepend(lead);
        }
      }
    }

    article.appendChild(content);
    content.classList.remove('doc-main-content');

    const toc = buildToc(article);
    const pager = buildPager();
    if (pager) article.appendChild(pager);

    main.appendChild(article);
    if (toc) main.appendChild(toc);

    shell.appendChild(sidebar);
    shell.appendChild(main);

    const wrapper = document.createElement('div');
    wrapper.className = 'doc-page-wrap';
    wrapper.appendChild(buildHeader());
    wrapper.appendChild(shell);
    wrapper.appendChild(buildFooter());

    document.body.insertBefore(wrapper, document.body.firstChild);

    const toggle = wrapper.querySelector('.doc-menu-toggle');
    toggle.addEventListener('click', () => {
      const open = document.body.classList.toggle('doc-sidebar-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    document.querySelectorAll('.copy-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const text = btn.getAttribute('data-copy');
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          const orig = btn.textContent;
          btn.textContent = 'Copied';
          setTimeout(() => { btn.textContent = orig; }, 2000);
        } catch (_) { /* ignore */ }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
