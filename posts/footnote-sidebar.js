// footnote-hover.js - Show footnotes in hover tooltips

console.log('[Footnote Hover] Script loaded!');

(function() {
    'use strict';

    function initFootnoteHovers() {
        console.log('[Footnote Hover] Initializing...');

        const footnotesSection = document.querySelector('.footnotes');
        if (!footnotesSection) {
            console.log('[Footnote Hover] No .footnotes section found');
            return;
        }

        const footnotesList = footnotesSection.querySelector('ol');
        if (!footnotesList) {
            console.log('[Footnote Hover] No ol in footnotes section');
            return;
        }

        const footnoteItems = footnotesList.querySelectorAll('li');
        if (footnoteItems.length === 0) {
            console.log('[Footnote Hover] No footnote items');
            return;
        }

        console.log('[Footnote Hover] Found', footnoteItems.length, 'footnotes');

        // Create a tooltip element
        const tooltip = document.createElement('div');
        tooltip.className = 'footnote-tooltip';
        document.body.appendChild(tooltip);

        // Process each footnote
        footnoteItems.forEach((footnoteItem) => {
            const footnoteId = footnoteItem.id; // e.g., "fn1"
            const footnoteNumber = parseInt(footnoteId.replace('fn', ''), 10);
            const refId = `fnref${footnoteNumber}`;

            // Find the reference in the text
            const ref = document.getElementById(refId);
            if (!ref) {
                return;
            }

            // Get the footnote content (remove the backref link)
            const footnoteContent = footnoteItem.cloneNode(true);
            const backref = footnoteContent.querySelector('.footnote-backref');
            if (backref) {
                backref.remove();
            }

            // Add hover listeners to show tooltip
            ref.addEventListener('mouseenter', (e) => {
                tooltip.innerHTML = footnoteContent.innerHTML.trim();
                tooltip.classList.add('visible');

                // Trigger MathJax to render the tooltip content
                if (window.MathJax && window.MathJax.typesetPromise) {
                    MathJax.typesetPromise([tooltip]).then(() => {
                        // Re-position after MathJax renders (content size may change)
                        positionTooltip();
                    }).catch((err) => console.log('MathJax error:', err));
                } else {
                    positionTooltip();
                }

                function positionTooltip() {
                    // Position tooltip near the reference
                    const refRect = ref.getBoundingClientRect();
                    const tooltipRect = tooltip.getBoundingClientRect();

                    // Position above the reference, centered
                    let left = refRect.left + (refRect.width / 2) - (tooltipRect.width / 2);
                    let top = refRect.top - tooltipRect.height - 10;

                    // Keep tooltip within viewport
                    if (left < 10) left = 10;
                    if (left + tooltipRect.width > window.innerWidth - 10) {
                        left = window.innerWidth - tooltipRect.width - 10;
                    }
                    if (top < 10) {
                        // If no room above, show below
                        top = refRect.bottom + 10;
                    }

                    tooltip.style.left = `${left}px`;
                    tooltip.style.top = `${top}px`;
                }
            });

            ref.addEventListener('mouseleave', () => {
                tooltip.classList.remove('visible');
            });
        });
    }

    // Run on load
    console.log('[Footnote Hover] Setting up event listeners...');

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFootnoteHovers);
    } else {
        initFootnoteHovers();
    }

})();
