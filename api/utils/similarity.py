"""
Similarity detection for campaign ideas.

Provides multiple methods to detect similar ideas:
- Jaccard similarity (word overlap)
- N-gram similarity (phrase overlap)
- TF-IDF based cosine similarity (optional, requires sklearn)
"""

import math
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    """
    Tokenize text into words, removing stopwords and punctuation.

    Args:
        text: Text to tokenize

    Returns:
        List of tokens
    """
    # Spanish stopwords
    stopwords = {
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'de', 'del', 'en', 'con', 'por', 'para', 'al', 'a',
        'y', 'o', 'que', 'es', 'son', 'como', 'más', 'pero',
        'su', 'sus', 'se', 'le', 'les', 'lo', 'este', 'esta',
        'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
        'the', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
        'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are'
    }

    # Extract words
    words = re.findall(r'\b[a-záéíóúüñ]+\b', text.lower())

    # Filter stopwords and short words
    return [w for w in words if w not in stopwords and len(w) > 2]


def get_idea_text(idea: dict) -> str:
    """
    Extract text content from an idea for comparison.

    Args:
        idea: Idea dictionary

    Returns:
        Combined text from key fields
    """
    fields = [
        idea.get('title', ''),
        idea.get('concept', ''),
        idea.get('insight', ''),
        idea.get('tagline', ''),
    ]

    # Also get execution details
    execution = idea.get('execution', {})
    if isinstance(execution, dict):
        fields.extend(execution.values())

    return ' '.join(str(f) for f in fields if f)


def jaccard_similarity(tokens1: list[str], tokens2: list[str]) -> float:
    """
    Calculate Jaccard similarity between two token lists.

    Args:
        tokens1: First token list
        tokens2: Second token list

    Returns:
        Similarity score between 0 and 1
    """
    set1 = set(tokens1)
    set2 = set(tokens2)

    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def get_ngrams(tokens: list[str], n: int = 2) -> set[tuple]:
    """
    Generate n-grams from token list.

    Args:
        tokens: List of tokens
        n: N-gram size

    Returns:
        Set of n-gram tuples
    """
    if len(tokens) < n:
        return set()

    return set(tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1))


def ngram_similarity(tokens1: list[str], tokens2: list[str], n: int = 2) -> float:
    """
    Calculate n-gram based similarity.

    Args:
        tokens1: First token list
        tokens2: Second token list
        n: N-gram size

    Returns:
        Similarity score between 0 and 1
    """
    ngrams1 = get_ngrams(tokens1, n)
    ngrams2 = get_ngrams(tokens2, n)

    if not ngrams1 or not ngrams2:
        return 0.0

    intersection = len(ngrams1 & ngrams2)
    union = len(ngrams1 | ngrams2)

    return intersection / union if union > 0 else 0.0


def cosine_similarity_simple(tokens1: list[str], tokens2: list[str]) -> float:
    """
    Calculate cosine similarity using term frequency.

    Args:
        tokens1: First token list
        tokens2: Second token list

    Returns:
        Similarity score between 0 and 1
    """
    # Build term frequency vectors
    counter1 = Counter(tokens1)
    counter2 = Counter(tokens2)

    # Get all terms
    all_terms = set(counter1.keys()) | set(counter2.keys())

    if not all_terms:
        return 0.0

    # Calculate dot product and magnitudes
    dot_product = sum(counter1.get(term, 0) * counter2.get(term, 0) for term in all_terms)
    mag1 = math.sqrt(sum(v ** 2 for v in counter1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in counter2.values()))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


def check_idea_similarity(
    new_idea: dict,
    existing_ideas: list[dict],
    threshold: float = 0.4,
    method: str = "combined"
) -> tuple[bool, float, str]:
    """
    Check if a new idea is too similar to existing ideas.

    Args:
        new_idea: The new idea to check
        existing_ideas: List of existing ideas
        threshold: Similarity threshold (0-1)
        method: Similarity method ("jaccard", "ngram", "cosine", "combined")

    Returns:
        Tuple of (is_similar, max_similarity, most_similar_idea_title)
    """
    if not existing_ideas:
        return False, 0.0, ""

    new_text = get_idea_text(new_idea)
    new_tokens = tokenize(new_text)

    if not new_tokens:
        return False, 0.0, ""

    max_similarity = 0.0
    most_similar_title = ""

    for existing in existing_ideas:
        existing_text = get_idea_text(existing)
        existing_tokens = tokenize(existing_text)

        if not existing_tokens:
            continue

        # Calculate similarity based on method
        if method == "jaccard":
            similarity = jaccard_similarity(new_tokens, existing_tokens)
        elif method == "ngram":
            similarity = ngram_similarity(new_tokens, existing_tokens)
        elif method == "cosine":
            similarity = cosine_similarity_simple(new_tokens, existing_tokens)
        else:  # combined
            # Weighted combination of methods
            jaccard = jaccard_similarity(new_tokens, existing_tokens)
            ngram = ngram_similarity(new_tokens, existing_tokens)
            cosine = cosine_similarity_simple(new_tokens, existing_tokens)
            similarity = 0.4 * jaccard + 0.3 * ngram + 0.3 * cosine

        if similarity > max_similarity:
            max_similarity = similarity
            most_similar_title = existing.get('title', 'Unknown')

    is_similar = max_similarity > threshold
    return is_similar, max_similarity, most_similar_title


def find_duplicate_clusters(
    ideas: list[dict],
    threshold: float = 0.5
) -> list[list[int]]:
    """
    Find clusters of similar ideas.

    Args:
        ideas: List of ideas
        threshold: Similarity threshold

    Returns:
        List of clusters (each cluster is a list of idea indices)
    """
    n = len(ideas)
    if n == 0:
        return []

    # Build similarity matrix
    tokens = [tokenize(get_idea_text(idea)) for idea in ideas]

    # Find connected components of similar ideas
    visited = set()
    clusters = []

    for i in range(n):
        if i in visited:
            continue

        cluster = [i]
        visited.add(i)
        stack = [i]

        while stack:
            current = stack.pop()
            for j in range(n):
                if j in visited:
                    continue

                # Check similarity
                jaccard = jaccard_similarity(tokens[current], tokens[j])
                if jaccard > threshold:
                    cluster.append(j)
                    visited.add(j)
                    stack.append(j)

        if len(cluster) > 1:
            clusters.append(cluster)

    return clusters
