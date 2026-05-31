(function() {
    'use strict';

    let lastClickedCitationId = null;
    let hoverTooltip = null;

    function getCitationData() {
        const citationLinks = document.querySelectorAll('.citation-ref');
        const data = [];
        citationLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (!href || !href.startsWith('#cite-')) return;
            const key = href.substring(6);
            
            const title = link.getAttribute('data-title') || '';
            const authors = link.getAttribute('data-authors') || '';
            const year = link.getAttribute('data-year') || '';

            data.push({ link, key, title, authors, year });
        });
        return data;
    }

    function setupCitationInteractions(data) {
        if (!hoverTooltip) {
            hoverTooltip = document.createElement('div');
            hoverTooltip.className = 'citation-tooltip';
            document.body.appendChild(hoverTooltip);
        }

        data.forEach(({ link, title, authors, year }) => {
            // 1. Hover tooltip
            link.addEventListener('mouseenter', () => {
                if (!title) return;
                
                hoverTooltip.innerHTML = `
                    <div class="tooltip-title">${title}</div>
                    <div class="tooltip-authors">${authors}</div>
                    <div class="tooltip-year">${year}</div>
                `.trim();
                
                hoverTooltip.classList.add('visible');

                const position = () => {
                    const refRect = link.getBoundingClientRect();
                    const tipRect = hoverTooltip.getBoundingClientRect();
                    let left = refRect.left + refRect.width / 2 - tipRect.width / 2;
                    let top = refRect.top - tipRect.height - 8;
                    
                    if (left < 10) left = 10;
                    if (left + tipRect.width > window.innerWidth - 10) {
                        left = window.innerWidth - tipRect.width - 10;
                    }
                    if (top < 10) {
                        top = refRect.bottom + 8;
                    }
                    
                    hoverTooltip.style.left = `${left}px`;
                    hoverTooltip.style.top = `${top}px`;
                };

                position();
            });

            link.addEventListener('mouseleave', () => {
                hoverTooltip.classList.remove('visible');
            });

            // 2. Click tracking for dynamic backlinks
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = link.getAttribute('href').substring(1);
                const targetEl = document.getElementById(targetId);
                if (targetEl) {
                    lastClickedCitationId = link.id;
                    
                    targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    
                    targetEl.classList.remove('ref-highlight');
                    void targetEl.offsetWidth; // Force reflow
                    targetEl.classList.add('ref-highlight');
                }
            });
        });

        // 3. Backlink return mapping
        const backlinks = document.querySelectorAll('.ref-backref');
        backlinks.forEach(backlink => {
            backlink.addEventListener('click', (e) => {
                e.preventDefault();
                if (lastClickedCitationId) {
                    const sourceEl = document.getElementById(lastClickedCitationId);
                    if (sourceEl) {
                        sourceEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        sourceEl.classList.remove('ref-highlight');
                        void sourceEl.offsetWidth; // Force reflow
                        sourceEl.classList.add('ref-highlight');
                        return;
                    }
                }
                
                const href = backlink.getAttribute('href');
                if (href) {
                    const sourceEl = document.querySelector(href);
                    if (sourceEl) {
                        sourceEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        sourceEl.classList.remove('ref-highlight');
                        void sourceEl.offsetWidth; // Force reflow
                        sourceEl.classList.add('ref-highlight');
                    }
                }
            });
        });
    }

    function init() {
        const citationData = getCitationData();
        if (citationData.length === 0) return;
        setupCitationInteractions(citationData);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
