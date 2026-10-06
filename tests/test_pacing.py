from shot_list.pacing import subdivide_footage_range


def test_short_range_stays_as_one_cut():
    assert subdivide_footage_range(0.0, 4.0) == [(0.0, 4.0)]


def test_range_at_max_cut_boundary_stays_as_one_cut():
    assert subdivide_footage_range(10.0, 16.0) == [(10.0, 16.0)]


def test_range_just_over_max_cut_splits_in_two_and_no_cut_exceeds_max():
    cuts = subdivide_footage_range(0.0, 6.1)

    assert len(cuts) == 2
    for start, end in cuts:
        assert 2.5 <= (end - start) <= 6.0


def test_seven_second_range_splits_instead_of_staying_one_long_cut():
    cuts = subdivide_footage_range(0.0, 7.0)

    assert len(cuts) == 2
    assert all((end - start) <= 6.0 for start, end in cuts)


def test_long_range_splits_into_multiple_paced_cuts():
    cuts = subdivide_footage_range(0.0, 25.0)

    assert cuts[0][0] == 0.0
    assert cuts[-1][1] == 25.0
    for start, end in cuts:
        assert 2.5 <= (end - start) <= 6.0
    for (_, end_a), (start_b, _) in zip(cuts, cuts[1:]):
        assert end_a == start_b


def test_very_long_range_never_produces_cuts_below_min():
    cuts = subdivide_footage_range(100.0, 143.0)

    for start, end in cuts:
        assert (end - start) >= 2.5
    assert cuts[0][0] == 100.0
    assert cuts[-1][1] == 143.0
