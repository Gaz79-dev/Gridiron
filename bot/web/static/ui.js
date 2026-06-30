document.addEventListener('DOMContentLoaded', () => {
  const path = window.location.pathname;
  document.querySelectorAll('.gx-nav-links a').forEach((link) => {
    const href = link.getAttribute('href');
    if (!href) return;
    if ((href === '/' && path === '/') || (href !== '/' && path.startsWith(href))) {
      link.classList.add('gx-active');
    }
  });
});
