# Screenshots

Gallery images for the landing page. Current files are synced from the main repo `assets/` folder.

To refresh from GitHub `main`:

```bash
python -c "
import urllib.request
from pathlib import Path
d = Path('website/assets/screenshots')
b = 'https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets'
for f in ['tui.png', 'live-graph-1.png', 'live-graph-2.png']:
    urllib.request.urlretrieve(b + '/' + f, d / f)
"
```

Add new PNGs here and wire them up in `index.html` inside `.gallery-grid`.
