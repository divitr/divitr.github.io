// footnote-sidebar.js - Moves footnotes to sidebar on wide screens

console.log('[Footnote Sidebar] Script loaded!');

(function() {
    'use strict';

    function initSidebarFootnotes() {
        console.log('[Footnote Sidebar] Initializing...');
        console.log('[Footnote Sidebar] Window width:', window.innerWidth);

        // Only run on wide screens
        if (window.innerWidth < 1200) {
            console.log('[Footnote Sidebar] Screen too narrow, skipping');
            return;
        }

        const footnotesSection = document.querySelector('.footnotes');
        if (!footnotesSection) {
            console.log('[Footnote Sidebar] No .footnotes section found');
            return;
        }
        console.log('[Footnote Sidebar] Found footnotes section');

        const footnotesList = footnotesSection.querySelector('ol');
        if (!footnotesList) {
            console.log('[Footnote Sidebar] No ol in footnotes section');
            return;
        }
        console.log('[Footnote Sidebar] Found footnotes list');

        const footnoteItems = footnotesList.querySelectorAll('li');
        const blogPost = document.querySelector('.blog-post');

        console.log('[Footnote Sidebar] Footnote items:', footnoteItems.length);
        console.log('[Footnote Sidebar] Blog post element:', blogPost ? 'found' : 'not found');

        if (!blogPost || footnoteItems.length === 0) {
            console.log('[Footnote Sidebar] Missing blog post or no footnote items');
            return;
        }

        console.log('[Footnote Sidebar] Starting to process footnotes...');

        const sidenotes = [];
        const footnoteData = [];

        // Collect all footnote data first
        footnoteItems.forEach((footnoteItem) => {
            const footnoteId = footnoteItem.id; // e.g., "fn1"
            const footnoteNumber = parseInt(footnoteId.replace('fn', ''), 10);
            const refId = `fnref${footnoteNumber}`;

            // Find the reference in the text
            const ref = document.getElementById(refId);
            if (!ref) {
                return;
            }

            footnoteData.push({
                number: footnoteNumber,
                item: footnoteItem,
                ref: ref
            });
        });

        // Sort by footnote number (not by position in document)
        footnoteData.sort((a, b) => {
            return a.number - b.number;
        });

        // Now process each footnote in document order
        footnoteData.forEach((data, index) => {
            const footnoteNumber = data.number;
            const footnoteItem = data.item;
            const ref = data.ref;

            // Get the footnote content (remove the backref link)
            const backref = footnoteItem.querySelector('.footnote-backref');
            const footnoteContent = footnoteItem.cloneNode(true);
            if (backref) {
                const clonedBackref = footnoteContent.querySelector('.footnote-backref');
                if (clonedBackref) {
                    clonedBackref.remove();
                }
            }

            // Create a sidenote element
            const sidenote = document.createElement('span');
            sidenote.className = 'sidenote';
            sidenote.id = `sidenote-${footnoteNumber}`;

            // Add the footnote number, content, and backlink
            sidenote.innerHTML = `<span class="sidenote-number">${footnoteNumber}.</span>${footnoteContent.innerHTML.trim()} <a href="#fnref${footnoteNumber}" class="sidenote-backref" aria-label="Back to reference">↩</a>`;

            // Insert the sidenote into the DOM
            // We'll position it relative to the blog-post container
            blogPost.appendChild(sidenote);

            // Store sidenote info for collision detection
            sidenotes.push({
                element: sidenote,
                ref: ref,
                index: index
            });

            // Add bidirectional hover interaction between reference and sidenote
            ref.addEventListener('mouseenter', () => {
                sidenote.style.background = '#faf9f6';
                sidenote.style.borderLeft = '3px solid #4a4a4a';
                ref.style.background = '#faf9f6';
            });
            ref.addEventListener('mouseleave', () => {
                sidenote.style.background = 'transparent';
                sidenote.style.borderLeft = 'none';
                ref.style.background = '';
            });

            sidenote.addEventListener('mouseenter', () => {
                sidenote.style.background = '#faf9f6';
                sidenote.style.borderLeft = '3px solid #4a4a4a';
                ref.style.background = '#faf9f6';
            });
            sidenote.addEventListener('mouseleave', () => {
                sidenote.style.background = 'transparent';
                sidenote.style.borderLeft = 'none';
                ref.style.background = '';
            });

            // Use requestAnimationFrame to ensure layout is complete
            requestAnimationFrame(() => {
                // Get the exact position of the sup element (the footnote reference)
                const refRect = ref.getBoundingClientRect();
                const blogPostRect = blogPost.getBoundingClientRect();

                // Calculate the offset from the top of the blog post
                // We need to account for any scrolling and the blog post's position
                const topOffset = refRect.top - blogPostRect.top;

                // Position the sidenote to align with the exact line of the reference
                sidenote.style.top = `${topOffset}px`;

                // Add animation delay for staggered appearance
                sidenote.style.animationDelay = `${index * 0.05}s`;
            });
        });

        // After all sidenotes are positioned, check for overlaps
        // Wait longer to ensure all positions are calculated
        setTimeout(() => {
            handleOverlaps(sidenotes);
        }, 300);

        // Hide the original footnotes section (CSS already does this on wide screens)
    }

    function handleOverlaps(sidenotes) {
        // DON'T re-sort! Keep them in the order they were added (which is by footnote number)
        // Just check each sidenote against ALL previous ones to avoid overlaps

        for (let i = 1; i < sidenotes.length; i++) {
            const current = sidenotes[i].element;
            let currentTop = parseFloat(current.style.top);
            let maxBottom = currentTop; // Track the lowest point we need to be below

            // Check against all previous sidenotes to find the lowest bottom
            for (let j = 0; j < i; j++) {
                const previous = sidenotes[j].element;
                const previousTop = parseFloat(previous.style.top);
                const previousHeight = previous.offsetHeight;
                const previousBottom = previousTop + previousHeight + 10; // 10px gap

                // If current would overlap with this previous one
                if (currentTop < previousBottom) {
                    maxBottom = Math.max(maxBottom, previousBottom);
                }
            }

            // Only adjust if we actually need to move it
            if (maxBottom > currentTop) {
                current.style.top = `${maxBottom}px`;
                current.style.transition = 'top 0.3s ease-out';
            }
        }
    }

    // Run on load
    console.log('[Footnote Sidebar] Setting up event listeners...');
    console.log('[Footnote Sidebar] Document ready state:', document.readyState);

    if (document.readyState === 'loading') {
        console.log('[Footnote Sidebar] Waiting for DOMContentLoaded...');
        document.addEventListener('DOMContentLoaded', initSidebarFootnotes);
    } else {
        console.log('[Footnote Sidebar] Document already loaded, running immediately');
        initSidebarFootnotes();
    }

    // Re-run on window resize (with debouncing)
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            // Remove existing sidenotes
            document.querySelectorAll('.sidenote').forEach(el => el.remove());

            // Show footnotes section on narrow screens
            const footnotesSection = document.querySelector('.footnotes');
            if (footnotesSection) {
                if (window.innerWidth < 1200) {
                    footnotesSection.style.display = 'block';
                } else {
                    footnotesSection.style.display = 'none';
                    initSidebarFootnotes();
                }
            }
        }, 250);
    });

    // Wait for MathJax to finish rendering before repositioning sidenotes
    let mathJaxRendered = false;

    const reinitAfterMathJax = () => {
        if (mathJaxRendered) return; // Only run once
        mathJaxRendered = true;

        console.log('[Footnote Sidebar] MathJax rendered, reinitializing...');
        setTimeout(() => {
            document.querySelectorAll('.sidenote').forEach(el => el.remove());
            initSidebarFootnotes();
        }, 300);
    };

    if (window.MathJax) {
        if (MathJax.startup && MathJax.startup.promise) {
            MathJax.startup.promise.then(reinitAfterMathJax).catch(err => {
                console.error('[Footnote Sidebar] MathJax error:', err);
            });
        } else {
            // MathJax exists but no startup promise, wait a bit
            setTimeout(reinitAfterMathJax, 1000);
        }
    }
})();
