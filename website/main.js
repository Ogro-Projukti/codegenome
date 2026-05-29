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
