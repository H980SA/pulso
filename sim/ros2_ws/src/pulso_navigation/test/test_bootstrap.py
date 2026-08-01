from pulso_navigation.bootstrap import bootstrap_viewpoints


def test_bootstrap_ids_advance_after_each_completed_sweep_step():
    first = bootstrap_viewpoints((0.0, 0.0, 0.0), 0)
    second = bootstrap_viewpoints((0.0, 0.0, 0.0), 1)
    assert first and second
    assert {item.candidate_id for item in first}.isdisjoint(
        {item.candidate_id for item in second}
    )
    assert all(item.rotation_only for item in first + second)
    assert all(item.path_length_m == 0.0 for item in first + second)


def test_bootstrap_is_bounded_when_mapping_cannot_initialize():
    assert bootstrap_viewpoints((0.0, 0.0, 0.0), 7)
    assert bootstrap_viewpoints((0.0, 0.0, 0.0), 8) == []
