(function () {
  'use strict';

  const media = window.matchMedia('(prefers-color-scheme: dark)');

  function apply(dark) {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  }

  apply(media.matches);
  media.addEventListener('change', function (e) {
    apply(e.matches);
  });
})();
