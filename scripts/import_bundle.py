"""Import a trusted, frozen export after checking every manifest digest."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from shutil import copyfileobj
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "PathSnap_HMM_Trained/"
MODEL = (
    "selected18_xgboost_model.ubj", "selected18_scaler.joblib",
    "selected18_model_config.json", "decoder_config.json", "shared_protocol.json",
    "feature_schema_18.csv", "evaluation_definitions.json",
)
PROVENANCE = ("metrics.json", "final_comparison.csv", "frozen_selection.json")
VENDOR = ("fast_decoder.py", "pathsnap_features18.py", "pathsnap_xgb_hmm18.py")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def import_bundle(archive, root=ROOT):
    with ZipFile(archive) as bundle:
        entries = [item for item in bundle.infolist() if not item.is_dir()]
        names = {item.filename for item in entries}
        if len(names) != len(entries) or sum(item.file_size for item in entries) > 512 * 1024**2:
            raise ValueError("Duplicate members or oversized bundle")
        if any(not n.startswith(PREFIX) or ".." in PurePosixPath(n).parts or "\\" in n for n in names):
            raise ValueError("Unexpected bundle root or unsafe member path")
        manifest_name = PREFIX + "SHA256SUMS.json"
        manifest = json.loads(bundle.read(manifest_name))
        if names != {PREFIX + path for path in manifest} | {manifest_name}:
            raise ValueError("Bundle files differ from SHA256SUMS.json")
        for path, expected in manifest.items():
            with bundle.open(PREFIX + path) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(f"Checksum mismatch: {path}")
        mappings = {
            **{f"results/{name}": f"artifacts/model/{name}" for name in MODEL},
            **{f"results/{name}": f"artifacts/provenance/{name}" for name in PROVENANCE},
            **{f"src/{name}": f"backend/vendor/{name}" for name in VENDOR},
            "SHA256SUMS.json": "artifacts/provenance/SHA256SUMS.json",
            "results/hmm_student_observation_predictions.csv.gz":
                "data/demo/frozen/hmm_student_observation_predictions.csv.gz",
            "results/selected_student_candidate_probabilities.npy":
                "data/demo/frozen/selected_student_candidate_probabilities.npy",
        }
        mappings.update({p: p.replace("test_inputs/", "data/demo/frozen/", 1)
                         for p in manifest if p.startswith("test_inputs/")})
        missing = set(mappings) - set(manifest) - {"SHA256SUMS.json"}
        if missing:
            raise ValueError(f"Required frozen files are missing: {sorted(missing)}")
        for source, relative in mappings.items():
            dest = root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(PREFIX + source) as stream, dest.open("wb") as out:
                copyfileobj(stream, out)
    print(f"Verified {len(manifest)} bundle files and imported {len(mappings)} runtime files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Trusted PathSnap_HMM_Trained.zip")
    args = parser.parse_args()
    import_bundle(args.archive)
