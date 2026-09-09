(() => {
  'use strict';
  const root = document.getElementById('reader');
  const pages = JSON.parse(document.getElementById('readerPages').textContent);
  if (!pages.length) return;
  const image = document.getElementById('pageImage'), paper = document.getElementById('paper');
  const stage = document.getElementById('stage'), select = document.getElementById('pageSelect');
  const status = document.getElementById('loadStatus'), pagesDialog = document.getElementById('pagesDialog');
  const clipDialog = document.getElementById('clipDialog'), selection = document.getElementById('selection');
  let index = Number(root.dataset.index), zoom = 1, requestId = 0, clipMode = false, start = null, clipURL = '';
  let pinch = null;
  const cache = new Map();
  const mobile = () => window.matchMedia('(max-width: 700px)').matches;
  const normalURL = page => mobile() && window.devicePixelRatio <= 2 ? page.mobile : page.image;
  const pageURL = () => { const url = new URL(root.dataset.editionUrl, location.origin); url.searchParams.set('page', index + 1); return url.href; };
  function toast(text) { const el = document.getElementById('toast'); el.textContent = text; el.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => el.hidden = true, 3000); }
  function bookmarks() { try { const saved = JSON.parse(localStorage.getItem(root.dataset.bookmarkKey) || '[]'); return Array.isArray(saved) ? saved.filter(n => Number.isInteger(n) && n >= 0 && n < pages.length) : []; } catch (_) { return []; } }
  function controls() {
    select.value = index;
    document.querySelectorAll('[data-action="first"],[data-action="previous"]').forEach(b => b.disabled = index === 0);
    document.querySelectorAll('[data-action="next"],[data-action="last"]').forEach(b => b.disabled = index === pages.length - 1);
    const saved = bookmarks().includes(index), button = document.getElementById('bookmark');
    button.setAttribute('aria-pressed', String(saved)); button.textContent = saved ? '★ Saved' : '☆ Save page';
    document.getElementById('whatsapp').href = 'https://wa.me/?text=' + encodeURIComponent(document.title + ' ' + pageURL());
    document.querySelectorAll('[data-page]').forEach(b => b.setAttribute('aria-current', String(Number(b.dataset.page) === index)));
  }
  function load(url) {
    if (cache.has(url)) return cache.get(url);
    const promise = new Promise((resolve, reject) => { const img = new Image(); img.crossOrigin = 'anonymous'; img.onload = () => resolve(img); img.onerror = reject; img.src = url; });
    cache.set(url, promise);
    // Bound retained decoded images; the browser HTTP cache still supports revisiting pages.
    if (cache.size > 5) cache.delete(cache.keys().next().value);
    promise.catch(() => cache.delete(url));
    return promise;
  }
  function preload() {
    if (navigator.connection?.saveData || /(^|-)2g$/.test(navigator.connection?.effectiveType || '')) return;
    if (pages[index + 1]) load(normalURL(pages[index + 1])).catch(() => {});
  }
  function fitWidth() {
    paper.style.maxWidth = 'none';
    const page = pages[index];
    const fitted = mobile() ? Math.min(stage.clientWidth, stage.clientHeight * page.width / page.height) : Math.min(1200, stage.clientWidth - 48);
    paper.style.width = fitted * zoom + 'px';
    document.getElementById('zoomLabel').textContent = Math.round(zoom * 100) + '%';
  }
  async function show(next, updateURL = true) {
    next = Math.max(0, Math.min(pages.length - 1, next));
    const ticket = ++requestId, page = pages[next];
    status.textContent = 'Opening page ' + (next + 1) + '…';
    root.setAttribute('aria-busy', 'true');
    try {
      await load(normalURL(page));
      if (ticket !== requestId) return;
      index = next; zoom = 1; setClip(false);
      image.removeAttribute('srcset'); image.src = normalURL(page);
      image.width = page.width; image.height = page.height; image.alt = document.title + ' — page ' + page.number;
      fitWidth(); stage.scrollLeft = 0; stage.scrollTop = 0;
      status.textContent = ''; root.removeAttribute('aria-busy'); controls();
      if (updateURL) history.replaceState(null, '', pageURL());
      if (!mobile()) stage.scrollIntoView({block: 'start', behavior: 'instant'});
      preload();
    } catch (_) {
      if (ticket !== requestId) return;
      root.removeAttribute('aria-busy');
      status.textContent = 'Page could not load. Select the page again to retry.';
    }
  }
  async function setZoom(value) {
    zoom = Math.max(1, Math.min(3, value)); fitWidth();
    if (zoom <= 1) return;
    const current = index, ticket = requestId;
    try {
      await load(pages[current].zoom);
      if (index !== current || requestId !== ticket || zoom <= 1) return;
      image.removeAttribute('srcset'); image.src = pages[current].zoom;
    } catch (_) { toast('High-detail image unavailable. Standard view is still available.'); }
  }
  function openPages() {
    const grid = document.getElementById('thumbnails');
    if (!grid.children.length) pages.forEach((page, n) => {
      const button = document.createElement('button'); button.type = 'button'; button.dataset.page = n;
      const thumb = document.createElement('img'); thumb.src = page.thumbnail; thumb.loading = 'lazy'; thumb.decoding = 'async'; thumb.alt = 'Page ' + page.number;
      button.append(thumb, document.createTextNode('Page ' + page.number)); grid.append(button);
    });
    const saved = document.getElementById('savedPages'); saved.replaceChildren();
    bookmarks().forEach(n => { const b = document.createElement('button'); b.type = 'button'; b.dataset.page = n; b.textContent = 'Page ' + (n + 1); saved.append(b); });
    if (!saved.children.length) saved.textContent = 'Use “Save page” to keep a bookmark on this device.';
    controls(); pagesDialog.showModal();
  }
  function setClip(value) { clipMode = value; start = null; selection.hidden = true; stage.classList.toggle('clipping', value); document.getElementById('clipToggle')?.setAttribute('aria-pressed', String(value)); }
  function point(event) { const r = image.getBoundingClientRect(); return {x: Math.max(0, Math.min(r.width, event.clientX - r.left)), y: Math.max(0, Math.min(r.height, event.clientY - r.top))}; }
  image.addEventListener('pointerdown', event => { if (!clipMode) return; event.preventDefault(); start = point(event); image.setPointerCapture(event.pointerId); });
  image.addEventListener('pointermove', event => {
    if (!clipMode || !start) return;
    const end = point(event); selection.hidden = false;
    Object.assign(selection.style, {left: Math.min(start.x,end.x)+'px',top: Math.min(start.y,end.y)+'px',width: Math.abs(end.x-start.x)+'px',height: Math.abs(end.y-start.y)+'px'});
  });
  image.addEventListener('pointerup', event => {
    if (!clipMode || !start) return;
    const end = point(event), origin = start; setClip(false);
    const width = Math.abs(end.x-origin.x), height = Math.abs(end.y-origin.y);
    if (width < 20 || height < 20) return toast('Select a larger area to clip.');
    const ratio = image.naturalWidth/image.clientWidth;
    const canvas = document.createElement('canvas'); canvas.width = Math.round(width*ratio); canvas.height = Math.round(height*ratio);
    try {
      canvas.getContext('2d').drawImage(image, Math.min(origin.x,end.x)*ratio, Math.min(origin.y,end.y)*ratio, canvas.width,canvas.height,0,0,canvas.width,canvas.height);
      canvas.toBlob(blob => {
        if (!blob) return toast('Could not create clipping.');
        if (clipURL) URL.revokeObjectURL(clipURL); clipURL = URL.createObjectURL(blob);
        document.getElementById('clipPreview').src = clipURL;
        const link = document.getElementById('clipDownload'); link.href = clipURL; link.download = 'epaper-page-'+(index+1)+'-clip.png'; clipDialog.showModal();
      }, 'image/png');
    } catch (_) { toast('Clipping is unavailable for this image.'); }
  });
  image.addEventListener('pointercancel', () => setClip(false));
  document.addEventListener('click', async event => {
    const page = event.target.closest('[data-page]');
    if (page) { pagesDialog.close(); show(Number(page.dataset.page)); return; }
    const close = event.target.closest('[data-close]'); if (close) { close.closest('dialog').close(); return; }
    const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
    switch (button.dataset.action) {
      case 'more': { const open = document.querySelector('.toolbar').classList.toggle('more-open'); button.setAttribute('aria-expanded', String(open)); break; }
      case 'next': show(index+1); break; case 'previous': show(index-1); break;
      case 'first': show(0); break; case 'last': show(pages.length-1); break;
      case 'zoom-in': setZoom(zoom+.35); break; case 'zoom-out': setZoom(zoom-.35); break;
      case 'fit': setZoom(1); stage.scrollLeft=0; break;
      case 'pages': openPages(); break;
      case 'fullscreen': try { if (document.fullscreenElement) await document.exitFullscreen(); else await root.requestFullscreen(); } catch (_) { toast('Fullscreen is not supported on this browser.'); } break;
      case 'bookmark': try { const saved = bookmarks(); localStorage.setItem(root.dataset.bookmarkKey, JSON.stringify(saved.includes(index) ? saved.filter(n=>n!==index) : [...saved,index])); controls(); } catch (_) { toast('Bookmarks are unavailable in this browser.'); } break;
      case 'clip': setClip(!clipMode); if (clipMode) toast('Drag across the article to make a clipping.'); break;
      case 'share': try { if (navigator.share) await navigator.share({title:document.title,url:pageURL()}); else { await navigator.clipboard.writeText(pageURL()); toast('Page link copied.'); } } catch (error) { if (error.name !== 'AbortError') toast('Use WhatsApp or copy the address bar link.'); } break;
    }
  });
  select.addEventListener('change', () => show(Number(select.value)));
  document.addEventListener('keydown', event => {
    if (event.target.closest('input,select,textarea,dialog') || document.querySelector('dialog[open]')) return;
    if (event.key==='ArrowRight') { event.preventDefault(); show(index+1); }
    if (event.key==='ArrowLeft') { event.preventDefault(); show(index-1); }
    if (event.key==='Escape') setClip(false);
  });
  let swipe=null;
  const distance = touches => Math.hypot(touches[0].clientX-touches[1].clientX,touches[0].clientY-touches[1].clientY);
  stage.addEventListener('touchstart', event => {
    if (clipMode) return;
    if (event.touches.length===2) { pinch={distance:distance(event.touches),zoom}; swipe=null; }
    else if (event.touches.length===1 && zoom===1) swipe={x:event.touches[0].clientX,y:event.touches[0].clientY,time:Date.now()};
  }, {passive:true});
  stage.addEventListener('touchmove', event => { if (pinch && event.touches.length===2) { event.preventDefault(); zoom=Math.max(1,Math.min(3,pinch.zoom*distance(event.touches)/pinch.distance)); fitWidth(); } }, {passive:false});
  stage.addEventListener('touchend', event => {
    if (pinch) { if (event.touches.length<2) { pinch=null; setZoom(zoom); } return; }
    if (!swipe || clipMode || zoom>1) return;
    const touch=event.changedTouches[0], dx=touch.clientX-swipe.x, dy=touch.clientY-swipe.y;
    if (Math.abs(dx)>60 && Math.abs(dx)>Math.abs(dy)*1.5 && Date.now()-swipe.time<900) show(index+(dx<0?1:-1));
    swipe=null;
  }, {passive:true});
  document.querySelectorAll('.filters select,.filters input').forEach(field => field.addEventListener('change', () => { if (mobile()) field.form.requestSubmit(); }));
  stage.addEventListener('dblclick', event => { if (!clipMode) { event.preventDefault(); setZoom(zoom === 1 ? 2 : 1); } });
  window.addEventListener('resize', fitWidth);
  new ResizeObserver(fitWidth).observe(stage);
  image.addEventListener('error', () => { status.textContent='Image unavailable. Select this page again to retry.'; });
  fitWidth(); controls();
  if (image.complete && image.naturalWidth) preload(); else image.addEventListener('load', preload, {once:true});
})();
