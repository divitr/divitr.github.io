(function() {
    'use strict';

    const SIDEBAR_BREAKPOINT = 1400;
    const SIDENOTE_WIDTH = 220;
    const SIDENOTE_MARGIN = 24;
    const MIN_GAP = 8;

    let sidenotes = [];
    let sidenoteItems = [];
    let sidenoteItemsData = [];
    let sidenoteScrollListener = null;
    let hoverTooltip = null;
    let currentMode = null;
    let footnoteData = [];
    let backToTopBtn = null;
    let scrollListener = null;

    // Back-to-top button — only for tall pages (>2.5 viewports) in sidebar mode.
    const SCROLL_SHOW_PX = () => window.innerHeight;   // show after 1 full viewport scrolled
    const MIN_PAGE_HEIGHT = () => window.innerHeight * 2.5;

    (function injectBackToTopStyles() {
        const style = document.createElement('style');
        style.textContent = `
            #back-to-top {
                position: fixed;
                bottom: 2rem;
                right: 2rem;
                background: none;
                border: none;
                color: #999;
                font-family: Charter, 'Bitstream Charter', 'Sitka Text', Cambria, Georgia, serif;
                font-size: 0.85rem;
                cursor: pointer;
                padding: 0;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s ease, color 0.2s ease;
                z-index: 999;
            }
            #back-to-top.visible {
                opacity: 1;
                pointer-events: auto;
            }
            #back-to-top:hover {
                color: #555;
            }
            .footnote-sidenote.tucked {
                opacity: 0.25;
            }
        `;
        document.head.appendChild(style);
    })();

    function createBackToTopButton() {
        if (backToTopBtn) return;
        if (document.documentElement.scrollHeight < MIN_PAGE_HEIGHT()) return;

        backToTopBtn = document.createElement('button');
        backToTopBtn.id = 'back-to-top';
        backToTopBtn.textContent = 'back to top';
        backToTopBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
        document.body.appendChild(backToTopBtn);

        scrollListener = () => {
            if (!backToTopBtn) return;
            backToTopBtn.classList.toggle('visible', window.scrollY > SCROLL_SHOW_PX());
        };
        window.addEventListener('scroll', scrollListener, { passive: true });
        scrollListener();
    }

    function removeBackToTopButton() {
        if (scrollListener) {
            window.removeEventListener('scroll', scrollListener);
            scrollListener = null;
        }
        if (backToTopBtn) {
            backToTopBtn.remove();
            backToTopBtn = null;
        }
    }

    function isSidebarMode() {
        return window.innerWidth > SIDEBAR_BREAKPOINT;
    }

    function getFootnoteData() {
        const footnotesSection = document.querySelector('.footnotes');
        if (!footnotesSection) return [];

        const footnoteItems = footnotesSection.querySelectorAll('li');
        const data = [];

        footnoteItems.forEach((item) => {
            const match = item.id.match(/^fn(\d+)$/);
            if (!match) return;
            const footnoteNumber = parseInt(match[1], 10);
            const ref = document.getElementById(`fnref${footnoteNumber}`);
            if (!ref) return;

            const content = item.cloneNode(true);
            const backref = content.querySelector('.footnote-backref');
            if (backref) backref.remove();

            data.push({ footnoteNumber, ref, content });
        });

        return data;
    }

    function createSidenotes(data) {
        clearSidenotes();

        const blogPost = document.querySelector('.blog-post');
        if (!blogPost) return;

        const blogPostRect = blogPost.getBoundingClientRect();
        const leftPos = blogPostRect.right + window.scrollX + SIDENOTE_MARGIN;

        const items = data.map(({ footnoteNumber, ref, content }) => {
            const el = document.createElement('aside');
            el.className = 'footnote-sidenote';
            el.innerHTML = `<span class="sidenote-number">${footnoteNumber}.</span> ${content.innerHTML}`;
            document.body.appendChild(el);

            const refRect = ref.getBoundingClientRect();
            const naturalTop = refRect.top + window.scrollY;

            return { el, naturalTop, ref };
        });

        // Greedy downward-push to resolve overlaps
        if (items.length > 0) {
            items[0].placedTop = items[0].naturalTop;
            for (let i = 1; i < items.length; i++) {
                const prev = items[i - 1];
                const prevBottom = prev.placedTop + prev.el.offsetHeight + MIN_GAP;
                items[i].placedTop = Math.max(items[i].naturalTop, prevBottom);
            }
        }

        sidenoteItemsData = items.map(({ el, ref, naturalTop, placedTop }) => ({ el, ref, naturalTop, placedTop }));

        items.forEach(({ el, placedTop, ref }, idx) => {
            el.style.top = `${placedTop}px`;
            el.style.left = `${leftPos}px`;

            ref.addEventListener('mouseenter', () => {
                el.classList.add('highlighted');
                applyHoverPositions(idx);
            });
            ref.addEventListener('mouseleave', () => {
                el.classList.remove('highlighted');
                restorePlacedPositions();
            });
        });

        sidenotes     = items.map(i => i.el);
        sidenoteItems = items.map(i => ({ el: i.el, ref: i.ref }));

        if (window.MathJax && window.MathJax.typesetPromise) {
            MathJax.typesetPromise(items.map(i => i.el)).then(() => {
                // Re-resolve overlaps now that sidenote heights reflect rendered math
                if (items.length > 0) {
                    items[0].placedTop = items[0].naturalTop;
                    for (let i = 1; i < items.length; i++) {
                        const prev = items[i - 1];
                        const prevBottom = prev.placedTop + prev.el.offsetHeight + MIN_GAP;
                        items[i].placedTop = Math.max(items[i].naturalTop, prevBottom);
                    }
                }
                sidenoteItemsData = items.map(({ el, ref, naturalTop, placedTop }) => ({ el, ref, naturalTop, placedTop }));
                items.forEach(({ el, placedTop }) => { el.style.top = `${placedTop}px`; });
            }).catch(err => console.log('MathJax sidenote error:', err));
        }

        // Tuck sidenotes that overlap the back-to-top button
        if (sidenoteScrollListener) window.removeEventListener('scroll', sidenoteScrollListener);
        sidenoteScrollListener = () => {
            const btnVisible = backToTopBtn && window.scrollY > SCROLL_SHOW_PX();
            const btnRect = btnVisible ? backToTopBtn.getBoundingClientRect() : null;
            sidenoteItems.forEach(({ el }) => {
                if (!btnRect) { el.classList.remove('tucked'); return; }
                const r = el.getBoundingClientRect();
                const overlaps = r.bottom > btnRect.top && r.top < btnRect.bottom &&
                                 r.right > btnRect.left && r.left < btnRect.right;
                el.classList.toggle('tucked', overlaps);
            });
        };
        window.addEventListener('scroll', sidenoteScrollListener, { passive: true });
        sidenoteScrollListener();
    }

    function applyHoverPositions(hoveredIdx) {
        const items = sidenoteItemsData;
        if (!items.length) return;

        // Start from placed positions, then pin the hovered note at its natural position
        const tops = items.map(it => it.placedTop);
        tops[hoveredIdx] = items[hoveredIdx].naturalTop;

        // Push notes below downward as needed
        for (let i = hoveredIdx + 1; i < items.length; i++) {
            const prevBottom = tops[i - 1] + items[i - 1].el.offsetHeight + MIN_GAP;
            tops[i] = Math.max(items[i].naturalTop, prevBottom);
        }

        // Push notes above upward if they'd now overlap the hovered note
        for (let i = hoveredIdx - 1; i >= 0; i--) {
            const nextTop = tops[i + 1];
            const myHeight = items[i].el.offsetHeight;
            if (tops[i] + myHeight + MIN_GAP > nextTop) {
                tops[i] = nextTop - myHeight - MIN_GAP;
            }
        }

        items.forEach((item, i) => { item.el.style.top = `${tops[i]}px`; });
    }

    function restorePlacedPositions() {
        sidenoteItemsData.forEach(item => { item.el.style.top = `${item.placedTop}px`; });
    }

    function clearSidenotes() {
        if (sidenoteScrollListener) {
            window.removeEventListener('scroll', sidenoteScrollListener);
            sidenoteScrollListener = null;
        }
        sidenotes.forEach(el => el.remove());
        sidenotes = [];
        sidenoteItems = [];
        sidenoteItemsData = [];
    }

    function setupHoverTooltips(data) {
        removeHoverTooltips();

        const tooltip = document.createElement('div');
        tooltip.className = 'footnote-tooltip';
        tooltip.id = 'footnote-hover-tooltip';
        document.body.appendChild(tooltip);
        hoverTooltip = tooltip;

        data.forEach(({ ref, content }) => {
            ref.addEventListener('mouseenter', () => {
                tooltip.innerHTML = content.innerHTML.trim();
                tooltip.classList.add('visible');

                const position = () => {
                    const refRect = ref.getBoundingClientRect();
                    const tipRect = tooltip.getBoundingClientRect();
                    let left = refRect.left + refRect.width / 2 - tipRect.width / 2;
                    let top = refRect.top - tipRect.height - 10;
                    if (left < 10) left = 10;
                    if (left + tipRect.width > window.innerWidth - 10) left = window.innerWidth - tipRect.width - 10;
                    if (top < 10) top = refRect.bottom + 10;
                    tooltip.style.left = `${left}px`;
                    tooltip.style.top = `${top}px`;
                };

                if (window.MathJax && window.MathJax.typesetPromise) {
                    MathJax.typesetPromise([tooltip]).then(position).catch(err => console.log('MathJax error:', err));
                } else {
                    position();
                }
            });

            ref.addEventListener('mouseleave', () => {
                tooltip.classList.remove('visible');
            });
        });
    }

    function removeHoverTooltips() {
        if (hoverTooltip) {
            hoverTooltip.remove();
            hoverTooltip = null;
        }
    }

    function applyMode(force) {
        const mode = isSidebarMode() ? 'sidebar' : 'bottom';
        if (mode === currentMode && !force) return;
        currentMode = mode;

        const footnotesSection = document.querySelector('.footnotes');

        if (mode === 'sidebar') {
            if (footnotesSection) footnotesSection.style.display = 'none';
            removeHoverTooltips();
            createSidenotes(footnoteData);
            createBackToTopButton();
        } else {
            if (footnotesSection) footnotesSection.style.display = '';
            clearSidenotes();
            setupHoverTooltips(footnoteData);
            removeBackToTopButton();
        }
    }

    // Poll for MathJax.startup.promise (MathJax loads async, so it may not be set yet)
    function afterMathJax(callback) {
        let attempts = 0;
        function tryHook() {
            if (window.MathJax && window.MathJax.startup && window.MathJax.startup.promise) {
                window.MathJax.startup.promise.then(callback);
            } else if (attempts < 30) {
                attempts++;
                setTimeout(tryHook, 100);
            }
            // If MathJax never loads, the initial positioning stands
        }
        tryHook();
    }

    function init() {
        footnoteData = getFootnoteData();
        if (footnoteData.length === 0) return;

        // First pass: position with current layout (header may not be loaded yet)
        applyMode(false);

        // Correct pass: reposition after MathJax finishes (header will be loaded by then too)
        afterMathJax(() => {
            if (currentMode === 'sidebar') {
                createSidenotes(footnoteData);
            }
        });

        window.addEventListener('resize', () => {
            const newMode = isSidebarMode() ? 'sidebar' : 'bottom';
            if (newMode !== currentMode) {
                applyMode(false);
            } else if (currentMode === 'sidebar') {
                createSidenotes(footnoteData);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
