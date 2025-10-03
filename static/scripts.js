// --- COUNTER HELPERS (use everywhere instead of touching a single #wishlistCount) ---
function setWishlistCount(n){
  document.querySelectorAll('#wishlistCount, .js-wishlist-count, [data-role="wishlistCount"]')
    .forEach(el => el.textContent = String(Math.max(0, Number(n)||0)));
}
function setCompareCount(n){
  document.querySelectorAll('#compareCount, .js-compare-count, [data-role="compareCount"]')
    .forEach(el => el.textContent = String(Math.max(0, Number(n)||0)));
}

(() => {
  'use strict';

  /* ---------------- Helpers (single copy) ---------------- */
  const $  = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  const usd   = new Intl.NumberFormat('en-US', { style:'currency', currency:'USD', maximumFractionDigits: 0 });
  const money = (n) => usd.format(Math.max(0, Number(n) || 0));
  const toNumber = (v, fallback=0) => {
    const n = parseFloat(String(v ?? '').replace(/[, $]/g, ''));
    return Number.isFinite(n) ? n : fallback;
  };

  function getCSRF(){
    // cookie first
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    // hidden input fallback
    const i = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (i?.value) return i.value;
    // meta fallback
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta?.content || '';
  }

  /* ---------------- Finance (redirect only) ---------------- */
  function monthlyPayment(principal, aprPct, months){
    const n = Math.max(1, Number(months) || 1);
    const r = Math.max(0, Number(aprPct) || 0) / 1200;
    if (!r) return principal / n;
    const f = Math.pow(1 + r, n);
    return principal * (r * f) / (f - 1);
  }
  function goToOffers(price, down, apr, term){
    const params = new URLSearchParams({
      price: String(Math.round(price || 0)),
      down : String(Math.round(down  || 0)),
      apr  : String(apr || 0),
      term : String(Math.round(term || 60)),
    });
    window.location.assign(`/finance/offers/?${params.toString()}`);
  }

  // Quick finance in hero (live monthly + redirect)
  (function wireQuickFinance(){
    const form  = $('#quickCalcForm');
    if (!form) return;

    const priceI = $('#qPrice'), downI = $('#qDown'), aprI = $('#qApr'), termI = $('#qTerm'), out = $('#qMonthly');

    function update(){
      const price = toNumber(priceI?.value);
      const down  = Math.min(price, toNumber(downI?.value));
      const apr   = toNumber(aprI?.value);
      const term  = Math.min(84, Math.max(12, Math.round(toNumber(termI?.value, 60))));
      const m = monthlyPayment(Math.max(0, price - down), apr, term);
      if (out) out.textContent = money(m);
    }
    ['input','change'].forEach(evt => [priceI, downI, aprI, termI].forEach(el => el && el.addEventListener(evt, update)));
    update();

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      goToOffers(toNumber(priceI?.value), toNumber(downI?.value), toNumber(aprI?.value), toNumber(termI?.value, 60));
    });
  })();

  // Detail finance (inside car modal)
  (function wireDetailFinance(){
    const form = $('#calcForm');
    if (!form) return;

    const downI = $('#downPayment'), aprI = $('#apr'), termI = $('#term'), out = $('#monthly');

    function update(){
      const price = toNumber($('#detailPrice')?.textContent);
      const down  = toNumber(downI?.value);
      const apr   = toNumber(aprI?.value);
      const term  = Math.min(84, Math.max(12, Math.round(toNumber(termI?.value, 60))));
      const m = monthlyPayment(Math.max(0, price - down), apr, term);
      if (out) out.textContent = money(m);
    }
    ['input','change'].forEach(evt => [downI, aprI, termI].forEach(el => el && el.addEventListener(evt, update)));
    update();

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const price = toNumber($('#detailPrice')?.textContent);
      goToOffers(price, toNumber(downI?.value), toNumber(aprI?.value), toNumber(termI?.value, 60));
    });
  })();


  /* ---------------- Compare (AJAX + drawer + modal) ---------------- */
  let compareItems = []; // server is the source of truth

  function paintCompareDrawer(){
    const n = compareItems.length;
    const drawer = $('.sticky-compare');
    const thumbs = $('#compareThumbs');
    const open   = $('#openCompare');
    const countB = $('#compareCount');
    const hint   = $('#compareHint');

    if (countB) countB.textContent = String(n);
    if (drawer) drawer.style.display = n ? 'block' : 'none';
    if (open)   open.disabled = n < 2;
    if (hint)   hint.textContent = n ? `Selected ${n} of 4` : 'Select up to 4 to compare';

    if (thumbs){
      thumbs.innerHTML = '';
      compareItems.forEach(it => {
        const div = document.createElement('div');
        div.className = 'd-flex align-items-center gap-2 border rounded-pill px-2 py-1';
        div.innerHTML = `
          <img src="${it.cover || '/static/img/sample1.jpg'}" class="rounded" style="width:32px;height:32px;object-fit:cover" alt="">
          <small class="text-secondary">${it.title || 'Vehicle'}</small>
          <button class="btn btn-sm btn-link text-danger p-0 remove-compare" data-id="${it.id}" title="Remove">
            <i class="bi bi-x-circle"></i>
          </button>`;
        thumbs.appendChild(div);
      });
    }
  }

  async function postToggle(url){
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With':'XMLHttpRequest', 'X-CSRFToken': getCSRF() },
      credentials: 'same-origin'
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'toggle failed');
    compareItems = data.items || [];
    if (typeof data.count === 'number') $('#compareCount')?.replaceChildren(document.createTextNode(String(data.count)));
    paintCompareDrawer();
    return data;
  }

  // Toggle from any ".add-compare" link
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.add-compare');
    if (!btn) return;

    e.preventDefault(); // prevent <a> navigation
    const url = btn.dataset.href || btn.getAttribute('href');
    if (!url) return;

    btn.setAttribute('disabled', 'disabled');
    try{
      const data = await postToggle(url);
      const active = data.in_compare === true;
      btn.classList.toggle('btn-primary', active);
      btn.classList.toggle('btn-outline-primary', !active);
    }catch(err){
      console.error('Compare toggle error:', err);
    }finally{
      btn.removeAttribute('disabled');
    }
  });

  // Remove from drawer
  $('#compareThumbs')?.addEventListener('click', (e) => {
    const rm = e.target.closest('.remove-compare');
    if (!rm) return;
    e.preventDefault();
    postToggle(`/compare/${rm.dataset.id}/toggle/`).catch(console.error);
  });

  // Clear all (loop toggles)
  $('#clearCompare')?.addEventListener('click', async (e) => {
    e.preventDefault();
    const snapshot = compareItems.slice();
    for (const it of snapshot) {
      try { await postToggle(`/compare/${it.id}/toggle/`); } catch (_) {}
    }
    compareItems = [];
    paintCompareDrawer();
  });

  // Fill compare modal table when opened
  $('#compareModal')?.addEventListener('show.bs.modal', () => {
    $$('#compareTable [data-spec]').forEach(td => td.textContent = '—');
    compareItems.slice(0, 4).forEach((it, idx) => {
      const i = idx + 1;
      const set = (k, v) => { const el = document.querySelector(`[data-spec="${k}-${i}"]`); if (el) el.textContent = v ?? '—'; };
      set('price',   it.price   != null ? money(Math.round(it.price))                 : '—');
      set('mileage', it.mileage != null ? `${Number(it.mileage).toLocaleString()} mi` : '—');
      set('fuel',    it.fuel || '—');
      set('trans',   it.transmission || '—');
      set('body',    it.body || '—');
    });
  });

  /* ---------------- Car Detail Modal population ---------------- */
  (function wireCarModal(){
    const modal = $('#carDetailModal');
    if (!modal) return;

    let carouselInstance = null;

    modal.addEventListener('show.bs.modal', (ev) => {
      const t = ev.relatedTarget;
      if (!t) return;

      // Read datasets from the clicked "View Details" button/link
      const title    = t.dataset.title || 'Vehicle';
      const priceNum = toNumber(t.dataset.price);
      const mileage  = t.dataset.mileage || '';
      const trans    = t.dataset.transmission || '';
      const fuel     = t.dataset.fuel || '';
      const overview = t.dataset.overview || '';
      const history  = t.dataset.history || '';
      const sName    = t.dataset.sellerName || '';
      const sMeta    = t.dataset.sellerMeta || '';

      // Title & price
      const titleEl = $('#carModalTitle', modal) || $('.modal-title', modal);
      if (titleEl) titleEl.textContent = title;
      const priceEl = $('#detailPrice', modal);
      if (priceEl) priceEl.textContent = priceNum ? money(priceNum) : '—';

      // Small headline specs
      $('.modal-mileage', modal)?.replaceChildren(document.createTextNode(mileage || '—'));
      $('.modal-transmission', modal)?.replaceChildren(document.createTextNode(trans || '—'));
      $('.modal-fuel', modal)?.replaceChildren(document.createTextNode(fuel || '—'));

      // Build gallery images from data-images JSON, then fallbacks
      let images = [];
      try { images = JSON.parse(t.dataset.images || '[]'); } catch (_) {}
      if (!images.length && t.dataset.cover) images = [t.dataset.cover];
      if (!images.length) {
        const cardImg = t.closest('.card')?.querySelector('img.card-img-top');
        if (cardImg?.src) images = [cardImg.src];
      }
      if (!images.length) images = ['/static/img/sample1.jpg'];

      // Insert slides
      const inner = $('#carModalCarouselInner', modal) || $('#cdCarouselInner', modal) || $('#carousel .carousel-inner', modal);
      if (inner) {
        inner.innerHTML = images.map((src, i) => `
          <div class="carousel-item ${i === 0 ? 'active' : ''}">
            <div class="ratio ratio-16x9">
              <img src="${src}" class="w-100 h-100" style="object-fit:cover" alt="${title} ${i+1}">
            </div>
          </div>`).join('');
      }

      // Start/reset carousel
      const carCarouselEl = $('#cdCarousel', modal) || $('#carousel', modal);
      if (carCarouselEl) {
        if (carouselInstance) { try { carouselInstance.dispose(); } catch (_) {} }
        carouselInstance = bootstrap.Carousel.getOrCreateInstance(carCarouselEl, { interval: 0, wrap: true });
        carouselInstance.to(0);
      }
    });
  })();

  /* ---------------- Keep scroll at results on submit ---------------- */
  $('#filtersForm')?.addEventListener('submit', function(){ this.action = location.pathname + '#results'; });
  $('#primarySearchForm')?.addEventListener('submit', function(){ this.action = location.pathname + '#results'; });
})();

(() => {
  'use strict';

  const $ = (sel, root=document) => root.querySelector(sel);

  // 1) Counters: pull from backend, and live-update when your toggle code fires
  async function refreshNavCounters() {
    try {
      const res = await fetch('/api/counters/', { credentials: 'same-origin' });
      if (!res.ok) return;
      const data = await res.json();
      setWishlistCount(data.wishlist ?? data.wishlist_count ?? 0);
      setCompareCount(data.compare ?? data.compare_count ?? 0);
    } catch (_) {}
  }
  document.addEventListener('DOMContentLoaded', refreshNavCounters);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshNavCounters(); });

  // Listen for cross-page updates
  document.addEventListener('wishlist:updated', (e) => setWishlistCount(e.detail?.count ?? 0));
  document.addEventListener('compare:updated',  (e) => setCompareCount(e.detail?.count  ?? 0));

  // 2) Search (desktop + mobile)
  function wireSearchForm(id){
    const form = document.getElementById(id);
    if (!form) return;
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = form.querySelector('input[type="search"]');
      const q = (input?.value || '').trim();
      const params = new URLSearchParams(window.location.search);
      if (q) params.set('q', q); else params.delete('q');
      window.location.assign('/?' + params.toString() + '#results');
    });
  }
  wireSearchForm('globalSearchForm');
  wireSearchForm('globalSearchFormMobile');

  // 3) Icon buttons
  const wishlistBtn = document.getElementById('wishlistBtn');
  if (wishlistBtn) {
    wishlistBtn.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.assign('/wishlist/');
    });
  }
  const compareBtn = document.getElementById('compareBtn');
  if (compareBtn) {
    compareBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const modal = document.getElementById('compareModal');
      if (modal && window.bootstrap) {
        bootstrap.Modal.getOrCreateInstance(modal).show();
      } else {
        window.location.assign('/compare/');
      }
    });
  }
})();

document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('start360Btn');
  var el  = document.getElementById('cdCarousel');
  if (!btn || !el) return;

  // Bootstrap instance (if bundle is loaded)
  var Carousel = (window.bootstrap && window.bootstrap.Carousel) ? window.bootstrap.Carousel : null;
  var inst = Carousel ? (Carousel.getInstance(el) || new Carousel(el, { interval: false, wrap: true, pause: false })) : null;

  var timer = null;

  function start() {
    // need at least 2 slides
    if (el.querySelectorAll('.carousel-item').length < 2) {
      btn.classList.add('disabled');
      btn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Need 2+ images';
      return;
    }
    if (inst) inst.pause();
    timer = setInterval(function(){ if (inst) inst.next(); }, 400);
    btn.dataset.playing = "1";
    btn.innerHTML = '<i class="bi bi-pause-circle"></i> Stop 360°';
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    if (inst) inst.pause();
    btn.dataset.playing = "";
    btn.innerHTML = '<i class="bi bi-arrows-angle-expand"></i> Start 360° View';
  }

  btn.addEventListener('click', function(){
    if (btn.dataset.playing) { stop(); } else { start(); }
  });
});

(() => {
  const $ = (s, r=document) => r.querySelector(s);
  const moneyFmt = new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0});

  // Finance calc
  const priceEl = $('#detailPrice');
  const basePrice = parseFloat(priceEl?.dataset.price || '0') || 0;
  const dp=$('#downPayment'), apr=$('#apr'), term=$('#term'), out=$('#monthly'), form=$('#calcForm');
  const mp = (P, aprPct, n) => { const r=(Number(aprPct||0)/100)/12, N=Math.max(1,parseInt(n||60,10)); if(!r) return P/N; const f=Math.pow(1+r,N); return P*(r*f)/(f-1); };
  const update = () => {
    const d=Math.max(0, parseFloat(dp?.value||'0')||0);
    const a=parseFloat(apr?.value||'0')||0;
    const n=parseInt(term?.value||'60',10);
    const m=mp(Math.max(0, basePrice-d), a, n);
    if(out) out.textContent = moneyFmt.format(isFinite(m)?m:0);
  };
  ['input','change'].forEach(evt => [dp,apr,term].forEach(x => x && x.addEventListener(evt, update)));
  update();
  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    const params = new URLSearchParams({
      max_price: String(Math.round(basePrice||0)),
      down: String(Math.round(parseFloat(dp.value||'0')||0)),
      apr: String(parseFloat(apr.value||'0')||0),
      term: String(parseInt(term.value||'60',10)||60)
    });
    window.location.assign(`/finance/offers/?${params.toString()}`);
  });
})();

// SHARE (single copy; fixed IIFE boundary)
(() => {
  const isLocalhost = () => /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(location.origin);

  function getShareData(btn){
    return {
      url:   btn.dataset.shareUrl || btn.dataset.url || location.href,
      title: btn.dataset.shareTitle || btn.dataset.title || document.title
    };
  }

  async function copyToClipboard(text){
    try {
      if (navigator.clipboard && (window.isSecureContext || isLocalhost())) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch(_) {}
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch(_) { return false; }
  }

  function flashTooltip(btn, text){
    if (!window.bootstrap) return;
    let tip = bootstrap.Tooltip.getInstance(btn);
    if (!tip) tip = new bootstrap.Tooltip(btn, { trigger: 'manual' });

    const attr = btn.hasAttribute('data-bs-title') ? 'data-bs-title' : 'title';
    const original = btn.getAttribute(attr) || 'Share link';
    btn.setAttribute(attr, text);
    if (tip.setContent) tip.setContent({ '.tooltip-inner': text });
    tip.show();

    setTimeout(() => {
      tip.hide();
      btn.setAttribute(attr, original);
      if (tip.setContent) tip.setContent({ '.tooltip-inner': original });
    }, 1200);
  }

  async function onShareClick(e){
    e.preventDefault();
    const btn = e.currentTarget;
    const { url, title } = getShareData(btn);
    const canShare = typeof navigator.share === 'function' && (window.isSecureContext || isLocalhost());

    try {
      if (canShare) {
        await navigator.share({ title, url });
        flashTooltip(btn, 'Shared');
      } else {
        const ok = await copyToClipboard(url);
        flashTooltip(btn, ok ? 'Copied!' : 'Copy failed');
      }
    } catch(_) {
      // user canceled → no-op
    }
  }

  document.querySelectorAll('#shareBtn, #shareBtn2, #shareBtn3, .share-btn, .share-card').forEach(btn => {
    if (!btn.hasAttribute('data-bs-toggle')) btn.setAttribute('data-bs-toggle', 'tooltip');
    if (!btn.hasAttribute('data-bs-title')) btn.setAttribute('data-bs-title', 'Share link');
    if (window.bootstrap) bootstrap.Tooltip.getOrCreateInstance(btn, { trigger: 'manual' });
    btn.addEventListener('click', onShareClick, { passive: false });
  });
})();

// RATING STARS
(function(){
  const id   = "{{ car.id }}";
  const wrap = document.getElementById("stars-" + id);
  if(!wrap) return;

  const hidden = document.getElementById("rating-" + id);
  const hint   = document.getElementById("stars-hint-" + id);
  const btns   = Array.from(wrap.querySelectorAll(".star"));
  const icons  = btns.map(b => b.querySelector("i"));
  let value    = parseFloat(wrap.dataset.value || hidden.value || "0") || 0;

  function paint(v){
    icons.forEach((ic, i) => {
      const n = i + 1;
      ic.className = "fa-regular fa-star";
      if (v >= n)            ic.className = "fa-solid fa-star on";
      else if (v >= n - 0.5) ic.className = "fa-solid fa-star-half-stroke half";
    });
    if (hint) hint.textContent = v ? (v + " out of 5") : "";
  }

  function valFrom(btn, clientX){
    const rect = btn.getBoundingClientRect();
    const n    = Number(btn.dataset.n);
    const isLeftHalf = (clientX - rect.left) < (rect.width / 2);
    return n - (isLeftHalf ? 0.5 : 0);
  }

  btns.forEach(btn => {
    btn.addEventListener("mousemove", e => paint(valFrom(btn, e.clientX)));
  });
  wrap.addEventListener("mouseleave", () => paint(value));

  function commit(e){
    const btn = e.target.closest(".star");
    if (!btn) return;
    value = valFrom(btn, e.clientX);
    hidden.value = value;
    paint(value);
  }
  wrap.addEventListener("click", commit);
  wrap.addEventListener("pointerdown", commit);

  wrap.tabIndex = 0;
  wrap.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft")       value = Math.max(0.5, (value || 0.5) - 0.5);
    else if (e.key === "ArrowRight") value = Math.min(5,   (value || 0.5) + 0.5);
    else if (e.key === "Home")       value = 0.5;
    else if (e.key === "End")        value = 5;
    else return;
    hidden.value = value; paint(value); e.preventDefault();
  });

  paint(value);
})();

// REVIEW ACTIONS
(function () {
  function onActionSubmit(e) {
    const form = e.target.closest('form.js-review-action');
    if (!form) return;
    e.preventDefault();

    const btn   = form.querySelector('[data-role="btn"]');
    const icon  = form.querySelector('[data-role="icon"]');
    const count = form.querySelector('[data-role="count"]');
    if (!btn || !count) return;

    const pressed = (btn.getAttribute('aria-pressed') === 'true');
    const kind    = form.dataset.kind; // "helpful" or "report"
    const tokenEl = form.querySelector('input[name="csrfmiddlewaretoken"]');
    const csrf    = tokenEl ? tokenEl.value : '';

    const current = parseInt(count.textContent.trim(), 10) || 0;
    const nextPressed = !pressed;
    const nextCount   = Math.max(0, current + (nextPressed ? 1 : -1));

    if (kind === 'helpful') {
      btn.classList.toggle('btn-success', nextPressed);
      btn.classList.toggle('btn-outline-success', !nextPressed);
      icon.classList.toggle('bi-hand-thumbs-up-fill', nextPressed);
      icon.classList.toggle('bi-hand-thumbs-up', !nextPressed);
    } else {
      btn.classList.toggle('btn-danger', nextPressed);
      btn.classList.toggle('btn-outline-danger', !nextPressed);
      icon.classList.toggle('bi-flag-fill', nextPressed);
      icon.classList.toggle('bi-flag', !nextPressed);
    }
    btn.setAttribute('aria-pressed', String(nextPressed));
    count.textContent = String(nextCount);

    btn.disabled = true;

    fetch(form.action, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrf,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: new FormData(form),
      redirect: 'follow'
    }).catch(() => {
      if (kind === 'helpful') {
        btn.classList.toggle('btn-success', pressed);
        btn.classList.toggle('btn-outline-success', !pressed);
        icon.classList.toggle('bi-hand-thumbs-up-fill', pressed);
        icon.classList.toggle('bi-hand-thumbs-up', !pressed);
      } else {
        btn.classList.toggle('btn-danger', pressed);
        btn.classList.toggle('btn-outline-danger', !pressed);
        icon.classList.toggle('bi-flag-fill', pressed);
        icon.classList.toggle('bi-flag', !pressed);
      }
      btn.setAttribute('aria-pressed', String(pressed));
      count.textContent = String(current);
    }).finally(() => {
      btn.disabled = false;
    });
  }

  document.addEventListener('submit', function(e){
    if (e.target && e.target.matches('form.js-review-action')) onActionSubmit(e);
  });
})();

// 360 SPIN (carSpin)
document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('spinBtn');
  var el  = document.getElementById('carSpin');

  if (!btn || !el || !window.bootstrap || !bootstrap.Carousel) return;

  var items = el.querySelectorAll('.carousel-item');
  var inst  = bootstrap.Carousel.getInstance(el) ||
              new bootstrap.Carousel(el, { interval: false, ride: false, wrap: true, pause: false });

  var timer = null;

  function setBtnSpinning(on) {
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.classList.toggle('btn-primary', on);
    btn.classList.toggle('btn-outline-primary', !on);
    btn.innerHTML = on
      ? '<i class="bi bi-pause-circle"></i><span>Stop 360°</span>'
      : '<i class="bi bi-arrows-angle-expand"></i><span>Start 360° View</span>';
  }

  if (items.length < 2) {
    btn.disabled = true;
    btn.title = 'Need at least 2 images';
    return;
  }

  btn.addEventListener('click', function () {
    if (timer) {
      clearInterval(timer);
      timer = null;
      setBtnSpinning(false);
      return;
    }
    setBtnSpinning(true);
    timer = setInterval(function(){ inst.next(); }, 500);
  });

  window.addEventListener('beforeunload', function () {
    if (timer) clearInterval(timer);
  });
});

// Tooltips (single init)
document.addEventListener('DOMContentLoaded', () => {
  if (!window.bootstrap) return;
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => bootstrap.Tooltip.getOrCreateInstance(el));
});

// Swiper (featured)
(function() {
  var el = document.getElementById('featuredSwiper');
  if (!el) return;
  new Swiper(el, {
    slidesPerView: 1.1,
    spaceBetween: 12,
    loop: false,
    keyboard: { enabled: true },
    navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev' },
    pagination: { el: '.swiper-pagination', clickable: true },
    breakpoints: {
      576: { slidesPerView: 2, spaceBetween: 16 },
      768: { slidesPerView: 3, spaceBetween: 18 },
      992: { slidesPerView: 4, spaceBetween: 20 }
    }
  });
})();

// === wishlist handler (debounced + stable UI) ===
const wlPending = new Set();

document.addEventListener('click', (e) => {
  const btn = e.target.closest('.add-wishlist');
  if (!btn || !btn.dataset.id) return;

  e.preventDefault();

  // Prevent Bootstrap :active/:focus “fill” from sticking visually
  btn.blur();
  btn.classList.remove('active');

  const id = String(btn.dataset.id);
  if (wlPending.has(id)) return;        // already in flight → ignore extra taps
  wlPending.add(id);
  btn.classList.add('disabled');        // simple click guard

  const url = btn.dataset.url || btn.href || `/wishlist/${id}/toggle/`;

  fetch(url, {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken':
        (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1]) ||
        document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || ''
    },
    credentials: 'same-origin'
  })
  .then(r => r.ok ? r.json() : Promise.reject(r))
  .then(data => {
    if (!data || data.ok === false) return;
    if (typeof data.count !== 'undefined') setWishlistCount(data.count);
    document.dispatchEvent(new CustomEvent('wishlist:updated', {
      detail: { count: data.count, in_wishlist: data.in_wishlist === true }
    }));
  })
  .catch(() => {})
  .finally(() => {
    wlPending.delete(id);
    btn.classList.remove('disabled');
  });
});

/////////////////////////////////////
// View Switch
/////////////////////////////////////
document.addEventListener('DOMContentLoaded', function () {
  const gridWrap = document.getElementById('cardsGrid');
  if (!gridWrap) return;

  const cols = Array.from(gridWrap.children);
  cols.forEach(col => { if (!col.dataset.orig) col.dataset.orig = col.className; });

  const radios = Array.from(document.querySelectorAll('input[name="view"]'));
  const STORAGE_KEY = 'automart:view';

  function apply(view){
    const isList = (view === 'list');
    cols.forEach(col => {
      if (isList) {
        col.className = 'col-12';
      } else {
        col.className = col.dataset.orig || col.className;
      }
    });
    radios.forEach(r => r.checked = (r.value === view));
    try { localStorage.setItem(STORAGE_KEY, view); } catch(_) {}
  }

  const initial = (localStorage.getItem(STORAGE_KEY) || (radios.find(r => r.checked)?.value) || 'grid');
  apply(initial);

  radios.forEach(r => r.addEventListener('change', (e) => {
    if (e.target.checked) apply(e.target.value);
  }));
});

// Compare nav (single copy)
document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('saveComparison');
  if (!btn) return;

  btn.addEventListener('click', function () {
    try {
      const modalEl = document.getElementById('compareModal');
      if (modalEl && window.bootstrap) {
        bootstrap.Modal.getOrCreateInstance(modalEl).hide();
      }
    } catch (_) {}

    window.location.assign("{% url 'compare_page' %}");
  });
});
