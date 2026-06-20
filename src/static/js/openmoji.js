/* 装飾的な絵文字を OpenMoji（手書き風）の画像に差し替える。
   ★☆（お気に入り）・☰（メニュー）・✓・✎ などの機能アイコンは対象外。
   静的・動的どちらの絵文字にも対応（MutationObserverで後から挿入された分も置換）。 */
(function () {
  const BASE = 'https://cdn.jsdelivr.net/npm/openmoji@15.0.0/color/svg/';

  // 置き換える絵文字（装飾用途のみ）
  const ALLOWED = [
    '🗾', '📍', '⏱️', '👥', '💴', '💰', '✨', '🍱', '🏨', '📅', '🍀',
    '🧳', '🤝', '🔗', '📷', '🔍', '🪧', '🧭', '❌', '⚠️', '💬', '🗂️', '🗑️'
  ];

  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'SELECT', 'OPTION', 'CODE', 'PRE']);

  function toUrl(emoji) {
    const cps = Array.from(emoji)
      .map(c => c.codePointAt(0))
      .filter(cp => cp !== 0xFE0F)
      .map(cp => cp.toString(16).toUpperCase())
      .join('-');
    return BASE + cps + '.svg';
  }

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  const RE = new RegExp(
    '(' + ALLOWED.slice().sort((a, b) => b.length - a.length).map(escapeRe).join('|') + ')',
    'gu'
  );

  function replaceInTextNode(node) {
    const text = node.nodeValue;
    if (!text) return;
    RE.lastIndex = 0;
    if (!RE.test(text)) return;
    RE.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0, m;
    while ((m = RE.exec(text)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const img = document.createElement('img');
      img.src = toUrl(m[0]);
      img.alt = m[0];
      img.className = 'emoji';
      img.loading = 'lazy';
      frag.appendChild(img);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    if (node.parentNode) node.parentNode.replaceChild(frag, node);
  }

  function openmojify(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) { replaceInTextNode(root); return; }
    if (root.nodeType !== Node.ELEMENT_NODE || SKIP_TAGS.has(root.tagName)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (!n.nodeValue || !n.parentNode || SKIP_TAGS.has(n.parentNode.tagName)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const targets = [];
    let n;
    while ((n = walker.nextNode())) targets.push(n);
    targets.forEach(replaceInTextNode);
  }

  window.openmojify = openmojify;

  const pending = new Set();
  let scheduled = false;
  const observer = new MutationObserver(muts => {
    for (const mut of muts) {
      mut.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) pending.add(node);
      });
    }
    if (pending.size && !scheduled) {
      scheduled = true;
      requestAnimationFrame(() => {
        observer.disconnect();
        pending.forEach(node => { if (node.isConnected) openmojify(node); });
        pending.clear();
        scheduled = false;
        observe();
      });
    }
  });
  function observe() { observer.observe(document.body, { childList: true, subtree: true }); }

  function init() {
    openmojify(document.body);
    observe();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
