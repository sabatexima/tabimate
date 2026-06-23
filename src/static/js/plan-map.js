(() => {
  const STADIA_KEY = document.querySelector('meta[name="stadia-key"]')?.content || '';
  const CACHE_PREFIX = 'tabimate_geo_';

  async function geocode(name, destination) {
    const query = destination ? `${name}, ${destination}` : name;
    const url = `/api/geocode?q=${encodeURIComponent(query)}`;
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data && data[0]) return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon), name };
    } catch (e) {
      // ネットワークエラーや JSON パース失敗は null 扱いで継続
    }
    return null;
  }

  async function resolveSpots(planId, spots, destination) {
    const cacheKey = CACHE_PREFIX + planId;
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) return JSON.parse(cached);

    const results = [];
    for (const spot of spots) {
      await new Promise(r => setTimeout(r, 1000));  // Nominatim rate limit: 1 req/s
      const coords = await geocode(spot, destination);
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
    return L.divIcon({
      className: '',
      html: `<div class="plan-map-pin">${n}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
  }

  window.initPlanMap = async function(containerId, planId, spots, destination) {
    const el = document.getElementById(containerId);
    if (!el || el.dataset.initialized) return;
    el.dataset.initialized = '1';

    el.innerHTML = '<div class="plan-map-loading">地図を読み込み中…</div>';

    const points = await resolveSpots(planId, spots, destination);

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
