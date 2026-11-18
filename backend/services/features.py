"""Apply the exported label-free feature augmentation."""
import numpy as np

from backend.services.input_loader import InputError
from backend.vendor.pathsnap_features18 import FEATURES, augment_trip


def augment(candidates, observations, nodes, arcs):
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        try:
            features = augment_trip(candidates, observations, nodes, arcs)
        except ValueError as error:
            raise InputError(f"Cannot derive model features: {error}") from error
    result = candidates.copy()
    result[FEATURES] = features
    return result
