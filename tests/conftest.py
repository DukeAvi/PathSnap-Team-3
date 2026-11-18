import pytest

from backend.services.model_loader import FrozenModel
from backend.settings import ROOT


@pytest.fixture(scope="session")
def frozen_model():
    return FrozenModel.load(ROOT / "artifacts")
