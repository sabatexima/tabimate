const CFG = JSON.parse(document.getElementById('page-config').textContent);
  const TRIP_ID = CFG.tripId;
  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // --- 共有モーダル ---
  document.getElementById('share-btn').addEventListener('click', () => {
    window.openShareModal('trip', TRIP_ID);
  });

  // --- お気に入り ---
  const favToggle = document.getElementById('fav-toggle');
  favToggle.addEventListener('click', async () => {
    const next = !favToggle.classList.contains('on');
    favToggle.disabled = true;
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}/favorite`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ favorite: next }),
      });
      const data = await res.json();
      if (res.ok) {
        const on = !!data.is_favorite;
        favToggle.classList.toggle('on', on);
        favToggle.textContent = on ? '★' : '☆';
      }
    } catch (e) { /* 据え置き */ }
    favToggle.disabled = false;
  });

  // --- タイトル編集 ---
  const titleEl = document.getElementById('trip-title');
  const titleRow = titleEl.parentElement;
  const titleEditor = document.getElementById('title-editor');
  const titleInput = document.getElementById('title-input');
  const titleSave = document.getElementById('title-save');
  const titleCancel = document.getElementById('title-cancel');

  function openTitleEdit() {
    titleInput.value = titleEl.textContent.trim();
    titleRow.hidden = true; titleEditor.hidden = false;
    titleInput.focus(); titleInput.select();
  }
  function closeTitleEdit() { titleEditor.hidden = true; titleRow.hidden = false; }

  document.getElementById('title-edit').addEventListener('click', openTitleEdit);
  titleCancel.addEventListener('click', closeTitleEdit);
  titleInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); titleSave.click(); }
    if (e.key === 'Escape') closeTitleEdit();
  });
  titleSave.addEventListener('click', async () => {
    const title = titleInput.value.trim();
    if (!title) { alert('タイトルを入力してください'); return; }
    titleSave.disabled = true; titleSave.textContent = '保存中...';
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      });
      const data = await res.json();
      if (res.ok && data.updated) {
        titleEl.textContent = data.title;
        document.title = data.title + ' — 旅の振り返り';
        closeTitleEdit();
      } else {
        alert(data.error || '更新に失敗しました');
      }
    } catch (e) { alert('更新に失敗しました'); }
    titleSave.disabled = false; titleSave.textContent = '保存';
  });

  // --- 日程（出発日・帰宅日）編集 ---
  const datesRow = document.getElementById('trip-dates');
  const datesText = document.getElementById('dates-text');
  const datesEditor = document.getElementById('dates-editor');
  const dateStart = document.getElementById('date-start');
  const dateEnd = document.getElementById('date-end');
  const datesSave = document.getElementById('dates-save');

  document.getElementById('dates-edit').addEventListener('click', () => {
    datesRow.hidden = true; datesEditor.hidden = false; dateStart.focus();
  });
  document.getElementById('dates-cancel').addEventListener('click', () => {
    datesEditor.hidden = true; datesRow.hidden = false;
  });
  // サーバ側の tripdates フィルターと同じ和文表記にする
  function fmtTripDates(start, end) {
    const p = (v) => {
      if (!v) return null;
      const [y, m, d] = String(v).slice(0, 10).split('-').map(Number);
      return (y && m && d) ? { y, m, d } : null;
    };
    let s = p(start), e = p(end);
    if (!s && !e) return '';
    if (s && !e) e = s;
    if (e && !s) s = e;
    const one = (x) => `${x.y}年${x.m}月${x.d}日`;
    if (s.y === e.y && s.m === e.m && s.d === e.d) return one(s);
    if (s.y !== e.y) return `${one(s)}〜${one(e)}`;
    if (s.m !== e.m) return `${one(s)}〜${e.m}月${e.d}日`;
    return `${one(s)}〜${e.d}日`;
  }
  datesSave.addEventListener('click', async () => {
    const start = dateStart.value || null;
    const end = dateEnd.value || null;
    if (start && end && end < start) { alert('帰宅日は出発日以降にしてください'); return; }
    datesSave.disabled = true; datesSave.textContent = '保存中...';
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_date: start, end_date: end }),
      });
      const data = await res.json();
      if (res.ok && data.updated) {
        const txt = fmtTripDates(data.start_date, data.end_date);
        datesText.textContent = txt ? `📅 ${txt}` : '日程未設定';
        datesEditor.hidden = true; datesRow.hidden = false;
      } else {
        alert(data.error || '更新に失敗しました');
      }
    } catch (e) { alert('更新に失敗しました'); }
    datesSave.disabled = false; datesSave.textContent = '保存';
  });

  // --- 写真アップロード ---
  const uploadBtn = document.getElementById('upload-btn');
  uploadBtn.addEventListener('click', async () => {
    const input = document.getElementById('photo-input');
    if (!input.files.length) { alert('写真を選択してください'); return; }
    const fd = new FormData();
    for (const f of input.files) fd.append('photos', f);
    uploadBtn.disabled = true; uploadBtn.textContent = 'アップロード中...';
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}/photos`, { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        const grid = document.getElementById('photo-grid');
        data.saved.forEach(p => grid.appendChild(makePhotoFigure(p)));
        const cnt = document.getElementById('photo-count');
        cnt.textContent = `現在 ${grid.querySelectorAll('.photo').length} 枚`;
        input.value = '';
      } else {
        alert(data.error || 'アップロードに失敗しました');
      }
    } catch (e) { alert('アップロードに失敗しました'); }
    uploadBtn.disabled = false; uploadBtn.textContent = 'アップロード';
  });

  // アップロード直後の写真も削除できるよう figure を組み立てる
  function makePhotoFigure(p) {
    const fig = document.createElement('figure');
    fig.className = 'photo';
    if (p.id != null) fig.dataset.id = p.id;
    const img = document.createElement('img');
    img.src = p.thumb_url || p.url;
    img.dataset.full = p.url;
    img.alt = 'photo'; img.loading = 'lazy'; img.decoding = 'async';
    img.onerror = () => { img.onerror = null; img.src = img.dataset.full; };
    const del = document.createElement('button');
    del.className = 'photo-del'; del.setAttribute('aria-label', '写真を削除'); del.textContent = '×';
    fig.appendChild(img); fig.appendChild(del);
    return fig;
  }

  // --- 写真を1枚削除 ---
  const photoGrid = document.getElementById('photo-grid');
  photoGrid.addEventListener('click', async (ev) => {
    const del = ev.target.closest('.photo-del');
    if (!del) return;
    const fig = del.closest('.photo');
    const id = fig.dataset.id;
    if (!id) { fig.remove(); return; }
    if (!confirm('この写真を削除しますか？元に戻せません。')) return;
    del.disabled = true;
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}/photos/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) {
        fig.remove();
        const cnt = document.getElementById('photo-count');
        cnt.textContent = `現在 ${photoGrid.querySelectorAll('.photo').length} 枚`;
      } else { alert('削除に失敗しました'); del.disabled = false; }
    } catch (e) { alert('削除に失敗しました'); del.disabled = false; }
  });

  // --- 写真の拡大表示（ライトボックス）---
  const lightbox = document.getElementById('lightbox');
  const lbImg = lightbox.querySelector('.lb-img');
  const lbCounter = lightbox.querySelector('.lb-counter');
  let lbIndex = 0;
  let lbCount = 0;

  function lbFigures() {
    return Array.from(photoGrid.querySelectorAll('.photo'));
  }
  function lbShow(i) {
    const figs = lbFigures();
    lbCount = figs.length;
    if (lbCount === 0) { lbClose(); return; }
    lbIndex = (i + lbCount) % lbCount;
    const img = figs[lbIndex].querySelector('img');
    lbImg.src = img ? (img.dataset.full || img.src) : '';
    lbCounter.textContent = `${lbIndex + 1} / ${lbCount}`;
  }
  function lbOpen(i) {
    lbShow(i);
    lightbox.hidden = false;
    lightbox.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }
  function lbClose() {
    lightbox.hidden = true;
    lightbox.setAttribute('aria-hidden', 'true');
    lbImg.src = '';
    document.body.style.overflow = '';
  }

  // 写真をタップで拡大（削除ボタンのクリックは除外）
  photoGrid.addEventListener('click', (ev) => {
    if (ev.target.closest('.photo-del')) return;
    const fig = ev.target.closest('.photo');
    if (!fig || !fig.querySelector('img')) return;
    lbOpen(lbFigures().indexOf(fig));
  });

  lightbox.querySelector('.lb-close').addEventListener('click', lbClose);
  lightbox.querySelector('.lb-prev').addEventListener('click', (e) => { e.stopPropagation(); lbShow(lbIndex - 1); });
  lightbox.querySelector('.lb-next').addEventListener('click', (e) => { e.stopPropagation(); lbShow(lbIndex + 1); });
  // 背景（画像以外）クリックで閉じる
  lightbox.addEventListener('click', (ev) => { if (ev.target === lightbox) lbClose(); });
  // キーボード操作（Esc=閉じる / ←→=前後）
  document.addEventListener('keydown', (ev) => {
    if (lightbox.hidden) return;
    if (ev.key === 'Escape') lbClose();
    else if (ev.key === 'ArrowLeft') lbShow(lbIndex - 1);
    else if (ev.key === 'ArrowRight') lbShow(lbIndex + 1);
  });
  // スワイプ（スマホ）で前後切り替え
  let lbTouchX = null;
  lightbox.addEventListener('touchstart', (e) => { lbTouchX = e.changedTouches[0].clientX; }, { passive: true });
  lightbox.addEventListener('touchend', (e) => {
    if (lbTouchX === null) return;
    const dx = e.changedTouches[0].clientX - lbTouchX;
    if (Math.abs(dx) > 40) lbShow(lbIndex + (dx < 0 ? 1 : -1));
    lbTouchX = null;
  });

  // --- 付箋生成 ---
  const board = document.getElementById('sticker-board');
  function renderStickers(items) {
    board.innerHTML = items.map(s =>
      `<div class="sticker">${esc(s.text)}<button class="del" aria-label="削除">×</button></div>`
    ).join('');
    const empty = document.getElementById('sticker-empty');
    if (empty) empty.style.display = items.length ? 'none' : '';
  }

  const stickerBtn = document.getElementById('sticker-btn');
  stickerBtn.addEventListener('click', async () => {
    stickerBtn.disabled = true; stickerBtn.textContent = '付箋を作っています...';
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}/stickers/generate`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        renderStickers(data.stickers || []);
      } else {
        alert(data.error || '付箋を作れませんでした');
      }
    } catch (e) { alert('付箋を作れませんでした'); }
    stickerBtn.disabled = false; stickerBtn.textContent = '付箋を作る';
  });

  // --- 付箋を1枚削除 ---
  board.addEventListener('click', async (ev) => {
    const del = ev.target.closest('.del');
    if (!del) return;
    const card = del.closest('.sticker');
    const id = card.dataset.id;
    // 生成直後（未保存IDなし）の場合は見た目だけ消す
    if (!id) { card.remove(); return; }
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}/stickers/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) card.remove();
    } catch (e) { /* 失敗時は何もしない（次の生成で整合する） */ }
  });

  // --- 旅の削除（写真・付箋もまとめて消える） ---
  const deleteBtn = document.getElementById('delete-trip-btn');
  deleteBtn.addEventListener('click', async () => {
    const title = titleEl.textContent.trim() || 'この旅';
    if (!confirm(`「${title}」を削除しますか？\n写真・付箋もすべて消え、元に戻せません。`)) return;
    deleteBtn.disabled = true; deleteBtn.textContent = '削除中...';
    try {
      const res = await fetch(`/reflection/trips/${TRIP_ID}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) {
        location.href = CFG.indexUrl;
      } else {
        alert('削除に失敗しました');
        deleteBtn.disabled = false; deleteBtn.textContent = 'この旅を削除する';
      }
    } catch (e) {
      alert('削除に失敗しました');
      deleteBtn.disabled = false; deleteBtn.textContent = 'この旅を削除する';
    }
  });
