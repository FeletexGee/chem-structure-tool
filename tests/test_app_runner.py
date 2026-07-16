import app as app_module


def test_run_uses_configured_debug_flag(monkeypatch):
    observed = {}
    monkeypatch.setattr(app_module, "DEBUG", True)
    monkeypatch.setattr(
        app_module.app,
        "run",
        lambda **kwargs: observed.update(kwargs),
    )

    app_module.run()

    assert observed["debug"] is True
    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 5000
