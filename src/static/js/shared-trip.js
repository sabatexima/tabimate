const CFG = JSON.parse(document.getElementById('page-config').textContent);

// 編集権限がある場合のみ: 付箋/写真/旅の編集・削除
if (CFG.canEdit) {
  const TRIP_ID = CFG.tripId;
  const SHARE_TOKEN = CFG.shareToken;
  function withToken(url) {
    return SHARE_TOKEN ? url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(SHARE_TOKEN) : url;
  }
  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // 写真アップロード
  const uploadBtn = document.getElementById('upload-btn');
  if (uploadBtn) uploadBtn.addEventListener('click', async () => {
    const input = document.getElementById('photo-input');
    if (!input.files.length) { alert('写真を選択してください'); return; }
    const fd = new FormData();
    for (const f of input.files) fd.append('photos', f);
    uploadBtn.disabled = true; uploadBtn.textContent = 'アップロード中...';
    try {
      const res = await fetch(withToken(`/shared/trip/${TRIP_ID}/photos`), { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        const grid = document.getElementById('photo-grid');
        data.saved.forEach(p => grid.appendChild(makePhotoFigure(p)));
        document.getElementById('photo-count').textContent = `現在 ${grid.querySelectorAll('.photo').length} 枚`;
        input.value = '';
      } else { alert(data.error || 'アップロードに失敗しました'); }
    } catch (e) { alert('アップロードに失敗しました'); }
    uploadBtn.disabled = false; uploadBtn.textContent = 'アップロード';
  });

  // 付箋生成
  const board = document.getElementById('sticker-board');
  const stickerBtn = document.getElementById('sticker-btn');
  if (stickerBtn) stickerBtn.addEventListener('click', async () => {
    stickerBtn.disabled = true; stickerBtn.textContent = '付箋を作っています...';
    try {
      const res = await fetch(withToken(`/shared/trip/${TRIP_ID}/stickers/generate`), { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        board.innerHTML = (data.stickers || []).map(s =>
          `<div class="sticker">${esc(s.text)}<button class="del" aria-label="削除">×</button></div>`
        ).join('');
        const empty = document.getElementById('sticker-empty');
        if (empty) empty.style.display = (data.stickers || []).length ? 'none' : '';
      } else { alert(data.error || '付箋を作れませんでした'); }
    } catch (e) { alert('付箋を作れませんでした'); }
    stickerBtn.disabled = false; stickerBtn.textContent = '付箋を作り直す';
  });

  // アップロード直後の写真も削除できるよう figure を組み立てる
  function makePhotoFigure(p) {
    const fig = document.createElement('figure');
    fig.className = 'photo';
    if (p.id != null) fig.dataset.id = p.id;
    const img = document.createElement('img');
    img.src = p.url; img.alt = 'photo'; img.loading = 'lazy'; img.decoding = 'async';
    const del = document.createElement('button');
    del.className = 'photo-del'; del.setAttribute('aria-label', '写真を削除'); del.textContent = '×';
    fig.appendChild(img); fig.appendChild(del);
    return fig;
  }

  // 写真を1枚削除（編集権限）
  const photoGrid = document.getElementById('photo-grid');
  if (photoGrid) photoGrid.addEventListener('click', async (ev) => {
    const del = ev.target.closest('.photo-del');
    if (!del) return;
    const fig = del.closest('.photo');
    const id = fig.dataset.id;
    if (!id) { fig.remove(); return; }
    if (!confirm('この写真を削除しますか？元に戻せません。')) return;
    del.disabled = true;
    try {
      const res = await fetch(withToken(`/shared/trip/${TRIP_ID}/photos/${id}`), { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) {
        fig.remove();
        document.getElementById('photo-count').textContent =
          `現在 ${photoGrid.querySelectorAll('.photo').length} 枚`;
      } else { alert('削除に失敗しました'); del.disabled = false; }
    } catch (e) { alert('削除に失敗しました'); del.disabled = false; }
  });

  // 付箋を1枚削除（編集権限）
  if (board) board.addEventListener('click', async (ev) => {
    const del = ev.target.closest('.del');
    if (!del) return;
    const card = del.closest('.sticker');
    const id = card.dataset.id;
    if (!id) { card.remove(); return; }
    try {
      const res = await fetch(withToken(`/shared/trip/${TRIP_ID}/stickers/${id}`), { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) card.remove();
    } catch (e) { /* 失敗時は次の生成で整合する */ }
  });

  // 旅ごと削除（編集権限）
  const deleteTripBtn = document.getElementById('delete-trip-btn');
  if (deleteTripBtn) deleteTripBtn.addEventListener('click', async () => {
    if (!confirm('この旅を削除しますか？\n写真・付箋もすべて消え、共有元の所有者の記録も消えます。元に戻せません。')) return;
    deleteTripBtn.disabled = true; deleteTripBtn.textContent = '削除中...';
    try {
      const res = await fetch(withToken(`/shared/trip/${TRIP_ID}`), { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) {
        alert('旅を削除しました');
        location.href = '/reflection/';
      } else {
        alert('削除に失敗しました');
        deleteTripBtn.disabled = false; deleteTripBtn.textContent = 'この旅を削除する';
      }
    } catch (e) {
      alert('削除に失敗しました');
      deleteTripBtn.disabled = false; deleteTripBtn.textContent = 'この旅を削除する';
    }
  });
}

// ログイン済みの場合のみ: 閲覧者自身のお気に入り登録
if (CFG.loggedIn) {
  // 共有された旅を、閲覧者自身のお気に入りとして登録/解除する
  (function () {
    const btn = document.getElementById('fav-toggle');
    if (!btn) return;
    const tripId = CFG.tripId;
    let on = !!CFG.isFavorite;
    btn.addEventListener('click', async () => {
      const next = !on;
      btn.disabled = true;
      try {
        const res = await fetch(`/reflection/trips/${tripId}/favorite`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ favorite: next }),
        });
        const data = await res.json();
        if (res.ok) {
          on = !!data.is_favorite;
          btn.classList.toggle('on', on);
          btn.textContent = on ? '★ お気に入り' : '☆ お気に入り';
        }
      } catch (e) { /* 失敗時は据え置き */ }
      btn.disabled = false;
    });
  })();
}
