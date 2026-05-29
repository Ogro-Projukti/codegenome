# Codegenome static website

Marketing landing page and **official documentation** for [Codegenome](https://github.com/Ogro-Projukti/codegenome). Pure static HTML/CSS/JS — no build step required.

## Structure

| Path | Purpose |
|------|---------|
| `index.html` | Product landing page |
| `docs/` | Multi-page documentation (Django-style layout) |
| `docs-shell.js` | Shared sidebar, header, footer, TOC, pager |
| `docs.css` | Documentation layout and typography |
| `style.css`, `main.js` | Landing page styles and effects |

## Local preview

From the `website` folder:

```bash
# Python
python -m http.server 8080

# Node (npx)
npx serve .
```

Open `http://localhost:8080` for the landing page and `http://localhost:8080/docs/` for documentation.

## Deploy

Upload the entire `website/` directory to any static host (GitHub Pages, Netlify, S3, etc.). Set the site root to this folder so `/docs/index.html` resolves correctly.

## Documentation map

- **Getting started** — overview, install, quickstart
- **Topics** — graphs, watch/live, exports, TUI, AI/MCP
- **How-to** — Cursor setup, CI builds
- **Reference** — CLI, commands, MCP, tools, artifacts, legacy CLI, troubleshooting
