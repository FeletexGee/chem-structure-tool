# ChemStructure Reliability Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor ChemStructure Tool so ambiguous chemistry requires explicit confirmation, failures are represented accurately, uploads are safe and temporary, exports are valid, and every behavior has regression coverage.

**Architecture:** Keep the existing Flask, RDKit, and vanilla JavaScript structure. Add small pure helpers for input classification, request validation, result-state construction, and upload normalization; expose structured ambiguity and stage-status responses through the existing API and render them in the current single-page UI.

**Tech Stack:** Python 3.10+, Flask 3, RDKit, Pillow, requests, pytest, vanilla JavaScript, Playwright.

---

## File Map

- `modules/text_parser.py`: explicit input modes, formula candidates, OPSIN warning candidates, stereochemistry confirmation.
- `modules/request_validation.py`: reusable JSON field validation for Flask routes.
- `modules/structure_processor.py`: PNG indices, strict format handling, SDF/PDB serialization, conformer fallback.
- `modules/image_parser.py`: verified image normalization, DECIMER-only inference, intermediate cleanup.
- `app.py`: schema validation, ambiguity HTTP mapping, stage results, upload cleanup, debug runner.
- `templates/index.html`: ambiguity and partial-failure UI containers.
- `static/js/main.js`: structured API errors, candidate selection, stale-state clearing, partial-stage rendering.
- `static/css/style.css`: candidate and stage-state presentation.
- `tests/`: Python regression and route tests.
- `tests/e2e/`: rendered frontend flows.
- `package.json`, `playwright.config.js`: browser-test tooling.
- `requirements-dev.txt`: Python test dependencies.
- `README.md`: behavior, API, setup, testing, image engine, and deployment documentation.

## Execution Rules

- Run each RED command and confirm the stated behavioral failure before editing production code.
- Keep tests and README changes in the same commit as their behavior.
- After each focused GREEN command, run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py config.py modules tests
node --check static\js\main.js
```

- Inspect `git diff --check` and the staged diff before every commit.

### Task 1: Explicit formula/SMILES ambiguity resolution

**Files:**
- Create: `tests/test_text_ambiguity.py`
- Create: `tests/test_api_ambiguity.py`
- Create: `tests/e2e/ambiguity.spec.js`
- Create: `package.json`
- Create: `playwright.config.js`
- Create: `requirements-dev.txt`
- Modify: `modules/text_parser.py`
- Modify: `app.py`
- Modify: `templates/index.html`
- Modify: `static/js/main.js`
- Modify: `static/css/style.css`
- Modify: `README.md`

- [ ] **Step 1: Add failing parser tests**

```python
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
    monkeypatch.setattr(
        text_parser,
        "parse_formula",
        lambda value: (_ for _ in ()).throw(AssertionError("formula lookup called")),
    )

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
    )

    result = text_parser.smart_parse("C6H12O6", input_type="formula")

    assert result["status"] == "ambiguous"
    assert [item["title"] for item in result["candidates"]] == [
        "D-Glucose",
        "D-Fructose",
    ]
    assert all(item["input_type"] == "smiles" for item in result["candidates"])
```

- [ ] **Step 2: Run RED parser tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_text_ambiguity.py -q
```

Expected: fail because `smart_parse` does not accept `input_type` and `CO` resolves directly as SMILES.

- [ ] **Step 3: Add failing API ambiguity test**

```python
from app import app


def test_process_returns_409_with_candidate_payload_for_co():
    client = app.test_client()

    response = client.post(
        "/api/process",
        json={"input": "CO", "input_type": "auto"},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["requires_selection"] is True
    assert len(payload["candidates"]) == 2
```

- [ ] **Step 4: Run RED API test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_ambiguity.py -q
```

Expected: fail because `/api/process` ignores `input_type` and returns a resolved methanol response.

- [ ] **Step 5: Implement explicit modes and ambiguity candidates**

Add constants and helpers in `modules/text_parser.py`:

```python
INPUT_TYPES = {"auto", "smiles", "formula", "name"}


def _is_formula_like(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", re.sub(r"\s+", "", value)))


def _resolved(result: Dict) -> Dict:
    return {"success": True, "status": "resolved", "error": None, **result}


def _ambiguous(reason: str, candidates: list[Dict]) -> Dict:
    return {
        "success": False,
        "status": "ambiguous",
        "requires_selection": True,
        "reason": reason,
        "candidates": candidates,
        "smiles": None,
        "error": None,
    }
```

Change `smart_parse` to `smart_parse(user_input: str, input_type: str = "auto")` and route explicit modes directly. In auto mode, if both `_is_formula_like` and `validate_smiles` succeed, return two candidates. The SMILES candidate includes canonical SMILES and RDKit molecular formula; the formula candidate contains the original formula and `input_type="formula"`.

Replace the single-CID formula helper with `_pubchem_formula_candidates(formula, max_results=5)`. Fetch up to five CIDs, then request `Title,CanonicalSMILES,MolecularFormula` for those CIDs. Return one resolved result only when PubChem provides exactly one valid structure; otherwise return an ambiguity response whose candidates use the returned SMILES as explicit `input_type="smiles"` selections.

Update `/api/process` and `/api/parse-text` to pass `input_type` and return ambiguity payloads with HTTP 409.

- [ ] **Step 6: Run GREEN backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_text_ambiguity.py tests/test_api_ambiguity.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Add the failing Playwright ambiguity flow**

Create browser tooling:

```json
{
  "private": true,
  "scripts": {
    "test:e2e": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "^1.54.0"
  }
}
```

```javascript
const { test, expect } = require("@playwright/test");

test("CO requires an explicit interpretation", async ({ page }) => {
  await page.goto("/");
  await page.locator("#text-input").fill("CO");
  await page.locator("#btn-parse-text").click();

  await expect(page.locator("#ambiguity-panel")).toBeVisible();
  await expect(page.locator("#ambiguity-candidates button")).toHaveCount(2);
  await page.getByRole("button", { name: /按 SMILES 解释/ }).click();
  await expect(page.locator("#result-section")).toBeVisible();
  await expect(page.locator("#text-status")).toContainText("解析成功");
});
```

Configure `webServer` in `playwright.config.js` to run `.venv\\Scripts\\python.exe app.py` at `http://127.0.0.1:5000`.

Create `requirements-dev.txt` with:

```text
pytest>=8,<9
```

- [ ] **Step 8: Install browser tooling and run RED e2e test**

```powershell
pnpm install
pnpm exec playwright install chromium
pnpm exec playwright test tests/e2e/ambiguity.spec.js
```

Expected: fail because the page has no ambiguity panel or candidate behavior.

- [ ] **Step 9: Implement candidate UI**

Add `#ambiguity-panel`, `#ambiguity-reason`, and `#ambiguity-candidates` to `templates/index.html`. Refactor frontend processing to:

```javascript
class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.status = status;
        this.data = data;
    }
}

async function processTextInput(input, inputType = "auto") {
    clearAmbiguity();
    try {
        const data = await apiCall("/api/process", {
            method: "POST",
            body: JSON.stringify({ input, input_type: inputType }),
        });
        renderResults(data);
    } catch (error) {
        if (error.data?.requires_selection) {
            renderAmbiguity(error.data);
            return;
        }
        throw error;
    }
}
```

Candidate buttons call `processTextInput(candidate.input, candidate.input_type)`. Add accessible button labels and visible focus styles.

- [ ] **Step 10: Run GREEN e2e and full regression checks**

```powershell
pnpm exec playwright test tests/e2e/ambiguity.spec.js
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py config.py modules tests
node --check static\js\main.js
```

- [ ] **Step 11: Document ambiguity behavior and commit**

Update README feature, API, and examples sections to explain explicit input types, HTTP 409 ambiguity responses, and candidate selection.

```powershell
git add modules/text_parser.py app.py templates/index.html static/js/main.js static/css/style.css tests package.json pnpm-lock.yaml playwright.config.js requirements-dev.txt README.md
git commit -m "feat: add explicit ambiguity resolution"
```

### Task 2: Confirmation for uncertain nomenclature

**Files:**
- Create: `tests/test_nomenclature_confirmation.py`
- Modify: `modules/text_parser.py`
- Modify: `modules/llm_name_resolver.py`
- Modify: `static/js/main.js`
- Modify: `README.md`

- [ ] **Step 1: Add failing OPSIN warning and stereo tests**

```python
from modules import text_parser


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


def test_stereo_prefix_is_never_silently_removed(monkeypatch):
    calls = []

    def fake_opsin(value):
        calls.append(value)
        if value == "2-methylhex-2-ene":
            return {"smiles": "CCC=C(C)CC", "source": "OPSIN"}
        return None

    monkeypatch.setattr(text_parser, "parse_iupac_name", fake_opsin)
    monkeypatch.setattr(
        text_parser,
        "resolve_name_to_iupac",
        lambda value: "(Z)-2-methylhex-2-ene",
    )

    result = text_parser.smart_parse("ambiguous alkene", input_type="name")

    assert result["status"] == "ambiguous"
    assert result["candidates"][0]["label"] == "忽略立体化学信息"
    assert result["smiles"] is None
```

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nomenclature_confirmation.py -q
```

Expected: OPSIN warnings resolve immediately and stereochemistry is silently stripped.

- [ ] **Step 3: Implement confirmation-only nomenclature behavior**

Preserve the OPSIN status in `parse_iupac_name`. Convert warning responses into candidates. Retain the stripped-name probe only to construct a candidate; never return it as resolved. Candidate selection sends the candidate SMILES with `input_type="smiles"`.

Remove the missing-locant default rule and examples from `SYSTEM_PROMPT`. Change the formula rule to return `UNKNOWN` because formula candidate selection belongs to PubChem, not the LLM.

- [ ] **Step 4: Run GREEN and full tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nomenclature_confirmation.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 5: Update documentation and commit**

Document OPSIN warnings and explicit stereochemistry downgrade confirmation.

```powershell
git add modules/text_parser.py modules/llm_name_resolver.py static/js/main.js tests/test_nomenclature_confirmation.py README.md
git commit -m "fix: require confirmation for uncertain nomenclature"
```

### Task 3: Request-schema validation

**Files:**
- Create: `modules/request_validation.py`
- Create: `tests/test_api_validation.py`
- Modify: `app.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing route-validation tests**

```python
import pytest
from app import app


@pytest.mark.parametrize("value", [None, 12, True, [], {}])
def test_process_rejects_non_string_input(value):
    response = app.test_client().post("/api/process", json={"input": value})
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_render_2d_rejects_non_boolean_show_indices():
    response = app.test_client().post(
        "/api/render-2d",
        json={"smiles": "CCO", "show_indices": "yes"},
    )
    assert response.status_code == 400


def test_export_rejects_unknown_format():
    response = app.test_client().post(
        "/api/export",
        json={"smiles": "CCO", "format": "PDF"},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_validation.py -q
```

Expected: non-string values raise server errors or reach downstream code.

- [ ] **Step 3: Implement validation helpers and use them in every route**

Create helpers:

```python
class RequestValidationError(ValueError):
    pass


def require_json_object(request) -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise RequestValidationError("请求体必须是 JSON 对象")
    return data


def require_string(data: dict, key: str, *, max_length: int) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise RequestValidationError(f"'{key}' 必须是字符串")
    value = value.strip()
    if not value:
        raise RequestValidationError(f"'{key}' 不能为空")
    if len(value) > max_length:
        raise RequestValidationError(f"'{key}' 长度不能超过 {max_length}")
    return value
```

Add `optional_choice` and `optional_bool`. Wrap each route validation block and return:

```python
return jsonify({
    "success": False,
    "code": "invalid_request",
    "error": str(exc),
}), 400
```

- [ ] **Step 4: Run GREEN and full tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_validation.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 5: Document limits and commit**

Document maximum input lengths, allowed formats, input types, and stable validation errors.

```powershell
git add modules/request_validation.py app.py tests/test_api_validation.py README.md
git commit -m "fix: validate API request schemas"
```

### Task 4: Partial processing status and stale-view cleanup

**Files:**
- Create: `tests/test_processing_status.py`
- Create: `tests/e2e/partial-status.spec.js`
- Modify: `app.py`
- Modify: `templates/index.html`
- Modify: `static/js/main.js`
- Modify: `static/css/style.css`
- Modify: `README.md`

- [ ] **Step 1: Add failing backend partial-status test**

```python
import app as app_module


def test_process_reports_3d_failure_as_partial(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "smart_parse",
        lambda value, input_type="auto": {
            "success": True,
            "status": "resolved",
            "smiles": "CCO",
            "source": "SMILES",
            "input_type": "smiles",
        },
    )
    monkeypatch.setattr(app_module, "render_2d_image", lambda value: (b"png", None))
    monkeypatch.setattr(
        app_module,
        "generate_3d_conformer",
        lambda value: (None, "3D 构象生成失败"),
    )

    response = app_module.app.test_client().post(
        "/api/process",
        json={"input": "CCO", "input_type": "smiles"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "partial"
    assert payload["stages"]["render_3d"]["success"] is False
    assert payload["pdb_data"] is None
```

- [ ] **Step 2: Run RED backend test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_processing_status.py -q
```

Expected: response says success without stage information.

- [ ] **Step 3: Implement stage objects**

Add a helper in `app.py`:

```python
def _stage(success: bool, error: str | None = None) -> dict:
    return {"success": success, "error": error}
```

Build `stages` for parse, 2D, 3D, molecule info, and validation. Set overall status to `resolved` when all succeed and `partial` when at least one optional stage fails.

- [ ] **Step 4: Add failing stale-view Playwright test**

Intercept two `/api/process` responses. The first contains PDB data; the second contains `status="partial"`, no PDB, and a 3D error. Assert that after the second request `#viewer-3d` no longer contains the first model and `#render-3d-status` displays the failure.

- [ ] **Step 5: Run RED e2e test**

```powershell
pnpm exec playwright test tests/e2e/partial-status.spec.js
```

Expected: stale viewer remains because `renderResults` skips 3D updates when `pdb_data` is absent.

- [ ] **Step 6: Implement frontend state reset and stage rendering**

Add `clearRenderedState()` that clears molecule info, validation, 2D area, 3D viewer, export output, and stage messages before every request. Render explicit failure messages from `data.stages`.

- [ ] **Step 7: Run GREEN tests and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_processing_status.py -q
pnpm exec playwright test tests/e2e/partial-status.spec.js
.\.venv\Scripts\python.exe -m pytest -q
git add app.py templates/index.html static/js/main.js static/css/style.css tests README.md
git commit -m "fix: expose partial processing failures"
```

### Task 5: Atom indices and valid exports

**Files:**
- Create: `tests/test_structure_outputs.py`
- Modify: `modules/structure_processor.py`
- Modify: `app.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing output tests**

```python
from modules.structure_processor import export_molecule, render_2d_image


def test_png_atom_indices_change_output():
    plain, plain_error = render_2d_image("CCO", format="PNG", show_atom_indices=False)
    indexed, indexed_error = render_2d_image("CCO", format="PNG", show_atom_indices=True)
    assert plain_error is None
    assert indexed_error is None
    assert plain != indexed


def test_sdf_has_record_separator():
    data, error = export_molecule("CCO", format="SDF")
    assert error is None
    assert data.rstrip().endswith("$$$$")


def test_unknown_2d_format_is_rejected():
    data, error = render_2d_image("CCO", format="WEBP")
    assert data is None
    assert "不支持" in error
```

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_structure_outputs.py -q
```

Expected: PNG bytes are identical, SDF lacks `$$$$`, and WEBP silently returns PNG.

- [ ] **Step 3: Implement strict drawing and serialization**

Use `rdMolDraw2D.MolDraw2DCairo` for indexed PNG and `MolDraw2DSVG` for SVG, applying `drawOptions().addAtomIndices` in both branches. Reject formats outside `{"PNG", "SVG"}`.

Return `Chem.MolToMolBlock(mol) + "$$$$\n"` for SDF. Assign `conf_ids = AllChem.EmbedMultipleConfs(...)` in the ETKDGv2 fallback and check PDB embedding success before serialization.

- [ ] **Step 4: Run GREEN and regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_structure_outputs.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 5: Update export documentation and commit**

```powershell
git add modules/structure_processor.py app.py tests/test_structure_outputs.py README.md
git commit -m "fix: support atom indices and valid exports"
```

### Task 6: Secure image upload lifecycle

**Files:**
- Create: `tests/test_image_upload_security.py`
- Modify: `config.py`
- Modify: `modules/image_parser.py`
- Modify: `app.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing malicious and legitimate upload tests**

```python
import io
from pathlib import Path
from PIL import Image
import app as app_module


def png_bytes(size=(32, 32)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def test_disguised_non_image_is_rejected(tmp_path, monkeypatch):
    app_module.app.config["UPLOAD_FOLDER"] = str(tmp_path)
    response = app_module.app.test_client().post(
        "/api/parse-image",
        data={"image": (io.BytesIO(b"not an image"), "fake.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_uploaded_files_are_removed_after_success(tmp_path, monkeypatch):
    app_module.app.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        app_module,
        "smart_parse_image",
        lambda path: {"success": True, "smiles": "CCO", "source": "DECIMER"},
    )
    response = app_module.app.test_client().post(
        "/api/parse-image",
        data={"image": (png_bytes(), "ethanol.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
```

Add an oversized-dimension test by monkeypatching `MAX_IMAGE_PIXELS` to a small value and posting a larger legitimate PNG.

- [ ] **Step 2: Run RED security tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_image_upload_security.py -q
```

Expected: disguised files are persisted until DECIMER failure and successful uploads remain on disk.

- [ ] **Step 3: Implement the narrow upload boundary**

Add `MAX_IMAGE_PIXELS` to config. Replace extension-only saving with:

```python
def save_verified_image(file_data, filename: str, upload_folder: str) -> str:
    if not _allowed_image(filename):
        raise ImageValidationError("不支持的图片格式")
    with Image.open(file_data.stream) as image:
        image.verify()
    file_data.stream.seek(0)
    with Image.open(file_data.stream) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ImageValidationError("图片像素尺寸过大")
        frame = image.convert("RGB")
        output = os.path.join(upload_folder, f"{uuid.uuid4().hex}.png")
        frame.save(output, "PNG")
    return output
```

Treat Pillow decompression-bomb warnings as errors. In `api_parse_image`, delete the normalized upload in `finally`. In `parse_image_decimer`, delete `_processed.png` in `finally`.

- [ ] **Step 4: Run security closure and legitimate-control tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_image_upload_security.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: malicious inputs never reach inference, supported PNG reaches the stub inference, and the directory is empty after success and failure.

- [ ] **Step 5: Update upload documentation and commit**

```powershell
git add config.py modules/image_parser.py app.py tests/test_image_upload_security.py README.md
git commit -m "security: harden image upload lifecycle"
```

### Task 7: Remove Img2Mol fallback

**Files:**
- Create: `tests/test_image_engine.py`
- Modify: `modules/image_parser.py`
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] **Step 1: Add failing DECIMER-only engine test**

```python
from modules import image_parser


def test_image_failure_does_not_advertise_img2mol(monkeypatch, tmp_path):
    image_path = tmp_path / "structure.png"
    image_path.write_bytes(b"fixture")
    monkeypatch.setattr(
        image_parser,
        "parse_image_decimer",
        lambda path: {"smiles": None, "source": "DECIMER", "error": "unavailable"},
    )

    result = image_parser.smart_parse_image(str(image_path))

    assert result["success"] is False
    assert "Img2Mol" not in result["error"]
    assert not hasattr(image_parser, "parse_image_img2mol")
```

- [ ] **Step 2: Run RED test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_image_engine.py -q
```

Expected: response advertises Img2Mol and the fallback function exists.

- [ ] **Step 3: Remove fallback code and claims**

Delete Img2Mol paths, imports, parser function, model guidance, requirements comments, README architecture entries, and license attribution that is no longer relevant to distributed code.

- [ ] **Step 4: Run GREEN and regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_image_engine.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 5: Commit**

```powershell
git add modules/image_parser.py requirements.txt tests/test_image_engine.py README.md
git commit -m "refactor: remove unavailable Img2Mol fallback"
```

### Task 8: Honor debug configuration and document deployment

**Files:**
- Create: `tests/test_app_runner.py`
- Modify: `app.py`
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] **Step 1: Add failing runner test**

```python
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
    assert observed["host"] == "0.0.0.0"
    assert observed["port"] == 5000
```

- [ ] **Step 2: Run RED test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app_runner.py -q
```

Expected: `run` does not exist and the main block hardcodes `debug=False`.

- [ ] **Step 3: Implement testable runner and deployment dependency**

```python
def run() -> None:
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)


if __name__ == "__main__":
    run()
```

Add a bounded Waitress dependency and document:

```powershell
waitress-serve --host=127.0.0.1 --port=5000 app:app
```

State explicitly that `python app.py` is development-only.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app_runner.py -q
.\.venv\Scripts\python.exe -m pytest -q
git add app.py requirements.txt tests/test_app_runner.py README.md
git commit -m "fix: honor debug configuration and document deployment"
```

### Task 9: Reproducible development and final QA

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add dependency compatibility bounds**

Use bounded major ranges for direct dependencies, preserving the versions proven by the test environment:

```text
flask>=3.0,<4
rdkit>=2024.03,<2027
requests>=2.31,<3
Pillow>=10,<13
opencv-python>=4.8,<5
numpy>=2.0,<3
decimer>=2.8,<3
waitress>=3,<4
```

Use:

```text
pytest>=8,<9
```

in `requirements-dev.txt` and document pnpm/Playwright setup separately.

- [ ] **Step 2: Validate fresh dependency metadata and repository checks**

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py config.py modules tests
node --check static\js\main.js
pnpm exec playwright test
git diff --check
```

- [ ] **Step 3: Run rendered desktop and mobile QA**

Run Playwright at 1280x800 and 390x844. Verify page title, nonblank content, no framework overlay, console health, ambiguity selection, stale-state cleanup, atom-index toggle, and image validation error presentation. Save screenshots outside the repository.

- [ ] **Step 4: Update setup/test documentation and commit**

Document environment creation, runtime installation, test installation, Python tests, browser tests, DECIMER model behavior, and production serving.

```powershell
git add requirements.txt requirements-dev.txt README.md .gitignore
git commit -m "chore: make development and tests reproducible"
```

### Task 10: Final security and change-chain verification

**Files:**
- No production changes expected.

- [ ] **Step 1: Inspect scope and commit boundaries**

```powershell
git status --short
git log --oneline dev-v1..HEAD
git diff --stat dev-v1...HEAD
```

Confirm each feature has one coherent commit and the worktree is clean.

- [ ] **Step 2: Run ordered security verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_image_upload_security.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_api_validation.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Reconfirm disguised files and oversized dimensions do not reach inference, while a legitimate PNG does.

- [ ] **Step 3: Run full frontend QA**

```powershell
pnpm exec playwright test
```

Capture final desktop and mobile screenshots outside the repository and record console warnings/errors.

- [ ] **Step 4: Fast-forward local dev-v1**

After all checks pass, remove the temporary worktree, fast-forward `dev-v1` to `codex/refactor-chem-structure`, and delete the temporary branch. Do not push.

```powershell
git merge --ff-only codex/refactor-chem-structure
```
