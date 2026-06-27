const hamburger = document.getElementById('hamburger');
    const overlay = document.getElementById('overlay');
    const sidebar = document.querySelector('.sidebar');

    // ログイン画面などサイドバーが無いページでは何もしない
    if (hamburger && overlay && sidebar) {
      const openSidebar = () => {
        sidebar.classList.add('open');
        overlay.classList.add('open');
        document.body.classList.add('sidebar-open');
      };
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
        (function (el) { setTimeout(function () { el.remove(); }, 1500); })(s);
      }
    };
