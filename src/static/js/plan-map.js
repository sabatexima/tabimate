(() => {
  const STADIA_KEY = document.querySelector('meta[name="stadia-key"]')?.content || '';
  // v2: 旧版で焼き付いた空配列([])キャッシュを無効化するためキーを更新
  const CACHE_PREFIX = 'tabimate_geo_v2_';

  // カテゴリごとの見た目（観光=若葉/グルメ=オレンジ/宿=青）
  const CATEGORIES = {
    spot:          { fill: '#4fa83a', text: '#3b8a2c', clover: true,  label: '観光' },
    restaurant:    { fill: '#e8883a', text: '#9a4e16', clover: false, label: 'グルメ', glyph: '食' },
    accommodation: { fill: '#4a90d9', text: '#23598f', clover: false, label: '宿',     glyph: '宿' },
    custom:        { fill: '#9b6dd6', text: '#5e3a99', clover: false, label: 'メモ' },
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
    return L.divIcon({ className: 'plan-map-pin', html: `<span class="pin-i">${svg}</span>`, iconSize: [32, 42], iconAnchor: [16, 39], popupAnchor: [0, -36] });
  }

  // 観光地名から Wikipedia(日本語) の代表画像サムネを取得（無ければ null）。結果はキャッシュ。
  const _thumbCache = {};
  async function wikiThumb(name) {
    if (!name) return null;
    if (name in _thumbCache) return _thumbCache[name];
    try {
      const url = `https://ja.wikipedia.org/w/api.php?action=query&prop=pageimages&piprop=thumbnail`
        + `&pithumbsize=260&redirects=1&format=json&origin=*&titles=${encodeURIComponent(name)}`;
      const res = await fetch(url);
      const data = await res.json();
      const pages = (data && data.query && data.query.pages) || {};
      let thumb = null;
      for (const k in pages) { if (pages[k].thumbnail && pages[k].thumbnail.source) { thumb = pages[k].thumbnail.source; break; } }
      _thumbCache[name] = thumb;
      return thumb;
    } catch (e) {
      _thumbCache[name] = null;
      return null;
    }
  }

  // ポップアップが開いたら写真サムネを遅延読み込みして差し込む。
  async function loadThumb(popup, name) {
    const el = popup.getElement();
    if (!el) return;
    const holder = el.querySelector('.pin-thumb');
    if (!holder || holder.dataset.loaded) return;
    holder.dataset.loaded = '1';
    const src = await wikiThumb(name);
    if (!src || !popup.isOpen()) return;
    holder.innerHTML = '<img alt="" loading="lazy">';
    const img = holder.querySelector('img');
    img.onload = () => { if (popup.isOpen()) popup.update(); };  // 画像分の高さに再配置
    img.src = src;
    popup.update();
  }

  function popupHtml(p) {
    // 各ピンから Google マップの経路ナビへ飛べるようにする。写真は開いたとき遅延読込。
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const url = `https://www.google.com/maps/dir/?api=1&destination=${dest}`;
    return `<div class="pin-thumb"></div><strong>${esc(p.name)}</strong><br>`
      + `<a href="${url}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで経路</a>`;
  }

  function addMarkers(map, points, cat, labelFor) {
    points.forEach((p, i) => {
      const label = labelFor ? labelFor(p) : (cat.glyph || (i + 1));
      const icon = makeIcon(label, cat);
      const m = L.marker([p.lat, p.lng], { icon }).addTo(map).bindPopup(popupHtml(p));
      m.on('popupopen', (e) => loadThumb(e.popup, p.name));
    });
  }

  // 表記ゆれ吸収（全角/半角・空白差でスケジュールとの照合を落とさない）
  function normText(s) {
    return String(s || '').normalize('NFKC').replace(/\s+/g, '');
  }

  // ピン名がスケジュール本文に最初に登場する位置を探す。
  // 完全一致で見つからなければ、名前の部分文字列（長い順・4文字以上）でも探す
  // （スケジュール側は「熱海銀座おさかな食堂」→「おさかな食堂で昼食」のように
  //  省略されがちなため。4文字未満は「ホテル」等の誤マッチを招くので使わない）。
  function findInSchedule(text, name) {
    const n = normText(name);
    if (!n) return -1;
    const direct = text.indexOf(n);
    if (direct >= 0) return direct;
    for (let len = Math.min(n.length - 1, 10); len >= 4; len--) {
      for (let s = 0; s + len <= n.length; s++) {
        const i = text.indexOf(n.substr(s, len));
        if (i >= 0) return i;
      }
    }
    return -1;
  }

  // 「移動する順番」をスケジュール本文から決める。
  // 各ピン名がスケジュール（タイムライン行）に最初に登場する位置で並べ、
  // 観光・グルメ・宿を横断した通し番号を振る。照合できない分は末尾に続番。
  // 線（route）は番号と完全に同じ順で全ピンをつなぐ（番号＝線の順序を保証）。
  // 照合できた点が2つ未満なら null を返し、従来表示に落とす。
  function orderByItinerary(points, schedule) {
    const text = normText(Array.isArray(schedule) ? schedule.join('\n') : '');
    if (!text || points.length === 0) return null;
    const hit = [];
    const miss = [];
    points.forEach((p) => {
      const i = findInSchedule(text, p.name);
      if (i >= 0) hit.push({ p, i }); else miss.push(p);
    });
    if (hit.length < 2) return null;
    hit.sort((a, b) => a.i - b.i);
    const ordered = hit.map((h) => h.p).concat(miss);
    const orderOf = new Map();
    ordered.forEach((p, idx) => orderOf.set(p, idx + 1));
    return { orderOf, route: ordered };
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

  // ピンの種類 → カテゴリ（色）。memo/未指定は紫。
  const PIN_TYPES = ['memo', 'spot', 'restaurant', 'accommodation'];
  const _TYPE_CAT = { spot: 'spot', restaurant: 'restaurant', accommodation: 'accommodation', memo: 'custom' };
  function _typeCat(type) { return CATEGORIES[_TYPE_CAT[type] || 'custom'] || CATEGORIES.custom; }

  // ユーザーが選べるピンの色パレット（選ばなければ種類の色）
  const PIN_COLORS = ['#4fa83a', '#e8883a', '#4a90d9', '#9b6dd6', '#f08ba0', '#f4607a', '#2bb3a3', '#e0a93b'];

  // しずく型ピン（中央の丸）。color 指定があればその色、なければ種類の色。
  function customIcon(type, color) {
    const fill = color || _typeCat(type).fill;
    const svg = `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="M16 2C8.8 2 3 7.8 3 15c0 9.2 13 24 13 24s13-14.8 13-24C29 7.8 23.2 2 16 2Z" fill="${fill}" stroke="#fff" stroke-width="2.5"/>`
      + `<circle cx="16" cy="15" r="4.5" fill="#fff9ec"/></svg>`;
    return L.divIcon({ className: 'plan-map-pin', html: `<span class="pin-i">${svg}</span>`, iconSize: [32, 42], iconAnchor: [16, 39], popupAnchor: [0, -36] });
  }

  function customPopup(p, editing) {
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const nav = `<a href="https://www.google.com/maps/dir/?api=1&destination=${dest}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで経路</a>`;
    const cat = _typeCat(p.type);
    const tag = `<span class="pin-type-tag" style="color:${cat.text || '#5e3a99'}">${cat.label}</span>`;
    const del = editing ? `<br><button type="button" class="pin-del">削除</button>` : '';
    return `<div class="pin-thumb"></div><strong>${esc(p.name || 'ピン')}</strong> ${tag}<br>${nav}${del}`;
  }

  // カスタムピンを描き直す。編集モードではドラッグ移動＋ポップアップに削除を出す。
  function renderCustomMarkers(map, pins, markers, editing, onDelete, onMove) {
    markers.forEach(m => map.removeLayer(m));
    markers.length = 0;
    pins.forEach((p, idx) => {
      const m = L.marker([p.lat, p.lng], { icon: customIcon(p.type, p.color), draggable: !!editing }).addTo(map);
      m.bindPopup(customPopup(p, editing));
      m.on('popupopen', (e) => {
        const btn = e.popup.getElement().querySelector('.pin-del');
        if (btn) btn.addEventListener('click', () => onDelete(idx));
        loadThumb(e.popup, p.name);
      });
      if (editing && onMove) m.on('dragend', () => onMove(idx, m.getLatLng()));
      markers.push(m);
    });
  }

  // 地図クリックで名前＋種類付きピンを追加・ドラッグ移動・削除・保存できる編集UI。
  // 未配置スポット（自動で立たなかった観光/グルメ/宿）をワンタップで配置もできる。
  function addPinEditor(map, planId, plan, pins, markers) {
    let editing = false;
    let backup = null;
    let pending = null;  // 未配置スポットの配置待ち {name, type}
    const ctl = L.control({ position: 'bottomleft' });
    ctl.onAdd = function () {
      const div = L.DomUtil.create('div', 'plan-map-editbar');
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      ctl._div = div;
      return div;
    };
    ctl.addTo(map);

    // 自動ジオコーディングで立たなかった項目（座標が無く、まだ手動配置もしていない）
    function unplaced() {
      const taken = new Set(pins.map(p => p.name));
      const out = [];
      [['spots', 'spot_coords', 'spot'], ['restaurants', 'restaurant_coords', 'restaurant'],
       ['accommodation', 'accommodation_coords', 'accommodation']].forEach(([nf, cf, type]) => {
        const placed = new Set((plan[cf] || []).map(c => c && c.name));
        (plan[nf] || []).forEach(n => { if (n && !placed.has(n) && !taken.has(n)) out.push({ name: n, type }); });
      });
      return out;
    }

    function rerender() {
      renderCustomMarkers(map, pins, markers, editing,
        (i) => { pins.splice(i, 1); rerender(); },
        (i, ll) => { pins[i].lat = ll.lat; pins[i].lng = ll.lng; });
      paint();
    }
    function paint() {
      const div = ctl._div;
      if (!div) return;
      if (!editing) {
        div.innerHTML = `<button type="button" class="pin-edit-btn" data-act="enter">📍 ピンを編集</button>`;
      } else {
        const ups = unplaced();
        const hint = pending ? `タップして「${esc(pending.name)}」を配置` : '地図をタップで追加 / ピンはドラッグで移動';
        const chips = ups.length
          ? `<div class="pin-unplaced"><span class="pin-unplaced-label">未配置:</span>`
            + ups.map((u, i) => `<button type="button" class="pin-chip" data-chip="${i}">${esc(u.name)}</button>`).join('')
            + `</div>`
          : '';
        div.innerHTML = `<div class="pin-edit-row"><span class="pin-edit-hint">${hint}</span>`
          + `<button type="button" class="pin-edit-btn save" data-act="save">💾 保存</button>`
          + `<button type="button" class="pin-edit-btn cancel" data-act="cancel">やめる</button></div>` + chips;
        div.querySelectorAll('.pin-chip').forEach(b => b.onclick = () => { pending = ups[+b.dataset.chip]; paint(); });
      }
      div.querySelectorAll('[data-act]').forEach(b => b.onclick = () => {
        const a = b.dataset.act;
        if (a === 'enter') enter(); else if (a === 'save') save(); else if (a === 'cancel') cancel();
      });
    }
    function enter() {
      editing = true; pending = null;
      backup = JSON.parse(JSON.stringify(pins));
      map.getContainer().style.cursor = 'crosshair';
      rerender();
    }
    function exit() {
      editing = false; pending = null;
      map.getContainer().style.cursor = '';
      rerender();
    }
    function cancel() {
      pins.length = 0;
      (backup || []).forEach(p => pins.push(p));  // 未保存の変更を破棄
      exit();
    }
    function save() {
      fetch(`/save_plan_pins/${planId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pins }),
      }).then(r => r.json()).then(d => {
        if (d.status === 'OK') { if (window.cloverBurst) window.cloverBurst(); exit(); }
        else alert(d.message || '保存に失敗しました');
      }).catch(() => alert('通信エラーが発生しました。もう一度お試しください。'));
    }

    // 地図クリック時：未配置スポット配置待ちならそれを置く。なければ入力フォームを開く。
    function openAddForm(latlng) {
      const opts = PIN_TYPES.map(t => `<option value="${t}">${_typeCat(t).label}</option>`).join('');
      const swatches = `<button type="button" class="pin-color sel" data-color="" title="種類の色">自動</button>`
        + PIN_COLORS.map(c => `<button type="button" class="pin-color" data-color="${c}" style="background:${c}" aria-label="${c}"></button>`).join('');
      const html = `<div class="pin-form"><div class="pin-form-top">`
        + `<input class="pin-name" type="text" placeholder="ピンの名前" maxlength="60">`
        + `<select class="pin-type">${opts}</select></div>`
        + `<div class="pin-colors">${swatches}</div>`
        + `<button type="button" class="pin-add">追加</button></div>`;
      const popup = L.popup({ closeButton: true, autoPan: true }).setLatLng(latlng).setContent(html).openOn(map);
      setTimeout(() => {
        const el = popup.getElement();
        if (!el) return;
        L.DomEvent.disableClickPropagation(el);
        const nameEl = el.querySelector('.pin-name');
        if (nameEl) nameEl.focus();
        let color = '';  // '' = 種類の色（自動）
        el.querySelectorAll('.pin-color').forEach(sw => sw.onclick = () => {
          color = sw.dataset.color || '';
          el.querySelectorAll('.pin-color').forEach(s => s.classList.remove('sel'));
          sw.classList.add('sel');
        });
        const addBtn = el.querySelector('.pin-add');
        if (addBtn) addBtn.onclick = () => {
          const name = (nameEl.value || '').trim();
          if (!name) { nameEl.focus(); return; }
          const pin = { name, type: el.querySelector('.pin-type').value || 'memo', lat: latlng.lat, lng: latlng.lng };
          if (color) pin.color = color;
          pins.push(pin);
          map.closePopup(popup);
          rerender();
        };
      }, 0);
    }
    map.on('click', (e) => {
      if (!editing) return;
      if (pending) {
        pins.push({ name: pending.name, type: pending.type, lat: e.latlng.lat, lng: e.latlng.lng });
        pending = null;
        rerender();
        return;
      }
      openAddForm(e.latlng);
    });
    rerender();
  }

  // ほぼ同一地点のピンは後から追加した方が上に重なり、下のピン（番号）が
  // 完全に隠れて見えなくなる。既出の点と極近（≈15m以内）の場合は少しずつ
  // 北東へずらして、全部のピンが見えるようにする（カスタムピンは対象外）。
  function spreadOverlaps(points) {
    const seen = [];
    points.forEach((p) => {
      let bump = 0;
      seen.forEach((q) => {
        if (Math.abs(p.lat - q.lat) < 0.00015 && Math.abs(p.lng - q.lng) < 0.00015) bump++;
      });
      if (bump > 0) {
        p.lng += 0.00022 * bump;  // 1件重なるごとに約20m 北東へ
        p.lat += 0.00013 * bump;
      }
      seen.push(p);
    });
  }

  // plan: { spots, spot_coords, restaurants, restaurant_coords, accommodation,
  //         accommodation_coords, custom_pins }
  // opts: { editable }  自分のプランなら editable=true でピン編集UIを出す
  window.initPlanMap = async function (containerId, planId, plan, opts) {
    opts = opts || {};
    const el = document.getElementById(containerId);
    if (!el || el.dataset.initialized) return;
    el.dataset.initialized = '1';
    plan = plan || {};

    el.innerHTML = '<div class="plan-map-loading">地図を読み込み中…</div>';

    const spotPoints = await resolveSpotPoints(planId, plan.spots, plan.spot_coords);
    const restPoints = mapStored(plan.restaurant_coords);
    const accPoints = mapStored(plan.accommodation_coords);
    const customPins = mapStored(plan.custom_pins);
    // 同一地点に重なった自動ピンをずらして、番号が隠れないようにする
    spreadOverlaps([...spotPoints, ...restPoints, ...accPoints]);
    const all = [...spotPoints, ...restPoints, ...accPoints, ...customPins];

    // 自動ピンが全滅でも、自分のプランなら手動ピンを置けるよう地図は出す。
    if (all.length === 0 && !opts.editable) {
      el.innerHTML = '<div class="plan-map-loading">スポットの位置を特定できませんでした</div>';
      return;
    }

    el.innerHTML = '';
    const map = L.map(el, { zoomControl: true, scrollWheelZoom: false });
    L.tileLayer(tileUrl(), { attribution: tileAttrib(), maxZoom: 18 }).addTo(map);

    // スケジュールに登場する順（＝移動する順番）で、観光・グルメ・宿を
    // 横断した通し番号を振る。色はカテゴリのまま、番号だけ移動順。
    const seq = orderByItinerary([...spotPoints, ...restPoints, ...accPoints], plan.schedule);

    // 点線も移動順につなぐ（スケジュールと照合できないときは従来どおり観光の並び順）。
    const routePts = seq ? seq.route : spotPoints;
    if (routePts.length > 1) {
      L.polyline(routePts.map(p => [p.lat, p.lng]),
        { color: '#7ab870', weight: 2.5, opacity: 0.7, dashArray: '6,4' }).addTo(map);
    }

    const labelFor = seq ? ((p) => seq.orderOf.get(p)) : null;
    addMarkers(map, spotPoints, CATEGORIES.spot, labelFor);
    addMarkers(map, restPoints, CATEGORIES.restaurant, labelFor);
    addMarkers(map, accPoints, CATEGORIES.accommodation, labelFor);

    // カスタムピン：自分のプランは編集UI付き、それ以外（共有閲覧）は表示のみ
    const customMarkers = [];
    if (opts.editable) {
      addPinEditor(map, planId, plan, customPins, customMarkers);
    } else {
      renderCustomMarkers(map, customPins, customMarkers, false, () => {});
    }

    const present = [];
    if (spotPoints.length) present.push('spot');
    if (restPoints.length) present.push('restaurant');
    if (accPoints.length) present.push('accommodation');
    if (customPins.length) present.push('custom');
    if (present.length > 1) addLegend(map, present);

    if (all.length > 0) {
      map.fitBounds(L.latLngBounds(all.map(p => [p.lat, p.lng])).pad(0.2));
    } else {
      map.setView([36.2, 138.2], 5);  // ピン未設置の編集時は日本全体を表示
    }
  };
})();
