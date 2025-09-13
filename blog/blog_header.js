// Blog header component loader
function loadBlogHeader() {
    // For blog posts, we need to go up one level to find the blog_header.html
    const headerPath = '../blog_header.html';
    
    fetch(headerPath)
        .then(response => response.text())
        .then(html => {
            document.getElementById('header-placeholder').innerHTML = html;
        })
        .catch(error => {
            console.error('Error loading blog header:', error);
            // Fallback: create a simple header if loading fails
            const headerPlaceholder = document.getElementById('header-placeholder');
            headerPlaceholder.innerHTML = `
                <header>
                    <div class="logo"><a href="/">DR</a></div>
                    <nav>
                        <a href="/research">Research</a>
                        <a href="/blog">Blog</a>
                    </nav>
                </header>
            `;
        });
}

// Load header when DOM is ready
document.addEventListener('DOMContentLoaded', loadBlogHeader);
