from importlib.resources import files


def test_monitor_widget_declares_korean_language_and_readable_type_scale() -> None:
    package = files("industrial_phm.apps")
    css = package.joinpath("monitor_widget.css").read_text(encoding="utf-8")
    javascript = package.joinpath("monitor_widget.js").read_text(encoding="utf-8")

    assert 'font: 15px/1.5 "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic",' in css
    assert "font-size: 14px" in css
    assert ".mw-shell:lang(ko)" in css
    assert "word-break: keep-all" in css
    assert "text-transform: none" in css
    assert "letter-spacing: 0" in css
    assert "root.lang = activeLocale;" in javascript
    assert "root.dataset.locale = activeLocale;" in javascript
