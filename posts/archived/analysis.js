import * as d3 from 'https://cdn.jsdelivr.net/npm/d3@7/+esm';

const colors = {
    primary: '#6b7fd7',
    secondary: '#8b9fd7',
    accent: '#9b8fd7',
    background: '#f8f9fa',
    text: '#2c3e50',
    clusters: [
        '#6b7fd7',
        '#d76b7f',
        '#7fd76b',
        '#d7b36b',
        '#6bd7d7',
        '#b36bd7'
    ]
};

async function loadData() {
    const [pcaData, wordFreqData, topicData] = await Promise.all([
        d3.csv('pca_data.csv'),
        d3.csv('word_frequencies.csv'),
        d3.csv('topic_analysis.csv')
    ]);

    pcaData.forEach(d => {
        d.pc1 = +d.pc1;
        d.pc2 = +d.pc2;
        d.pc1_variance = +d.pc1_variance;
        d.pc2_variance = +d.pc2_variance;
    });

    wordFreqData.forEach(d => {
        d.frequency = +d.frequency;
    });

    topicData.forEach(d => {
        d.strength = +d.strength;
        d.coherence = +d.coherence;
        d.core_content = d.core_content.split(' | ');
        d.connections = d.connections ? d.connections.split(' | ') : [];
    });

    return { pcaData, wordFreqData, topicData };
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
        [<a href="/posts/analysis/">How I generated these topics</a><span class="desktop-only"> | </span><span class="desktop-only"><a href="#" class="toggle-analysis">Show detailed analysis</a></span>]</p>
    `;
    return summary;
}

function createCollapsibleContainer(title, contentCreator) {
    const container = document.createElement('div');
    container.className = 'collapsible-container';
    
    const header = document.createElement('div');
    header.className = 'collapsible-header';
    header.innerHTML = `
        <div class="header-content">
            <svg class="chevron" viewBox="0 0 24 24" width="16" height="16">
                <path d="M7 10l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <h2>${title}</h2>
        </div>
    `;
    
    const content = document.createElement('div');
    content.className = 'collapsible-content';
    content.style.display = 'none';
    
    container.appendChild(header);
    container.appendChild(content);
    
    header.addEventListener('click', () => {
        const isVisible = content.style.display !== 'none';
        content.style.display = isVisible ? 'none' : 'block';
        const chevron = header.querySelector('.chevron');
        chevron.style.transform = isVisible ? 'rotate(0deg)' : 'rotate(180deg)';
        
        if (!isVisible && !content.hasChildNodes()) {
            console.log(`Creating visualization for ${title}`);
            const visualization = contentCreator();
            if (visualization) {
                content.appendChild(visualization);
            } else {
                console.error(`Failed to create visualization for ${title}`);
            }
        }
    });
    
    return container;
}

function createPCAPlot(data) {

    const validData = data.pcaData.filter(d => d.text && d.text.trim() !== '');

    const categories = data.topicData
        .sort((a, b) => b.strength - a.strength)
        .map((topic, index) => ({
            name: topic.topic,
            color: colors.clusters[index % colors.clusters.length],
            coreContent: topic.core_content
        }));

    const margin = { top: 20, right: 20, bottom: 40, left: 60 };
    const width = 600 - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    const container = document.createElement('div');
    container.className = 'visualization-container';

    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    const xScale = d3.scaleLinear()
        .domain(d3.extent(validData, d => d.pc1))
        .range([0, width])
        .nice();

    const yScale = d3.scaleLinear()
        .domain(d3.extent(validData, d => d.pc2))
        .range([height, 0])
        .nice();

    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale))
        .selectAll('text')
        .style('font-size', '12px')
        .attr('fill', '#2c3e50');

    svg.append('g')
        .call(d3.axisLeft(yScale))
        .selectAll('text')
        .style('font-size', '12px')
        .attr('fill', '#2c3e50');

    svg.append('text')
        .attr('x', width / 2)
        .attr('y', height + 35)
        .attr('fill', '#2c3e50')
        .style('font-size', '12px')
        .style('text-anchor', 'middle')
        .text(`PC1 (${(validData[0].pc1_variance * 100).toFixed(1)}% variance)`);

    svg.append('text')
        .attr('transform', 'rotate(-90)')
        .attr('y', -40)
        .attr('x', -height / 2)
        .attr('fill', '#2c3e50')
        .style('font-size', '12px')
        .style('text-anchor', 'middle')
        .text(`PC2 (${(validData[0].pc2_variance * 100).toFixed(1)}% variance)`);

    svg.selectAll('g.axis path, g.axis line')
        .attr('stroke', '#e0e0e0');

    function getCategoryAndColor(d) {
        const matchingCategory = categories.find(category => 
            category.coreContent.some(content => 
                content.toLowerCase().includes(d.text.toLowerCase())
            )
        );

        if (matchingCategory) {
            return { 
                category: matchingCategory.name, 
                color: matchingCategory.color 
            };
        }

        return { 
            category: 'Other Topics', 
            color: colors.clusters[colors.clusters.length - 1] 
        };
    }

    const points = svg.selectAll('circle')
        .data(validData)
        .enter()
        .append('circle')
        .attr('cx', d => xScale(d.pc1))
        .attr('cy', d => yScale(d.pc2))
        .attr('r', 5)
        .attr('fill', d => getCategoryAndColor(d).color)
        .attr('opacity', 0.7);

    const tooltip = d3.select('body')
        .append('div')
        .attr('class', 'tooltip')
        .style('opacity', 0)
        .style('position', 'absolute')
        .style('background-color', 'white')
        .style('padding', '10px')
        .style('border-radius', '5px')
        .style('box-shadow', '0 0 10px rgba(0,0,0,0.1)');

    points.on('mouseover', (event, d) => {
        const { category } = getCategoryAndColor(d);
        tooltip.transition()
            .duration(200)
            .style('opacity', 0.9);
        tooltip.html(`
            <strong>${d.text}</strong><br>
            <span style="color: #666;">Category: ${category}</span>
        `)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 28) + 'px');
    })
    .on('mouseout', () => {
        tooltip.transition()
            .duration(500)
            .style('opacity', 0);
    });

    const legend = svg.append('g')
        .attr('class', 'legend')
        .attr('transform', `translate(${width - 150}, 20)`);

    categories.forEach((category, i) => {
        const legendRow = legend.append('g')
            .attr('transform', `translate(0, ${i * 20})`);

        legendRow.append('circle')
            .attr('r', 4)
            .attr('fill', category.color)
            .attr('opacity', 0.7);

        legendRow.append('text')
            .attr('x', 10)
            .attr('y', 4)
            .style('font-size', '10px')
            .style('fill', '#2c3e50')
            .text(category.name);
    });

    return container;
}

function createWordFrequency(data) {
    if (!data || data.length === 0) {
        console.error('No data provided for word frequency visualization');
        return null;
    }

    const margin = { top: 20, right: 20, bottom: 40, left: 120 };
    const width = 600 - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    const container = document.createElement('div');
    container.className = 'visualization-container';

    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    const sortedData = [...data.wordFreqData].sort((a, b) => b.frequency - a.frequency);
    const top20Data = sortedData.slice(0, 20);

    const xScale = d3.scaleLinear()
        .domain([0, d3.max(top20Data, d => d.frequency)])
        .range([0, width]);

    const yScale = d3.scaleBand()
        .domain(top20Data.map(d => d.term))
        .range([0, height])
        .padding(0.2);

    svg.selectAll('rect')
        .data(top20Data)
        .enter()
        .append('rect')
        .attr('x', 0)
        .attr('y', d => yScale(d.term))
        .attr('width', d => xScale(d.frequency))
        .attr('height', yScale.bandwidth())
        .attr('fill', colors.primary)
        .attr('opacity', 0.7)
        .attr('rx', 2)
        .attr('ry', 2);

    svg.selectAll('text')
        .data(top20Data)
        .enter()
        .append('text')
        .attr('x', d => xScale(d.frequency) + 5)
        .attr('y', d => yScale(d.term) + yScale.bandwidth() / 2)
        .attr('dy', '0.35em')
        .text(d => d.frequency)
        .attr('fill', '#2c3e50')
        .style('font-size', '12px');

    svg.append('g')
        .call(d3.axisLeft(yScale))
        .selectAll('text')
        .attr('fill', '#2c3e50')
        .style('font-size', '12px')
        .style('text-transform', 'capitalize');

    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale))
        .selectAll('text')
        .style('font-size', '12px')
        .attr('fill', '#2c3e50');

    svg.selectAll('g.axis path, g.axis line')
        .attr('stroke', '#e0e0e0');

    svg.append('text')
        .attr('x', width / 2)
        .attr('y', height + 35)
        .attr('fill', '#2c3e50')
        .style('font-size', '12px')
        .style('text-anchor', 'middle')
        .text('Frequency');

    return container;
}

async function init() {
    try {
        const data = await loadData();
        console.log('Loaded data:', data);
        
        const container = document.createElement('div');
        container.className = 'blog-analysis';
        
        container.appendChild(createTopicSummary(data));
        
        const analysisSection = document.createElement('div');
        analysisSection.className = 'analysis-section';
        analysisSection.style.display = 'none';
        
        const pcaContainer = createCollapsibleContainer(
            'Content Distribution (PCA)',
            () => {
                console.log('Creating PCA plot with data:', data.pcaData);
                return createPCAPlot(data);
            }
        );
        analysisSection.appendChild(pcaContainer);
        
        const freqContainer = createCollapsibleContainer(
            'Word Frequency Analysis',
            () => {
                console.log('Creating word frequency plot with data:', data.wordFreqData);
                return createWordFrequency(data);
            }
        );
        analysisSection.appendChild(freqContainer);
        
        container.appendChild(analysisSection);
        
        const toggleLink = container.querySelector('.toggle-analysis');
        toggleLink.addEventListener('click', (e) => {
            e.preventDefault();
            const isVisible = analysisSection.style.display !== 'none';
            analysisSection.style.display = isVisible ? 'none' : 'block';
            toggleLink.textContent = isVisible ? 'Show detailed analysis' : 'Hide detailed analysis';
        });
        
        return container;
    } catch (error) {
        console.error('Error initializing visualizations:', error);
        throw error;
    }
}

const style = document.createElement('style');
style.textContent = `
    .blog-analysis {
        margin: 2rem 0;
        font-family: inherit;
        color: inherit;
    }
    .topic-summary {
        margin-bottom: 1rem;
    }
    .topic-summary p {
        margin: 0;
        line-height: inherit;
        font-size: inherit;
    }
    .topic-summary a {
        color: inherit;
        text-decoration: none;
        border-bottom: 1px solid currentColor;
        transition: opacity 0.2s ease;
    }
    .topic-summary a:hover {
        opacity: 0.7;
    }
    .analysis-section {
        margin-top: 2rem;
        background: #ffffff;
        border-radius: 8px;
        padding: 1.5rem;
        border: 1px solid #e0e0e0;
    }
    .collapsible-container {
        margin-bottom: 2rem;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        overflow: hidden;
    }
    .collapsible-header {
        cursor: pointer;
        padding: 1rem;
        background-color: #ffffff;
        transition: background-color 0.2s ease;
    }
    .collapsible-header:hover {
        background-color: #f8f9fa;
    }
    .header-content {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    .chevron {
        color: inherit;
        opacity: 0.7;
        transition: transform 0.3s ease;
    }
    .collapsible-header h2 {
        margin: 0;
        font-size: 1.2rem;
        color: inherit;
    }
    .collapsible-content {
        margin-top: 0;
        padding: 1.5rem;
        background-color: #ffffff;
    }
    .visualization-container {
        margin-bottom: 2rem;
    }
    .tooltip {
        position: absolute;
        background-color: white;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 0 10px rgba(0,0,0,0.1);
        z-index: 1000;
        font-family: inherit;
        color: inherit;
    }
    .desktop-only {
        display: inline;
    }
    @media (max-width: 768px) {
        .desktop-only {
            display: none;
        }
        .analysis-section {
            display: none !important;
        }
    }
`;
document.head.appendChild(style);

export { init }; 