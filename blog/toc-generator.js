document.addEventListener('DOMContentLoaded', () => {
    function truncateText(text, maxLength = 20) {
        return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
    }

    function createIdFromText(text) {
        return text.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
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
                width: 250px;
                transition: all 0.3s ease;
            }

            #toc-container a:hover {
                text-decoration: none;
            }
            
            #toc-header {
                font-weight: bold;
                color: #333;
                margin-bottom: 15px;
                font-size: 1.1em;
                padding-left: 0px;
            }
            
            #toc-menu {
                display: flex;
                flex-direction: column;
                gap: 10px;
                opacity: 0.8;
                transition: all 0.3s ease;
            }
            
            .toc-section {
                position: relative;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .toc-line {
                width: 30px;
                height: 2px;
                background-color: #333;
                transition: all 0.3s ease;
                flex-shrink: 0;
            }
            
            .toc-section:hover .toc-line,
            .toc-section.active .toc-line {
                background-color: #6B46C1;
                width: 50px;
            }
            
            .toc-subsections {
                display: none;
                margin-left: 40px;
                margin-top: 5px;
                font-size: 0.9em;
            }
            
            .toc-section:hover .toc-subsections,
            .toc-section.active .toc-subsections {
                display: block;
                margin-left: 30px;
            }
            
            .toc-subsection {
                margin-bottom: 5px;
                opacity: 0.7;
                transition: opacity 0.3s ease;
            }
            
            .toc-subsection:hover {
                opacity: 1;
            }
            
            .toc-section-title,
            .toc-subsection-title {
                text-decoration: none;
                color: #1a1a1a;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 180px;
                transition: color 0.3s ease;
            }
            
            .toc-section.active .toc-section-title,
            .toc-subsection.active .toc-subsection-title {
                font-weight: bold;
                color: #6B46C1;
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
        
        const line = document.createElement('div');
        line.className = 'toc-line';
        
        const sectionLink = document.createElement('a');
        sectionLink.href = `#${h2.id}`;
        sectionLink.className = 'toc-section-title';
        sectionLink.textContent = truncateText(h2.textContent);
        
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
            subsectionLink.textContent = truncateText(h3.textContent);
            
            const subsectionElement = document.createElement('div');
            subsectionElement.className = 'toc-subsection';
            subsectionElement.appendChild(subsectionLink);
            
            subsectionsContainer.appendChild(subsectionElement);
        });
        
        sectionElement.appendChild(line);
        sectionElement.appendChild(sectionLink);
        sectionElement.appendChild(subsectionsContainer);
        
        tocMenu.appendChild(sectionElement);
    });
    
    function highlightCurrentSection() {
        const scrollPosition = window.scrollY;
        let h3Index = 0;
        h2Elements.forEach((h2, index) => {
            const sectionElement = tocMenu.children[index];
            const nextH2 = h2Elements[index + 1];
            const currentSectionTop = h2.offsetTop;
            const nextSectionTop = nextH2 ? nextH2.offsetTop : document.body.scrollHeight;

            if (scrollPosition >= currentSectionTop - 100 && scrollPosition < nextSectionTop - 100) {
                sectionElement.classList.add('active');
                const subsections = sectionElement.querySelectorAll('.toc-subsection');
                const h3sInSection = [];
                let next = h2.nextElementSibling;
                while (next && !(next.tagName && next.tagName.toLowerCase() === 'h2')) {
                    if (next.tagName && next.tagName.toLowerCase() === 'h3') {
                        h3sInSection.push(next);
                    }
                    next = next.nextElementSibling;
                }
                subsections.forEach((subsection, subIdx) => {
                    const h3 = h3sInSection[subIdx];
                    const nextH3 = h3sInSection[subIdx + 1];
                    if (h3 && scrollPosition >= h3.offsetTop - 100 && scrollPosition < (nextH3 ? nextH3.offsetTop : nextSectionTop) - 100) {
                        subsection.classList.add('active');
                    } else {
                        subsection.classList.remove('active');
                    }
                });
            } else {
                sectionElement.classList.remove('active');
            }
        });
    }
    
    highlightCurrentSection();
    window.addEventListener('scroll', highlightCurrentSection);
});