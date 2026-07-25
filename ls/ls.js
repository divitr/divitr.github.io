(function () {
    'use strict';

    const CONTENT_EXTENSIONS = new Set([
        'html', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'
    ]);
    const IGNORED_PARTS = new Set([
        '.git', '.github', '.agents', '.codex', 'node_modules', '__pycache__',
        'output', 'tmp', 'src'
    ]);
    const ROOT_ORDER = new Map([
        ['research', 0],
        ['posts', 1],
        ['notes', 2],
        ['projects', 3],
        ['misc', 4],
        ['assets', 5],
        ['ls', 6]
    ]);
    const formatter = new Intl.NumberFormat('en', { maximumFractionDigits: 1 });

    const treeElement = document.getElementById('ls-tree');
    const statusElement = document.getElementById('ls-status');
    const emptyElement = document.getElementById('ls-empty');
    const filterElement = document.getElementById('ls-filter');
    const expandButton = document.getElementById('ls-expand');
    const collapseButton = document.getElementById('ls-collapse');

    let root = null;
    let query = '';

    function normalizePath(value) {
        return String(value || '')
            .replace(/\\/g, '/')
            .replace(/^\/+/, '')
            .replace(/\/+/g, '/');
    }

    function extensionOf(path) {
        const name = path.split('/').pop() || '';
        const dot = name.lastIndexOf('.');
        return dot === -1 ? '' : name.slice(dot + 1).toLowerCase();
    }

    function isVisibleFile(path) {
        const parts = path.split('/');
        if (!path || parts.some(part => !part || part.startsWith('.') || IGNORED_PARTS.has(part))) {
            return false;
        }
        return CONTENT_EXTENSIONS.has(extensionOf(path));
    }

    function makeDirectory(name, path) {
        return {
            type: 'directory',
            name,
            path,
            url: null,
            children: new Map()
        };
    }

    function buildTree(files) {
        const rootNode = makeDirectory('divitr.github.io', '');
        const seen = new Set();

        files.forEach(file => {
            const path = normalizePath(file.path);
            if (!isVisibleFile(path) || seen.has(path)) return;
            seen.add(path);

            const parts = path.split('/');
            const fileName = parts.pop();
            let directory = rootNode;
            let directoryPath = '';

            parts.forEach(part => {
                directoryPath = directoryPath ? `${directoryPath}/${part}` : part;
                if (!directory.children.has(part)) {
                    directory.children.set(part, makeDirectory(part, directoryPath));
                }
                directory = directory.children.get(part);
            });

            if (fileName.toLowerCase() === 'index.html') {
                directory.url = directory.path ? `/${directory.path}/` : '/';
                return;
            }

            directory.children.set(fileName, {
                type: 'file',
                name: fileName,
                path,
                url: `/${path}`,
                extension: extensionOf(path),
                size: Number(file.size) || 0
            });
        });

        return rootNode;
    }

    function compareNodes(a, b, depth) {
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
        if (depth === 0 && a.type === 'directory') {
            const aOrder = ROOT_ORDER.has(a.name) ? ROOT_ORDER.get(a.name) : 99;
            const bOrder = ROOT_ORDER.has(b.name) ? ROOT_ORDER.get(b.name) : 99;
            if (aOrder !== bOrder) return aOrder - bOrder;
        }
        return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    }

    function childrenOf(node, depth) {
        return Array.from(node.children.values()).sort((a, b) => compareNodes(a, b, depth));
    }

    function matchingTree(node, needle) {
        if (!needle) return node;
        if (node.type === 'file') {
            return node.path.toLowerCase().includes(needle) ? node : null;
        }

        const ownMatch = node.path.toLowerCase().includes(needle);
        const filtered = makeDirectory(node.name, node.path);
        filtered.url = node.url;

        node.children.forEach((child, key) => {
            const match = matchingTree(child, needle);
            if (match) filtered.children.set(key, match);
        });

        return ownMatch || filtered.children.size ? filtered : null;
    }

    function formatSize(bytes) {
        if (!bytes) return '';
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${formatter.format(bytes / 1024)} KB`;
        return `${formatter.format(bytes / (1024 * 1024))} MB`;
    }

    function makeName(node) {
        const text = node.type === 'directory' ? `${node.name}/` : node.name;
        if (!node.url) {
            const span = document.createElement('span');
            span.className = 'tree-name';
            span.textContent = text;
            return span;
        }

        const link = document.createElement('a');
        link.className = 'tree-name';
        link.href = node.url;
        link.textContent = text;
        return link;
    }

    function renderNode(node, depth, forceOpen) {
        const item = document.createElement('li');
        item.className = node.type === 'directory' ? 'tree-item tree-dir' : 'tree-item tree-file';
        item.dataset.path = node.path;

        const row = document.createElement('div');
        row.className = 'tree-row';

        if (node.type === 'directory') {
            const children = childrenOf(node, depth);
            const toggle = document.createElement('button');
            const initiallyOpen = forceOpen;
            toggle.type = 'button';
            toggle.className = 'tree-toggle';
            toggle.setAttribute('aria-expanded', String(initiallyOpen));
            toggle.setAttribute('aria-label', `${initiallyOpen ? 'Collapse' : 'Expand'} ${node.name}`);
            toggle.innerHTML = '<span aria-hidden="true"></span>';

            const childList = document.createElement('ul');
            childList.className = 'tree-children';
            childList.hidden = !initiallyOpen;
            children.forEach(child => childList.appendChild(renderNode(child, depth + 1, forceOpen)));

            toggle.addEventListener('click', function () {
                const open = toggle.getAttribute('aria-expanded') === 'true';
                toggle.setAttribute('aria-expanded', String(!open));
                toggle.setAttribute('aria-label', `${open ? 'Expand' : 'Collapse'} ${node.name}`);
                childList.hidden = open;
            });

            const meta = document.createElement('span');
            meta.className = 'tree-meta';
            meta.textContent = `${children.length} ${children.length === 1 ? 'item' : 'items'}`;

            row.append(toggle, makeName(node), meta);
            item.append(row, childList);
            return item;
        }

        const spacer = document.createElement('span');
        spacer.className = 'tree-spacer';
        spacer.setAttribute('aria-hidden', 'true');

        const meta = document.createElement('span');
        meta.className = 'tree-meta';
        meta.textContent = formatSize(node.size) || node.extension;
        row.append(spacer, makeName(node), meta);
        item.appendChild(row);
        return item;
    }

    function countTree(node) {
        const counts = { directories: 0, files: 0 };
        node.children.forEach(child => {
            if (child.type === 'directory') {
                counts.directories += 1;
                const nested = countTree(child);
                counts.directories += nested.directories;
                counts.files += nested.files;
            } else {
                counts.files += 1;
            }
        });
        return counts;
    }

    function render() {
        const filteredRoot = matchingTree(root, query);
        treeElement.replaceChildren();
        emptyElement.hidden = Boolean(filteredRoot);

        if (!filteredRoot) {
            statusElement.textContent = '0 matches';
            return;
        }

        const list = document.createElement('ul');
        childrenOf(filteredRoot, 0).forEach(child => {
            list.appendChild(renderNode(child, 0, Boolean(query)));
        });
        treeElement.appendChild(list);

        const counts = countTree(filteredRoot);
        const prefix = query ? 'matching ' : '';
        statusElement.textContent =
            `${prefix}${counts.directories} ${counts.directories === 1 ? 'directory' : 'directories'} · ` +
            `${counts.files} ${counts.files === 1 ? 'file' : 'files'}`;
    }

    function setAllFolders(open) {
        treeElement.querySelectorAll('.tree-toggle').forEach(toggle => {
            toggle.setAttribute('aria-expanded', String(open));
            const name = toggle.closest('.tree-dir').dataset.path.split('/').pop();
            toggle.setAttribute('aria-label', `${open ? 'Collapse' : 'Expand'} ${name}`);
        });
        treeElement.querySelectorAll('.tree-children').forEach(list => {
            list.hidden = !open;
        });
    }

    async function loadFiles() {
        const manifests = ['/ls/site-files.json', '/ls/site-files-fallback.json'];
        for (const manifest of manifests) {
            try {
                const response = await fetch(manifest, { cache: 'no-cache' });
                if (!response.ok) continue;
                const files = await response.json();
                if (Array.isArray(files)) return files;
            } catch (error) {
                // The Jekyll manifest contains Liquid locally; use the static fallback.
            }
        }
        throw new Error('No readable site manifest');
    }

    filterElement.addEventListener('input', function () {
        query = filterElement.value.trim().toLowerCase();
        render();
    });
    filterElement.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            filterElement.value = '';
            query = '';
            render();
            filterElement.blur();
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === '/' && document.activeElement !== filterElement) {
            event.preventDefault();
            filterElement.focus();
        }
    });
    expandButton.addEventListener('click', () => setAllFolders(true));
    collapseButton.addEventListener('click', () => setAllFolders(false));

    loadFiles()
        .then(files => {
            root = buildTree(files);
            render();
        })
        .catch(() => {
            statusElement.textContent = 'tree unavailable';
            treeElement.innerHTML = '<p class="ls-error">The file tree could not be compiled.</p>';
        });
}());
