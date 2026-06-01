document.addEventListener('DOMContentLoaded', () => {
  // Intersection Observer for scroll animations
  const observerOptions = {
    root: null,
    rootMargin: '0px',
    threshold: 0.1
  };

  const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  document.querySelectorAll('.fade-in').forEach(element => {
    observer.observe(element);
  });

  // Copy to clipboard functionality
  const copyButtons = document.querySelectorAll('.copy-btn');
  copyButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
      const textToCopy = btn.getAttribute('data-copy');
      try {
        await navigator.clipboard.writeText(textToCopy);
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.color = 'var(--accent-color)';
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.color = '';
        }, 2000);
      } catch (err) {
        console.error('Failed to copy text: ', err);
      }
    });
  });

  // Terminal Typewriter Effect
  const terminalBody = document.getElementById('typewriter');
  if (terminalBody) {
    const lines = [
      "$ codegenome analyze .",
      "[*] Initializing CodeGenome Engine...",
      "[*] Parsing 107 files via tree-sitter...",
      "[*] Extracting symbols and relationships...",
      "[*] Committing graph to SQLite...",
      "[*] Architecture graph generated successfully.",
      "$ codegenome tui",
      "[*] Launching Terminal UI..."
    ];

    let lineIndex = 0;
    let charIndex = 0;
    let currentHtml = "";

    function typeWriter() {
      if (lineIndex < lines.length) {
        const currentLine = lines[lineIndex];
        if (charIndex < currentLine.length) {
          // If it's the start of a command line, style it
          if (charIndex === 0 && currentLine.startsWith('$')) {
             currentHtml += '<span class="command">';
          }
          currentHtml += currentLine.charAt(charIndex);
          charIndex++;
          
          if (charIndex === currentLine.length && currentLine.startsWith('$')) {
             currentHtml += '</span>';
          }
          
          terminalBody.innerHTML = currentHtml + '<span class="dither-blink"></span>';
          setTimeout(typeWriter, Math.random() * 30 + 20);
        } else {
          currentHtml += "<br>";
          terminalBody.innerHTML = currentHtml + '<span class="dither-blink"></span>';
          charIndex = 0;
          lineIndex++;
          setTimeout(typeWriter, currentLine.startsWith('$') ? 500 : 200);
        }
      } else {
        // Keep blinking cursor at the end
        terminalBody.innerHTML = currentHtml + '<span class="dither-blink"></span>';
      }
    }

    // Start typewriter when section is visible
    const terminalObserver = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        setTimeout(typeWriter, 500);
        terminalObserver.disconnect();
      }
    });
    
    terminalObserver.observe(document.querySelector('.demo-section'));
  }

  // Screenshot gallery lightbox
  initGallery();

  // Bio-tech canvas background effect
  initCanvas();

  // Scroll Progress logic
  const progressBtn = document.getElementById('explore-progress');
  if (progressBtn) {
    const progressCircle = progressBtn.querySelector('.progress-ring-circle');
    // Using fixed circumference for r=22 (2 * PI * 22 ≈ 138.23)
    const circumference = 138.23;
    
    function setProgress(percent) {
      const offset = circumference - (percent / 100) * circumference;
      progressCircle.style.strokeDashoffset = offset;
    }
    
    window.addEventListener('scroll', () => {
      const scrollY = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const scrollPercent = (scrollY / docHeight) * 100;
      
      // Prevent calculation errors on very short pages
      setProgress(docHeight > 0 ? scrollPercent : 100);
      
      // If near bottom, arrow points up
      if (scrollPercent > 95) {
        progressBtn.classList.add('is-bottom');
        progressBtn.setAttribute('aria-label', 'Scroll to top');
      } else {
        progressBtn.classList.remove('is-bottom');
        progressBtn.setAttribute('aria-label', 'Scroll to bottom');
      }
    });
    
    progressBtn.addEventListener('click', () => {
      if (progressBtn.classList.contains('is-bottom')) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
      }
    });
    
    // Initial call to set correct progress on page load
    window.dispatchEvent(new Event('scroll'));
  }
});

function initGallery() {
  const items = document.querySelectorAll('.gallery-item');
  const lightbox = document.getElementById('gallery-lightbox');
  if (!items.length || !lightbox) return;

  const imgEl = lightbox.querySelector('.gallery-lightbox-img');
  const captionEl = lightbox.querySelector('.gallery-lightbox-caption');
  const slides = Array.from(items).map((btn) => {
    const img = btn.querySelector('img');
    const cap = btn.querySelector('.gallery-caption');
    return {
      src: img?.src || '',
      alt: img?.alt || '',
      caption: cap?.textContent || '',
    };
  });

  let currentIndex = 0;

  function show(index) {
    currentIndex = (index + slides.length) % slides.length;
    const slide = slides[currentIndex];
    imgEl.src = slide.src;
    imgEl.alt = slide.alt;
    captionEl.textContent = slide.caption;
  }

  function open(index) {
    show(index);
    lightbox.hidden = false;
    lightbox.setAttribute('aria-hidden', 'false');
    document.body.classList.add('gallery-open');
    lightbox.querySelector('.gallery-lightbox-close')?.focus();
  }

  function close() {
    lightbox.hidden = true;
    lightbox.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('gallery-open');
    imgEl.removeAttribute('src');
  }

  items.forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.getAttribute('data-gallery-index'), 10);
      open(Number.isNaN(idx) ? 0 : idx);
    });
  });

  lightbox.querySelectorAll('[data-lightbox-close]').forEach((el) => {
    el.addEventListener('click', close);
  });

  lightbox.querySelector('[data-lightbox-prev]')?.addEventListener('click', () => {
    show(currentIndex - 1);
  });

  lightbox.querySelector('[data-lightbox-next]')?.addEventListener('click', () => {
    show(currentIndex + 1);
  });

  document.addEventListener('keydown', (e) => {
    if (lightbox.hidden) return;
    if (e.key === 'Escape') close();
    if (e.key === 'ArrowLeft') show(currentIndex - 1);
    if (e.key === 'ArrowRight') show(currentIndex + 1);
  });
}

function initCanvas() {
  const canvas = document.getElementById('bioCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  let width, height;
  let nodes = [];
  
  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  
  window.addEventListener('resize', resize);
  resize();

  // Create nodes
  const nodeCount = Math.floor((width * height) / 20000); // Responsive density
  for (let i = 0; i < nodeCount; i++) {
    nodes.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      radius: Math.random() * 2 + 1
    });
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    
    // Update and draw nodes
    ctx.fillStyle = '#00ffaa';
    for (let i = 0; i < nodes.length; i++) {
      let node = nodes[i];
      node.x += node.vx;
      node.y += node.vy;
      
      // Bounce off edges
      if (node.x < 0 || node.x > width) node.vx *= -1;
      if (node.y < 0 || node.y > height) node.vy *= -1;
      
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();
    }
    
    // Draw connections
    ctx.strokeStyle = 'rgba(0, 255, 170, 0.15)';
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[i].x - nodes[j].x;
        let dy = nodes[i].y - nodes[j].y;
        let dist = dx * dx + dy * dy;
        
        if (dist < 15000) {
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.stroke();
        }
      }
    }
    
    requestAnimationFrame(draw);
  }
  
  draw();
}

// --- GitHub & PyPI Stats with LocalStorage Cache ---
async function fetchStats() {
  try {
    // Read from cache
    const cachedGh = localStorage.getItem('cg_gh_stats');
    if (cachedGh) {
      const data = JSON.parse(cachedGh);
      const s = document.getElementById('github-stars');
      const f = document.getElementById('github-forks');
      if (s) s.textContent = data.stars;
      if (f) f.textContent = data.forks;
    }
    
    // Fetch fresh
    const ghRes = await fetch('https://api.github.com/repos/Ogro-Projukti/codegenome');
    if (ghRes.ok) {
      const ghData = await ghRes.json();
      const stars = ghData.stargazers_count || 0;
      const forks = ghData.forks_count || 0;
      const s = document.getElementById('github-stars');
      const f = document.getElementById('github-forks');
      if (s) s.textContent = stars;
      if (f) f.textContent = forks;
      localStorage.setItem('cg_gh_stats', JSON.stringify({stars, forks}));
    } else if (!cachedGh) {
      const s = document.getElementById('github-stars');
      const f = document.getElementById('github-forks');
      if (s) s.textContent = "N/A";
      if (f) f.textContent = "N/A";
    }

    // PyPI Stats
    const cachedPypi = localStorage.getItem('cg_pypi_stats');
    const pEl = document.getElementById('pypi-downloads');
    if (cachedPypi && pEl) {
      pEl.textContent = cachedPypi;
    }
    
    const pypiRes = await fetch('https://img.shields.io/pypi/dm/codegenome.json');
    if (pypiRes.ok) {
      const pypiData = await pypiRes.json();
      const val = (pypiData.value || "N/A").replace('/month', '');
      if (pEl) pEl.textContent = val;
      localStorage.setItem('cg_pypi_stats', val);
    } else if (!cachedPypi && pEl) {
      pEl.textContent = "N/A";
    }
  } catch (error) {
    console.error('Error fetching stats:', error);
  }
}

// --- Top Contributors with LocalStorage Cache ---
function renderContributors(contributors) {
  const container = document.getElementById('contributors-grid');
  if (!container) return;
  container.innerHTML = '';
  contributors.forEach(c => {
    const card = document.createElement('a');
    card.href = c.html_url;
    card.target = '_blank';
    card.rel = 'noopener';
    card.className = 'contributor-card';
    card.title = c.login;
    
    const img = document.createElement('img');
    img.src = c.avatar_url;
    img.alt = c.login;
    img.className = 'contributor-avatar';
    img.loading = 'lazy';
    
    const info = document.createElement('div');
    info.className = 'contributor-info';
    
    const name = document.createElement('div');
    name.className = 'contributor-name';
    name.textContent = c.login;
    
    const commits = document.createElement('div');
    commits.className = 'contributor-commits';
    commits.textContent = `${c.contributions} commit${c.contributions !== 1 ? 's' : ''}`;
    
    info.appendChild(name);
    info.appendChild(commits);
    
    card.appendChild(img);
    card.appendChild(info);
    
    container.appendChild(card);
  });
}

async function fetchContributors() {
  const container = document.getElementById('contributors-grid');
  try {
    const cached = localStorage.getItem('cg_contributors');
    if (cached) {
      renderContributors(JSON.parse(cached));
    }
    
    // Fetch recent commits to bypass GitHub's /contributors cache which can be delayed by 24h
    const res = await fetch('https://api.github.com/repos/Ogro-Projukti/codegenome/commits?per_page=100');
    if (res.ok) {
      const commits = await res.json();
      const contributorMap = new Map();
      
      commits.forEach(item => {
        // Linked GitHub accounts
        if (item.author && item.author.login) {
          const login = item.author.login;
          if (!contributorMap.has(login)) {
            contributorMap.set(login, {
              login: login,
              avatar_url: item.author.avatar_url,
              html_url: item.author.html_url,
              contributions: 1
            });
          } else {
            contributorMap.get(login).contributions++;
          }
        } 
        // Unlinked/anonymous commits
        else if (item.commit && item.commit.author) {
          const name = item.commit.author.name;
          if (!contributorMap.has(name)) {
            contributorMap.set(name, {
              login: name,
              avatar_url: 'https://ui-avatars.com/api/?name=' + encodeURIComponent(name) + '&background=0a1f18&color=00ffaa',
              html_url: 'https://github.com/Ogro-Projukti/codegenome/commits?author=' + encodeURIComponent(name),
              contributions: 1
            });
          } else {
            contributorMap.get(name).contributions++;
          }
        }
      });

      // Sort by contributions descending
      const contributors = Array.from(contributorMap.values()).sort((a, b) => b.contributions - a.contributions);

      renderContributors(contributors);
      localStorage.setItem('cg_contributors', JSON.stringify(contributors));
    } else if (!cached && container) {
      container.innerHTML = 'Failed to load contributors.';
    }
  } catch (error) {
    console.error('Error fetching contributors:', error);
    if (container && !localStorage.getItem('cg_contributors')) {
      container.innerHTML = 'Failed to load contributors.';
    }
  }
}

// Initialize fetches on load
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('community')) {
    fetchStats();
    fetchContributors();
  }
});
