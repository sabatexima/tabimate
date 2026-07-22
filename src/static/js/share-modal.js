(function () {
  let rtype = null, rid = null, editableSupported = true;
  const overlay = document.getElementById('sm-overlay');
  const linkPerm = document.getElementById('sm-link-perm');
  const grantPerm = document.getElementById('sm-grant-perm');
  const linkList = document.getElementById('sm-link-list');
  const grantList = document.getElementById('sm-grant-list');
  const linkEmpty = document.getElementById('sm-link-empty');
  const grantEmpty = document.getElementById('sm-grant-empty');
  const grantEmail = document.getElementById('sm-grant-email');

  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function permBadge(p) {
    return p === 'edit'
      ? '<span class="sm-badge edit">編集可</span>'
      : '<span class="sm-badge">閲覧</span>';
  }
  function setEditOptionVisible(visible) {
    [linkPerm, grantPerm].forEach(sel => {
      const opt = sel.querySelector('option[value=edit]');
      if (opt) opt.hidden = !visible;
      if (!visible) sel.value = 'view';
    });
  }

  function renderLinks(links) {
    linkList.innerHTML = '';
    linkEmpty.style.display = links.length ? 'none' : '';
    links.forEach(l => {
      const li = document.createElement('li');
      li.className = 'sm-li';
      li.innerHTML = `
        <span class="sm-grow sm-url">${esc(l.url)}</span>
        ${permBadge(l.permission)}
        <button class="sm-mini copy">コピー</button>
        <button class="sm-mini del">取消</button>`;
      li.querySelector('.copy').addEventListener('click', () => {
        navigator.clipboard.writeText(l.url).then(() => {
          const b = li.querySelector('.copy'); b.textContent = 'コピー済'; setTimeout(() => b.textContent = 'コピー', 1200);
        });
      });
      li.querySelector('.del').addEventListener('click', async () => {
        if (!confirm('このリンクを取り消しますか？')) return;
        try {
          const res = await fetch(`/share/link/${l.id}`, { method: 'DELETE' });
          if (res.ok) refresh();
          else alert('リンクの取り消しに失敗しました');
        } catch (e) { alert('リンクの取り消しに失敗しました'); }
      });
      linkList.appendChild(li);
    });
  }

  function renderGrants(grants) {
    grantList.innerHTML = '';
    grantEmpty.style.display = grants.length ? 'none' : '';
    grants.forEach(g => {
      const li = document.createElement('li');
      li.className = 'sm-li';
      // 編集共有が可能なリソース（旅）では、その場で権限を変更できるよう
      // セレクトを表示する。プランは閲覧専用なのでバッジ表示のみ。
      const permHtml = editableSupported
        ? `<select class="sm-perm">
             <option value="view"${g.permission !== 'edit' ? ' selected' : ''}>閲覧のみ</option>
             <option value="edit"${g.permission === 'edit' ? ' selected' : ''}>編集も可</option>
           </select>`
        : permBadge(g.permission);
      li.innerHTML = `
        <span class="sm-grow">${esc(g.grantee_email)}</span>
        ${permHtml}
        <button class="sm-mini del">取消</button>`;
      const sel = li.querySelector('.sm-perm');
      if (sel) sel.addEventListener('change', async () => {
        const prev = g.permission;
        sel.disabled = true;
        try {
          // add_grant は upsert（同一メールなら権限を更新）なので再POSTで変更できる
          const res = await fetch(`/share/${rtype}/${rid}/grant`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: g.grantee_email, permission: sel.value }),
          });
          if (res.ok) { g.permission = sel.value; }
          else { alert('権限の変更に失敗しました'); sel.value = prev; }
        } catch (e) { alert('権限の変更に失敗しました'); sel.value = prev; }
        sel.disabled = false;
      });
      li.querySelector('.del').addEventListener('click', async () => {
        if (!confirm(`${g.grantee_email} への共有を取り消しますか？`)) return;
        try {
          const res = await fetch(`/share/grant/${g.id}`, { method: 'DELETE' });
          if (res.ok) refresh();
          else alert('共有の取り消しに失敗しました');
        } catch (e) { alert('共有の取り消しに失敗しました'); }
      });
      grantList.appendChild(li);
    });
  }

  async function refresh() {
    try {
      const res = await fetch(`/share/${rtype}/${rid}`);
      const data = await res.json();
      editableSupported = !!data.editable_supported;
      setEditOptionVisible(editableSupported);
      renderLinks(data.links || []);
      renderGrants(data.grants || []);
    } catch (e) { /* noop */ }
  }

  document.getElementById('sm-link-create').addEventListener('click', async (e) => {
    const btn = e.currentTarget; btn.disabled = true;
    try {
      await fetch(`/share/${rtype}/${rid}/link`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permission: linkPerm.value }),
      });
      await refresh();
    } catch (e) { alert('リンクの作成に失敗しました'); }
    btn.disabled = false;
  });

  document.getElementById('sm-grant-add').addEventListener('click', async (e) => {
    const email = grantEmail.value.trim();
    if (!email || !email.includes('@')) { alert('正しいメールアドレスを入力してください'); return; }
    const btn = e.currentTarget; btn.disabled = true;
    try {
      const res = await fetch(`/share/${rtype}/${rid}/grant`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, permission: grantPerm.value }),
      });
      const data = await res.json();
      if (res.ok) { grantEmail.value = ''; await refresh(); }
      else alert(data.error || '共有の追加に失敗しました');
    } catch (e) { alert('共有の追加に失敗しました'); }
    btn.disabled = false;
  });

  function close() { overlay.style.display = 'none'; }
  document.getElementById('sm-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  window.openShareModal = function (resourceType, resourceId) {
    rtype = resourceType; rid = resourceId;
    grantEmail.value = '';
    overlay.style.display = 'flex';
    refresh();
  };
})();
