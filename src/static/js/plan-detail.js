/* 保存プランの詳細ページ。#plan-data に埋め込まれた1件を描画し、
   修正・評価・共有・削除・地図・天気をこのページで完結させる。 */
const PLAN = JSON.parse(document.getElementById('plan-data').textContent);
const CFG = JSON.parse(document.getElementById('page-config').textContent);
const root = document.getElementById('plan-root');

function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmt(n) {
  return n != null ? Number(n).toLocaleString() : '—';
}

// 目的地の宿を Google マップで探すリンク（公式の Maps URLs 形式・スマホはアプリが開く）。
function bookingUrl(destination) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((destination || '') + ' 宿')}`;
}

// 評価済みの表示（1プラン1評価・上書き式）。「修正」で再編集できる（誤入力の救済）。
function ratedRateHtml(rating, comment) {
  const stars = [1, 2, 3, 4, 5]
    .map(n => `<span class="rate-star-static${rating >= n ? ' on' : ''}">★</span>`)
    .join('');
  const c = comment ? `<span class="rate-comment-view">「${esc(comment)}」</span>` : '';
  return `
    <div class="plan-rate rated">
      <span class="rate-label">あなたの評価</span>
      <span class="rate-stars-static" aria-label="${rating}つ星">${stars}</span>
      ${c}
      <button class="rate-edit" type="button">修正</button>
    </div>`;
}

// 編集可能な評価ウィジェット（既存の評価があれば★とコメントを引き継ぐ）。
function editableRateHtml(plan) {
  const r = plan.rating || 0;
  const stars = [1, 2, 3, 4, 5]
    .map(n => `<button class="rate-star${r >= n ? ' on' : ''}" data-n="${n}" type="button" aria-label="${n}つ星">★</button>`)
    .join('');
  return `
    <div class="plan-rate">
      <span class="rate-label">この旅はどうだった？</span>
      <div class="rate-controls">
        <span class="rate-stars">${stars}</span>
        <input type="text" class="rate-comment" autocomplete="off"
               placeholder="ひとこと（例: 歩きすぎた / ご飯が最高）" value="${esc(plan.rating_comment || '')}">
        <button class="rate-save" type="button">${r ? '更新' : '記録'}</button>
      </div>
    </div>`;
}

// 評価エリアのイベントを結線する。記録/更新で読み取り表示へ、「修正」で編集へ戻る（相互再結線）。
function mountRate(card, plan) {
  const box = card.querySelector('.plan-rate');
  if (!box) return;

  if (box.classList.contains('rated')) {
    const editBtn = box.querySelector('.rate-edit');
    if (editBtn) editBtn.addEventListener('click', () => {
      box.outerHTML = editableRateHtml(plan);
      mountRate(card, plan);
    });
    return;
  }

  const starEls = box.querySelectorAll('.rate-star');
  const saveBtn = box.querySelector('.rate-save');
  let current = plan.rating || 0;
  const paint = (val) => starEls.forEach((s) => {
    s.classList.toggle('on', parseInt(s.dataset.n, 10) <= val);
  });
  starEls.forEach((b) => {
    b.addEventListener('click', () => { current = parseInt(b.dataset.n, 10); paint(current); });
    b.addEventListener('mouseenter', () => paint(parseInt(b.dataset.n, 10)));
  });
  box.querySelector('.rate-stars').addEventListener('mouseleave', () => paint(current));

  saveBtn.addEventListener('click', async () => {
    if (!current) { alert('★で評価を選んでください'); return; }
    const comment = box.querySelector('.rate-comment').value.trim();
    const orig = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中…';
    try {
      const res = await fetch(`/rate_plan/${plan.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating: current, comment }),
      });
      const result = await res.json();
      if (res.ok && result.status === 'OK') {
        plan.rating = current; plan.rating_comment = comment;
        box.outerHTML = ratedRateHtml(current, comment);
        mountRate(card, plan);
        // しおりリボンを金＋★に更新
        card.classList.add('has-rating');
        const ribbon = card.querySelector('.book-ribbon');
        if (ribbon) ribbon.textContent = '★' + current;
        if (window.cloverBurst) window.cloverBurst();
      } else {
        alert(result.message || '記録に失敗しました');
        saveBtn.disabled = false;
        saveBtn.textContent = orig;
      }
    } catch (err) {
      alert('通信エラーが発生しました。もう一度お試しください。');
      saveBtn.disabled = false;
      saveBtn.textContent = orig;
    }
  });
}

// セクションは閉じた状態が既定（見出しだけで全体を見渡し、気になる所だけひらく）
function accordion(icon, label, items) {
  if (!items || items.length === 0) return '';
  const lis = items.map(i => `<li>${esc(i)}</li>`).join('');
  return `<details>
    <summary>${icon} ${esc(label)}</summary>
    <div class="plan-accordion-body"><ul>${lis}</ul></div>
  </details>`;
}

// 表紙ヘッダー（目的地・チップ・保存日）。詳細ページでは静的な見出し。
function heroHtml(plan) {
  const saved = plan.created_at
    ? new Date(plan.created_at).toLocaleDateString('ja-JP')
    : '';
  const cost = plan.total_per_person
    ? `💴 ${fmt(plan.total_per_person)}円/人`
    : (plan.budget_limit ? `💴 〜${fmt(plan.budget_limit)}円/人` : '');
  const chips = [
    plan.departure_location ? `📍 ${esc(plan.departure_location)}発` : '',
    plan.duration ? `⏱ ${esc(plan.duration)}` : '',
    plan.num_people != null ? `👥 ${esc(plan.num_people)}人` : '',
    cost,
  ].filter(Boolean).map((c) => `<span class="cover-chip">${c}</span>`).join('');
  const countdown = countdownLabel(plan.depart_iso);
  return `
    <div class="plan-cover">
      <span class="cover-icon" aria-hidden="true">🗾</span>
      <span class="cover-main">
        <span class="cover-dest">${esc(plan.destination)}</span>
        ${countdown ? `<span class="cover-countdown">${countdown}</span>` : ''}
        <span class="cover-chips">${chips}</span>
        ${saved ? `<span class="cover-meta">保存日 ${esc(saved)}</span>` : ''}
      </span>
    </div>`;
}

// 出発日(ISO)まであと何日か。過去は null。
function daysUntilDepart(iso) {
  if (!iso) return null;
  const dep = new Date(iso + 'T00:00:00');
  if (isNaN(dep)) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const d = Math.round((dep - today) / 86400000);
  return d >= 0 ? d : null;
}

// 出発カウントダウンの絵本トーンなラベル（四つ葉スタンプ風）。過去は空文字。
function countdownLabel(iso) {
  const d = daysUntilDepart(iso);
  if (d === null) return '';
  if (d === 0) return '🍀 今日は出発の日！';
  if (d === 1) return '🍀 明日は出発！';
  return `🍀 旅まであと${d}日`;
}

// 詳細（天気・アコーディオン・宿・地図）
function sectionsHtml(plan) {
  const mapId = `plan-map-${esc(plan.id)}`;
  const hasSpots = plan.spots && plan.spots.length > 0;
  const mapSection = hasSpots ? `
    <div class="plan-map-section">
      <button class="plan-map-btn" type="button" data-map-id="${mapId}"
              data-plan-id="${esc(plan.id)}">🗺 地図で見る</button>
      <div class="plan-map-container" id="${mapId}" hidden></div>
    </div>` : '';
  return `
    <div class="plan-weather" id="weather-${esc(plan.id)}" hidden></div>
    <div class="plan-accordion">
      ${accordion('✨', '主要観光地', plan.spots)}
      ${accordion('🍱', 'グルメ', plan.restaurants)}
      ${accordion('🏨', '宿泊施設', plan.accommodation)}
      ${accordion('📅', 'スケジュール', plan.schedule)}
      ${accordion('💰', '費用見積もり', plan.budget_estimate)}
    </div>
    <div class="plan-book">
      <a class="plan-book-btn" href="${bookingUrl(plan.destination)}" target="_blank" rel="noopener">🏨 ${esc(plan.destination)}の宿を探す</a>
    </div>
    ${mapSection}`;
}

// 地図ボタン：クリックでコンテナを開閉し、初回のみ地図を初期化
function mountMap(card, plan) {
  const mapBtn = card.querySelector('.plan-map-btn');
  if (!mapBtn) return;
  mapBtn.addEventListener('click', () => {
    const container = document.getElementById(mapBtn.dataset.mapId);
    if (!container) return;
    const opening = container.hidden;
    container.hidden = !opening;
    mapBtn.textContent = opening ? '🗺 地図を閉じる' : '🗺 地図で見る';
    if (opening) {
      // 座標は初回オープン時にサーバーでまとめて取得＆キャッシュ（保存は即時のまま）
      container.innerHTML = '<div class="plan-map-loading">地図を読み込み中…</div>';
      fetch(`/api/plan_geo/${plan.id}`)
        .then(r => r.json())
        .then(geo => { Object.assign(plan, geo); })
        .catch(() => { /* 失敗時はスポットのオンデマンド取得にフォールバック */ })
        .finally(() => window.initPlanMap(mapBtn.dataset.mapId, mapBtn.dataset.planId, plan, { editable: true }));
    }
  });
}

// 修正案のプレビュー（未保存）。確定するまで元プランは変更しない。
function renderPreview(proposed, origPlan) {
  const card = document.createElement('div');
  card.className = 'plan-card plan-preview open';
  card.innerHTML = `
    <div class="preview-banner">✏️ 修正案のプレビュー（まだ保存していません）</div>
    ${heroHtml(proposed)}
    <div class="plan-body">
      ${sectionsHtml(proposed)}
      <div class="plan-footer">
        <button class="preview-cancel" type="button">やめる</button>
        <button class="preview-apply" type="button">この内容で更新する</button>
      </div>
    </div>`;

  card.querySelector('.preview-cancel').addEventListener('click', () => {
    renderDetail(origPlan);  // 元のプランに戻す
  });

  card.querySelector('.preview-apply').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = '保存中…';
    try {
      const res = await fetch(`/apply_saved_plan/${proposed.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan: proposed }),
      });
      const result = await res.json();
      if (result.status === 'OK' && result.plan) {
        renderDetail(result.plan);
      } else {
        alert(result.message || '更新に失敗しました');
        btn.disabled = false;
        btn.textContent = 'この内容で更新する';
      }
    } catch (err) {
      alert('通信エラーが発生しました。もう一度お試しください。');
      btn.disabled = false;
      btn.textContent = 'この内容で更新する';
    }
  });

  root.replaceChildren(card);
  mountMap(card, proposed);
}

function renderDetail(plan) {
  const card = document.createElement('div');
  card.className = 'plan-card open';
  if (plan.rating) card.classList.add('has-rating');
  const ribbonHtml = `<span class="book-ribbon">${plan.rating ? '★' + esc(plan.rating) : ''}</span>`;

  card.innerHTML = `
    ${ribbonHtml}
    ${heroHtml(plan)}
    <div class="plan-body">
      ${sectionsHtml(plan)}
      <div class="plan-footer">
        <button class="edit-btn" type="button">✏️ チャットで修正</button>
        <a class="cal-btn" href="/plan/${esc(plan.id)}/print" target="_blank" rel="noopener">🖨 しおり</a>
        <a class="cal-btn" href="/export_plan_ics/${esc(plan.id)}">📅 カレンダー</a>
        <button class="share-btn" type="button">🔗 共有</button>
        <button class="delete-btn" type="button">削除</button>
      </div>
      <div class="plan-edit" hidden>
        <input type="text" class="plan-edit-input" autocomplete="off"
               placeholder="例: 2日目をゆっくりに / 宿を変えて / 予算を抑えて">
        <button class="plan-edit-send" type="button">修正する</button>
      </div>
      ${plan.rating ? ratedRateHtml(plan.rating, plan.rating_comment || '') : editableRateHtml(plan)}
    </div>
  `;
  root.replaceChildren(card);

  // チャットで修正：入力欄の開閉
  const editBox = card.querySelector('.plan-edit');
  const editInput = card.querySelector('.plan-edit-input');
  const editSend = card.querySelector('.plan-edit-send');
  card.querySelector('.edit-btn').addEventListener('click', () => {
    editBox.hidden = !editBox.hidden;
    if (!editBox.hidden) editInput.focus();
  });

  const resetEdit = () => {
    editInput.disabled = false;
    editSend.disabled = false;
    editSend.textContent = '修正する';
  };

  const submitEdit = async () => {
    const message = editInput.value.trim();
    if (!message) return;
    editInput.disabled = true;
    editSend.disabled = true;
    editSend.textContent = '修正中…';
    try {
      const res = await fetch(`/edit_saved_plan/${plan.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      // 事前バリデーションのエラー（429/400/403）は通常のJSONで返る
      if (!res.ok) {
        let m = '修正に失敗しました';
        try { const j = await res.json(); m = j.message || m; } catch (e) { /* noop */ }
        alert(m); resetEdit(); return;
      }
      // 本処理は SSE ストリーム（thinking → OK/ERROR）
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let settled = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let d;
          try { d = JSON.parse(line.slice(6)); } catch (e) { continue; }
          if (d.status === 'OK' && d.plan) {
            settled = true;
            // まだ保存せず、修正案をプレビュー表示（確定は「更新する」で）
            renderPreview(d.plan, plan);
            if (d.plan.feedback && d.plan.feedback.includes('⚠️')) alert(d.plan.feedback);
          } else if (d.status === 'ERROR') {
            settled = true;
            alert(d.message || '修正に失敗しました');
            resetEdit();
          }
        }
      }
      if (!settled) {
        alert('完了までに時間がかかりすぎたか、通信が途切れたようです。もう一度お試しください。');
        resetEdit();
      }
    } catch (e) {
      alert('通信エラーが発生しました。もう一度お試しください。');
      resetEdit();
    }
  };
  editSend.addEventListener('click', submitEdit);
  editInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitEdit(); });

  card.querySelector('.share-btn').addEventListener('click', () => {
    window.openShareModal('plan', plan.id);
  });

  card.querySelector('.delete-btn').addEventListener('click', async (e) => {
    if (!confirm(`「${plan.destination}」のプランを削除しますか？\n元に戻せません。`)) return;
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = '削除中...';
    try {
      const res = await fetch(`/delete_plan/${plan.id}`, { method: 'DELETE' });
      const result = await res.json();
      if (result.status === 'OK') {
        location.href = CFG.listUrl;  // 消えたプランに用はないので一覧へ
        return;
      }
    } catch (err) { /* 下のエラー表示へ */ }
    btn.disabled = false;
    btn.textContent = '削除';
    alert('削除に失敗しました');
  });

  mountRate(card, plan);
  mountMap(card, plan);
  loadWeather(plan);
}

// ---- 旅行日の天気（保存一覧と同じ判定・表示） ----
function wxDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
  return m ? `${parseInt(m[2], 10)}/${parseInt(m[3], 10)}` : esc(s);
}
// 旅行日をDateに。西暦つきはそのまま、年なし（7/2・7月2日）は直近の該当日を推定。
function parseTravelDate(travelDate) {
  const s = travelDate || '';
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let m = /(\d{4})\D+(\d{1,2})\D+(\d{1,2})/.exec(s);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  m = /(\d{1,2})\s*[/\-月]\s*(\d{1,2})/.exec(s);   // 「7/2」「7-2」「7月2日」
  if (m) {
    const mo = +m[1] - 1, da = +m[2];
    for (const yr of [today.getFullYear(), today.getFullYear() + 1]) {
      const d = new Date(yr, mo, da);
      if ((today - d) / 86400000 <= 60) return d;  // 60日以上前でなければ採用
    }
  }
  return null;
}
async function loadWeather(plan) {
  const el = document.getElementById(`weather-${plan.id}`);
  if (!el) return;
  const d = parseTravelDate(plan.travel_date);
  if (!d) return;  // 日付が読み取れないプランは天気行そのものを出さない
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const min = new Date(today); min.setDate(min.getDate() - 7);   // 旅行中（数日前開始）も拾う
  const max = new Date(today); max.setDate(max.getDate() + 16);  // 予報が取れるのは16日先まで
  if (d < min) return;  // 終わった旅の天気は出さない
  if (d > max) {
    // まだ予報範囲外：黙って消さず「出発が近づいたら出る」ことを伝える
    const daysTo = Math.round((d - max) / 86400000);
    el.innerHTML = '<span class="plan-weather-label">🌤 旅行日の天気</span>'
      + `<span class="wx-note">出発が近づくと表示されます（予報が届くのは16日前から・あと約${daysTo}日）</span>`;
    el.hidden = false;
    return;
  }
  el.innerHTML = '<span class="plan-weather-label">🌤 旅行日の天気</span><span class="wx-loading">取得中…</span>';
  el.hidden = false;
  try {
    const res = await fetch(`/api/plan_weather/${plan.id}`);
    const data = await res.json();
    if (!data.days || data.days.length === 0) { el.hidden = true; return; }
    el.innerHTML = '<span class="plan-weather-label">🌤 旅行日の天気</span>'
      + data.days.map(d => `<span class="wx-day"><b>${wxDate(d.date)}</b>`
        + `<span class="wx-emoji">${d.emoji}</span>`
        + `<span class="wx-temp">${d.tmax != null ? d.tmax + '°' : '–'}<i>/</i>${d.tmin != null ? d.tmin + '°' : '–'}</span></span>`).join('');
  } catch (e) {
    el.hidden = true;  // 天気は付加情報なので、取得失敗時は行ごと消す
  }
}

renderDetail(PLAN);
