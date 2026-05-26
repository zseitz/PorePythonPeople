from nanoporethon.consensus_maker_gui import consensus_signal, orient_sequence, reverse_complement, sanitize_sequence


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
    first = consensus_signal(seq, kmer_size=5, orientation="5'→3' forward strand")
    second = consensus_signal(seq, kmer_size=5, orientation="5'→3' forward strand")
    assert first.shape == second.shape
    assert (first == second).all()


def test_consensus_signal_length_matches_kmer_windows():
    seq = "ACGTACGT"
    signal = consensus_signal(seq, kmer_size=4, orientation="5'→3' forward strand")
    assert len(signal) == len(seq) - 4 + 1


def test_orient_sequence_supports_forward_and_reverse_complement_modes():
    seq = "ACGTAC"
    assert orient_sequence(seq, "5'→3' forward strand") == seq
    assert orient_sequence(seq, "5'→3' reverse-complement strand") == reverse_complement(seq)


def test_orientation_changes_signal_for_directional_kmer_map():
    seq = "AACGTTCA"
    forward = consensus_signal(seq, kmer_size=5, orientation="5'→3' forward strand")
    reverse_complement_signal = consensus_signal(seq, kmer_size=5, orientation="5'→3' reverse-complement strand")
    assert len(forward) == len(reverse_complement_signal)
    assert not (forward == reverse_complement_signal).all()


def test_orient_sequence_rejects_unsupported_orientation_labels():
    try:
        orient_sequence("ACGT", "3' forwards")
    except ValueError as exc:
        assert "unsupported orientation" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for unsupported orientation label")
