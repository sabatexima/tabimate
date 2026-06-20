function esc(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function fmt(n) {
    return n != null ? Number(n).toLocaleString() : '—';
  }

  function accordion(icon, label, items) {
    if (!items || items.length === 0) return '';
    const lis = items.map(i => `<li>${esc(i)}</li>`).join('');
    return `<details>
      <summary>${icon} ${esc(label)}</summary>
      <div class="plan-accordion-body"><ul>${lis}</ul></div>
    </details>`;
  }

  function renderPlan(plan, opts = {}) {
    const shared = !!opts.shared;
    const card = document.createElement('div');
    card.className = 'plan-card';

    const saved = plan.created_at
      ? new Date(plan.created_at).toLocaleDateString('ja-JP')
      : '';

    const footer = shared
      ? `<div class="plan-footer">
           <span class="shared-flag">🤝 共有された</span>
           <a class="open-link" href="/shared/plan/${esc(plan.id)}">詳細を開く ›</a>
         </div>`
      : `<div class="plan-footer">
           <button class="share-btn" data-id="${esc(plan.id)}">🔗 共有</button>
           <button class="delete-btn" data-id="${esc(plan.id)}">削除</button>
         </div>`;

    card.innerHTML = `
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
      <div class="plan-accordion">
        ${accordion('✨', '主要観光地', plan.spots)}
        ${accordion('🍱', 'グルメ', plan.restaurants)}
        ${accordion('🏨', '宿泊施設', plan.accommodation)}
        ${accordion('📅', 'スケジュール', plan.schedule)}
        ${accordion('💰', '費用見積もり', plan.budget_estimate)}
      </div>
      ${footer}
    `;

    if (!shared) {
      card.querySelector('.share-btn').addEventListener('click', () => {
        window.openShareModal('plan', plan.id);
      });

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

    return card;
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
      myPlans.forEach(plan => container.appendChild(renderPlan(plan)));
      sharedPlans.forEach(plan => container.appendChild(renderPlan(plan, { shared: true })));
    } catch (err) {
      loading.textContent = 'プランの読み込みに失敗しました';
      console.error(err);
    }
  }

  loadPlans();
