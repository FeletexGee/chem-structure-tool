from modules import image_parser


def test_image_failure_reports_only_decimer(monkeypatch, tmp_path):
    image_path = tmp_path / "structure.png"
    image_path.write_bytes(b"fixture")
    monkeypatch.setattr(
        image_parser,
        "parse_image_decimer",
        lambda path: {
            "smiles": None,
            "source": "DECIMER",
            "error": "DECIMER unavailable",
        },
    )

    result = image_parser.smart_parse_image(str(image_path))

    assert result["success"] is False
    assert "DECIMER unavailable" in result["error"]


def test_missing_image_error_does_not_expose_absolute_path(tmp_path):
    missing = tmp_path / "private" / "structure.png"

    result = image_parser.smart_parse_image(str(missing))

    assert result["success"] is False
    assert str(missing) not in result["error"]
