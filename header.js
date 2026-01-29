// Header component loader
function loadHeader() {
    // Determine the correct path to header.html based on current page location
    const currentPath = window.location.pathname;
    let headerPath = 'header.html';

    // If we're in a subdirectory, go up one level to find header.html
    if (currentPath.includes('/research/') || currentPath.includes('/notes/') || currentPath.includes('/misc/') || currentPath.includes('/projects/')) {
        headerPath = '../header.html';
    }
    // If we're in a post subdirectory, go up two levels to find header.html
    else if (currentPath.includes('/posts/') && currentPath.split('/').length > 3) {
        headerPath = '../../header.html';
    }
    // If we're in the main posts directory, go up one level
    else if (currentPath.includes('/posts/')) {
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
