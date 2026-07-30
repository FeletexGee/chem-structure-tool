# ChemStructure Reliability Refactor Design

**Date:** 2026-07-17
**Target branch:** `dev-v1`
**Implementation branch:** `codex/refactor-chem-structure`

## Context

ChemStructure Tool is a Flask application that accepts chemical names,
molecular formulae, SMILES, and structure images, then produces normalized
SMILES, molecular properties, 2D depictions, and 3D conformers. The current
implementation works as a prototype but silently guesses when an input has
multiple chemically reasonable interpretations, hides partial rendering
failures, accepts weakly validated uploads, and has no automated regression
suite.

This refactor keeps the existing Flask and vanilla JavaScript architecture.
It improves correctness and reliability incrementally so that every
user-visible behavior can be tested and reverted independently.

## Goals

1. Never silently choose a chemical identity when the input is ambiguous.
2. Require an explicit user choice before accepting an uncertain formula,
   nomenclature interpretation, or stereochemistry downgrade.
3. Return accurate per-stage processing status and never display stale output.
4. Validate API requests and uploaded images at their trust boundaries.
5. Produce standards-compliant exports and consistent 2D rendering options.
6. Remove the unavailable Img2Mol fallback and document DECIMER accurately.
7. Make development, testing, and deployment instructions reproducible.
8. Add focused regression coverage before each production change.

## Non-goals

- Replacing Flask or the vanilla JavaScript frontend.
- Introducing authentication, accounts, persistence, or a job queue.
- Guaranteeing that external services such as PubChem, OPSIN, or DeepSeek are
  available.
- Automatically selecting a preferred isomer from a molecular formula.
- Retaining compatibility with the local Img2Mol/TensorFlow 1.x fallback.

## Architecture

The existing modules remain in place, with small helpers added around their
current responsibilities:

- `modules/text_parser.py` owns input classification, explicit parsing modes,
  ambiguity candidates, and external name/formula resolution.
- `modules/structure_processor.py` owns RDKit validation, rendering, conformer
  generation, and export serialization.
- `modules/image_parser.py` owns image validation, safe normalization, DECIMER
  inference, and temporary-file cleanup support.
- `app.py` owns request-schema validation and maps domain results to HTTP
  responses.
- `static/js/main.js` owns candidate selection and rendered-state lifecycle.
- `templates/index.html` provides the ambiguity-candidate UI container.

No broad service-layer rewrite is required. Helpers are introduced only where
they create a testable boundary or remove duplicated validation.

## Explicit Input Modes

Text-processing requests accept an optional `input_type`:

```json
{
  "input": "CO",
  "input_type": "auto"
}
```

Allowed values are:

- `auto`
- `smiles`
- `formula`
- `name`

`auto` classifies the input without choosing between conflicting valid
interpretations. An explicit type bypasses classification and invokes only the
selected parser.

## Result Contract

### Resolved result

```json
{
  "success": true,
  "status": "resolved",
  "smiles": "CO",
  "source": "SMILES",
  "input_type": "smiles"
}
```

### Ambiguous result

```json
{
  "success": false,
  "status": "ambiguous",
  "requires_selection": true,
  "reason": "输入既可以解释为 SMILES，也可以解释为分子式",
  "candidates": [
    {
      "id": "smiles:CO",
      "label": "按 SMILES 解释",
      "input": "CO",
      "input_type": "smiles",
      "smiles": "CO",
      "formula": "CH4O",
      "note": "RDKit 将该 SMILES 解释为甲醇"
    },
    {
      "id": "formula:CO",
      "label": "按分子式解释",
      "input": "CO",
      "input_type": "formula",
      "note": "该分子式可能对应多个结构，选择后查询候选"
    }
  ]
}
```

Ambiguity responses use HTTP 409. API errors retain their structured JSON
payload so the frontend can render candidates instead of reducing the response
to a generic error string.

## Ambiguity Rules

### Formula versus SMILES

If an input is syntactically valid both as SMILES and as a molecular formula,
`auto` returns both interpretations. Examples include `CO`, `NO`, and `CN`.
The application does not decide which interpretation the user intended.

### Formula with multiple compounds

Formula parsing requests multiple PubChem candidates rather than taking the
first CID as the most common compound. Candidate responses include CID,
available compound title, canonical SMILES, molecular formula, and source.
The user selects a specific candidate before structure generation.

If PubChem is unavailable, the response distinguishes service failure from an
unrecognized formula. It does not invoke the LLM to invent a preferred
compound.

### OPSIN warnings

An OPSIN `WARNING` result is treated as an interpretation candidate, not an
automatically resolved structure. The OPSIN message and proposed SMILES are
shown to the user for explicit confirmation.

### Incomplete alkene names

The DeepSeek prompt no longer claims that a missing double-bond locant defaults
to position 1. Incomplete names return `UNKNOWN` or remain unresolved unless a
deterministic service provides a candidate that the user explicitly confirms.

### Stereochemistry downgrade

The parser never silently strips E/Z, R/S, cis/trans, syn/anti, or related
stereochemical descriptors. If the original name fails but a stripped name
parses, the stripped structure may be returned only as a candidate labelled
"忽略立体化学信息". Selecting it is an explicit user action.

## Processing-Stage Status

`/api/process` returns status for each stage:

```json
{
  "success": true,
  "status": "partial",
  "smiles": "...",
  "stages": {
    "parse": {"success": true, "error": null},
    "render_2d": {"success": true, "error": null},
    "render_3d": {"success": false, "error": "3D 构象生成失败"},
    "molecule_info": {"success": true, "error": null},
    "validation": {"success": true, "error": null}
  }
}
```

Parsing failure fails the whole request. A 2D or 3D failure produces a partial
result when other useful output exists. The frontend clears every previous
result before starting a request and renders an explicit unavailable state for
each failed stage.

## API Validation

All JSON endpoints validate:

- request body is a JSON object;
- required values are strings, not null, arrays, booleans, or numbers;
- strings are non-empty after trimming;
- text and SMILES inputs are bounded in length;
- format values belong to a documented allow-list;
- boolean options are actual booleans;
- `input_type` belongs to the explicit input-mode allow-list.

Validation failures return HTTP 400 with a stable error object. Internal
exceptions are logged server-side and are not returned with local paths or
trace details.

## Rendering and Export

- PNG and SVG both honor `show_indices`.
- Unsupported 2D formats return an error instead of silently producing PNG.
- SDF export includes a valid record terminator (`$$$$`).
- PDB export checks conformer generation before serialization.
- The ETKDGv2 fallback stores and evaluates the conformer IDs returned by the
  fallback call rather than reusing the failed ETKDGv3 result.

## Image Upload Security Contract

The attacker-controlled source is the multipart upload. The inference sink is
Pillow/OpenCV/DECIMER processing. The invariant is: only a decodable image with
an allowed format, bounded byte size, and bounded decoded pixel count reaches
inference, and all request-owned temporary files are deleted after processing.

The upload pipeline is:

```text
multipart upload
  -> request byte limit
  -> extension allow-list
  -> Pillow format verification
  -> decoded pixel-count limit
  -> safe RGB re-encoding to a generated PNG
  -> DECIMER inference
  -> finally delete normalized and intermediate files
```

Animated images use the first verified frame. Image metadata is discarded by
re-encoding. Decompression-bomb warnings are treated as validation failures.
Expected validation errors return a generic client message; detailed decoder
exceptions remain in server logs.

## Img2Mol Removal

The Img2Mol fallback, model-path checks, error messages, imports, and README
claims are removed. DECIMER is the only supported OCSR engine. If DECIMER is not
installed or inference fails, the API reports image recognition as unavailable
without suggesting an unsupported fallback.

## Frontend Candidate Flow

The frontend adds an ambiguity panel inside the input card. It displays:

- the reason the input is ambiguous;
- one button/card per candidate;
- source, formula, CID, and explanatory note when available;
- a cancel action that returns focus to the text input.

Selecting a candidate sends the candidate input with its explicit `input_type`.
During a new request the frontend clears molecule information, validation,
2D content, 3D viewer state, export output, and previous ambiguity state.

The target browser flow is:

```text
app loads
  -> user enters CO
  -> candidate panel appears
  -> user selects SMILES or formula interpretation
  -> selected interpretation is processed
  -> old rendered state is absent
  -> new result or explicit partial-failure state appears
```

## Configuration and Deployment

- `FLASK_DEBUG` controls the debug flag used by `app.run` for local development.
- The README states that Flask's built-in server is development-only.
- Windows production deployment documentation uses Waitress as the primary
  example.
- Secrets continue to come from environment variables; the development secret
  fallback is documented as unsuitable for public deployment.

## Dependency and Test Reproducibility

- Runtime dependencies remain in `requirements.txt` with compatible bounded
  ranges where repository evidence supports them.
- Test-only dependencies are placed in `requirements-dev.txt`.
- The README documents the exact commands to create an environment, install
  runtime and test dependencies, run focused tests, and run the full suite.
- Tests do not require live DeepSeek, OPSIN, or PubChem access. External HTTP
  boundaries use deterministic fixtures while pure classification and RDKit
  behavior use real implementations.

## Test Strategy

Every behavior change follows red-green-refactor:

1. Add a focused regression test and observe the expected failure.
2. Implement the smallest production change that makes it pass.
3. Run the focused test.
4. Run the full Python suite and JavaScript syntax checks.
5. For frontend changes, run the app and validate the target flow with
   Playwright because the Browser plugin is not available in this session.
6. Update README/API documentation in the same feature commit.
7. Inspect the staged diff and create one commit for the feature.

Security tests cover both malicious and legitimate inputs through the same
upload boundary: disguised non-images, oversized dimensions, supported images,
cleanup after success, and cleanup after inference failure.

## Commit Boundaries

Implementation is split into the following independently revertible commits:

1. `feat: add explicit ambiguity resolution`
2. `fix: require confirmation for uncertain nomenclature`
3. `fix: validate API request schemas`
4. `fix: expose partial processing failures`
5. `fix: support atom indices and valid exports`
6. `security: harden image upload lifecycle`
7. `refactor: remove unavailable Img2Mol fallback`
8. `fix: honor debug configuration and document deployment`
9. `chore: make development and tests reproducible`

Tests and documentation for a behavior are committed with that behavior. The
design and implementation-plan documents are separate preparatory commits.

## Documentation

README sections for features, architecture, setup, API endpoints, image
recognition, ambiguity handling, export formats, testing, and deployment are
updated alongside the responsible code changes. Documentation must not claim
that a molecular formula maps uniquely to a structure, that incomplete alkene
names default to position 1, that Img2Mol is bundled, or that Flask's built-in
server is production-ready.

## Completion Criteria

- All focused and full regression tests pass.
- Python modules compile in the supported test environment.
- JavaScript syntax checks pass.
- The ambiguity flow is exercised through the rendered frontend.
- Image-upload exploit reproductions no longer reach inference.
- Legitimate supported image uploads still reach DECIMER.
- Every implementation commit contains one coherent behavior change with its
  tests and documentation.
- The final commit chain is fast-forwarded to local `dev-v1` without pushing.
