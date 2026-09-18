"""Chapter 15: `cache_key`'s own normalization, the whole reason a
repeated question hits the cache at all. No network, no fake, nothing
but the function itself.
"""

from pkgintel_app.cost_cache import cache_key


def test_the_same_question_hashes_identically_regardless_of_case_or_padding():
    assert cache_key("What does httpx do?") == cache_key("  what does httpx do?  ")


def test_a_different_question_hashes_differently():
    assert cache_key("What does httpx do?") != cache_key("What does requests do?")
