/* 旅の振り返り一覧（reflection/index.html）＝アルバムの表紙が並ぶページ。

   カードそのものはサーバー（Jinja2）が描いて返す。ここがやるのは、
   その並びを触る操作だけ:
     ・新しい旅を作る
     ・★ / 削除 / 共有解除
     ・検索・並び替え・お気に入り絞り込み

   検索と並び替えは**サーバーに問い合わせない**。旅の件数はせいぜい数十で、
   全カードが最初からDOMにあるため、hidden の付け外しと並べ替えで足りる。
   通信が無いぶん、打った瞬間に絞り込まれる。

   カードが持つ情報は data-* 属性（data-title / data-created / data-favorite …）に
   載せてあり、JS はそこだけを見る。テンプレートを直すときはこの属性も一緒に。 */

const CFG = JSON.parse(document.getElementById('page-config').textContent);
  // --- 新しい旅フォームの開閉 ---
  const toggleBtn = document.getElementById('new-trip-toggle');
  const form = document.getElementById('new-trip-form');
  const ntClose = document.getElementById('nt-close');
  // 既定はボタン1つだけ。押して初めてフォームが開く（一覧を主役にするため）
  function openForm() {
    form.hidden = false; toggleBtn.hidden = true;
    document.getElementById('f-title').focus();   // 開いたらすぐ打てるように
  }
  function closeForm() { form.hidden = true; toggleBtn.hidden = false; }
  toggleBtn.addEventListener('click', openForm);
  ntClose.addEventListener('click', closeForm);

  // --- 作成 ---
  const createBtn = document.getElementById('create-btn');
  createBtn.addEventListener('click', async () => {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { alert('旅のタイトルを入力してください'); return; }
    const start_date = document.getElementById('f-start').value || null;
    const end_date = document.getElementById('f-end').value || null;
    createBtn.disabled = true; createBtn.textContent = '作成中...';
    try {
      const res = await fetch(CFG.createUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, start_date, end_date }),
      });
      const data = await res.json();
      if (res.ok && data.id) {
        location.href = `/reflection/trips/${data.id}`;
      } else {
        alert(data.error || '作成に失敗しました');
        createBtn.disabled = false; createBtn.textContent = '作成';
      }
    } catch (e) {
      alert('作成に失敗しました'); createBtn.disabled = false; createBtn.textContent = '作成';
    }
  });

  // --- カード上の操作（★・⋯メニュー・削除・共有解除）---
  // カードは数十枚あるので、1枚ずつイベントを付けず、親の #trips で
  // まとめて受けて「何が押されたか」を closest() で判定する
  const tripsEl = document.getElementById('trips');

  function closeAllMenus() {
    tripsEl.querySelectorAll('.menu').forEach(m => m.hidden = true);
  }

  tripsEl.addEventListener('click', async (ev) => {
    // 共有された旅の「共有解除」（受領者が自分のアルバムから外す）
    const unshare = ev.target.closest('.unshare-btn');
    if (unshare) {
      ev.preventDefault();
      const card = unshare.closest('.trip-card');
      const id = unshare.dataset.grant;
      if (!id || !confirm('この共有を自分のアルバムから解除しますか？\n（相手の元データは消えません）')) return;
      unshare.disabled = true;
      try {
        const res = await fetch(`/shared/grant/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.deleted) {
          card.remove();
          if (typeof applyFilterSort === 'function') applyFilterSort();
        } else {
          alert('解除に失敗しました');
          unshare.disabled = false;
        }
      } catch (e) {
        alert('解除に失敗しました');
        unshare.disabled = false;
      }
      return;
    }

    // お気に入りトグル。★はカード全体を覆う <a> の中にあるので、
    // preventDefault() しないと詳細ページへ飛んでしまう
    const fav = ev.target.closest('.fav-btn');
    if (fav) {
      ev.preventDefault();
      const card = fav.closest('.trip-card');
      const id = card.dataset.id;
      const next = card.dataset.favorite !== '1';
      fav.disabled = true;
      try {
        const res = await fetch(`/reflection/trips/${id}/favorite`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ favorite: next }),
        });
        const data = await res.json();
        if (res.ok) {
          // 見た目だけでなく data 属性も更新する。並び替え（お気に入り順）と
          // 絞り込みはこの属性を見るので、片方だけ変えるとずれる
          const on = !!data.is_favorite;
          card.dataset.favorite = on ? '1' : '0';
          fav.classList.toggle('on', on);
          fav.textContent = on ? '★' : '☆';
          applyFilterSort();
        }
      } catch (e) { /* 失敗時は据え置き */ }
      fav.disabled = false;
      return;
    }

    // メニューの開閉
    const kebab = ev.target.closest('.kebab');
    if (kebab) {
      ev.preventDefault();
      const menu = kebab.parentElement.querySelector('.menu');
      const willOpen = menu.hidden;
      closeAllMenus();
      menu.hidden = !willOpen;
      return;
    }

    // 旅の削除（写真・付箋もまとめて消える）
    const del = ev.target.closest('.menu-del');
    if (!del) return;
    ev.preventDefault();
    const card = del.closest('.trip-card');
    const id = card.dataset.id;
    const title = card.dataset.title || 'この旅';
    closeAllMenus();
    if (!confirm(`「${title}」を削除しますか？\n写真・付箋もすべて消え、元に戻せません。`)) return;
    try {
      const res = await fetch(`/reflection/trips/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.deleted) {
        card.remove();
        if (!document.querySelector('.trip-card')) {
          tripsEl.innerHTML =
            '<div class="empty-state" id="empty"><div class="icon">🧳</div>まだ旅がありません。最初の旅を作ってみましょう。</div>';
        }
      } else {
        alert('削除に失敗しました');
      }
    } catch (e) {
      alert('削除に失敗しました');
    }
  });

  // メニュー外クリックで閉じる
  document.addEventListener('click', (ev) => {
    if (!ev.target.closest('.card-menu')) closeAllMenus();
  });

  // --- 検索・並び替え・お気に入り絞り込み（すべて手元で・通信なし）---
  const searchEl = document.getElementById('album-search');
  const sortEl = document.getElementById('album-sort');
  const noResults = document.getElementById('no-results');
  const favFilterBtn = document.getElementById('fav-filter');
  let favOnly = false;

  // カタカナ→ひらがな（検索でカナ表記ゆれを吸収）
  const kataToHira = (s) => s.replace(/[ァ-ヶ]/g,
    (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60));
  // 全角/半角・大文字小文字・カナ種別を正規化して比較しやすくする
  const norm = (s) => kataToHira((s || '').toString().normalize('NFKC').toLowerCase());

  // 並び替えの比較関数。日付は ISO 文字列なので、そのまま文字列比較でよい
  function compareCards(a, b, mode) {
    // カードの data-* から、比較しやすい形で取り出す小道具
    const txt = (c) => norm(c.dataset.title);
    const num = (c, k) => parseInt(c.dataset[k] || '0', 10) || 0;
    const str = (c, k) => c.dataset[k] || '';
    switch (mode) {
      case 'created_asc':  return str(a, 'created').localeCompare(str(b, 'created'));
      // お気に入りを先頭に、同条件内は新しい順
      case 'fav_first':    return (num(b, 'favorite') - num(a, 'favorite'))
                                  || str(b, 'created').localeCompare(str(a, 'created'));
      case 'start_desc':   return str(b, 'start').localeCompare(str(a, 'start'));
      // 出発日なしは末尾へ（昇順）
      case 'start_asc':    return (str(a, 'start') || '9999').localeCompare(str(b, 'start') || '9999');
      case 'title_asc':    return txt(a).localeCompare(txt(b), 'ja');
      case 'photos_desc':  return num(b, 'photos') - num(a, 'photos');
      case 'created_desc':
      default:             return str(b, 'created').localeCompare(str(a, 'created'));
    }
  }

  // 絞り込みと並び替えをまとめてかけ直す。★の付け外しや共有解除のあとにも呼ぶ
  function applyFilterSort() {
    if (!searchEl) return;   // 旅が0件のときは検索欄自体が無い
    // スペース区切りは AND 検索（各語をすべて含むものだけ表示）
    const terms = norm(searchEl.value).trim().split(/\s+/).filter(Boolean);
    const cards = Array.from(tripsEl.querySelectorAll('.trip-card'));
    let visible = 0;
    cards.forEach((c) => {
      const hay = norm(c.dataset.title) + ' ' + norm(c.dataset.stickers);
      const matchText = terms.every((t) => hay.indexOf(t) !== -1);
      const matchFav = !favOnly || c.dataset.favorite === '1';
      const show = matchText && matchFav;
      c.hidden = !show;
      if (show) visible++;
    });
    // 並べ替えは appendChild で末尾へ動かすだけ。既にDOMにある要素を
    // append すると「移動」になるので、作り直さずに順番だけ変えられる
    cards.slice().sort((a, b) => compareCards(a, b, sortEl.value))
         .forEach((c) => tripsEl.appendChild(c));
    if (noResults) noResults.hidden = visible !== 0;
  }

  if (favFilterBtn) {
    favFilterBtn.addEventListener('click', () => {
      favOnly = !favOnly;
      favFilterBtn.classList.toggle('active', favOnly);
      favFilterBtn.setAttribute('aria-pressed', favOnly ? 'true' : 'false');
      favFilterBtn.querySelector('.star').textContent = favOnly ? '★' : '☆';
      applyFilterSort();
    });
  }

  if (searchEl && sortEl) {
    searchEl.addEventListener('input', applyFilterSort);
    sortEl.addEventListener('change', applyFilterSort);
  }
