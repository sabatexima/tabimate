/* 保存プラン一覧。表紙カード（本棚）だけを描画し、
   クリックで詳細ページ（自分: /plan/<id> ・共有: /shared/plan/<id>）へ移動する。 */
function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmt(n) {
  return n != null ? Number(n).toLocaleString() : '—';
}

const container = document.getElementById('plans-container');

// 表紙カード（絵本の背表紙＋タイトル＋ちいさなチップ）
function coverCard(plan, opts = {}) {
  const shared = !!opts.shared;
  const item = document.createElement('div');
  item.className = 'plan-item';

  const href = shared ? `/shared/plan/${esc(plan.id)}` : `/plan/${esc(plan.id)}`;
  const saved = plan.created_at
    ? new Date(plan.created_at).toLocaleDateString('ja-JP')
    : '';
  const cost = plan.total_per_person
    ? `💴 ${fmt(plan.total_per_person)}円/人`
    : (plan.budget_limit ? `💴 〜${fmt(plan.budget_limit)}円/人` : '');
  const chips = [
    plan.duration ? `⏱ ${esc(plan.duration)}` : '',
    plan.num_people != null ? `👥 ${esc(plan.num_people)}人` : '',
    cost,
  ].filter(Boolean).map((c) => `<span class="cover-chip">${c}</span>`).join('');
  const rated = !shared && plan.rating;

  item.innerHTML = `
    <a class="plan-cover-card" href="${href}">
      <span class="book-ribbon">${rated ? '★' + esc(plan.rating) : ''}</span>
      <span class="cover-icon" aria-hidden="true">🗾</span>
      <span class="cover-main">
        <span class="cover-dest">${esc(plan.destination)}${shared ? '<span class="cover-shared">🤝 共有</span>' : ''}</span>
        <span class="cover-chips">${chips}</span>
        ${saved ? `<span class="cover-meta">保存日 ${esc(saved)}</span>` : ''}
      </span>
      <span class="cover-go" aria-hidden="true">›</span>
    </a>
    <div class="card-menu">
      <button class="kebab" type="button" aria-label="メニュー">⋯</button>
      <div class="menu" hidden>
        ${shared
          ? `<button class="menu-unshare" type="button">🤝 共有を解除</button>`
          : `<button class="menu-del" type="button">🗑 削除</button>`}
      </div>
    </div>`;

  const menu = item.querySelector('.menu');
  item.querySelector('.kebab').addEventListener('click', () => {
    const willOpen = menu.hidden;
    closeAllMenus();
    menu.hidden = !willOpen;
  });

  const del = item.querySelector('.menu-del');
  if (del) del.addEventListener('click', async () => {
    menu.hidden = true;
    if (!confirm(`「${plan.destination}」のプランを削除しますか？`)) return;
    try {
      const res = await fetch(`/delete_plan/${plan.id}`, { method: 'DELETE' });
      const result = await res.json();
      if (result.status === 'OK') {
        item.remove();
        if (!container.querySelector('.plan-item')) showEmpty();
        return;
      }
    } catch (e) { /* 下のエラー表示へ */ }
    alert('削除に失敗しました');
  });

  const unshare = item.querySelector('.menu-unshare');
  if (unshare) unshare.addEventListener('click', async () => {
    menu.hidden = true;
    if (!plan.grant_id || !confirm('この共有を保存プランから解除しますか？\n（相手の元データは消えません）')) return;
    try {
      const res = await fetch(`/shared/grant/${plan.grant_id}`, { method: 'DELETE' });
      const result = await res.json();
      if (res.ok && result.deleted) {
        item.remove();
        if (!container.querySelector('.plan-item')) showEmpty();
        return;
      }
    } catch (e) { /* 下のエラー表示へ */ }
    alert('解除に失敗しました');
  });

  return item;
}

function closeAllMenus() {
  container.querySelectorAll('.menu').forEach(m => m.hidden = true);
}
document.addEventListener('click', (ev) => {
  if (!ev.target.closest('.card-menu')) closeAllMenus();
});

function showEmpty() {
  container.style.display = 'block';
  container.innerHTML = `<div class="empty-state">
    <img class="empty-mate" src="/static/img/mate.png" alt="">
    <p>まだ保存した旅はありません。<br>ちゃむと一緒に、最初の旅をつくろう🍀</p>
    <a class="empty-cta" href="/chat">✨ 最初の旅をつくる</a>
  </div>`;
}

async function loadPlans() {
  const loading = document.getElementById('loading');
  try {
    // 自分のプランと共有されたプランを同時に取得し、同じ本棚に並べる
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
    myPlans.forEach(plan => container.appendChild(coverCard(plan)));
    sharedPlans.forEach(plan => container.appendChild(coverCard(plan, { shared: true })));
  } catch (err) {
    loading.textContent = 'プランの読み込みに失敗しました';
    console.error(err);
  }
}

loadPlans();
