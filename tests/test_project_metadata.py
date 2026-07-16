from pathlib import Path

from app import app


ROOT = Path(__file__).resolve().parents[1]


def active_requirements(path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_runtime_dependencies_have_compatibility_upper_bounds():
    requirements = active_requirements(ROOT / "requirements.txt")

    assert requirements
    assert all(">=" in item and "<" in item for item in requirements)


def test_test_dependency_is_documented_with_a_bound():
    requirements = active_requirements(ROOT / "requirements-dev.txt")

    assert requirements == ["pytest>=8,<9"]


def test_readme_documents_python_and_browser_test_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "python -m pytest -q" in readme
    assert "playwright test" in readme
    assert "requirements-dev.txt" in readme


def test_browser_favicon_request_does_not_return_404():
    response = app.test_client().get("/favicon.ico")

    assert response.status_code == 204
