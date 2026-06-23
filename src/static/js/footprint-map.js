(() => {
  const STADIA_KEY = document.querySelector('meta[name="stadia-key"]')?.content || '';

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function tileUrl() {
    if (STADIA_KEY) {
      return `https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg?api_key=${STADIA_KEY}`;
    }
    return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  }

  function tileAttrib() {
    if (STADIA_KEY) {
      return '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://stamen.com">Stamen Design</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    }
    return '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  }

  // 撮影順の番号付きピン（マスコット色のピンクのしずく型）
  function footIcon(n) {
    const fs = String(n).length > 1 ? 11 : 13;
    const ty = (15 + fs * 0.35).toFixed(1);
    const svg = `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="M16 2C8.8 2 3 7.8 3 15c0 9.2 13 24 13 24s13-14.8 13-24C29 7.8 23.2 2 16 2Z" fill="#f08ba0" stroke="#fff" stroke-width="2.5"/>`
      + `<circle cx="16" cy="15" r="8.5" fill="#fff9ec"/>`
      + `<text x="16" y="${ty}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="#c25274" font-family="'Zen Maru Gothic',sans-serif">${esc(n)}</text>`
      + `</svg>`;
    return L.divIcon({ className: 'plan-map-pin', html: svg, iconSize: [32, 42], iconAnchor: [16, 39], popupAnchor: [0, -36] });
  }

  function popupHtml(p) {
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const url = `https://www.google.com/maps/dir/?api=1&destination=${dest}`;
    const thumb = p.thumb ? `<img src="${esc(p.thumb)}" alt="" style="width:120px;height:80px;object-fit:cover;border-radius:8px;display:block;margin-bottom:4px;">` : '';
    const when = p.taken ? `<div style="font-size:11px;color:#8a817a;">${esc(p.taken)}</div>` : '';
    return thumb + when
      + `<a href="${url}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで開く</a>`;
  }

  // points: [{ lat, lng, thumb, taken }]（撮影時刻順）
  window.initFootprintMap = function (containerId, points) {
    const el = document.getElementById(containerId);
    if (!el || el.dataset.initialized) return;
    el.dataset.initialized = '1';

    const pts = (points || [])
      .filter(p => p && p.lat != null && p.lng != null)
      .map(p => ({ lat: parseFloat(p.lat), lng: parseFloat(p.lng), thumb: p.thumb, taken: p.taken }));

    if (pts.length === 0) {
      el.innerHTML = '<div class="plan-map-loading">位置情報つきの写真がありません</div>';
      return;
    }

    el.innerHTML = '';
    const map = L.map(el, { zoomControl: true, scrollWheelZoom: false });
    L.tileLayer(tileUrl(), { attribution: tileAttrib(), maxZoom: 18 }).addTo(map);

    // 撮影順に点線でつなぐ＝歩いた道のり（足あと）
    if (pts.length > 1) {
      L.polyline(pts.map(p => [p.lat, p.lng]),
        { color: '#f0a8bb', weight: 2.5, opacity: 0.8, dashArray: '6,4' }).addTo(map);
    }

    pts.forEach((p, i) => {
      L.marker([p.lat, p.lng], { icon: footIcon(i + 1) }).addTo(map).bindPopup(popupHtml(p));
    });

    map.fitBounds(L.latLngBounds(pts.map(p => [p.lat, p.lng])).pad(0.2));
  };
})();
