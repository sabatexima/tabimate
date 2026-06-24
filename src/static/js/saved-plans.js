function esc(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function fmt(n) {
    return n != null ? Number(n).toLocaleString() : '—';
  }

  // 評価済みの表示（1プラン1評価・上書き式）。「修正」で再編集できる（誤入力の救済）。
  function ratedRateHtml(rating, comment) {
    const stars = [1, 2, 3, 4, 5]
      .map(n => `<span class="rate-star-static${rating >= n ? ' on' : ''}">★</span>`)
      .join('');
    const c = comment
      ? `<span class="rate-comment-view">「${esc(comment)}」</span>`
      : '';
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

  function accordion(icon, label, items) {
    if (!items || items.length === 0) return '';
    const lis = items.map(i => `<li>${esc(i)}</li>`).join('');
    return `<details>
      <summary>${icon} ${esc(label)}</summary>
      <div class="plan-accordion-body"><ul>${lis}</ul></div>
    </details>`;
  }

  // プラン本体（概要＋アコーディオン）のHTML。renderPlan / プレビューで共用。
  function planBodyHtml(plan) {
    const saved = plan.created_at
      ? new Date(plan.created_at).toLocaleDateString('ja-JP')
      : '';
    const mapId = `plan-map-${esc(plan.id)}`;
    const hasSpots = plan.spots && plan.spots.length > 0;
    const mapSection = hasSpots ? `
      <div class="plan-map-section">
        <button class="plan-map-btn" type="button" data-map-id="${mapId}"
                data-plan-id="${esc(plan.id)}">🗺 地図で見る</button>
        <div class="plan-map-container" id="${mapId}" hidden></div>
      </div>` : '';
    return `
      <div class="plan-summary-block">
        <div class="plan-title">🗾 旅行プラン：${esc(plan.destination)}</div>
        ${saved ? `<div class="plan-meta">保存日: ${esc(saved)}</div>` : ''}
        <div class="plan-summary-grid">
          <span>📍 出発地: ${esc(plan.departure_location || '—')}</span>
          <span>⏱️ 期間: ${esc(plan.duration || '—')}</span>
          <span>👥 人数: ${plan.num_people != null ? esc(plan.num_people) + '人' : '—'}</span>
          <span>💴 予算上限: ${fmt(plan.budget_limit)}円/人</span>
        </div>
      </div>
      <div class="plan-weather" id="weather-${esc(plan.id)}" hidden></div>
      <div class="plan-accordion">
        ${accordion('✨', '主要観光地', plan.spots)}
        ${accordion('🍱', 'グルメ', plan.restaurants)}
        ${accordion('🏨', '宿泊施設', plan.accommodation)}
        ${accordion('📅', 'スケジュール', plan.schedule)}
        ${accordion('💰', '費用見積もり', plan.budget_estimate)}
      </div>
      ${mapSection}`;
  }

  // 修正案のプレビュー（未保存）。確定するまで元プランは変更しない。
  function renderPreview(proposed, origPlan, opts = {}) {
    const shared = !!opts.shared;
    const card = document.createElement('div');
    card.className = 'plan-card plan-preview';
    card.innerHTML = `
      <div class="preview-banner">✏️ 修正案のプレビュー（まだ保存していません）</div>
      ${planBodyHtml(proposed)}
      <div class="plan-footer">
        <button class="preview-cancel" type="button">やめる</button>
        <button class="preview-apply" type="button">この内容で更新する</button>
      </div>`;

    card.querySelector('.preview-cancel').addEventListener('click', () => {
      card.replaceWith(renderPlan(origPlan, { shared }));  // 元のプランに戻す
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
          const merged = Object.assign({}, result.plan, {
            permission: origPlan.permission, grant_id: origPlan.grant_id,
          });
          card.replaceWith(renderPlan(merged, { shared }));
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

    return card;
  }

  function renderPlan(plan, opts = {}) {
    const shared = !!opts.shared;
    // 自分のプラン、または「編集可」で共有されたプランはチャット修正できる
    const editable = !shared || plan.permission === 'edit';
    const card = document.createElement('div');
    card.className = 'plan-card';

    const editBtnHtml = editable
      ? `<button class="edit-btn" data-id="${esc(plan.id)}">✏️ チャットで修正</button>`
      : '';
    const footer = shared
      ? `<div class="plan-footer">
           <span class="shared-flag">🤝 共有された${plan.permission === 'edit' ? '（編集可）' : ''}</span>
           ${editBtnHtml}
           <button class="unshare-btn" data-grant="${esc(plan.grant_id)}">共有解除</button>
         </div>`
      : `<div class="plan-footer">
           ${editBtnHtml}
           <a class="cal-btn" href="/export_plan_ics/${esc(plan.id)}">📅 カレンダー</a>
           <button class="share-btn" data-id="${esc(plan.id)}">🔗 共有</button>
           <button class="delete-btn" data-id="${esc(plan.id)}">削除</button>
         </div>`;

    const editArea = editable ? `
      <div class="plan-edit" hidden>
        <input type="text" class="plan-edit-input" autocomplete="off"
               placeholder="例: 2日目をゆっくりに / 宿を変えて / 予算を抑えて">
        <button class="plan-edit-send" type="button">修正する</button>
      </div>` : '';

    // 評価エリア（自分のプランのみ）。次回のプラン生成に好みとして活かす。
    // 1プラン1評価（上書き式）。記録済みは読み取り表示＋「修正」で再編集できる。
    const ratingArea = shared
      ? ''
      : (plan.rating
        ? ratedRateHtml(plan.rating, plan.rating_comment || '')
        : editableRateHtml(plan));

    card.innerHTML = `
      ${planBodyHtml(plan)}
      ${footer}
      ${editArea}
      ${ratingArea}
    `;

    if (editable) {
      // チャットで修正：入力欄の開閉（自分のプラン or 編集可で共有されたプラン）
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
                const proposed = Object.assign({}, d.plan, {
                  permission: plan.permission, grant_id: plan.grant_id,
                });
                card.replaceWith(renderPreview(proposed, plan, { shared }));
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
    }

    // 地図ボタン：クリックでコンテナを開閉し、初回のみ地図を初期化
    const mapBtn = card.querySelector('.plan-map-btn');
    if (mapBtn) {
      mapBtn.addEventListener('click', () => {
        const container = document.getElementById(mapBtn.dataset.mapId);
        if (!container) return;
        const opening = container.hidden;
        container.hidden = !opening;
        mapBtn.textContent = opening ? '🗺 地図を閉じる' : '🗺 地図で見る';
        if (opening) {
          // 座標は初回オープン時にサーバーでまとめて取得＆キャッシュ（保存は即時のまま）
          const cont = document.getElementById(mapBtn.dataset.mapId);
          if (cont) cont.innerHTML = '<div class="plan-map-loading">地図を読み込み中…</div>';
          fetch(`/api/plan_geo/${plan.id}`)
            .then(r => r.json())
            .then(geo => { Object.assign(plan, geo); })
            .catch(() => { /* 失敗時はスポットのオンデマンド取得にフォールバック */ })
            .finally(() => window.initPlanMap(mapBtn.dataset.mapId, mapBtn.dataset.planId, plan));
        }
      });
    }

    if (!shared) {
      card.querySelector('.share-btn').addEventListener('click', () => {
        window.openShareModal('plan', plan.id);
      });

      // ★評価＋コメント（次回のプラン生成に好みとして活かす）。記録後も「修正」で再編集可。
      mountRate(card, plan);

      card.querySelector('.delete-btn').addEventListener('click', async (e) => {
        if (!confirm('このプランを削除しますか？')) return;
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = '削除中...';
        const res = await fetch(`/delete_plan/${plan.id}`, { method: 'DELETE' });
        const result = await res.json();
        if (result.status === 'OK') {
          card.remove();
          if (!document.querySelector('#plans-container .plan-card')) showEmpty();
        } else {
          btn.disabled = false;
          btn.textContent = '削除';
          alert('削除に失敗しました');
        }
      });
    }

    if (shared) {
      // 共有された側が自分の保存プラン一覧から共有を解除する
      const ub = card.querySelector('.unshare-btn');
      if (ub) ub.addEventListener('click', async () => {
        if (!plan.grant_id || !confirm('この共有を保存プランから解除しますか？\n（相手の元データは消えません）')) return;
        ub.disabled = true;
        try {
          const res = await fetch(`/shared/grant/${plan.grant_id}`, { method: 'DELETE' });
          const result = await res.json();
          if (res.ok && result.deleted) {
            card.remove();
            if (!document.querySelector('#plans-container .plan-card')) showEmpty();
          } else {
            ub.disabled = false;
            alert('解除に失敗しました');
          }
        } catch (e) {
          ub.disabled = false;
          alert('解除に失敗しました');
        }
      });
    }

    return card;
  }

  // 旅行日の天気予報を読み込んでカード上部に表示する（自分のプランのみ）。
  function wxDate(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
    return m ? `${parseInt(m[2], 10)}/${parseInt(m[3], 10)}` : esc(s);
  }
  // 旅行日が予報の取れる範囲（当日〜16日先）かをクライアントで判定し、
  // 範囲外のプランは無駄なリクエストを投げない（N+1 リクエストの抑制）。
  function withinForecast(travelDate) {
    const m = /(\d{4})\D+(\d{1,2})\D+(\d{1,2})/.exec(travelDate || '');
    if (!m) return false;
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const min = new Date(today); min.setDate(min.getDate() - 7);   // 旅行中（数日前開始）も拾う
    const max = new Date(today); max.setDate(max.getDate() + 16);
    return d >= min && d <= max;
  }
  async function loadWeather(plan) {
    if (!withinForecast(plan.travel_date)) return;
    try {
      const res = await fetch(`/api/plan_weather/${plan.id}`);
      const data = await res.json();
      if (!data.days || data.days.length === 0) return;
      const el = document.getElementById(`weather-${plan.id}`);
      if (!el) return;
      el.innerHTML = '<span class="plan-weather-label">🌤 旅行日の天気</span>'
        + data.days.map(d => `<span class="wx-day"><b>${wxDate(d.date)}</b>`
          + `<span class="wx-emoji">${d.emoji}</span>`
          + `<span class="wx-temp">${d.tmax != null ? d.tmax + '°' : '–'}<i>/</i>${d.tmin != null ? d.tmin + '°' : '–'}</span></span>`).join('');
      el.hidden = false;
    } catch (e) { /* 天気は付加情報なので失敗は無視 */ }
  }

  function showEmpty() {
    const container = document.getElementById('plans-container');
    container.innerHTML = `<div class="empty-state"><div class="icon">🗂️</div>保存済みのプランはありません</div>`;
  }

  async function loadPlans() {
    const loading = document.getElementById('loading');
    const container = document.getElementById('plans-container');
    try {
      // 自分のプランと共有されたプランを同時に取得し、同じ一覧に並べる
      const [mineRes, sharedRes] = await Promise.all([
        fetch('/get_my_plans'),
        fetch('/get_shared_plans'),
      ]);
      const mine = await mineRes.json();
      let shared = { plans: [] };
      try { shared = await sharedRes.json(); } catch (e) { /* 共有取得失敗は無視 */ }

      loading.style.display = 'none';
      container.style.display = 'flex';

      const myPlans = (mine && mine.plans) || [];
      const sharedPlans = (shared && shared.status === 'OK' && shared.plans) || [];

      if (myPlans.length === 0 && sharedPlans.length === 0) {
        showEmpty();
        return;
      }
      myPlans.forEach(plan => { container.appendChild(renderPlan(plan)); loadWeather(plan); });
      sharedPlans.forEach(plan => container.appendChild(renderPlan(plan, { shared: true })));
    } catch (err) {
      loading.textContent = 'プランの読み込みに失敗しました';
      console.error(err);
    }
  }

  loadPlans();
