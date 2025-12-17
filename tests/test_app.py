from newsyacht.web.app import label_text_color
import pytest


@pytest.mark.parametrize("color", ["#ff6600", "#d7ff64", "#ff0000"])
def test_label_text_color(color, snapshot):
    assert label_text_color(color) == snapshot
