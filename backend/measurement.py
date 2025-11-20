import os
import math
import cv2
import numpy as np

DEFAULT_EST_HEIGHT_CM = 170.0
DEFAULT_SHOULDER_TO_HEIGHT_RATIO = 0.25  # Average human shoulder width ≈ 25% of height
PHOTO_WIDTH_TO_CM_MULTIPLIER = 2.6
EXPECTED_HEIGHT_TO_SHOULDER_RATIO = 3.2  # Typical human height is ~3.2x shoulder width
RELIABLE_HEIGHT_PX = 350.0  # Below this, assume the photo is cropped and height-based scaling is noisy.

def _euclidean_pts(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def _largest_contour_bbox(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    edged = cv2.Canny(blur, 30, 120)

    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    return cv2.boundingRect(largest)  # x, y, w, h

def estimate_measurements(image_path: str, height_cm: int = None, weight_kg: int = None) -> dict:
    """
    Render-safe fallback measurement estimator (NO MEDIAPIPE).
    Uses silhouette bounding box + proportional estimation.
    """
    if not os.path.exists(image_path):
        raise ValueError(f"Image not found: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image. File may be corrupted or unsupported.")

    img_h, img_w = img.shape[:2]

    bbox = _largest_contour_bbox(img)
    if bbox is None:
        raise ValueError("No body detected. Use a clearer full-body photo.")

    x, y, w, h = bbox

    # Estimate shoulders as ~45% of body width
    shoulder_width_px = w * 0.45
    chest_width_px = shoulder_width_px * 0.9
    seat_width_px = w * 0.55  # slightly larger than shoulders
    height_px = h

    # Convert pixels to cm. Use/default height to keep values person-specific
    baseline_height_cm = float(height_cm) if height_cm else DEFAULT_EST_HEIGHT_CM
    expected_shoulder_cm = baseline_height_cm * DEFAULT_SHOULDER_TO_HEIGHT_RATIO
    px_to_cm_shoulder = expected_shoulder_cm / shoulder_width_px if shoulder_width_px else 0.0
    effective_height_px = float(height_px)
    if shoulder_width_px:
        expected_height_px = shoulder_width_px * EXPECTED_HEIGHT_TO_SHOULDER_RATIO
        effective_height_px = max(effective_height_px, expected_height_px)
    px_to_cm_height = baseline_height_cm / effective_height_px if effective_height_px else 0.0

    def _weighted_px_to_cm(base_height_bias: float):
        """
        Blend height-based scaling with shoulder-based scaling. When the detected silhouette
        height is very small (cropped torso shot), height_px is unreliable so we lean harder
        on the shoulder heuristic to keep measurements realistic.
        """
        if not effective_height_px:
            height_quality = 0.0
        else:
            height_quality = min(1.0, max(0.0, float(effective_height_px) / RELIABLE_HEIGHT_PX))
        height_weight = base_height_bias * height_quality
        shoulder_weight = max(0.0, 1.0 - height_weight)
        blended = (px_to_cm_height * height_weight) + (px_to_cm_shoulder * shoulder_weight)
        if blended == 0.0:
            return px_to_cm_height or px_to_cm_shoulder
        return blended

    if height_cm:
        px_to_cm = _weighted_px_to_cm(0.6)
        est_height_cm = float(height_cm)
    else:
        # Without explicit height, rely mostly on silhouette height so results vary per photo.
        px_to_cm = _weighted_px_to_cm(0.85)
        est_height_cm = baseline_height_cm

    shoulder_cm = shoulder_width_px * px_to_cm
    chest_width_cm = chest_width_px * px_to_cm
    seat_width_cm = seat_width_px * px_to_cm
    waist_width_cm = seat_width_cm * 0.85

    chest_cm = chest_width_cm * PHOTO_WIDTH_TO_CM_MULTIPLIER
    waist_cm = waist_width_cm * PHOTO_WIDTH_TO_CM_MULTIPLIER
    seat_cm = seat_width_cm * PHOTO_WIDTH_TO_CM_MULTIPLIER

    return {
        "height_px": float(height_px),
        "shoulder_width_px": float(shoulder_width_px),
        "chest_width_px": float(chest_width_px),
        "seat_width_px": float(seat_width_px),

        "height_cm": float(est_height_cm),
        "shoulder_cm": float(shoulder_cm),
        "chest_cm": float(chest_cm),
        "waist_cm": float(waist_cm),
        "seat_cm": float(seat_cm),
    }
