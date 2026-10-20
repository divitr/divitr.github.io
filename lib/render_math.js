#!/usr/bin/env node
const katex = require('katex');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
    const equations = JSON.parse(input);
    const results = equations.map(({ latex, display }) => {
        try {
            return katex.renderToString(latex, {
                displayMode: display,
                throwOnError: false,
                strict: false,
            });
        } catch (e) {
            process.stderr.write(`KaTeX error: ${e.message}\nInput: ${latex}\n`);
            return `<span class="math-error">${latex}</span>`;
        }
    });
    process.stdout.write(JSON.stringify(results));
});
