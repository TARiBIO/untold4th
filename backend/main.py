from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict, deque
from functools import lru_cache
from typing import Optional, Dict, Any, List
from pathlib import Path
from pydantic import BaseModel
import csv
import io
import json
import os
import time

# --- Imports inside the backend package (Render-friendly) ---
from .measurement import estimate_measurements
from .fit_engine import recommend_size
from .tryon import generate_tryon
from .utils import save_upload_file


SIZE_CHART_PATH = os.path.join(os.path.dirname(__file__), "sizeChart.json")
DEFAULT_HEIGHT_CM = 170
PHOTO_WIDTH_TO_CM_MULTIPLIER = 2.6
BASE_DIR = Path(__file__).parent
SIZE_CHARTS_PATH = BASE_DIR / "data" / "size_charts.json"
API_KEYS_FILE = Path(__file__).with_name("api_keys.json")
_API_KEYS_CACHE: Dict[str, str] = {}
_API_KEYS_MTIME: Optional[float] = None
PROTECTED_PATHS = ("/estimate", "/fit-assist")
PRODUCT_ID_ALIAS = {
    "product1": "TEE_MIN_BLACK",
    "product2": "HOODIE_CORE_GREY",
    "product3": "JEAN_SKINNY_BLACK",
    "product4": "DRESS_SUMMER_FLORAL",
}
RATE_LIMITS = [
    {"name": "per_minute", "limit": 60, "window": 60},
    {"name": "per_hour", "limit": 500, "window": 3600},
    {"name": "per_day", "limit": 1500, "window": 86400},
]
RATE_STATE: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))


@lru_cache(maxsize=1)
def load_product_size_chart() -> Dict[str, Any]:
    if not os.path.exists(SIZE_CHART_PATH):
        raise FileNotFoundError(f"Size chart not found at {SIZE_CHART_PATH}")
    with open(SIZE_CHART_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ----- Size chart storage (CSV -> JSON) -----

class SizeEntry(BaseModel):
    label: str
    chest_cm: Optional[float] = None
    bust_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hips_cm: Optional[float] = None
    shoulder_cm: Optional[float] = None
    sleeve_cm: Optional[float] = None
    length_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    notes: Optional[str] = None


class SizeChart(BaseModel):
    product_id: str
    product_name: str
    gender: str
    product_type: str
    fit_type: str
    sizes: List[SizeEntry]


def load_size_charts() -> Dict[str, dict]:
    if not SIZE_CHARTS_PATH.exists():
        return {}
    with SIZE_CHARTS_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_size_charts(data: Dict[str, dict]) -> None:
    SIZE_CHARTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SIZE_CHARTS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def parse_size_chart_csv(file_bytes: bytes) -> Dict[str, SizeChart]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    charts: Dict[str, SizeChart] = {}

    for row in reader:
        product_id = row.get("product_id", "").strip()
        if not product_id:
            continue

        product_name = row.get("product_name", "").strip()
        gender = row.get("gender", "").strip().lower() or "unisex"
        product_type = row.get("product_type", "").strip().lower() or "generic"
        fit_type = row.get("fit_type", "").strip().lower() or "true_to_size"
        size_label = row.get("size_label", "").strip()
        if not size_label:
            continue

        def _float(key: str) -> Optional[float]:
            val = (row.get(key) or "").strip()
            try:
                return float(val) if val != "" else None
            except ValueError:
                return None

        size_entry = SizeEntry(
            label=size_label,
            chest_cm=_float("chest_cm"),
            bust_cm=_float("bust_cm"),
            waist_cm=_float("waist_cm"),
            hips_cm=_float("hips_cm"),
            shoulder_cm=_float("shoulder_cm"),
            sleeve_cm=_float("sleeve_cm"),
            length_cm=_float("length_cm"),
            inseam_cm=_float("inseam_cm"),
            notes=(row.get("notes") or "").strip() or None,
        )

        if product_id not in charts:
            charts[product_id] = SizeChart(
                product_id=product_id,
                product_name=product_name,
                gender=gender,
                product_type=product_type,
                fit_type=fit_type,
                sizes=[size_entry],
            )
        else:
            charts[product_id].sizes.append(size_entry)

    return charts


def ease_factor_for_fit(fit_type: str) -> float:
    fit_type = (fit_type or "true_to_size").lower()
    if fit_type == "slim":
        return 1.02
    if fit_type == "oversized":
        return 1.08
    if fit_type == "relaxed":
        return 1.05
    if fit_type == "boxy":
        return 1.04
    return 1.03


def recommend_size_for_product(product_chart: dict, user_measurements: dict) -> dict:
    gender = (product_chart.get("gender") or user_measurements.get("gender") or "unisex").lower()
    product_type = (product_chart.get("product_type") or "generic").lower()
    fit_type = (product_chart.get("fit_type") or "true_to_size").lower()
    sizes = product_chart.get("sizes", [])
    if not sizes:
        raise ValueError("No sizes defined for this product")

    ease = ease_factor_for_fit(fit_type)

    def relevant_keys() -> List[str]:
        # For tops, base the decision on chest/bust and shoulder; only fall back to waist if nothing else is present.
        if product_type in {"tshirt", "hoodie", "sweatshirt", "shirt"}:
            keys: List[str] = []
            if gender == "women":
                if user_measurements.get("bust_cm"):
                    keys.append("bust_cm")
                elif user_measurements.get("chest_cm"):
                    keys.append("chest_cm")
            else:
                if user_measurements.get("chest_cm"):
                    keys.append("chest_cm")
                elif user_measurements.get("bust_cm"):
                    keys.append("bust_cm")
            if user_measurements.get("shoulder_cm"):
                keys.append("shoulder_cm")
            if not keys and user_measurements.get("waist_cm"):
                keys.append("waist_cm")
            if keys:
                return keys
        if product_type in {"jeans", "trousers", "pants"}:
            return ["waist_cm", "hips_cm", "inseam_cm"]
        if product_type in {"dress", "skirt"}:
            return ["bust_cm", "waist_cm", "hips_cm"]
        return ["chest_cm", "bust_cm", "waist_cm", "hips_cm"]

    keys = relevant_keys()
    scored_sizes: List[Dict[str, Any]] = []

    for size in sizes:
        size_label = size.get("label")
        score = 0.0
        penalty_too_small = 0.0

        for key in keys:
            body_val = user_measurements.get(key)
            garment_val = size.get(key)
            if body_val is None or garment_val is None:
                continue
            target_garment = body_val * ease
            diff = garment_val - target_garment
            if diff < 0:
                penalty_too_small += abs(diff) * 8.0
            score += abs(diff)

        score += penalty_too_small
        scored_sizes.append({"label": size_label, "score": score})

    scored_sizes.sort(key=lambda x: x["score"])
    best = scored_sizes[0]
    return {
        "recommended_size": best["label"],
        "scores": scored_sizes,
        "reason": f"Based on {', '.join(keys)} with {fit_type.replace('_', ' ')} fit",
    }


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_api_keys() -> Dict[str, str]:
    """
    Load active API keys (key -> brand). Uses mtime caching so updates via manage_keys.py
    are picked up without restarting the server.
    """
    global _API_KEYS_CACHE, _API_KEYS_MTIME
    try:
        mtime = API_KEYS_FILE.stat().st_mtime
    except FileNotFoundError:
        _API_KEYS_CACHE = {}
        _API_KEYS_MTIME = None
        return _API_KEYS_CACHE

    if _API_KEYS_MTIME != mtime:
        try:
            with API_KEYS_FILE.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            _API_KEYS_CACHE = {}
            _API_KEYS_MTIME = mtime
            return _API_KEYS_CACHE

        _API_KEYS_CACHE = {
            info["key"]: brand
            for brand, info in raw.items()
            if isinstance(info, dict) and info.get("key") and info.get("active", True)
        }
        _API_KEYS_MTIME = mtime

    return _API_KEYS_CACHE


def _rate_identifier(request: Request, keys_map: Dict[str, str]) -> str:
    key = request.headers.get("x-api-key")
    if key and key in keys_map:
        return f"key:{key}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    path = request.url.path
    keys_map = load_api_keys()

    if path.startswith("/estimate"):
        key = request.headers.get("x-api-key")
        if key not in keys_map:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    if any(path.startswith(p) for p in PROTECTED_PATHS):
        identifier = _rate_identifier(request, keys_map)
        _enforce_rate_limits(identifier)

    return await call_next(request)


def _enforce_rate_limits(identifier: str):
    """Simple in-memory sliding-window limiter keyed by API key or client IP."""
    now = time.time()
    buckets = RATE_STATE[identifier]
    for rule in RATE_LIMITS:
        bucket = buckets[rule["name"]]
        window_start = now - rule["window"]
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= rule["limit"]:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({rule['name']}: {rule['limit']} requests per {rule['window']}s).",
            )
        bucket.append(now)


@app.get("/")
def root():
    return {"status": "ok", "message": "Untold 4th backend is running"}


@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.post("/size-charts/upload-csv")
async def upload_size_chart_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()
    new_charts = parse_size_chart_csv(content)
    if not new_charts:
        raise HTTPException(status_code=400, detail="No valid size chart rows found")

    existing = load_size_charts()
    for pid, chart in new_charts.items():
        existing[pid] = json.loads(chart.json())
    save_size_charts(existing)

    return {"status": "ok", "message": "Size charts uploaded successfully", "product_ids": list(new_charts.keys())}


@app.get("/size-charts/{product_id}", response_model=SizeChart)
def get_size_chart(product_id: str):
    charts = load_size_charts()
    chart = charts.get(product_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Size chart not found")
    return SizeChart(**chart)


@app.post("/size-charts/recommend/{product_id}")
def recommend_size_for_chart(product_id: str, user: Dict[str, Any]):
    charts = load_size_charts()
    chart = charts.get(product_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Size chart not found")
    try:
        result = recommend_size_for_product(chart, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "product_id": product_id,
        "recommended_size": result["recommended_size"],
        "reason": result["reason"],
        "debug_scores": result["scores"],
    }


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

    resolved_pid = PRODUCT_ID_ALIAS.get(product_id, product_id)
    size_charts = load_size_charts()
    chart = size_charts.get(resolved_pid)

    if chart:
        user_measurements = {
            # Use chart gender as a hint; body data otherwise
            "gender": chart.get("gender"),
            "chest_cm": profile_cm.get("chest"),
            "bust_cm": profile_cm.get("chest"),
            "waist_cm": profile_cm.get("waist"),
            "hips_cm": profile_cm.get("seat"),
            "shoulder_cm": measurements.get("shoulder_cm"),
            "inseam_cm": measurements.get("inseam_cm"),
        }
        try:
            rec_raw = recommend_size_for_product(chart, user_measurements)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        recommendation = {
            "size": rec_raw.get("recommended_size"),
            "reason": rec_raw.get("reason"),
            "scores": rec_raw.get("scores"),
            "chart_product_id": resolved_pid,
        }
    else:
        # Fallback to legacy chart logic
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
        "product_id": product_id,
        "chart_product_id": resolved_pid,
        "uploaded_image": saved_name,
    }


@app.get("/uploads/{fname}")
def get_upload(fname: str):
    path = os.path.join(os.path.dirname(__file__), "uploads", fname)
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)
