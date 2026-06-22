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
