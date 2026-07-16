from modules import llm_name_resolver, text_parser


def test_opsin_warning_is_a_confirmation_candidate(monkeypatch):
    monkeypatch.setattr(
        text_parser,
        "parse_iupac_name",
        lambda value: {
            "smiles": "CCCCC=C",
            "source": "OPSIN",
            "input_type": "iupac_name",
            "opsin_status": "WARNING",
            "opsin_warning": "Unspecified double bond locant",
        },
    )

    result = text_parser.smart_parse("hexene", input_type="name")

    assert result["status"] == "ambiguous"
    assert result["candidates"][0]["requires_confirmation"] is True
    assert result["candidates"][0]["smiles"] == "C=CCCCC"


def test_stereo_prefix_is_never_silently_removed(monkeypatch):
    def fake_opsin(value):
        if value == "2-methylhex-2-ene":
            return {"smiles": "CCC=C(C)CC", "source": "OPSIN"}
        return None

    monkeypatch.setattr(text_parser, "parse_iupac_name", fake_opsin)
    monkeypatch.setattr(text_parser, "parse_common_name", lambda value: None)
    monkeypatch.setattr(
        text_parser,
        "resolve_name_to_iupac",
        lambda value: "(Z)-2-methylhex-2-ene",
    )

    result = text_parser.smart_parse("ambiguous alkene", input_type="name")

    assert result["status"] == "ambiguous"
    assert result["candidates"][0]["label"] == "忽略立体化学信息"
    assert result["candidates"][0]["requires_confirmation"] is True
    assert result["smiles"] is None


def test_llm_prompt_does_not_invent_formula_or_alkene_identity():
    assert "most common compound" not in llm_name_resolver.SYSTEM_PROMPT
    assert "DEFAULT to position 1" not in llm_name_resolver.SYSTEM_PROMPT
