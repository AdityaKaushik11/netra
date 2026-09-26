from app.services.watchlist_matcher import levenshtein_le1


def test_levenshtein_le1():
    assert levenshtein_le1("GJ01XX0001", "GJ01XX0001")
    assert levenshtein_le1("GJ01XX0001", "GJ01XX0O01")  # substitution (0 -> O)
    assert levenshtein_le1("GJ01XX0001", "GJ01XX001")  # deletion
    assert levenshtein_le1("GJ01XX001", "GJ01XX0001")  # insertion
    assert not levenshtein_le1("GJ01XX0001", "GJ01XX0099")
    assert levenshtein_le1("GJ01XX0001", "GJ01XX00012")  # trailing insertion
    assert not levenshtein_le1("GJ01XX0001", "GJ01XX000123")
