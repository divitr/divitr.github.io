.topic-summary {
    margin-bottom: 1rem;
}

.topic-summary a {
    color: inherit;
    text-decoration: underline;
    opacity: 0.8;
    transition: opacity 0.2s;
}

.topic-summary a:hover {
    opacity: 1;
}

.analysis-section {
    margin-top: 1rem;
    display: none;
}

@media (max-width: 768px) {
    .analysis-section {
        display: none !important;
    }
}

.collapsible-header {
    // ... rest of existing code ...
}

function createTopicSummary(data) {
    const topics = data.topicData
        .sort((a, b) => b.strength - a.strength)
        .slice(0, 5)
        .map(d => d.topic);

    const summary = document.createElement('div');
    summary.className = 'topic-summary';
    summary.innerHTML = `
        <p>I mostly write about ${topics.slice(0, -1).join(', ')}, and ${topics[topics.length - 1]}. 
        [<a href="/posts/analysis/">How I generated these topics</a> | <a href="#" class="toggle-analysis">Show detailed analysis</a>]</p>
    `;
    return summary;
} 