/* 装飾的な絵文字を OpenMoji（手書き風）の画像に差し替える（全ページ共通）。

   なぜ要るか: 絵文字の見た目は OS 任せで、Windows・Mac・Android でまるで違う。
   絵本のトーンで統一したいので、手書き風の OpenMoji に置き換えて揃える。

   置き換えるのは ALLOWED に挙げた**装飾用の絵文字だけ**。★☆（お気に入り）・
   ☰（メニュー）・✓・✎ のような、押せる／状態を表すアイコンは対象外にしている。
   これらは JS が textContent を読み書きして状態を切り替えるので、<img> に
   変えられると比較が壊れる。

   後から追加された絵文字（チャットの返事など）にも効くよう、MutationObserver で
   DOM の変化を見張る。 */
(function () {
  const BASE = 'https://cdn.jsdelivr.net/npm/openmoji@15.0.0/color/svg/';

  // 置き換える絵文字（装飾用途のみ）
  const ALLOWED = [
    '🗾', '📍', '⏱️', '👥', '💴', '💰', '✨', '🍱', '🏨', '📅', '🍀',
    '🧳', '🤝', '🔗', '📷', '🔍', '🪧', '🧭', '❌', '⚠️', '💬', '🗂️', '🗑️'
  ];

  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'SELECT', 'OPTION', 'CODE', 'PRE']);

  // 絵文字 → OpenMoji のファイル名。異体字セレクタ(FE0F)は付いていたり
  // いなかったりするので落とす。付いたままだとファイルが見つからない
  function toUrl(emoji) {
    const cps = Array.from(emoji)
      .map(c => c.codePointAt(0))
      .filter(cp => cp !== 0xFE0F)
      .map(cp => cp.toString(16).toUpperCase())
      .join('-');
    return BASE + cps + '.svg';
  }

  // 絵文字の中には正規表現の特殊文字と重なるものがあるので、逃がしてから並べる
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  const RE = new RegExp(
    '(' + ALLOWED.slice().sort((a, b) => b.length - a.length).map(escapeRe).join('|') + ')',
    'gu'
  );

  // テキストノード1つを走査し、絵文字の箇所だけ <img> に差し替える。
  // 要素ごと作り直さないのは、周りのテキストや状態を壊さないため
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

  // root 以下のテキストを全部たどって置き換える。
  // 先に対象を配列へ集めてから差し替えるのが要点。走査しながらDOMを
  // 書き換えると TreeWalker の位置がずれて、置き残しが出る
  function openmojify(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) { replaceInTextNode(root); return; }
    if (root.nodeType !== Node.ELEMENT_NODE || SKIP_TAGS.has(root.tagName)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      // <script> や <input> の中のテキストは触らない。
      // REJECT はその枝ごと飛ばすので、まとめて除外できる
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

  // 後から挿入された絵文字も置き換える。ただし自分の差し替えもまた
  // DOM の変化として飛んでくるので、そのまま処理すると無限に回る。
  //   1. 変化をいったん pending に溜める
  //   2. 次の描画のタイミングで observer を止めてから置き換える
  //   3. 終わってから見張りを再開する
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
  // 見張りを（再）開始する。置き換えの前後で止める／再開するために関数にしてある
  function observe() { observer.observe(document.body, { childList: true, subtree: true }); }

  // 最初に今あるぶんを置き換えてから、見張りを始める
  function init() {
    openmojify(document.body);
    observe();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
