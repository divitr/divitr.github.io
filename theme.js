(function () {
  'use strict';

  // 1. Immediate theme application (avoids flash of light mode on dark systems)
  const saved = localStorage.getItem('theme');
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  if (saved === 'dark' || (!saved && systemDark)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
  }

  // 2. Dynamic button injection when DOM is ready
  document.addEventListener('DOMContentLoaded', function () {
    const nav = document.querySelector('header nav');
    if (!nav) return;

    // Create the anchor link for the toggle
    const toggleBtn = document.createElement('a');
    toggleBtn.href = '#';
    toggleBtn.id = 'theme-toggle';
    toggleBtn.className = 'theme-toggle';
    toggleBtn.setAttribute('aria-label', 'Toggle theme');
    toggleBtn.style.cssText = 'display: inline-flex; align-items: center; justify-content: center; margin-left: 1.25rem; vertical-align: middle; transition: opacity 0.2s ease; cursor: pointer; color: var(--primary-color); opacity: 0.75;';

    // Hover opacity transition
    toggleBtn.addEventListener('mouseenter', () => toggleBtn.style.opacity = '1');
    toggleBtn.addEventListener('mouseleave', () => toggleBtn.style.opacity = '0.75');

    // Premium, custom "Celestial Chart" Sun (hollow circle + delicate orbit of 8 micro-dots)
    const sunSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
        <circle cx="12" cy="12" r="4.5"></circle>
        <circle cx="12" cy="3.5" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="12" cy="20.5" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="3.5" cy="12" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="20.5" cy="12" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="6" cy="6" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="18" cy="6" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="6" cy="18" r="1" fill="currentColor" stroke="none"></circle>
        <circle cx="18" cy="18" r="1" fill="currentColor" stroke="none"></circle>
      </svg>
    `;

    // Elegant, fine-stroke Moon crescent
    const moonSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
        <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
      </svg>
    `;

    // Swap logic: show what it CURRENTLY is (Light -> Sun, Dark -> Moon)
    function updateIcon() {
      const currentTheme = document.documentElement.getAttribute('data-theme');
      toggleBtn.innerHTML = currentTheme === 'dark' ? moonSvg : sunSvg;
    }

    nav.appendChild(toggleBtn);
    updateIcon();

    // Toggle event listener
    toggleBtn.addEventListener('click', function (e) {
      e.preventDefault();
      const currentTheme = document.documentElement.getAttribute('data-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('theme', newTheme);
      updateIcon();
    });
  });
})();
