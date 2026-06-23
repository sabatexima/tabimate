(() => {
  const STADIA_KEY = document.querySelector('meta[name="stadia-key"]')?.content || '';
  // v2: 旧版で焼き付いた空配列([])キャッシュを無効化するためキーを更新
  const CACHE_PREFIX = 'tabimate_geo_v2_';

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

  async function resolveSpots(planId, spots, destination, coords) {
    // 生成・編集時に保存された座標があればそれを使う（ジオコーディング不要・即時）。
    if (Array.isArray(coords) && coords.length > 0) {
      return coords
        .filter(c => c && c.lat != null && c.lng != null)
        .map(c => ({ lat: parseFloat(c.lat), lng: parseFloat(c.lng), name: c.name }));
    }

    // 座標未保存の旧プランは従来どおりオンデマンドでジオコーディングする。
    const cacheKey = CACHE_PREFIX + planId;
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      const parsed = JSON.parse(cached);
      // 空配列のキャッシュは「失敗の焼き付き」なので無視して再取得する
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }

    const results = [];
    for (const spot of spots) {
      await new Promise(r => setTimeout(r, 1000));  // Nominatim rate limit: 1 req/s
      const coords = await geocode(spot);
      if (coords) results.push(coords);
    }
    // 全スポット失敗時はキャッシュしない（次回リトライを可能にする）
    if (results.length > 0) {
      sessionStorage.setItem(cacheKey, JSON.stringify(results));
    }
    return results;
  }

  function tileUrl() {
    if (STADIA_KEY) {
      return `https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg?api_key=${STADIA_KEY}`;
    }
    // Stadia APIキー未設定時はOSM標準タイルにフォールバック
    return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  }

  function tileAttrib() {
    if (STADIA_KEY) {
      return '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://stamen.com">Stamen Design</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    }
    return '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  }

  function numberIcon(n) {
    // しずく型のマップピン（緑＝若葉色 / クリームの中抜き / 番号）に、
    // マスコット「みつば」の四つ葉アクセント（ピンク）を添えた世界観仕様。
    const fs = String(n).length > 1 ? 11 : 13;
    const ty = (15 + fs * 0.35).toFixed(1);
    const svg = `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="M16 2C8.8 2 3 7.8 3 15c0 9.2 13 24 13 24s13-14.8 13-24C29 7.8 23.2 2 16 2Z" fill="#4fa83a" stroke="#fff" stroke-width="2.5"/>`
      + `<circle cx="16" cy="15" r="8.5" fill="#fff9ec"/>`
      + `<text x="16" y="${ty}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="#3b8a2c" font-family="'Zen Maru Gothic',sans-serif">${n}</text>`
      + `<g stroke="#fff" stroke-width="1">`
      + `<circle cx="24.5" cy="4.4" r="2.3" fill="#f08ba0"/><circle cx="26.6" cy="6.5" r="2.3" fill="#f08ba0"/>`
      + `<circle cx="24.5" cy="8.6" r="2.3" fill="#f08ba0"/><circle cx="22.4" cy="6.5" r="2.3" fill="#f08ba0"/>`
      + `</g></svg>`;
    return L.divIcon({
      className: 'plan-map-pin',
      html: svg,
      iconSize: [32, 42],
      iconAnchor: [16, 39],
      popupAnchor: [0, -36],
    });
  }

  window.initPlanMap = async function(containerId, planId, spots, destination, coords) {
    const el = document.getElementById(containerId);
    if (!el || el.dataset.initialized) return;
    el.dataset.initialized = '1';

    el.innerHTML = '<div class="plan-map-loading">地図を読み込み中…</div>';

    const points = await resolveSpots(planId, spots, destination, coords);

    if (points.length === 0) {
      el.innerHTML = '<div class="plan-map-loading">スポットの位置を特定できませんでした</div>';
      return;
    }

    el.innerHTML = '';
    const map = L.map(el, { zoomControl: true, scrollWheelZoom: false });

    L.tileLayer(tileUrl(), {
      attribution: tileAttrib(),
      maxZoom: 18,
    }).addTo(map);

    const latlngs = points.map(p => [p.lat, p.lng]);

    if (latlngs.length > 1) {
      L.polyline(latlngs, { color: '#7ab870', weight: 2.5, opacity: 0.7, dashArray: '6,4' }).addTo(map);
    }

    points.forEach((p, i) => {
      L.marker([p.lat, p.lng], { icon: numberIcon(i + 1) })
        .addTo(map)
        .bindPopup(`<strong>${p.name}</strong>`);
    });

    map.fitBounds(L.latLngBounds(latlngs).pad(0.2));
  };
})();
