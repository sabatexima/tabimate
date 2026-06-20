const hamburger = document.getElementById('hamburger');
    const overlay = document.getElementById('overlay');
    const sidebar = document.querySelector('.sidebar');

    function openSidebar() {
      sidebar.classList.add('open');
      overlay.classList.add('open');
    }
    function closeSidebar() {
      sidebar.classList.remove('open');
      overlay.classList.remove('open');
    }

    hamburger.addEventListener('click', openSidebar);
    overlay.addEventListener('click', closeSidebar);
    sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', closeSidebar));
