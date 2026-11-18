import json
import shutil

import pandas as pd
import pytest

from backend.services.demo import validate_frozen_files
from backend.services.model_loader import FrozenModel
from backend.settings import ROOT
from backend.vendor.pathsnap_features18 import FEATURES
from scripts.import_bundle import MODEL, PROVENANCE, VENDOR, digest


def test_frozen_assets_and_vendor_are_byte_identical(frozen_model):
    manifest = json.loads((ROOT / "artifacts/provenance/SHA256SUMS.json").read_text())
    paths = ([(ROOT / "artifacts/model" / name, f"results/{name}") for name in MODEL]
             + [(ROOT / "artifacts/provenance" / name, f"results/{name}") for name in PROVENANCE]
             + [(ROOT / "backend/vendor" / name, f"src/{name}") for name in VENDOR])
    for path, original in paths:
        assert digest(path) == manifest[original]
    validate_frozen_files(ROOT / "data/demo", manifest)
    assert frozen_model.decoder["max_gap_s"] == 30
    assert list(frozen_model.scaler.feature_names_in_) == FEATURES


def test_artifact_integrity_and_feature_order(tmp_path, frozen_model):
    shutil.copytree(ROOT / "artifacts", tmp_path / "artifacts")
    path = tmp_path / "artifacts/model/decoder_config.json"
    config = json.loads(path.read_text())
    path.write_text(json.dumps({**config, "max_gap_s": 31}))
    with pytest.raises(ValueError, match="checksum"):
        FrozenModel.load(tmp_path / "artifacts")
    manifest_path = tmp_path / "artifacts/provenance/SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["results/decoder_config.json"] = digest(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="30-second rule"):
        FrozenModel.load(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="frozen order"):
        frozen_model.probabilities(pd.DataFrame([[0.] * 18], columns=FEATURES[::-1]))
