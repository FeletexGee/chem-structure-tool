import io
import sys
from types import SimpleNamespace

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

import app as app_module
from modules import image_parser


def png_bytes(size=(32, 32)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def configure_upload_folder(tmp_path, monkeypatch):
    app_module.app.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(image_parser, "UPLOAD_FOLDER", str(tmp_path))


def test_disguised_non_image_is_rejected_before_inference(tmp_path, monkeypatch):
    configure_upload_folder(tmp_path, monkeypatch)

    def inference_must_not_run(path):
        raise AssertionError("inference reached")

    monkeypatch.setattr(app_module, "smart_parse_image", inference_must_not_run)

    response = app_module.app.test_client().post(
        "/api/parse-image",
        data={"image": (io.BytesIO(b"not an image"), "fake.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_image"
    assert list(tmp_path.iterdir()) == []


def test_oversized_decoded_dimensions_are_rejected(tmp_path, monkeypatch):
    configure_upload_folder(tmp_path, monkeypatch)
    monkeypatch.setattr(image_parser, "MAX_IMAGE_PIXELS", 100)

    def inference_must_not_run(path):
        raise AssertionError("inference reached")

    monkeypatch.setattr(app_module, "smart_parse_image", inference_must_not_run)

    response = app_module.app.test_client().post(
        "/api/parse-image",
        data={"image": (png_bytes((20, 20)), "large.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "像素" in response.get_json()["error"]
    assert list(tmp_path.iterdir()) == []


def test_uploaded_files_are_removed_after_success(tmp_path, monkeypatch):
    configure_upload_folder(tmp_path, monkeypatch)
    observed_paths = []

    def successful_inference(path):
        observed_paths.append(path)
        assert Image.open(path).format == "PNG"
        return {"success": True, "smiles": "CCO", "source": "DECIMER"}

    monkeypatch.setattr(app_module, "smart_parse_image", successful_inference)

    response = app_module.app.test_client().post(
        "/api/parse-image",
        data={"image": (png_bytes(), "ethanol.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert observed_paths
    assert list(tmp_path.iterdir()) == []


def test_uploaded_files_are_removed_after_inference_failure(tmp_path, monkeypatch):
    configure_upload_folder(tmp_path, monkeypatch)
    monkeypatch.setattr(
        app_module,
        "smart_parse_image",
        lambda path: {
            "success": False,
            "smiles": None,
            "source": None,
            "error": "DECIMER unavailable",
        },
    )

    response = app_module.app.test_client().post(
        "/api/parse-image",
        data={"image": (png_bytes(), "structure.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is False
    assert list(tmp_path.iterdir()) == []


def test_decimer_intermediate_is_removed_after_inference_exception(tmp_path, monkeypatch):
    original = tmp_path / "original.png"
    processed = tmp_path / "processed.png"
    original.write_bytes(b"original")
    processed.write_bytes(b"processed")

    monkeypatch.setattr(
        image_parser,
        "_preprocess_image",
        lambda path: str(processed),
    )
    monkeypatch.setitem(
        sys.modules,
        "DECIMER",
        SimpleNamespace(
            predict_SMILES=lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("inference failed")
            )
        ),
    )

    result = image_parser.parse_image_decimer(str(original))

    assert result["smiles"] is None
    assert not processed.exists()


def test_partial_preprocessed_file_is_removed_when_save_fails(tmp_path, monkeypatch):
    original = tmp_path / "original.png"
    Image.new("RGB", (32, 32), "white").save(original, format="PNG")
    processed = tmp_path / "original_processed.png"

    def failing_save(image, path, format=None, **kwargs):
        with open(path, "wb") as partial:
            partial.write(b"partial")
        raise OSError("disk write failed")

    monkeypatch.setattr(Image.Image, "save", failing_save)

    with pytest.raises(OSError, match="disk write failed"):
        image_parser._preprocess_image(str(original), clean_lines=False)

    assert not processed.exists()


def test_partial_normalized_file_is_removed_when_reencoding_fails(tmp_path, monkeypatch):
    upload = FileStorage(stream=png_bytes(), filename="structure.png")

    def failing_save(image, path, format=None, **kwargs):
        with open(path, "wb") as partial:
            partial.write(b"partial")
        raise OSError("disk write failed")

    monkeypatch.setattr(Image.Image, "save", failing_save)

    with pytest.raises(image_parser.ImageValidationError):
        image_parser.save_verified_image(
            upload,
            upload.filename,
            upload_folder=str(tmp_path),
        )

    assert list(tmp_path.iterdir()) == []


def test_pixel_limit_is_checked_before_decoder_verification(tmp_path, monkeypatch):
    upload = FileStorage(stream=io.BytesIO(b"encoded"), filename="structure.png")
    monkeypatch.setattr(image_parser, "MAX_IMAGE_PIXELS", 100)

    class OversizedImage:
        format = "PNG"
        width = 20
        height = 20

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def verify(self):
            raise AssertionError("decoder verification should not run")

    monkeypatch.setattr(Image, "open", lambda stream: OversizedImage())

    with pytest.raises(image_parser.ImageValidationError, match="像素"):
        image_parser.save_verified_image(
            upload,
            upload.filename,
            upload_folder=str(tmp_path),
        )


def test_decimer_error_does_not_expose_local_paths(tmp_path, monkeypatch):
    original = tmp_path / "private-structure.png"
    processed = tmp_path / "processed.png"
    original.write_bytes(b"original")
    processed.write_bytes(b"processed")

    monkeypatch.setattr(image_parser, "_preprocess_image", lambda path: str(processed))
    monkeypatch.setitem(
        sys.modules,
        "DECIMER",
        SimpleNamespace(
            predict_SMILES=lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError(f"failed while reading {original}")
            )
        ),
    )

    result = image_parser.parse_image_decimer(str(original))

    assert str(original) not in result["error"]
    assert result["error"] == "DECIMER 推理失败"
