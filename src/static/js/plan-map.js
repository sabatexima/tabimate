(() => {
  const STADIA_KEY = document.querySelector('meta[name="stadia-key"]')?.content || '';
  // v2: 旧版で焼き付いた空配列([])キャッシュを無効化するためキーを更新
  const CACHE_PREFIX = 'tabimate_geo_v2_';

  // カテゴリごとの見た目（観光=若葉/グルメ=オレンジ/宿=青）
  const CATEGORIES = {
    spot:          { fill: '#4fa83a', text: '#3b8a2c', clover: true,  label: '観光' },
    restaurant:    { fill: '#e8883a', text: '#9a4e16', clover: false, label: 'グルメ', glyph: '食' },
    accommodation: { fill: '#4a90d9', text: '#23598f', clover: false, label: '宿',     glyph: '宿' },
  };

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function geocode(name) {
    // destination（「関西」「浅草」等）を付けると Nominatim のヒット率が下がるため、
    // スポット名のみで検索する（国の絞り込みはサーバー側の countrycodes=jp で担保）。
    const url = `/api/geocode?q=${encodeURIComponent(name)}`;
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data && data[0]) return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon), name };
    } catch (e) {
      // ネットワークエラーや JSON パース失敗は null 扱いで継続
    }
    return null;
  }

  // 保存済み座標 [{name,lat,lng}] を地図用の点に変換する。
  function mapStored(coords) {
    if (!Array.isArray(coords)) return [];
    return coords
      .filter(c => c && c.lat != null && c.lng != null)
      .map(c => ({ lat: parseFloat(c.lat), lng: parseFloat(c.lng), name: c.name }));
  }

  // 観光スポットの点を解決する。保存済み座標があれば即利用、無ければ（旧プラン）
  // 従来どおりオンデマンドでジオコーディングする。
  async function resolveSpotPoints(planId, spots, coords) {
    if (Array.isArray(coords) && coords.length > 0) return mapStored(coords);

    const cacheKey = CACHE_PREFIX + planId;
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      const parsed = JSON.parse(cached);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;  // 空配列は焼き付きなので無視
    }
    const results = [];
    for (const spot of (spots || [])) {
      await new Promise(r => setTimeout(r, 1000));  // Nominatim rate limit: 1 req/s
      const c = await geocode(spot);
      if (c) results.push(c);
    }
    if (results.length > 0) sessionStorage.setItem(cacheKey, JSON.stringify(results));
    return results;
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

  // しずく型ピン。label は番号 or グリフ（食/宿）。観光だけ四つ葉アクセント付き。
  function makeIcon(label, cat) {
    const s = String(label);
    const fs = s.length > 1 ? 11 : 13;
    const ty = (15 + fs * 0.35).toFixed(1);
    const clover = cat.clover
      ? `<g stroke="#fff" stroke-width="1">`
        + `<circle cx="24.5" cy="4.4" r="2.3" fill="#f08ba0"/><circle cx="26.6" cy="6.5" r="2.3" fill="#f08ba0"/>`
        + `<circle cx="24.5" cy="8.6" r="2.3" fill="#f08ba0"/><circle cx="22.4" cy="6.5" r="2.3" fill="#f08ba0"/></g>`
      : '';
    const svg = `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="M16 2C8.8 2 3 7.8 3 15c0 9.2 13 24 13 24s13-14.8 13-24C29 7.8 23.2 2 16 2Z" fill="${cat.fill}" stroke="#fff" stroke-width="2.5"/>`
      + `<circle cx="16" cy="15" r="8.5" fill="#fff9ec"/>`
      + `<text x="16" y="${ty}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="${cat.text}" font-family="'Zen Maru Gothic',sans-serif">${esc(s)}</text>`
      + clover + `</svg>`;
    return L.divIcon({ className: 'plan-map-pin', html: svg, iconSize: [32, 42], iconAnchor: [16, 39], popupAnchor: [0, -36] });
  }

  function popupHtml(p) {
    // 各ピンから Google マップの経路ナビへ飛べるようにする。
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const url = `https://www.google.com/maps/dir/?api=1&destination=${dest}`;
    return `<strong>${esc(p.name)}</strong><br>`
      + `<a href="${url}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで経路</a>`;
  }

  function addMarkers(map, points, cat) {
    points.forEach((p, i) => {
      const icon = makeIcon(cat.glyph || (i + 1), cat);
      L.marker([p.lat, p.lng], { icon }).addTo(map).bindPopup(popupHtml(p));
    });
  }

  function addLegend(map, present) {
    const legend = L.control({ position: 'topright' });
    legend.onAdd = function () {
      const div = L.DomUtil.create('div', 'plan-map-legend');
      div.innerHTML = present
        .map(k => `<span><i style="background:${CATEGORIES[k].fill}"></i>${CATEGORIES[k].label}</span>`)
        .join('');
      return div;
    };
    legend.addTo(map);
  }

  // plan: { spots, spot_coords, restaurants, restaurant_coords, accommodation, accommodation_coords }
  window.initPlanMap = async function (containerId, planId, plan) {
    const el = document.getElementById(containerId);
    if (!el || el.dataset.initialized) return;
    el.dataset.initialized = '1';
    plan = plan || {};

    el.innerHTML = '<div class="plan-map-loading">地図を読み込み中…</div>';

    const spotPoints = await resolveSpotPoints(planId, plan.spots, plan.spot_coords);
    const restPoints = mapStored(plan.restaurant_coords);
    const accPoints = mapStored(plan.accommodation_coords);
    const all = [...spotPoints, ...restPoints, ...accPoints];

    if (all.length === 0) {
      el.innerHTML = '<div class="plan-map-loading">スポットの位置を特定できませんでした</div>';
      return;
    }

    el.innerHTML = '';
    const map = L.map(el, { zoomControl: true, scrollWheelZoom: false });
    L.tileLayer(tileUrl(), { attribution: tileAttrib(), maxZoom: 18 }).addTo(map);

    // 観光スポットはルート順に点線でつなぐ（グルメ・宿はつながない）。
    if (spotPoints.length > 1) {
      L.polyline(spotPoints.map(p => [p.lat, p.lng]),
        { color: '#7ab870', weight: 2.5, opacity: 0.7, dashArray: '6,4' }).addTo(map);
    }

    addMarkers(map, spotPoints, CATEGORIES.spot);
    addMarkers(map, restPoints, CATEGORIES.restaurant);
    addMarkers(map, accPoints, CATEGORIES.accommodation);

    const present = [];
    if (spotPoints.length) present.push('spot');
    if (restPoints.length) present.push('restaurant');
    if (accPoints.length) present.push('accommodation');
    if (present.length > 1) addLegend(map, present);

    map.fitBounds(L.latLngBounds(all.map(p => [p.lat, p.lng])).pad(0.2));
  };
})();
