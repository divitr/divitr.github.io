function initTOC() {
    function truncateText(text, maxLength = 20) {
        return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
    }

    function createIdFromText(text) {
        return text.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    }

    function getHeadingHTML(element) {
        // Clone the element to avoid modifying the original
        const clone = element.cloneNode(true);
        // Return innerHTML to preserve LaTeX markup
        return clone.innerHTML;
    }

    const tocContainer = document.createElement('div');
    tocContainer.id = 'toc-container';
    tocContainer.innerHTML = `
        <style>
            #toc-container {
                position: fixed;
                top: 120px;
                left: 20px;
                z-index: 1000;
                width: 200px;
                transition: all 0.3s ease;
            }

            #toc-container a:hover {
                text-decoration: underline;
            }

            #toc-header {
                font-weight: 600;
                color: #4a4a4a;
                margin-bottom: 1rem;
                font-size: 1rem;
                padding-left: 0px;
                padding-bottom: 0.5rem;
                cursor: pointer;
                user-select: none;
                border-bottom: 1px solid transparent;
                transition: border-color 0.2s ease;
                position: relative;
            }

            #toc-header::after {
                content: '(hide)';
                position: absolute;
                right: 0;
                font-weight: normal;
                font-size: 0.85rem;
                color: #999;
            }

            #toc-container.collapsed #toc-header::after {
                content: '(show)';
            }

            #toc-header:hover {
                border-bottom-color: #ddd;
            }

            #toc-container.collapsed #toc-header {
                margin-bottom: 0;
                border-bottom-color: transparent;
            }

            #toc-menu.collapsed {
                display: none;
            }

            #toc-menu {
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
                opacity: 1;
                transition: opacity 0.2s ease;
            }

            .toc-section {
                position: relative;
                cursor: pointer;
                padding: 0.25rem 0;
                border-left: 2px solid transparent;
                padding-left: 0.75rem;
                transition: border-color 0.2s ease;
            }

            .toc-section:hover,
            .toc-section.active {
                border-left-color: #4a4a4a;
            }

            .toc-subsections {
                display: none;
                margin-left: 0.75rem;
                margin-top: 0.5rem;
                font-size: 0.85rem;
            }

            .toc-section:hover .toc-subsections,
            .toc-section.active .toc-subsections {
                display: block;
            }

            .toc-subsection {
                margin-bottom: 0.25rem;
                opacity: 0.7;
                transition: opacity 0.2s ease;
            }

            .toc-subsection:hover {
                opacity: 1;
            }

            .toc-section-title,
            .toc-subsection-title {
                text-decoration: none;
                color: #4a4a4a;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 180px;
                transition: color 0.2s ease;
                font-size: 0.9rem;
            }

            .toc-section.active .toc-section-title {
                color: #4a4a4a;
            }

            .toc-subsection.active .toc-subsection-title {
                color: #4a4a4a;
                opacity: 1;
                font-weight: 600;
            }

            @media (max-width: 1400px) {
                #toc-container {
                    display: none;
                }
            }
        </style>
        <div id="toc-header">Contents</div>
        <div id="toc-menu"></div>
    `;
    
    document.body.appendChild(tocContainer);
    const tocMenu = document.getElementById('toc-menu');
    const tocHeader = document.getElementById('toc-header');

    // Add toggle functionality
    tocHeader.addEventListener('click', () => {
        tocMenu.classList.toggle('collapsed');
        tocContainer.classList.toggle('collapsed');
    });
    
    const h2Elements = document.querySelectorAll('h2');
    const h3Elements = document.querySelectorAll('h3');
    
    // First pass: assign IDs to h2 elements
    h2Elements.forEach((h2) => {
        if (!h2.id) {
            h2.id = createIdFromText(h2.textContent);
        }
    });
    
    // Second pass: assign IDs to h3 elements with parent section prefix
    h2Elements.forEach((h2) => {
        let next = h2.nextElementSibling;
        while (next && !(next.tagName && next.tagName.toLowerCase() === 'h2')) {
            if (next.tagName && next.tagName.toLowerCase() === 'h3' && !next.id) {
                next.id = `${h2.id}.${createIdFromText(next.textContent)}`;
            }
            next = next.nextElementSibling;
        }
    });
    
    Array.from(h2Elements).forEach((h2) => {
        const sectionElement = document.createElement('div');
        sectionElement.className = 'toc-section';

        const sectionLink = document.createElement('a');
        sectionLink.href = `#${h2.id}`;
        sectionLink.className = 'toc-section-title';
        sectionLink.innerHTML = truncateText(getHeadingHTML(h2), 25);

        const subsectionsContainer = document.createElement('div');
        subsectionsContainer.className = 'toc-subsections';

        const h3sInSection = [];
        let next = h2.nextElementSibling;
        while (next && !(next.tagName && next.tagName.toLowerCase() === 'h2')) {
            if (next.tagName && next.tagName.toLowerCase() === 'h3') {
                h3sInSection.push(next);
            }
            next = next.nextElementSibling;
        }

        h3sInSection.forEach(h3 => {
            const subsectionLink = document.createElement('a');
            subsectionLink.href = `#${h3.id}`;
            subsectionLink.className = 'toc-subsection-title';
            subsectionLink.innerHTML = truncateText(getHeadingHTML(h3), 25);

            const subsectionElement = document.createElement('div');
            subsectionElement.className = 'toc-subsection';
            subsectionElement.appendChild(subsectionLink);

            subsectionsContainer.appendChild(subsectionElement);
        });

        sectionElement.appendChild(sectionLink);
        sectionElement.appendChild(subsectionsContainer);

        tocMenu.appendChild(sectionElement);
    });
    
    function highlightCurrentSection() {
        // Get viewport information
        const viewportTop = window.scrollY;
        const viewportMiddle = viewportTop + (window.innerHeight / 3); // Use top third of viewport as "current"

        // Find which h2 section we're currently in
        let currentH2Index = -1;
        let currentH3Index = -1;

        // First, determine which h2 section contains the viewport middle
        for (let i = h2Elements.length - 1; i >= 0; i--) {
            const h2 = h2Elements[i];
            if (h2.offsetTop <= viewportMiddle) {
                currentH2Index = i;
                break;
            }
        }

        // Clear all active states
        Array.from(tocMenu.children).forEach(section => {
            section.classList.remove('active');
            section.querySelectorAll('.toc-subsection').forEach(sub => {
                sub.classList.remove('active');
            });
        });

        // If we found a current section, highlight it
        if (currentH2Index >= 0) {
            const sectionElement = tocMenu.children[currentH2Index];
            const h2 = h2Elements[currentH2Index];

            // Get all h3s in this section
            const h3sInSection = [];
            let next = h2.nextElementSibling;
            while (next && !(next.tagName && next.tagName.toLowerCase() === 'h2')) {
                if (next.tagName && next.tagName.toLowerCase() === 'h3') {
                    h3sInSection.push(next);
                }
                next = next.nextElementSibling;
            }

            // Check if we're in a subsection
            let foundActiveH3 = false;
            for (let i = h3sInSection.length - 1; i >= 0; i--) {
                const h3 = h3sInSection[i];
                if (h3.offsetTop <= viewportMiddle) {
                    const subsections = sectionElement.querySelectorAll('.toc-subsection');
                    if (subsections[i]) {
                        subsections[i].classList.add('active');
                        foundActiveH3 = true;
                    }
                    break;
                }
            }

            // Always highlight the parent h2 section
            sectionElement.classList.add('active');
        }
    }

    highlightCurrentSection();
    window.addEventListener('scroll', highlightCurrentSection);
    window.addEventListener('resize', highlightCurrentSection);

    // Trigger MathJax to render TOC content if available
    if (window.MathJax && window.MathJax.typesetPromise) {
        MathJax.typesetPromise([tocContainer]).catch((err) => console.log('MathJax TOC error:', err));
    }
}

// Initialize TOC after DOM loads (before MathJax renders)
document.addEventListener('DOMContentLoaded', initTOC);