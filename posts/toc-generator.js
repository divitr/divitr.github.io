/* Table of contents.
   A labelled outline in the left gutter, shown whenever the gutter is wide
   enough to hold it and out of the way when it is not. Heading IDs come from
   the compiler; this file only reads them, so section links work without it. */
(function () {
    'use strict';

    // Narrower than this and a readable column of labels no longer clears the
    // 800px text column. See the width clamp in posts.css.
    const TOC_BREAKPOINT = 1220;
    const ANCHOR_OFFSET  = 24;     // breathing room above a linked heading
    const MIN_SECTIONS   = 2;      // one section is not an outline

    const scrollBehavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'auto'
        : 'smooth';

    let entries = [];
    let nav = null;
    let list = null;
    let toggle = null;
    let currentMode = null;
    let offsetsStale = true;
    let spyQueued = false;
    let activeIndex = -1;
    let userScrolled = false;

    function modeForWidth() {
        return window.innerWidth >= TOC_BREAKPOINT ? 'full' : 'hidden';
    }

    // Keep the rendered math in the label; drop the MathML duplicate (it would
    // double every visible character) and the permalink mark. Labels wrap
    // rather than truncate, so the plain text is only needed for the tooltip.
    function labelFor(heading) {
        const clone = heading.cloneNode(true);
        clone.querySelectorAll('.katex-mathml, .heading-anchor').forEach(el => el.remove());
        return { html: clone.innerHTML, text: clone.textContent.trim() };
    }

    function collectHeadings() {
        const post = document.querySelector('main.blog-post');
        if (!post) return [];

        const found = [];
        let parent = -1;

        post.querySelectorAll('h2[id], h3[id]').forEach(el => {
            if (el.closest('.env-box, .proof-box, .example-box')) return;
            const level = el.tagName === 'H2' ? 2 : 3;
            if (level === 2) parent = found.length;
            found.push({ el: el, level: level, parent: level === 3 ? parent : -1, top: 0 });
        });

        return found.filter(e => e.level === 2).length >= MIN_SECTIONS ? found : [];
    }

    function readCollapsed() {
        try { return sessionStorage.getItem('toc-collapsed'); } catch (e) { return null; }
    }

    function writeCollapsed(collapsed) {
        try { sessionStorage.setItem('toc-collapsed', collapsed ? '1' : '0'); } catch (e) { /* private mode */ }
    }

    function applyCollapsed(collapsed) {
        nav.classList.toggle('collapsed', collapsed);
        toggle.setAttribute('aria-expanded', String(!collapsed));
    }

    function syncCollapsed() {
        applyCollapsed(readCollapsed() === '1');
    }

    function build() {
        nav = document.createElement('nav');
        nav.id = 'toc';
        nav.setAttribute('aria-label', 'Table of contents');

        toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.id = 'toc-toggle';
        toggle.className = 'toc-toggle';
        toggle.setAttribute('aria-controls', 'toc-list');
        toggle.innerHTML = '<span class="toc-toggle-label">Contents</span>'
                         + '<span class="toc-toggle-state" aria-hidden="true"></span>';

        list = document.createElement('ol');
        list.id = 'toc-list';
        list.className = 'toc-list';

        entries.forEach(entry => {
            const label = labelFor(entry.el);

            const link = document.createElement('a');
            link.className = 'toc-link';
            link.href = '#' + entry.el.id;
            link.innerHTML = label.html;
            link.title = label.text;

            const item = document.createElement('li');
            item.className = 'toc-item toc-h' + entry.level;
            item.appendChild(link);

            list.appendChild(item);
            entry.item = item;
            entry.link = link;
        });

        nav.appendChild(toggle);
        nav.appendChild(list);

        toggle.addEventListener('click', () => {
            const collapsed = !nav.classList.contains('collapsed');
            applyCollapsed(collapsed);
            writeCollapsed(collapsed);
            updateFades();
        });

        list.addEventListener('scroll', updateFades, { passive: true });

        list.addEventListener('click', event => {
            const link = event.target.closest('a.toc-link');
            if (!link) return;
            const target = document.getElementById(decodeURIComponent(link.getAttribute('href').slice(1)));
            if (!target) return;
            event.preventDefault();
            scrollToHeading(target, scrollBehavior);
            history.replaceState(null, '', link.getAttribute('href'));
        });

        document.body.appendChild(nav);
    }

    function applyMode(force) {
        const next = modeForWidth();
        if (!force && next === currentMode) return;
        currentMode = next;
        nav.dataset.mode = next;
        syncCollapsed();
        updateFades();
        offsetsStale = true;
        queueSpy();
    }

    function measure() {
        entries.forEach(entry => {
            entry.top = entry.el.getBoundingClientRect().top + window.scrollY;
        });
        offsetsStale = false;
    }

    function scrollToHeading(target, behavior) {
        const top = target.getBoundingClientRect().top + window.scrollY - ANCHOR_OFFSET;
        window.scrollTo({ top: Math.max(0, top), behavior: behavior });
    }

    // An outline taller than the gutter scrolls, so fade whichever edge it runs
    // past; a hard clip mid-title just reads as a rendering fault.
    function updateFades() {
        const overflow = list.scrollHeight - list.clientHeight;
        list.classList.toggle('fade-top', list.scrollTop > 2);
        list.classList.toggle('fade-bottom', overflow > 2 && list.scrollTop < overflow - 2);
    }

    // Keep the active entry on screen when the outline is long enough to scroll.
    function revealInNav(item) {
        if (currentMode === 'hidden' || nav.classList.contains('collapsed')) return;
        if (list.scrollHeight <= list.clientHeight) return;
        const frame = list.getBoundingClientRect();
        const box = item.getBoundingClientRect();
        if (box.top < frame.top) list.scrollTop -= (frame.top - box.top) + 8;
        else if (box.bottom > frame.bottom) list.scrollTop += (box.bottom - frame.bottom) + 8;
    }

    function setActive(index) {
        if (index === activeIndex) return;
        activeIndex = index;

        entries.forEach(entry => {
            entry.item.classList.remove('active', 'in-section');
            entry.link.removeAttribute('aria-current');
        });
        if (index < 0) return;

        const entry = entries[index];
        entry.item.classList.add('active');
        entry.link.setAttribute('aria-current', 'true');
        if (entry.parent >= 0) entries[entry.parent].item.classList.add('in-section');
        revealInNav(entry.item);
        updateFades();
    }

    function updateActive() {
        if (offsetsStale) measure();

        const band = window.scrollY + Math.min(160, window.innerHeight / 3);
        let index = -1;
        for (let i = entries.length - 1; i >= 0; i--) {
            if (entries[i].top <= band) { index = i; break; }
        }

        // At the foot of the page the last section wins however short it is,
        // otherwise a brief closing section never lights up.
        const doc = document.documentElement;
        if (window.scrollY + window.innerHeight >= doc.scrollHeight - 2) {
            index = entries.length - 1;
        }

        setActive(index);
    }

    function queueSpy() {
        if (spyQueued) return;
        spyQueued = true;
        requestAnimationFrame(() => {
            spyQueued = false;
            updateActive();
        });
    }

    // KaTeX webfonts and lazy images land after the fragment is resolved, which
    // leaves a cold deep link short of its target by however much the page grew.
    function settleHash() {
        if (userScrolled) return;
        const id = decodeURIComponent((location.hash || '').slice(1));
        if (!id) return;
        const target = document.getElementById(id);
        if (!target) return;
        const want = Math.max(0, target.getBoundingClientRect().top + window.scrollY - ANCHOR_OFFSET);
        if (Math.abs(window.scrollY - want) < 2) return;
        window.scrollTo({ top: want, behavior: 'auto' });
    }

    function init() {
        entries = collectHeadings();
        if (entries.length === 0) return;

        build();
        applyMode(true);

        ['wheel', 'touchstart', 'keydown'].forEach(type => {
            window.addEventListener(type, () => { userScrolled = true; }, { passive: true, once: true });
        });

        window.addEventListener('scroll', queueSpy, { passive: true });
        window.addEventListener('resize', () => {
            offsetsStale = true;
            applyMode(false);
            queueSpy();
        });

        document.addEventListener('click', event => {
            const anchor = event.target.closest('a.heading-anchor');
            if (!anchor) return;
            const target = document.getElementById(decodeURIComponent(anchor.getAttribute('href').slice(1)));
            if (!target) return;
            event.preventDefault();
            scrollToHeading(target, scrollBehavior);
            history.replaceState(null, '', anchor.getAttribute('href'));
        });

        window.addEventListener('hashchange', () => {
            const target = document.getElementById(decodeURIComponent((location.hash || '').slice(1)));
            if (target) scrollToHeading(target, 'auto');
        });

        const post = document.querySelector('main.blog-post');
        if (post && 'ResizeObserver' in window) {
            new ResizeObserver(() => {
                offsetsStale = true;
                queueSpy();
                settleHash();
            }).observe(post);
        }

        document.addEventListener('load', event => {
            if (event.target instanceof HTMLImageElement) {
                offsetsStale = true;
                queueSpy();
                settleHash();
            }
        }, true);

        queueSpy();
        settleHash();

        // Same settling point the footnote sidebar waits for: fonts and math
        // have stopped changing the page's metrics.
        if (document.fonts) document.fonts.ready.then(() => { offsetsStale = true; queueSpy(); settleHash(); });
        window.addEventListener('load', () => { offsetsStale = true; queueSpy(); settleHash(); }, { once: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
