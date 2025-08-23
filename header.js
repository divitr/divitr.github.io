// Header component loader
function loadHeader() {
    // Determine the correct path to header.html based on current page location
    const currentPath = window.location.pathname;
    let headerPath = 'header.html';
    
    // If we're in a subdirectory, go up one level to find header.html
    if (currentPath.includes('/research/') || currentPath.includes('/blog/') || currentPath.includes('/projects/') || currentPath.includes('/notes/')) {
        headerPath = '../header.html';
    }
    
    fetch(headerPath)
        .then(response => response.text())
        .then(html => {
            document.getElementById('header-placeholder').innerHTML = html;
        })
        .catch(error => {
            console.error('Error loading header:', error);
        });
}

// Load header when DOM is ready
document.addEventListener('DOMContentLoaded', loadHeader);
