// Posts header component loader
function loadPostsHeader() {
    // For posts, we need to go up one level to find the posts_header.html
    const headerPath = '../posts_header.html';
    
    fetch(headerPath)
        .then(response => response.text())
        .then(html => {
            document.getElementById('header-placeholder').innerHTML = html;
        })
        .catch(error => {
            console.error('Error loading posts header:', error);
            // Fallback: create a simple header if loading fails
            const headerPlaceholder = document.getElementById('header-placeholder');
            headerPlaceholder.innerHTML = `
                <header>
                    <div class="logo"><a href="/">DR</a></div>
                    <nav>
                        <a href="/research">Research</a>
                        <a href="/posts">Posts</a>
                    </nav>
                </header>
            `;
        });
}

// Load header when DOM is ready
document.addEventListener('DOMContentLoaded', loadPostsHeader);
