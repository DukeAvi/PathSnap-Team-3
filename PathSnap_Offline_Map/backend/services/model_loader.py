"""Load and validate the trusted frozen artifacts once per app process."""
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from backend.vendor.pathsnap_features18 import FEATURES

MODEL_FILES = (
    "selected18_xgboost_model.ubj", "selected18_scaler.joblib",
    "selected18_model_config.json", "decoder_config.json",
    "shared_protocol.json", "feature_schema_18.csv", "evaluation_definitions.json",
)
DECODER_GAP_S = 30.0


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class FrozenModel:
    classifier: XGBClassifier
    scaler: object
    decoder: dict
    protocol: dict
    definitions: dict
    metrics: dict

    @classmethod
    def load(cls, artifacts: Path):
        model = artifacts / "model"
        provenance = artifacts / "provenance"
        manifest = read_json(provenance / "SHA256SUMS.json")
        for name in MODEL_FILES:
            with (model / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != manifest.get(f"results/{name}"):
                    raise ValueError(f"Frozen model checksum mismatch: {name}")
        config = read_json(model / "selected18_model_config.json")
        protocol = read_json(model / "shared_protocol.json")
        with (model / "feature_schema_18.csv").open(encoding="utf-8", newline="") as source:
            schema = [row["name"] for row in csv.DictReader(source)]
        if any(order != FEATURES for order in (config["features"], protocol["features"], schema)):
            raise ValueError("Frozen 18-feature order mismatch")
        decoder = read_json(model / "decoder_config.json")
        if decoder["max_gap_s"] != DECODER_GAP_S:
            raise ValueError("Decoder max_gap_s must match the compiled 30-second rule")
        for key in ("beta_m", "beta_displacement", "max_speed_mps", "slack_m", "jitter_m", "search_limit_m"):
            if not np.isfinite(decoder[key]) or decoder[key] <= 0:
                raise ValueError(f"Invalid frozen decoder parameter: {key}")
        scaler = joblib.load(model / "selected18_scaler.joblib")
        classifier = XGBClassifier()
        classifier.load_model(model / "selected18_xgboost_model.ubj")
        classifier.set_params(n_jobs=config["parameters"]["n_jobs"], device="cpu")
        if (scaler.n_features_in_ != len(FEATURES)
                or list(scaler.feature_names_in_) != FEATURES
                or classifier.n_features_in_ != len(FEATURES)
                or list(classifier.classes_) != [0, 1] or protocol["positive_class"] != 1):
            raise ValueError("Scaler or classifier differs from the frozen input contract")
        return cls(classifier, scaler, decoder, protocol,
                   read_json(model / "evaluation_definitions.json"),
                   read_json(provenance / "metrics.json"))

    def probabilities(self, features: pd.DataFrame):
        if list(features.columns) != FEATURES or not np.isfinite(features.to_numpy()).all():
            raise ValueError("Expected the 18 finite predictors in frozen order")
        if not len(features):
            return np.empty(0, dtype=np.float32)
        scaled = self.scaler.transform(features)
        return self.classifier.predict_proba(scaled)[:, 1]
