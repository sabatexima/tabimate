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

  // しずく型ピン。実績(写真)=ピンク / 計画(プラン)=緑。
  function pin(label, fill, textFill) {
    const s = String(label);
    const fs = s.length > 1 ? 11 : 13;
    const ty = (15 + fs * 0.35).toFixed(1);
    const svg = `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="M16 2C8.8 2 3 7.8 3 15c0 9.2 13 24 13 24s13-14.8 13-24C29 7.8 23.2 2 16 2Z" fill="${fill}" stroke="#fff" stroke-width="2.5"/>`
      + `<circle cx="16" cy="15" r="8.5" fill="#fff9ec"/>`
      + `<text x="16" y="${ty}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="${textFill}" font-family="'Zen Maru Gothic',sans-serif">${esc(s)}</text>`
      + `</svg>`;
    return L.divIcon({ className: 'plan-map-pin', html: svg, iconSize: [32, 42], iconAnchor: [16, 39], popupAnchor: [0, -36] });
  }
  const footIcon = (n) => pin(n, '#f08ba0', '#c25274');
  const planIcon = (n) => pin(n, '#4fa83a', '#3b8a2c');

  function popupHtml(p) {
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const url = `https://www.google.com/maps/dir/?api=1&destination=${dest}`;
    const thumb = p.thumb ? `<img src="${esc(p.thumb)}" alt="" style="width:120px;height:80px;object-fit:cover;border-radius:8px;display:block;margin-bottom:4px;">` : '';
    const when = p.taken ? `<div style="font-size:11px;color:#8a817a;">${esc(p.taken)}</div>` : '';
    return thumb + when
      + `<a href="${url}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで開く</a>`;
  }

  function addLegend(map, hasFoot, hasPlan) {
    const rows = [];
    if (hasFoot) rows.push('<span><i style="background:#f08ba0"></i>実績（写真）</span>');
    if (hasPlan) rows.push('<span><i style="background:#4fa83a"></i>計画（プラン）</span>');
    if (rows.length < 2) return;
    const legend = L.control({ position: 'topright' });
    legend.onAdd = function () {
      const div = L.DomUtil.create('div', 'plan-map-legend');
      div.innerHTML = rows.join('');
      return div;
    };
    legend.addTo(map);
  }

  // points: 写真の足あと [{lat,lng,thumb,taken}]（撮影順）
  // planned: 紐付けプランの観光スポット [{name,lat,lng}]（任意・重ね合わせ用）
  window.initFootprintMap = function (containerId, points, planned) {
    const el = document.getElementById(containerId);
    if (!el || el.dataset.initialized) return;
    el.dataset.initialized = '1';

    const pts = (points || [])
      .filter(p => p && p.lat != null && p.lng != null)
      .map(p => ({ lat: parseFloat(p.lat), lng: parseFloat(p.lng), thumb: p.thumb, taken: p.taken }));
    const plan = (planned || [])
      .filter(p => p && p.lat != null && p.lng != null)
      .map(p => ({ lat: parseFloat(p.lat), lng: parseFloat(p.lng), name: p.name }));

    if (pts.length === 0 && plan.length === 0) {
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
    // 計画スポット（緑）を重ねる
    plan.forEach((p, i) => {
      L.marker([p.lat, p.lng], { icon: planIcon(i + 1) }).addTo(map)
        .bindPopup(`<strong>${esc(p.name)}</strong><br><span style="font-size:11px;color:#3b8a2c;">計画スポット</span>`);
    });
    // 実績（写真）ピンク
    pts.forEach((p, i) => {
      L.marker([p.lat, p.lng], { icon: footIcon(i + 1) }).addTo(map).bindPopup(popupHtml(p));
    });

    addLegend(map, pts.length > 0, plan.length > 0);
    const all = [...pts, ...plan].map(p => [p.lat, p.lng]);
    map.fitBounds(L.latLngBounds(all).pad(0.2));
  };
})();
