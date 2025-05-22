from bs4 import BeautifulSoup
import requests
from typing import List, Tuple, Dict
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
import logging
import time
from collections import defaultdict
import pandas as pd
from collections import Counter
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def get_embeddings(texts: List[str], model_name: str = 'all-MiniLM-L6-v2') -> np.ndarray:
    logger.info(f"Loading BERT model: {model_name}")
    start_time = time.time()
    model = SentenceTransformer(model_name)
    logger.info(f"Model loaded in {time.time() - start_time:.2f} seconds")
    
    logger.info(f"Generating embeddings for {len(texts)} texts")
    start_time = time.time()
    embeddings = model.encode(texts)
    logger.info(f"Embeddings generated in {time.time() - start_time:.2f} seconds")
    logger.info(f"Embedding shape: {embeddings.shape}")
    
    return embeddings

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if b.ndim == 1:
        b = b.reshape(1, -1)
    
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    
    return np.dot(a_norm, b_norm.T).flatten()

def extract_blog_info(html_path: str) -> Dict:
    logger.info(f"Reading HTML file: {html_path}")
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    logger.info("Parsing HTML content")
    soup = BeautifulSoup(html_content, 'html.parser')
    
    logger.info("Extracting coming soon topics")
    coming_soon = []
    intro_paragraph = soup.find('main').find('p')
    if intro_paragraph:
        coming_soon_list = intro_paragraph.find_all('li')
        coming_soon = [item.text.strip() for item in coming_soon_list]
    logger.info(f"Found {len(coming_soon)} coming soon topics")
    
    logger.info("Extracting blog posts")
    blog_posts = soup.find_all('article', class_='blog-post')
    
    posts_info = []
    post_texts = []
    
    for post in blog_posts:
        title_elem = post.find('h2').find('a')
        title = title_elem.text.strip()
        
        date = post.find('div', class_='post-date').text.strip()
        
        description = post.find('p').text.strip()
        
        posts_info.append((title, date, description))
        post_texts.append(f"{title} {description}")
    
    logger.info(f"Found {len(posts_info)} blog posts")
    
    logger.info("Generating embeddings for blog content")
    post_embeddings = get_embeddings(post_texts)
    coming_soon_embeddings = get_embeddings(coming_soon)
    
    return {
        'coming_soon': coming_soon,
        'posts': posts_info,
        'post_embeddings': post_embeddings,
        'coming_soon_embeddings': coming_soon_embeddings
    }

def perform_pca_analysis(blog_info: Dict, n_components: int = 2) -> Dict:
    logger.info(f"Starting PCA analysis with {n_components} components")
    
    all_embeddings = np.vstack([
        blog_info['post_embeddings'],
        blog_info['coming_soon_embeddings']
    ])
    
    pca = PCA(n_components=n_components)
    transformed_embeddings = pca.fit_transform(all_embeddings)
    
    n_posts = len(blog_info['posts'])
    post_transformed = transformed_embeddings[:n_posts]
    coming_soon_transformed = transformed_embeddings[n_posts:]
    
    return {
        'pca': pca,
        'post_transformed': post_transformed,
        'coming_soon_transformed': coming_soon_transformed,
        'explained_variance_ratio': pca.explained_variance_ratio_
    }

def analyze_interdisciplinary_topics(blog_info: Dict, n_topics: int = 5, similarity_threshold: float = 0.3) -> Dict:
    logger.info(f"Analyzing {n_topics} interdisciplinary topics")
    
    all_embeddings = np.vstack([
        blog_info['post_embeddings'],
        blog_info['coming_soon_embeddings']
    ])
    
    all_texts = []
    all_texts.extend([f"{title} {desc}" for title, _, desc in blog_info['posts']])
    all_texts.extend(blog_info['coming_soon'])
    
    kmeans = KMeans(n_clusters=n_topics, random_state=42)
    kmeans.fit(all_embeddings)
    topic_centers = kmeans.cluster_centers_
    
    topics = []
    for i, center in enumerate(topic_centers):
        similarities = cosine_similarity(all_embeddings, center.reshape(1, -1)).flatten()
        
        related_indices = np.where(similarities > similarity_threshold)[0]
        related_texts = [all_texts[idx] for idx in related_indices]
        related_scores = similarities[related_indices]
        
        sorted_pairs = sorted(zip(related_texts, related_scores), key=lambda x: x[1], reverse=True)
        
        topics.append({
            'topic_id': i,
            'center': center,
            'related_content': sorted_pairs,
            'strength': len(related_indices)
        })
    
    return {
        'topics': topics,
        'topic_centers': topic_centers
    }

def interpret_interdisciplinary_topics(topic_analysis: Dict) -> List[Dict]:
    logger.info("Interpreting topics")
    
    term_mappings = load_term_mappings()
    compound_topics = load_compound_topics()
    
    interpreted_topics = []
    for topic in topic_analysis['topics']:
        top_content = [text for text, score in topic['related_content'][:5]]
        
        term_freq = defaultdict(int)
        for text in top_content:
            words = text.lower().split()
            for word in words:
                if len(word) > 3:  # Ignore short words
                    term_freq[word] += 1
        
        common_terms = sorted(term_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        common_text = ' '.join([term for term, _ in common_terms]).lower()
        
        topic_name = None
        
        for (term1, term2), mapping in compound_topics.items():
            if term1 in common_text and term2 in common_text:
                topic_name = mapping
                break
        
        if not topic_name:
            for term, freq in common_terms:
                if term in term_mappings and term_mappings[term]:
                    topic_name = term_mappings[term]
                    break
        
        # bit hacky
        if not topic_name:
            if any('information' in text.lower() and 'statistical' in text.lower() for text in top_content):
                topic_name = "Information Theory in Statistical Mechanics"
            elif any('neural' in text.lower() and 'kernel' in text.lower() for text in top_content):
                topic_name = "Neural Tangent Kernels"
            elif any('hopfield' in text.lower() for text in top_content):
                topic_name = "Hopfield Networks"
            elif any('markov' in text.lower() for text in top_content):
                topic_name = "Markov Processes"
            elif any('cookie' in text.lower() for text in top_content):
                topic_name = "Cookie Story"
            else:
                main_term = common_terms[0][0]
                context_terms = [t for t, _ in common_terms if t != main_term]
                if context_terms:
                    topic_name = f"{main_term.title()} in {context_terms[0].title()}"
                else:
                    topic_name = main_term.title()
        
        connections = []
        for text, score in topic['related_content']:
            if score > 0.5 and text not in top_content:  # strong connection and not in core
                connections.append(text)
        
        coherence = np.mean([score for _, score in topic['related_content'][:5]])
        
        interpreted_topics.append({
            'topic': topic_name,
            'strength': topic['strength'],
            'coherence': coherence,
            'core_content': top_content,
            'connections': connections,
            'topic_id': topic['topic_id']
        })
    
    interpreted_topics.sort(key=lambda x: (x['strength'] * x['coherence']), reverse=True)
    
    return interpreted_topics

def analyze_word_frequencies(texts):
    all_text = ' '.join(texts).lower()
    
    words = re.findall(r'\b\w+\b', all_text)
    
    stop_words = set(['the', 'and', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'])
    words = [word for word in words if word not in stop_words and len(word) > 3]
    
    word_freq = Counter(words)
    
    return word_freq

def load_term_mappings():
    try:
        df = pd.read_csv('term_mappings.csv')
        mappings = df[df['mapping'].notna()].set_index('term')['mapping'].to_dict()
        logger.info(f"Loaded {len(mappings)} term mappings")
        return mappings
    except Exception as e:
        logger.error(f"Error loading term mappings: {e}")
        return {}

def load_compound_topics():
    """Load compound topics from CSV file."""
    try:
        df = pd.read_csv('compound_topics.csv')
        mappings = {(row['term1'], row['term2']): row['mapping'] 
                   for _, row in df.iterrows()}
        logger.info(f"Loaded {len(mappings)} compound topics")
        return mappings
    except Exception as e:
        logger.error(f"Error loading compound topics: {e}")
        return {}

def save_word_frequencies_to_csv(word_freq, filename='word_frequencies.csv'):
    df = pd.DataFrame(list(word_freq.items()), columns=['term', 'frequency'])
    df = df.sort_values('frequency', ascending=False)
    df.to_csv(filename, index=False)
    logger.info(f"Saved word frequencies to {filename}")

def save_topic_analysis_to_csv(interpreted_topics, filename='topic_analysis.csv'):
    topics_data = []
    for topic in interpreted_topics:
        topics_data.append({
            'topic': topic['topic'],
            'strength': topic['strength'],
            'coherence': topic['coherence'],
            'core_content': ' | '.join(topic['core_content']),
            'connections': ' | '.join(topic['connections']) if topic['connections'] else ''
        })
    
    df = pd.DataFrame(topics_data)
    df.to_csv(filename, index=False)
    logger.info(f"Saved topic analysis to {filename}")

def save_pca_data_to_csv(pca_results, blog_info, filename='pca_data.csv'):
    all_points = np.vstack([
        pca_results['post_transformed'],
        pca_results['coming_soon_transformed']
    ])
    
    all_texts = []
    all_texts.extend([title for title, _, _ in blog_info['posts']])
    all_texts.extend(blog_info['coming_soon'])
    
    df = pd.DataFrame({
        'text': all_texts,
        'pc1': all_points[:, 0],
        'pc2': all_points[:, 1],
        'type': ['blog_post'] * len(blog_info['posts']) + ['coming_soon'] * len(blog_info['coming_soon'])
    })
    
    var_ratio = pca_results['explained_variance_ratio']
    df['pc1_variance'] = var_ratio[0]
    df['pc2_variance'] = var_ratio[1]
    
    df.to_csv(filename, index=False)
    logger.info(f"Saved PCA data to {filename}")

if __name__ == "__main__":
    logger.info("Starting blog analysis")
    start_time = time.time()
    
    term_mappings = load_term_mappings()
    compound_topics = load_compound_topics()
    
    blog_info = extract_blog_info('index.html')
    
    all_texts = []
    all_texts.extend([f"{title} {desc}" for title, _, desc in blog_info['posts']])
    all_texts.extend(blog_info['coming_soon'])
    
    word_freq = analyze_word_frequencies(all_texts)
    
    save_word_frequencies_to_csv(word_freq)
    
    pca_results = perform_pca_analysis(blog_info)
    topic_analysis = analyze_interdisciplinary_topics(blog_info)
    interpreted_topics = interpret_interdisciplinary_topics(topic_analysis)
    
    save_topic_analysis_to_csv(interpreted_topics)
    save_pca_data_to_csv(pca_results, blog_info)
    
    logger.info(f"Analysis completed in {time.time() - start_time:.2f} seconds") 