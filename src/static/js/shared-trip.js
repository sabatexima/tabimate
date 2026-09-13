/* 共有された旅のページ（shared/trip.html）。
   自分の旅のページ（reflection-trip.js）と似ているが、別ファイルにしてある。
   見ている人が「所有者ではない」ため、できることが2つの軸で変わるから:

     canEdit  … 編集権限つきで共有された人だけ。写真・付箋・旅の削除ができる
     loggedIn … ログインしている人だけ。自分のお気に入りに入れられる

   公開リンク（ログイン不要）で来た人は両方 false になり、何も操作できない。
   権限の判定はサーバー（views/sharing.py）が済ませていて、その結果が
   テンプレートから #page-config に JSON で載ってくる。ここでは受け取るだけ。 */

const CFG = JSON.parse(document.getElementById('page-config').textContent);

// ここから先は編集権限つきで共有された人だけ。権限の無い人には
// テンプレート側がボタン自体を出していないので、ここも丸ごと動かさない
if (CFG.canEdit) {
  const TRIP_ID = CFG.tripId;
  const SHARE_TOKEN = CFG.shareToken;
  // 公開リンク（/s/<token>）から来た場合、その先の操作でもトークンを
  // 引き継がないとサーバーに「誰だか分からない」と断られる。
  // ログイン中の人は SHARE_TOKEN が空なので、URL はそのまま
  function withToken(url) {
    return SHARE_TOKEN ? url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(SHARE_TOKEN) : url;
  }
  // 付箋の文字をそのまま innerHTML に入れる場所があるので、HTMLとして
  // 解釈されうる文字を潰す（AIの出力にも記号は混じる）
  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // 写真アップロード
  // 「写真を選ぶ」で選んだ枚数を横に出す（input 自体は隠してある）
  const photoInput = document.getElementById('photo-input');
  const chosen = document.getElementById('photo-chosen');
  if (photoInput && chosen) {
    photoInput.addEventListener('change', () => {
      const n = photoInput.files ? photoInput.files.length : 0;
      chosen.textContent = n ? `${n}枚を選択中` : '';
    });
  }
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

  // アップロード直後の写真も削除できるよう figure を組み立てる。
  // テンプレート側と同じ形（figure.photo > img + button.photo-del）にしないと
  // ポラロイドの CSS が当たらず、その写真だけ枠なしで並ぶ
  function makePhotoFigure(p) {
    const fig = document.createElement('figure');
    fig.className = 'photo';
    if (p.id != null) fig.dataset.id = p.id;
    const img = document.createElement('img');
    img.src = p.thumb_url || p.url;
    img.dataset.full = p.url;
    img.alt = 'photo'; img.loading = 'lazy'; img.decoding = 'async';
    // サムネイルがまだ無い写真（生成前・古いもの）は原寸に落とす。
    // onerror を null にしてから差し替えないと、原寸も失敗したとき無限に回る
    img.onerror = () => { img.onerror = null; img.src = img.dataset.full; };
    const del = document.createElement('button');
    del.className = 'photo-del'; del.setAttribute('aria-label', '写真を削除'); del.textContent = '×';
    fig.appendChild(img); fig.appendChild(del);
    return fig;
  }

  // 写真を1枚削除（編集権限）。写真は後から増えるので、1枚ずつに
  // イベントを付けず、親のグリッドで受けて .photo-del かどうかを見る
  const photoGrid = document.getElementById('photo-grid');
  if (photoGrid) photoGrid.addEventListener('click', async (ev) => {
    const del = ev.target.closest('.photo-del');
    if (!del) return;
    const fig = del.closest('.photo');
    const id = fig.dataset.id;
    // id が無い＝まだサーバーに送られていない見た目だけの要素。消すだけでよい
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
    } catch (e) { /* 失敗時は次の生成で整合する（付箋は作り直せる） */ }
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

// ここからはログインしている人だけ。共有された旅でも「自分の」お気に入りに
// 入れられる（★は旅ではなく、見ている人ごとに持つ。DBは trip_favorites 表）
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
