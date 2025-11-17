from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from functools import lru_cache
from typing import Optional, Dict, Any, List
import json
import os

# --- Imports inside the backend package (Render-friendly) ---
from .measurement import estimate_measurements
from .fit_engine import recommend_size
from .tryon import generate_tryon
from .utils import save_upload_file


SIZE_CHART_PATH = os.path.join(os.path.dirname(__file__), "sizeChart.json")
DEFAULT_HEIGHT_CM = 170
PHOTO_WIDTH_TO_CM_MULTIPLIER = 2.6


@lru_cache(maxsize=1)
def load_product_size_chart() -> Dict[str, Any]:
    if not os.path.exists(SIZE_CHART_PATH):
        raise FileNotFoundError(f"Size chart not found at {SIZE_CHART_PATH}")
    with open(SIZE_CHART_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "message": "Untold 4th backend is running"}


@app.post("/estimate")
async def estimate(file: UploadFile = File(...), user_height_cm: int = Form(None)):
    import shutil
    os.makedirs("/tmp/uploads", exist_ok=True)
    saved = f"/tmp/uploads/{file.filename}"
    with open(saved, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        meas = estimate_measurements(saved, height_cm=user_height_cm)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    rec = recommend_size(meas, brand_id="brand_acme", user_height_cm=user_height_cm)
    return {"measurements": meas, "recommendation": rec, "image": os.path.basename(saved)}


@app.post("/tryon")
async def tryon(file: UploadFile = File(...), garment: str = Form(...)):
    import shutil
    os.makedirs("/tmp/uploads", exist_ok=True)
    saved = f"/tmp/uploads/{file.filename}"
    with open(saved, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        meas = estimate_measurements(saved)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    out_path = generate_tryon(saved, garment, meas)
    return {"tryon_image": os.path.basename(out_path)}


def measurements_from_metrics(height_cm: Optional[int], weight_kg: Optional[int]):
    if not height_cm and not weight_kg:
        raise ValueError("height_cm or weight_kg is required")
    height_cm = height_cm or DEFAULT_HEIGHT_CM
    weight_kg = weight_kg or 70

    chest = 0.40 * height_cm + 0.50 * weight_kg
    waist = 0.32 * height_cm + 0.40 * weight_kg
    seat = 0.34 * height_cm + 0.45 * weight_kg
    shoulder = 0.22 * height_cm + 0.25 * weight_kg
    virtual_height = height_cm * 2.4
    return {
        "chest_width_px": float(chest),
        "shoulder_width_px": float(shoulder),
        "height_px": float(virtual_height),
        "chest_cm": float(chest),
        "waist_cm": float(waist),
        "seat_cm": float(seat),
    }


WIDTH_BASED_CM_KEYS = {"chest_cm", "waist_cm", "seat_cm"}


def _normalize_width_based_value(key: str, value: Optional[float]) -> Optional[float]:
    """
    Photo-based cm values represent widths while metrics are circumferences.
    Convert photo widths to approximated circumferences so blended averages
    remain in the same unit space.
    """
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value

    if key in WIDTH_BASED_CM_KEYS and value < 70:
        return value * PHOTO_WIDTH_TO_CM_MULTIPLIER
    return value


def merge_measurements(primary: Optional[dict], secondary: Optional[dict]) -> dict:
    if not primary:
        return secondary or {}
    if not secondary:
        return primary
    merged = {}
    for key in set(primary.keys()).union(secondary.keys()):
        p_val = primary.get(key)
        s_val = secondary.get(key)
        if p_val is None:
            merged[key] = s_val
        elif s_val is None:
            merged[key] = p_val
        else:
            norm_primary = _normalize_width_based_value(key, p_val)
            norm_secondary = _normalize_width_based_value(key, s_val)
            try:
                merged[key] = (norm_primary + norm_secondary) / 2
            except TypeError:
                # Fallback if values are non-numeric objects (e.g., strings)
                merged[key] = norm_primary
    return merged


def scale_px_to_cm(value_px: Optional[float], height_px: Optional[float], user_height_cm: Optional[int]):
    if value_px is None or height_px in (None, 0):
        return None
    height_cm = user_height_cm or DEFAULT_HEIGHT_CM
    return float(value_px) * (float(height_cm) / float(height_px))


def derive_body_profile(measurements: dict, user_height_cm: Optional[int]):
    profile = {}
    if not measurements:
        return profile

    for field in ("chest", "waist", "seat"):
        cm_key = f"{field}_cm"
        value = measurements.get(cm_key)
        if value is None:
            continue
        value = float(value)
        if value < 70:  # raw photo outputs are widths; convert to circumference
            value *= PHOTO_WIDTH_TO_CM_MULTIPLIER
        profile[field] = value

    if "chest" not in profile:
        scaled = scale_px_to_cm(
            measurements.get("chest_width_px"),
            measurements.get("height_px"),
            user_height_cm,
        )
        if scaled:
            profile["chest"] = float(scaled * PHOTO_WIDTH_TO_CM_MULTIPLIER)

    return profile


def size_diff(value: float, span: List[float]):
    if not span or len(span) != 2:
        return abs(value - span) if isinstance(span, (int, float)) else 0.0
    low, high = span
    if value < low:
        return low - value
    if value > high:
        return value - high
    return 0.0


def recommend_size_from_chart(profile: dict, metrics: Optional[List[str]] = None):
    chart = load_product_size_chart()
    metrics = metrics or ["chest", "waist", "seat"]
    best_size = None
    best_score = None
    best_detail = None

    for size_label, size_data in chart.items():
        score = 0.0
        detail = {}
        comparisons = 0

        for metric_key in metrics:
            value = profile.get(metric_key)
            target = size_data.get(metric_key)
            if value is None or target is None:
                continue
            comparisons += 1
            diff = size_diff(value, target)
            score += diff
            detail[metric_key] = {
                "value": value,
                "target_range": target,
                "diff": diff,
            }

        if comparisons == 0:
            continue

        if best_score is None or score < best_score:
            best_score = score
            best_size = size_label
            best_detail = detail

    if best_size is None:
        raise HTTPException(status_code=400, detail="Unable to match measurements to the size chart.")

    return {"size": best_size, "score": best_score, "comparison": best_detail}


@app.post("/fit-assist")
async def fit_assist(
    mode: str = Form(...),
    height_cm: int = Form(None),
    weight_kg: int = Form(None),
    product_id: str = Form("product1"),
    file: UploadFile = File(None),
):
    mode = mode.lower()
    if mode not in {"upload", "metrics", "both"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    photo_required = mode in {"upload", "both"}
    metrics_required = mode in {"metrics", "both"}

    photo_measurements = None
    metric_measurements = None
    saved_name = None

    if photo_required:
        if not file:
            raise HTTPException(status_code=400, detail="Photo upload is required for this option.")
        saved_path = await save_upload_file(file)
        saved_name = os.path.basename(saved_path)
        try:
            # Pass height/weight if provided for more accurate ML scaling
            photo_measurements = estimate_measurements(
                saved_path,
                height_cm=height_cm,
                weight_kg=weight_kg,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Photo parsing failed: {exc}") from exc

    if metrics_required:
        try:
            metric_measurements = measurements_from_metrics(height_cm, weight_kg)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    measurements = merge_measurements(photo_measurements, metric_measurements)
    if not measurements:
        raise HTTPException(status_code=400, detail="Unable to derive measurements.")

    profile_cm = derive_body_profile(measurements, height_cm)

    if product_id == "product1":
        if "chest" not in profile_cm:
            raise HTTPException(
                status_code=400,
                detail="Unable to derive chest measurement for product sizing. Please include your height/metrics.",
            )
        recommendation = recommend_size_from_chart(profile_cm, metrics=["chest"])
    elif product_id == "product3":
        if "waist" not in profile_cm:
            raise HTTPException(
                status_code=400,
                detail="Unable to derive waist measurement for product sizing. Provide your height/weight to continue.",
            )
        recommendation = recommend_size_from_chart(profile_cm, metrics=["waist"])
    else:
        recommendation = recommend_size(measurements, brand_id="brand_acme", user_height_cm=height_cm)

    return {
        "mode": mode,
        "measurements": measurements,
        "profile_cm": profile_cm,
        "recommendation": recommendation,
        "uploaded_image": saved_name,
    }


@app.get("/uploads/{fname}")
def get_upload(fname: str):
    path = os.path.join(os.path.dirname(__file__), "uploads", fname)
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)
