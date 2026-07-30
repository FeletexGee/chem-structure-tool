from modules import text_parser


def test_auto_mode_reports_formula_smiles_conflict():
    result = text_parser.smart_parse("CO", input_type="auto")

    assert result["status"] == "ambiguous"
    assert result["requires_selection"] is True
    assert {item["input_type"] for item in result["candidates"]} == {
        "smiles",
        "formula",
    }


def test_explicit_smiles_mode_resolves_without_formula_lookup(monkeypatch):
    def fail_formula_lookup(value):
        raise AssertionError("formula lookup called")

    monkeypatch.setattr(text_parser, "parse_formula", fail_formula_lookup)

    result = text_parser.smart_parse("CO", input_type="smiles")

    assert result["status"] == "resolved"
    assert result["smiles"] == "CO"
    assert result["input_type"] == "smiles"


def test_formula_mode_returns_multiple_pubchem_candidates(monkeypatch):
    monkeypatch.setattr(
        text_parser,
        "_pubchem_formula_candidates",
        lambda value, max_results=5: [
            {
                "cid": 5793,
                "title": "D-Glucose",
                "smiles": "C(C1C(C(C(C(O1)O)O)O)O)O",
                "formula": "C6H12O6",
            },
            {
                "cid": 5984,
                "title": "D-Fructose",
                "smiles": "C(C(C(C(C(=O)CO)O)O)O)O",
                "formula": "C6H12O6",
            },
        ],
        raising=False,
    )

    result = text_parser.smart_parse("C6H12O6", input_type="formula")

    assert result["status"] == "ambiguous"
    assert [item["title"] for item in result["candidates"]] == [
        "D-Glucose",
        "D-Fructose",
    ]
    assert all(item["input_type"] == "smiles" for item in result["candidates"])
