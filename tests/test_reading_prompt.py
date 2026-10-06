from graph_intake.reading_prompt import build_reading_prompt


def test_prompt_names_the_image_path_and_the_italic_phrase():
    prompt = build_reading_prompt("/abs/graph_inputs/graph_0.jpg", "GDP per capita ranges widely")

    assert "/abs/graph_inputs/graph_0.jpg" in prompt
    assert '"GDP per capita ranges widely"' in prompt
    assert "Read tool" in prompt


def test_prompt_forbids_inventing_values_and_states_the_schema():
    prompt = build_reading_prompt("/abs/g.png", "x")

    assert "Never fill in a value that is not printed" in prompt
    assert '"readable": false' in prompt
    assert 'e.g. "$8K"' in prompt and "8000" in prompt
    for key in ('"title"', '"subtitle"', '"graph_kind"', '"unit"', '"source_line"', '"values"',
                '"notes"', '"label"', '"display"', '"value"', '"readable"'):
        assert key in prompt
    assert "Respond with ONLY a JSON object" in prompt


def test_prompt_asks_for_the_printed_source_not_the_publisher():
    prompt = build_reading_prompt("/abs/g.png", "x")

    assert "not the name or logo of whoever published the image" in prompt


def test_prompt_handles_rotated_images_and_excludes_scale_markings():
    prompt = build_reading_prompt("/abs/g.png", "x")

    assert "rotated or mirrored" in prompt
    assert "colour-legend endpoints are scale markings, not data values" in prompt
