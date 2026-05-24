from nanoporethon.consensus_maker_gui import consensus_signal, sanitize_sequence


def test_sanitize_sequence_normalizes_whitespace_and_case():
    assert sanitize_sequence(" a c g t \nac ") == "ACGTAC"


def test_sanitize_sequence_rejects_invalid_bases():
    try:
        sanitize_sequence("ACGTN")
    except ValueError as exc:
        assert "invalid characters" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for invalid base")


def test_consensus_signal_is_deterministic_for_same_input():
    seq = "ACGTACGTAC"
    first = consensus_signal(seq, kmer_size=5)
    second = consensus_signal(seq, kmer_size=5)
    assert first.shape == second.shape
    assert (first == second).all()


def test_consensus_signal_length_matches_kmer_windows():
    seq = "ACGTACGT"
    signal = consensus_signal(seq, kmer_size=4)
    assert len(signal) == len(seq) - 4 + 1
