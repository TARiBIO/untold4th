import json
import os
from typing import Optional

SIZE_CHART = os.path.join(os.path.dirname(__file__), "sizeChart.json")
PHOTO_WIDTH_TO_CM_MULTIPLIER = 2.6  # Empirical ratio to move from pit-to-pit width to circumference


def load_size_chart():
    if not os.path.exists(SIZE_CHART):
        raise FileNotFoundError(f"sizeChart.json not found at {SIZE_CHART}")
    with open(SIZE_CHART, "r") as f:
        return json.load(f)


def _resolve_height_cm(measurements: dict, user_height_cm: Optional[int]) -> Optional[float]:
    if user_height_cm:
        return float(user_height_cm)
    if measurements.get("height_cm"):
        return float(measurements["height_cm"])
    return None


def _normalize_chest_cm(measurements: dict, user_height_cm: Optional[int]) -> Optional[float]:
    """
    Measurements coming solely from the photo represent pit-to-pit width.
    Convert that into an approximate circumference so we can compare to the size chart ranges.
    """
    chest_cm = measurements.get("chest_cm")
    if chest_cm:
        chest_cm = float(chest_cm)
        if chest_cm < 70:  # widths from photo are <70cm; metrics-based values already in circumference
            return chest_cm * PHOTO_WIDTH_TO_CM_MULTIPLIER
        return chest_cm

    chest_px = measurements.get("chest_width_px")
    if chest_px is None:
        return None

    chest_px = float(chest_px)
    height_px = measurements.get("height_px")
    height_cm = _resolve_height_cm(measurements, user_height_cm)

    if height_cm and height_px:
        try:
            scale = float(height_cm) / float(height_px)
            chest_cm = chest_px * scale
        except (TypeError, ZeroDivisionError):
            chest_cm = chest_px
    else:
        chest_cm = chest_px

    if chest_cm < 70:
        chest_cm *= PHOTO_WIDTH_TO_CM_MULTIPLIER
    return chest_cm


def recommend_size(measurements, brand_id=None, user_height_cm=None):
    chart = load_size_chart()
    chest_cm = _normalize_chest_cm(measurements, user_height_cm)

    if chest_cm is None:
        return {"size": None, "diff": None}

    best = None
    best_diff = float("inf")

    for size_label, size_data in chart.items():
        target_range = size_data["chest"]
        mid = sum(target_range) / 2

        diff = abs(chest_cm - mid)
        if diff < best_diff:
            best_diff = diff
            best = size_label

    return {"size": best, "diff": best_diff}
