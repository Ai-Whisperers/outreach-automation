"""
Unit tests for similarity detection utilities.

Tests cover:
- Text tokenization
- Jaccard similarity
- N-gram similarity
- Cosine similarity
- Combined similarity checking
- Duplicate cluster detection
"""

import pytest


class TestTokenize:
    """Tests for text tokenization."""

    def test_tokenize_basic_text(self):
        """Test basic text tokenization."""
        from api.utils.similarity import tokenize

        tokens = tokenize("Hello world this is a test")

        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_tokenize_removes_stopwords(self):
        """Test stopword removal."""
        from api.utils.similarity import tokenize

        tokens = tokenize("the quick and the lazy fox")

        assert "the" not in tokens
        assert "and" not in tokens
        assert "quick" in tokens
        assert "lazy" in tokens
        assert "fox" in tokens

    def test_tokenize_removes_spanish_stopwords(self):
        """Test Spanish stopword removal."""
        from api.utils.similarity import tokenize

        tokens = tokenize("el gato y el perro son amigos")

        assert "el" not in tokens
        assert "y" not in tokens
        assert "son" not in tokens
        assert "gato" in tokens
        assert "perro" in tokens
        assert "amigos" in tokens

    def test_tokenize_removes_short_words(self):
        """Test short word removal."""
        from api.utils.similarity import tokenize

        tokens = tokenize("I am a cat")

        # Words with <= 2 chars should be removed
        assert "a" not in tokens
        assert "am" not in tokens
        assert "cat" in tokens

    def test_tokenize_handles_punctuation(self):
        """Test punctuation handling."""
        from api.utils.similarity import tokenize

        tokens = tokenize("Hello, world! How are you?")

        assert "hello" in tokens
        assert "world" in tokens
        # Punctuation should be stripped

    def test_tokenize_lowercase(self):
        """Test case normalization."""
        from api.utils.similarity import tokenize

        tokens = tokenize("HELLO World TEST")

        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "HELLO" not in tokens

    def test_tokenize_empty_string(self):
        """Test empty string handling."""
        from api.utils.similarity import tokenize

        tokens = tokenize("")

        assert tokens == []

    def test_tokenize_only_stopwords(self):
        """Test string with only stopwords."""
        from api.utils.similarity import tokenize

        tokens = tokenize("the and or but in on")

        assert tokens == []


class TestGetIdeaText:
    """Tests for idea text extraction."""

    def test_get_idea_text_basic(self):
        """Test basic idea text extraction."""
        from api.utils.similarity import get_idea_text

        idea = {
            "title": "Campaign Title",
            "concept": "Main concept description",
            "insight": "Consumer insight",
        }

        text = get_idea_text(idea)

        assert "Campaign Title" in text
        assert "Main concept description" in text
        assert "Consumer insight" in text

    def test_get_idea_text_with_execution(self):
        """Test idea text with execution details."""
        from api.utils.similarity import get_idea_text

        idea = {
            "title": "Test",
            "concept": "Concept",
            "execution": {
                "headline": "Big Bold Headline",
                "copy": "Supporting copy text",
            },
        }

        text = get_idea_text(idea)

        assert "Big Bold Headline" in text
        assert "Supporting copy text" in text

    def test_get_idea_text_missing_fields(self):
        """Test idea with missing fields."""
        from api.utils.similarity import get_idea_text

        idea = {
            "title": "Only Title",
        }

        text = get_idea_text(idea)

        assert "Only Title" in text

    def test_get_idea_text_empty(self):
        """Test empty idea."""
        from api.utils.similarity import get_idea_text

        idea = {}

        text = get_idea_text(idea)

        assert text == ""


class TestJaccardSimilarity:
    """Tests for Jaccard similarity."""

    def test_jaccard_identical(self):
        """Test identical token lists."""
        from api.utils.similarity import jaccard_similarity

        tokens = ["hello", "world", "test"]

        score = jaccard_similarity(tokens, tokens)

        assert score == 1.0

    def test_jaccard_completely_different(self):
        """Test completely different token lists."""
        from api.utils.similarity import jaccard_similarity

        tokens1 = ["hello", "world"]
        tokens2 = ["foo", "bar"]

        score = jaccard_similarity(tokens1, tokens2)

        assert score == 0.0

    def test_jaccard_partial_overlap(self):
        """Test partial overlap."""
        from api.utils.similarity import jaccard_similarity

        tokens1 = ["hello", "world", "test"]
        tokens2 = ["hello", "world", "other"]

        # Intersection: {hello, world} = 2
        # Union: {hello, world, test, other} = 4
        # Score: 2/4 = 0.5
        score = jaccard_similarity(tokens1, tokens2)

        assert score == 0.5

    def test_jaccard_empty_lists(self):
        """Test empty token lists."""
        from api.utils.similarity import jaccard_similarity

        score = jaccard_similarity([], [])
        assert score == 0.0

        score = jaccard_similarity(["hello"], [])
        assert score == 0.0


class TestGetNgrams:
    """Tests for n-gram generation."""

    def test_get_bigrams(self):
        """Test bigram generation."""
        from api.utils.similarity import get_ngrams

        tokens = ["hello", "world", "test"]

        ngrams = get_ngrams(tokens, n=2)

        assert ("hello", "world") in ngrams
        assert ("world", "test") in ngrams
        assert len(ngrams) == 2

    def test_get_trigrams(self):
        """Test trigram generation."""
        from api.utils.similarity import get_ngrams

        tokens = ["a", "b", "c", "d"]

        ngrams = get_ngrams(tokens, n=3)

        assert ("a", "b", "c") in ngrams
        assert ("b", "c", "d") in ngrams
        assert len(ngrams) == 2

    def test_get_ngrams_short_list(self):
        """Test n-grams with list shorter than n."""
        from api.utils.similarity import get_ngrams

        tokens = ["hello"]

        ngrams = get_ngrams(tokens, n=2)

        assert ngrams == set()

    def test_get_ngrams_exact_length(self):
        """Test n-grams with list exactly n length."""
        from api.utils.similarity import get_ngrams

        tokens = ["a", "b"]

        ngrams = get_ngrams(tokens, n=2)

        assert ngrams == {("a", "b")}


class TestNgramSimilarity:
    """Tests for n-gram similarity."""

    def test_ngram_identical(self):
        """Test identical token lists."""
        from api.utils.similarity import ngram_similarity

        tokens = ["hello", "world", "test", "case"]

        score = ngram_similarity(tokens, tokens)

        assert score == 1.0

    def test_ngram_different(self):
        """Test completely different token lists."""
        from api.utils.similarity import ngram_similarity

        tokens1 = ["hello", "world"]
        tokens2 = ["foo", "bar"]

        score = ngram_similarity(tokens1, tokens2)

        assert score == 0.0

    def test_ngram_partial_overlap(self):
        """Test partial overlap in n-grams."""
        from api.utils.similarity import ngram_similarity

        tokens1 = ["the", "quick", "brown", "fox"]
        tokens2 = ["the", "quick", "red", "fox"]

        # Bigrams1: {(the, quick), (quick, brown), (brown, fox)}
        # Bigrams2: {(the, quick), (quick, red), (red, fox)}
        # Intersection: {(the, quick)} = 1
        # Union: 5 unique bigrams
        score = ngram_similarity(tokens1, tokens2)

        assert 0 < score < 1

    def test_ngram_empty_lists(self):
        """Test empty token lists."""
        from api.utils.similarity import ngram_similarity

        score = ngram_similarity([], [])
        assert score == 0.0


class TestCosineSimilarity:
    """Tests for cosine similarity."""

    def test_cosine_identical(self):
        """Test identical token lists."""
        from api.utils.similarity import cosine_similarity_simple

        tokens = ["hello", "world", "test"]

        score = cosine_similarity_simple(tokens, tokens)

        assert round(score, 4) == 1.0

    def test_cosine_different(self):
        """Test completely different token lists."""
        from api.utils.similarity import cosine_similarity_simple

        tokens1 = ["hello", "world"]
        tokens2 = ["foo", "bar"]

        score = cosine_similarity_simple(tokens1, tokens2)

        assert score == 0.0

    def test_cosine_partial_overlap(self):
        """Test partial overlap."""
        from api.utils.similarity import cosine_similarity_simple

        tokens1 = ["hello", "world", "hello"]  # hello appears twice
        tokens2 = ["hello", "test", "hello"]

        score = cosine_similarity_simple(tokens1, tokens2)

        assert 0 < score < 1

    def test_cosine_term_frequency(self):
        """Test that term frequency affects score."""
        from api.utils.similarity import cosine_similarity_simple

        tokens1 = ["hello", "hello", "hello"]
        tokens2 = ["hello"]

        # Should still have high similarity due to shared term
        score = cosine_similarity_simple(tokens1, tokens2)

        assert score > 0

    def test_cosine_empty_lists(self):
        """Test empty token lists."""
        from api.utils.similarity import cosine_similarity_simple

        score = cosine_similarity_simple([], [])
        assert score == 0.0


class TestCheckIdeaSimilarity:
    """Tests for idea similarity checking."""

    def test_check_similar_ideas(self):
        """Test detecting similar ideas."""
        from api.utils.similarity import check_idea_similarity

        new_idea = {
            "title": "Digital Banking Revolution",
            "concept": "Innovative banking experience",
        }
        existing_ideas = [
            {
                "title": "Digital Banking Innovation",
                "concept": "Revolutionary banking experience",
            },
        ]

        is_similar, score, similar_to = check_idea_similarity(
            new_idea, existing_ideas, threshold=0.3
        )

        assert is_similar is True
        assert score > 0.3
        assert "Digital Banking" in similar_to

    def test_check_different_ideas(self):
        """Test different ideas not flagged as similar."""
        from api.utils.similarity import check_idea_similarity

        new_idea = {
            "title": "Social Media Campaign",
            "concept": "Viral marketing approach",
        }
        existing_ideas = [
            {
                "title": "Print Advertisement",
                "concept": "Traditional newspaper ads",
            },
        ]

        is_similar, score, similar_to = check_idea_similarity(
            new_idea, existing_ideas, threshold=0.5
        )

        assert is_similar is False

    def test_check_no_existing_ideas(self):
        """Test with no existing ideas."""
        from api.utils.similarity import check_idea_similarity

        new_idea = {"title": "Test", "concept": "Test concept"}

        is_similar, score, similar_to = check_idea_similarity(
            new_idea, [], threshold=0.4
        )

        assert is_similar is False
        assert score == 0.0
        assert similar_to == ""

    def test_check_different_methods(self):
        """Test different similarity methods."""
        from api.utils.similarity import check_idea_similarity

        new_idea = {
            "title": "Campaign Test",
            "concept": "Testing the campaign",
        }
        existing = [
            {
                "title": "Campaign Test Run",
                "concept": "Running the campaign test",
            },
        ]

        # Test each method
        methods = ["jaccard", "ngram", "cosine", "combined"]

        for method in methods:
            is_similar, score, _ = check_idea_similarity(
                new_idea, existing, threshold=0.3, method=method
            )
            # All should return valid results
            assert isinstance(is_similar, bool)
            assert 0 <= score <= 1

    def test_check_combined_method_default(self):
        """Test combined method is default."""
        from api.utils.similarity import check_idea_similarity

        new_idea = {"title": "Test", "concept": "Concept"}
        existing = [{"title": "Test Similar", "concept": "Similar Concept"}]

        # Without specifying method, should use combined
        _, score_default, _ = check_idea_similarity(new_idea, existing)
        _, score_combined, _ = check_idea_similarity(
            new_idea, existing, method="combined"
        )

        assert score_default == score_combined


class TestFindDuplicateClusters:
    """Tests for duplicate cluster detection."""

    def test_find_clusters_no_duplicates(self):
        """Test with no duplicate ideas."""
        from api.utils.similarity import find_duplicate_clusters

        ideas = [
            {"title": "Banking App", "concept": "Mobile banking"},
            {"title": "Food Delivery", "concept": "Restaurant delivery"},
            {"title": "Travel Guide", "concept": "Tourism application"},
        ]

        clusters = find_duplicate_clusters(ideas, threshold=0.6)

        # No clusters expected (all different)
        assert len(clusters) == 0

    def test_find_clusters_with_duplicates(self):
        """Test with duplicate ideas."""
        from api.utils.similarity import find_duplicate_clusters

        ideas = [
            {"title": "Banking Innovation", "concept": "Digital banking app"},
            {"title": "Banking Revolution", "concept": "Digital banking application"},
            {"title": "Food Delivery", "concept": "Restaurant service"},
            {"title": "Food Ordering", "concept": "Restaurant delivery"},
        ]

        clusters = find_duplicate_clusters(ideas, threshold=0.3)

        # Should find clusters of similar ideas
        assert len(clusters) >= 1

    def test_find_clusters_empty_list(self):
        """Test with empty idea list."""
        from api.utils.similarity import find_duplicate_clusters

        clusters = find_duplicate_clusters([], threshold=0.5)

        assert clusters == []

    def test_find_clusters_single_idea(self):
        """Test with single idea."""
        from api.utils.similarity import find_duplicate_clusters

        ideas = [{"title": "Test", "concept": "Test concept"}]

        clusters = find_duplicate_clusters(ideas, threshold=0.5)

        assert clusters == []

    def test_find_clusters_all_identical(self):
        """Test with all identical ideas."""
        from api.utils.similarity import find_duplicate_clusters

        ideas = [
            {"title": "Same Title", "concept": "Same concept"},
            {"title": "Same Title", "concept": "Same concept"},
            {"title": "Same Title", "concept": "Same concept"},
        ]

        clusters = find_duplicate_clusters(ideas, threshold=0.5)

        # All should be in one cluster
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_find_clusters_returns_indices(self):
        """Test that clusters contain indices."""
        from api.utils.similarity import find_duplicate_clusters

        ideas = [
            {"title": "Banking App", "concept": "Mobile banking solution"},
            {"title": "Banking Application", "concept": "Mobile banking app"},
        ]

        clusters = find_duplicate_clusters(ideas, threshold=0.4)

        if clusters:
            # Indices should be 0 and 1
            assert 0 in clusters[0]
            assert 1 in clusters[0]
