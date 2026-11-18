"""Publish verifiable model metadata and benchmark provenance."""
from fastapi import APIRouter, Request

from backend.schemas import ModelInfo
from backend.vendor.pathsnap_features18 import FEATURES

router = APIRouter(tags=["model"])


@router.get("/model", response_model=ModelInfo)
def model_info(request: Request):
    model = request.app.state.model
    return dict(algorithm=model.metrics["decoder_type"], features=FEATURES,
                schema_version=model.protocol["schema_version"], decoder=model.decoder,
                benchmark={key: model.metrics[key] for key in ("test_top1_accuracy",
                           "correct_observations", "total_observations", "labels")},
                evaluation_definitions=model.definitions)
