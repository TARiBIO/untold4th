import os
import math
import cv2
import numpy as np

DEFAULT_EST_HEIGHT_CM = 170.0
DEFAULT_SHOULDER_CM = 42.0

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
    px_to_cm_shoulder = DEFAULT_SHOULDER_CM / shoulder_width_px if shoulder_width_px else 0
    baseline_height_cm = float(height_cm) if height_cm else DEFAULT_EST_HEIGHT_CM
    px_to_cm_height = baseline_height_cm / float(height_px)

    if height_cm:
        px_to_cm = 0.6 * px_to_cm_height + 0.4 * px_to_cm_shoulder
        est_height_cm = float(height_cm)
    else:
        # Without explicit height, rely mostly on silhouette height so results vary per photo
        px_to_cm = 0.85 * px_to_cm_height + 0.15 * px_to_cm_shoulder
        est_height_cm = baseline_height_cm

    shoulder_cm = shoulder_width_px * px_to_cm
    chest_cm = chest_width_px * px_to_cm
    seat_cm = seat_width_px * px_to_cm
    waist_cm = seat_cm * 0.85

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
