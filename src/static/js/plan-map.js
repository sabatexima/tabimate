/* プランの地図（プラン詳細・共有プラン）。観光・グルメ・宿を色分けしたピンで、
   **まわる順**につないで見せる。JS の中で一番長いファイル。

   ■ 「まわる順」がこのファイルの主題
     地図に点を打つだけなら簡単だが、それでは「どこにあるか」しか分からない。
     知りたいのは「どう歩くか」なので、スケジュール（"09:00 兼六園を散策"）の
     文章からスポット名を探して、出てくる順に番号を振る（orderByItinerary）。
     ここが一番むずかしく、地名の表記ゆれ・部分一致・一般的すぎる語の除外を
     normText / isGenericFragment / findInSchedule で処理している。

   ■ 座標はできるだけ取りに行かない
     ジオコーディングは外部APIで、遅くて回数制限もある。そこで3段構え:
       1. プランに保存済みの座標（spot_coords）をまず使う
       2. localStorage のキャッシュ（CACHE_PREFIX）
       3. どちらにも無いものだけ /api/geocode へ問い合わせ、結果を保存する

   ■ 自分でピンを足せる（addPinEditor）
     AIが出さなかった場所を「メモ」として置ける。編集モードの間だけ地図の
     クリックを拾い、保存でまとめて /save_plan_pins/<id> に送る。

   window.initPlanMap() を公開し、「地図で見る」で初めて呼ばれる。 */
(() => {
  // Stadia のキーはタイル取得のためブラウザに出る（仕組み上避けられない）。
  // 無ければ通常の OSM タイルに落ちるので、キー無しでも地図は出る
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

  // ピン・吹き出しは文字列で HTML を組むので、店名などは先に無害化する
  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // 地名 → 座標。同じ場所を何度も引かないよう localStorage に貯める。
  // 見つからなかった場合も「無い」ことを覚える（毎回聞きに行かないため）
  async function geocode(name) {
    // destination（「関西」「浅草」等）を付けると Nominatim のヒット率が下がるため、
    // スポット名のみで検索する（国の絞り込みはサーバー側が行き先から決める）。
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
  // プランに保存済みの座標配列を、名前で引ける形に直す
  function mapStored(coords) {
    if (!Array.isArray(coords)) return [];
    return coords
      .filter(c => c && c.lat != null && c.lng != null)
      .map(c => ({ lat: parseFloat(c.lat), lng: parseFloat(c.lng), name: c.name }));
  }

  // 観光スポットの点を解決する。保存済み座標があれば即利用、無ければ（旧プラン）
  // 従来どおりオンデマンドでジオコーディングする。
  // スポット名の並びから、地図に置ける点の並びを作る。
  // 保存済み → キャッシュ → 問い合わせ、の順に落ちていく
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

  // 水彩タイル（有料キーが要る）か、通常の OSM タイルか
  function tileUrl() {
    if (STADIA_KEY) {
      return `https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg?api_key=${STADIA_KEY}`;
    }
    return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  }

  // タイルの帰属表示は提供元の条件。地図の右下に必ず出す
  function tileAttrib() {
    if (STADIA_KEY) {
      return '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://stamen.com">Stamen Design</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    }
    return '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  }

  // しずく型ピン。label は番号 or グリフ（食/宿）。観光だけ四つ葉アクセント付き。
  // しずく型ピンを SVG で描く。Leaflet の既定ピン（青い画像）は世界観に合わない。
  // 観光だけ四つ葉、グルメと宿は「食」「宿」の字を入れて、色が見えなくても分かるように
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
  // 吹き出しに出す写真を Wikipedia から借りる。無くても地図は成立するので、
  // 失敗したら黙って諦める（このためにローディングを出したりはしない）
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
  // 吹き出しを開いた**あと**で写真を差し込む。先に取りに行くと、
  // 開かないピンのぶんまで通信してしまう
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

  // ピンの吹き出し。名前＋Googleマップの経路案内へのリンク
  function popupHtml(p) {
    // 各ピンから Google マップの経路ナビへ飛べるようにする。写真は開いたとき遅延読込。
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const url = `https://www.google.com/maps/dir/?api=1&destination=${dest}`;
    return `<div class="pin-thumb"></div><strong>${esc(p.name)}</strong><br>`
      + `<a href="${url}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで経路</a>`;
  }

  // 1カテゴリぶんのピンを地図に置く。置いたマーカーを点と組にして返す
  // （日ごとの表示切り替えで出し入れするのに使う）
  function addMarkers(map, points, cat, labelFor) {
    return points.map((p, i) => {
      const label = labelFor ? labelFor(p) : (cat.glyph || (i + 1));
      const icon = makeIcon(label, cat);
      const m = L.marker([p.lat, p.lng], { icon }).addTo(map).bindPopup(popupHtml(p));
      m.on('popupopen', (e) => loadThumb(e.popup, p.name));
      return { m, p };
    });
  }

  // 表記ゆれ吸収（全角/半角・空白差でスケジュールとの照合を落とさない）
  // 突き合わせ用に文字をそろえる（全角半角・大小・カナ・記号・空白）。
  // スケジュールの文とスポット名は、同じ場所でも書き方が微妙に違うため
  function normText(s) {
    return String(s || '').normalize('NFKC').replace(/\s+/g, '');
  }

  // 店名の断片として照合すると誤マッチしやすい一般語。
  // スケジュール本文で「（別の店の）食事」を指して使われがちな語だけに絞る
  // （ガーデン・テラス等は店名の識別部分になり得るため入れない。
  //  他ピンとの曖昧性は otherNames ガードが防ぐ）。
  const GENERIC_WORDS = ['レストラン', 'ラーメン', 'ビュッフェ', 'カフェテリア'];
  // 一般語の「断片」（レスト・ストラン等）も情報を持たないため除外する。
  // 一般語＋固有部分を含む長い断片（ガーデンレストラン等）は有効なまま。
  // 「公園」「駅」のような一般的すぎる語は、部分一致に使うと何にでも当たる。
  // これらだけで一致したことにはしない
  function isGenericFragment(w) {
    return GENERIC_WORDS.some((g) => g.indexOf(w) >= 0);
  }

  // ピン名がスケジュール本文に最初に登場する位置を探す。
  // 完全一致で見つからなければ、名前の部分文字列（長い順・4文字以上）でも探す
  // （スケジュール側は「熱海銀座おさかな食堂」→「おさかな食堂で昼食」のように
  //  省略されがちなため）。誤マッチ対策の二段ガード:
  //   1. 一般語そのもの（レストラン等）は断片として使わない
  //   2. 他のピン名にも含まれる断片は使わない（別ピンの記述位置を拾わない）
  // スケジュールの文の中に、そのスポットが出てくる位置を探す。
  // まず名前まるごとで探し、見つからなければ意味のある断片で探す。
  // ほかのスポット名のほうが長く一致する場合は、そちらを優先して取り違えを防ぐ
  function findInSchedule(text, name, otherNames) {
    const n = normText(name);
    if (!n) return -1;
    const direct = text.indexOf(n);
    if (direct >= 0) return direct;
    for (let len = Math.min(n.length - 1, 10); len >= 4; len--) {
      for (let s = 0; s + len <= n.length; s++) {
        const w = n.substr(s, len);
        if (isGenericFragment(w)) continue;
        if (otherNames.some((o) => o !== n && o.indexOf(w) >= 0)) continue;
        const i = text.indexOf(w);
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
  // ★このファイルの肝。スケジュールに出てくる順にスポットを並べ替える。
  // 見つからなかったものは元の順のまま後ろに置く（消さない）
  function orderByItinerary(points, schedule) {
    const text = normText(Array.isArray(schedule) ? schedule.join('\n') : '');
    if (!text || points.length === 0) return null;
    const allNames = points.map((p) => normText(p.name));
    const hit = [];
    const miss = [];
    points.forEach((p) => {
      const i = findInSchedule(text, p.name, allNames);
      if (i >= 0) hit.push({ p, i }); else miss.push(p);
    });
    if (hit.length < 2) return null;
    hit.sort((a, b) => a.i - b.i);
    const ordered = hit.map((h) => h.p).concat(miss);
    const orderOf = new Map();
    ordered.forEach((p, idx) => orderOf.set(p, idx + 1));
    return { orderOf, route: ordered };
  }

  // 「N日目」の見出し行か。エージェント側（agents.py の _days_in）と同じ判定。
  // 全角数字や「【1日目】」「1日目：熱海へ」も見出しとして扱う
  const DAY_HEADER_RE = /^[【\[]?\s*(\d+)\s*日目/;
  function dayNumber(line) {
    const m = DAY_HEADER_RE.exec(String(line || '').normalize('NFKC').trim());
    return m ? parseInt(m[1], 10) : null;
  }

  // スケジュールを「N日目」の見出しで日ごとのブロックに分ける。
  // 見出し行そのものもブロックに含める（「1日目：熱海へ」のように地名が入ることがある）。
  // 返り値: [{ day, text }]（text は照合用に正規化済み）。見出しが無ければ []
  function splitDays(schedule) {
    const blocks = [];
    (Array.isArray(schedule) ? schedule : []).forEach((line) => {
      const d = dayNumber(line);
      if (d !== null) { blocks.push({ day: d, lines: [line] }); return; }
      if (blocks.length) blocks[blocks.length - 1].lines.push(line);
    });
    return blocks.map(b => ({ day: b.day, text: normText(b.lines.join('\n')) }));
  }

  // 各ピンが登場する日の集合を求める。
  // 宿は初日にチェックインして翌朝に出るので、複数の日に属する（だから集合）。
  // どの日にも見つからないピンは空集合（「すべて」のときだけ出る）。
  // 返り値: { days: ピンが1本でもある日（昇順）, daysOf: Map(点 → Set(日)) }。
  //
  // null を返す（＝切り替えを出さない）のは次の2つ:
  //   ・ピンのある日が2つ未満（切り替える意味が無い）
  //   ・日が付いたピンが半分に満たない（スケジュールとの照合が効いていない）。
  //     日を選ぶと日の付かないピンは消えるので、照合が弱いまま切り替えを出すと
  //     「押したら地図から店が消えた」という壊れて見える状態になる。
  //     並べ替え（orderByItinerary）と違い、こちらは見えなくなるぶん基準を厳しくする。
  function daysByItinerary(points, schedule) {
    const blocks = splitDays(schedule);
    if (!points.length) return null;
    const allNames = points.map(p => normText(p.name));
    const daysOf = new Map();
    points.forEach((p) => {
      const set = new Set();
      blocks.forEach((b) => { if (findInSchedule(b.text, p.name, allNames) >= 0) set.add(b.day); });
      daysOf.set(p, set);
    });
    const placed = points.filter(p => daysOf.get(p).size).length;
    if (placed * 2 < points.length) return null;
    const days = [...new Set(blocks.map(b => b.day))].sort((a, b) => a - b)
      .filter(d => points.some(p => daysOf.get(p).has(d)));
    return days.length >= 2 ? { days, daysOf } : null;
  }
  window.planMapDays = daysByItinerary;  // 検査用（tests/test_static_js.py）

  // 日の切り替え（左上・ズームの下）。「すべて」と、ピンのある日だけを並べる
  function addDayControl(map, dayInfo, onSelect) {
    const ctl = L.control({ position: 'topleft' });
    ctl.onAdd = function () {
      const div = L.DomUtil.create('div', 'plan-map-days');
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      const chips = [{ day: '', label: 'すべて' }].concat(dayInfo.days.map(d => ({ day: String(d), label: `${d}日目` })));
      div.innerHTML = chips.map((c, i) =>
        `<button type="button" class="day-chip${i === 0 ? ' on' : ''}" data-day="${c.day}" aria-pressed="${i === 0}">${c.label}</button>`
      ).join('');
      div.querySelectorAll('.day-chip').forEach(b => b.onclick = () => {
        div.querySelectorAll('.day-chip').forEach(x => { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
        b.classList.add('on');
        b.setAttribute('aria-pressed', 'true');
        onSelect(b.dataset.day === '' ? null : parseInt(b.dataset.day, 10));
      });
      return div;
    };
    ctl.addTo(map);
  }

  // 凡例。実際に地図にあるカテゴリだけ載せる
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
  // 自分で足したピンの種類 → 見た目のカテゴリ。知らない種類は「メモ」に落とす
  function _typeCat(type) { return CATEGORIES[_TYPE_CAT[type] || 'custom'] || CATEGORIES.custom; }

  // ユーザーが選べるピンの色パレット（選ばなければ種類の色）
  const PIN_COLORS = ['#4fa83a', '#e8883a', '#4a90d9', '#9b6dd6', '#f08ba0', '#f4607a', '#2bb3a3', '#e0a93b'];

  // しずく型ピン（中央の丸）。color 指定があればその色、なければ種類の色。
  // 自分で足したピン。種類ごとの色と、好きな色の指定にも対応する
  function customIcon(type, color) {
    const fill = color || _typeCat(type).fill;
    const svg = `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
      + `<path d="M16 2C8.8 2 3 7.8 3 15c0 9.2 13 24 13 24s13-14.8 13-24C29 7.8 23.2 2 16 2Z" fill="${fill}" stroke="#fff" stroke-width="2.5"/>`
      + `<circle cx="16" cy="15" r="4.5" fill="#fff9ec"/></svg>`;
    return L.divIcon({ className: 'plan-map-pin', html: `<span class="pin-i">${svg}</span>`, iconSize: [32, 42], iconAnchor: [16, 39], popupAnchor: [0, -36] });
  }

  // 自分で足したピンの吹き出し。編集モードのときだけ削除ボタンを出す
  function customPopup(p, editing) {
    const dest = encodeURIComponent(`${p.lat},${p.lng}`);
    const nav = `<a href="https://www.google.com/maps/dir/?api=1&destination=${dest}" target="_blank" rel="noopener" class="plan-map-nav">🧭 Googleマップで経路</a>`;
    const cat = _typeCat(p.type);
    const tag = `<span class="pin-type-tag" style="color:${cat.text || '#5e3a99'}">${cat.label}</span>`;
    const del = editing ? `<br><button type="button" class="pin-del">削除</button>` : '';
    return `<div class="pin-thumb"></div><strong>${esc(p.name || 'ピン')}</strong> ${tag}<br>${nav}${del}`;
  }

  // カスタムピンを描き直す。編集モードではドラッグ移動＋ポップアップに削除を出す。
  // 自分で足したピンをまとめて置き直す。編集モードでは drag で動かせる
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
  // ピンの編集モード一式（「ピンを編集」ボタン → 地図クリックで追加 → 保存/取消）。
  // 保存を押すまでサーバーには送らない。取消で元に戻せるよう、入る時点の状態を控えておく
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

    // ピンの配列が変わったら、地図の上と操作パネルの両方を作り直す。
    // 編集中は削除・移動が起きるたびに呼ばれる
    function rerender() {
      renderCustomMarkers(map, pins, markers, editing,
        (i) => { pins.splice(i, 1); rerender(); },
        (i, ll) => { pins[i].lat = ll.lat; pins[i].lng = ll.lng; });
      paint();
    }
    // 操作パネル（左下）を今の状態に描き直す。編集中かどうかでボタンが変わる
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
    // 編集モードに入る。取消で戻せるよう、この時点のピンを控えておく
    function enter() {
      editing = true; pending = null;
      backup = JSON.parse(JSON.stringify(pins));
      map.getContainer().style.cursor = 'crosshair';
      rerender();
    }
    // 編集モードを抜ける（保存でも取消でも通る共通の後始末）
    function exit() {
      editing = false; pending = null;
      map.getContainer().style.cursor = '';
      rerender();
    }
    // 取消。控えておいた状態に戻す。pins は外から参照されている同じ配列なので、
    // 新しい配列に差し替えず、中身を入れ替える
    function cancel() {
      pins.length = 0;
      (backup || []).forEach(p => pins.push(p));  // 未保存の変更を破棄
      exit();
    }
    // 保存。ここで初めてサーバーに送る（編集中の追加・移動・削除はすべて手元だけ）
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
  // 北東へずらして、全部のピンが見えるようにする。
  // fixed には動かしたくない点（ユーザーが置いたカスタムピン）を渡す。
  // 自動ピン側が避けることで、カスタムピンの位置は尊重しつつ番号の隠れを防ぐ。
  // 同じ場所に複数のピンが重なると、下のピンが押せなくなる。
  // ほんの少しずつずらして、全部触れるようにする（座標そのものは変えない）
  function spreadOverlaps(points, fixed) {
    const seen = (fixed || []).slice();
    points.forEach((p) => {
      // 「重なっている数」だけずらすと、3件目が2件目と同じ位置に落ちてしまう。
      // 空いている場所が見つかるまで、1段（約20m 北東）ずつ押しやる。
      let bump = 0;
      const overlaps = () => seen.some((q) =>
        Math.abs(p.lat + 0.00013 * bump - q.lat) < 0.00015 &&
        Math.abs(p.lng + 0.00022 * bump - q.lng) < 0.00015);
      while (bump <= seen.length && overlaps()) bump++;
      if (bump > 0) {
        p.lng += 0.00022 * bump;
        p.lat += 0.00013 * bump;
      }
      seen.push(p);
    });
  }

  // plan: { spots, spot_coords, restaurants, restaurant_coords, accommodation,
  //         accommodation_coords, custom_pins }
  // opts: { editable }  自分のプランなら editable=true でピン編集UIを出す
  // 「地図で見る」から呼ばれる入口。座標を集める → 順番に並べる →
  // ピンを置く → 全部が収まる範囲に合わせる
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
    // （カスタムピンは動かさず、自動ピン側が避ける）
    spreadOverlaps([...spotPoints, ...restPoints, ...accPoints], customPins);
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
    const autoPoints = [...spotPoints, ...restPoints, ...accPoints];
    const seq = orderByItinerary(autoPoints, plan.schedule);

    // 点線も移動順につなぐ（スケジュールと照合できないときは従来どおり観光の並び順）。
    // 日で絞ったときに引き直すので、関数にしてある
    const routeAll = seq ? seq.route : spotPoints;
    let routeLine = null;
    function drawRoute(pts) {
      if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
      if (pts.length > 1) {
        routeLine = L.polyline(pts.map(p => [p.lat, p.lng]),
          { color: '#7ab870', weight: 2.5, opacity: 0.7, dashArray: '6,4' }).addTo(map);
      }
    }
    drawRoute(routeAll);

    const labelFor = seq ? ((p) => seq.orderOf.get(p)) : null;
    const autoMarkers = [
      ...addMarkers(map, spotPoints, CATEGORIES.spot, labelFor),
      ...addMarkers(map, restPoints, CATEGORIES.restaurant, labelFor),
      ...addMarkers(map, accPoints, CATEGORIES.accommodation, labelFor),
    ];

    // 複数日のプランは「N日目」ごとにピンと線を絞れるようにする。
    // 番号は通しのまま（しおりの番号と地図の番号を一致させておく）。
    // 自分で置いたピンは日を持たないので、どの日でも出しておく
    const dayInfo = daysByItinerary(autoPoints, plan.schedule);
    if (dayInfo) {
      addDayControl(map, dayInfo, (day) => {
        const show = (p) => day === null || dayInfo.daysOf.get(p).has(day);
        autoMarkers.forEach(({ m, p }) => {
          if (show(p)) { if (!map.hasLayer(m)) m.addTo(map); }
          else if (map.hasLayer(m)) map.removeLayer(m);
        });
        drawRoute(routeAll.filter(show));
        const visible = autoPoints.filter(show);
        if (visible.length) {
          map.fitBounds(L.latLngBounds(visible.map(p => [p.lat, p.lng])).pad(0.2), { maxZoom: 15 });
        }
      });
    }

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
    } else if (plan.center && Number.isFinite(plan.center.lat) && Number.isFinite(plan.center.lng)) {
      // ピン未設置でも行き先は分かっている（/api/plan_geo が添える）。その街を出す。
      // 海外のプランで日本全図から探させないため
      map.setView([plan.center.lat, plan.center.lng], 11);
    } else {
      map.setView([36.2, 138.2], 5);  // 行き先も引けなかったときだけ日本全体
    }
  };
})();
