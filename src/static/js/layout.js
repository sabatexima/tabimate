/* 全ページ共通の小さな仕掛け（layout.html が必ず読み込む）。
   1. スマホのサイドバー開閉（PCでは CSS 側で常時表示なので出番なし）
   2. 保存成功などで🍀が舞う演出 window.cloverBurst()

   ここに置くものの基準: どのページにもあって、ページ固有の知識が要らないもの。
   ページごとの処理は各ページの JS（home.js など）に書く。 */

const hamburger = document.getElementById('hamburger');
    const overlay = document.getElementById('overlay');
    const sidebar = document.querySelector('.sidebar');

    // ログイン画面などサイドバーが無いページでは何もしない
    if (hamburger && overlay && sidebar) {
      // body にもクラスを付けるのは、サイドバーを開いている間だけ
      // 三本線アイコンを隠すため（layout.css の body.sidebar-open）
      const openSidebar = () => {
        sidebar.classList.add('open');
        overlay.classList.add('open');
        document.body.classList.add('sidebar-open');
      };
      // 背景タップでもメニュー内のリンクを踏んだときでも閉じる
      const closeSidebar = () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('open');
        document.body.classList.remove('sidebar-open');
      };

      hamburger.addEventListener('click', openSidebar);
      overlay.addEventListener('click', closeSidebar);
      sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', closeSidebar));
    }

    // 保存などの成功時に🍀をふわっと舞わせる小さな演出（全ページ共通）。
    // x,y を渡すとその位置から、省略すると画面中央上から。
    window.cloverBurst = function (x, y) {
      var cx = x != null ? x : window.innerWidth / 2;
      var cy = y != null ? y : window.innerHeight / 3;
      // 8枚を少しずつ違う方向・角度・遅れで飛ばすと、群れっぽく見える。
      // 実際の動き（上へ流れて消える）は layout.css の @keyframes cloverFloat
      for (var i = 0; i < 8; i++) {
        var s = document.createElement('span');
        s.className = 'clover-burst';
        s.textContent = '🍀';
        s.style.left = cx + 'px';
        s.style.top = cy + 'px';
        s.style.setProperty('--dx', (Math.random() * 160 - 80).toFixed(0) + 'px');
        s.style.setProperty('--rot', (Math.random() * 120 - 60).toFixed(0) + 'deg');
        s.style.animationDelay = (Math.random() * 0.12).toFixed(2) + 's';
        document.body.appendChild(s);
        // アニメが終わったら DOM から片づける（1.4秒 + 余裕）。
        // 放っておくと押すたびに span が溜まっていく
        (function (el) { setTimeout(function () { el.remove(); }, 1500); })(s);
      }
    };
