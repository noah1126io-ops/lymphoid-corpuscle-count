from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import streamlit_drawable_canvas as drawable_canvas
from PIL import Image, ImageOps
from streamlit.elements.lib import image_utils
from streamlit.elements.lib.layout_utils import LayoutConfig
from streamlit_drawable_canvas import st_canvas


APP_TITLE = "手動好酸球アノテーションツール"

PROJECT_TEMPLATES = [
    "ECRS_nasal_polyp",
    "CRS_sinonasal_mucosa",
    "EoE_esophagus_reference",
    "GI_eosinophilia_reference",
    "generic_eosinophil_reference",
    "multi_tissue_eosinophil_reference",
    "generic_granulocyte",
    "custom",
]
DISEASE_CONTEXTS = ["ECRS", "CRSwNP", "CRSsNP", "eosinophilic_inflammation", "control", "other", "unknown"]
TISSUE_TYPES = [
    "nasal_polyp",
    "sinonasal_mucosa",
    "inferior_turbinate",
    "other",
    "unknown",
]
SOURCE_ORGANS = ["liver", "sinonasal_mucosa", "esophagus", "skin", "lung", "other", "unknown"]
TISSUE_REGIONS = [
    "portal_tract",
    "lobule",
    "interface_area",
    "bile_duct_area",
    "lamina_propria",
    "epithelium",
    "other",
    "unknown",
]
ANATOMICAL_SITES = [
    "ethmoid_sinus",
    "maxillary_sinus",
    "nasal_cavity",
    "other",
    "unknown",
]
STAINING_OPTIONS = ["H&E", "other", "unknown"]
OBJECTIVE_MAGNIFICATIONS = ["20x", "40x", "other", "unknown"]
SECTION_QUALITY_OPTIONS = ["good", "acceptable", "poor"]
REGION_TYPES = [
    "epithelium",
    "lamina_propria",
    "glandular_area",
    "vascular_area",
    "mucus",
    "blood_clot",
    "necrosis",
    "artifact",
    "unknown",
]

LABELS = [
    "eosinophil",
    "neutrophil",
    "basophil",
    "mast_cell",
    "lymphocyte",
    "plasma_cell",
    "other_cell",
    "artifact",
    "ignore",
]
PRIMARY_LABELS = ["eosinophil", "other_cell", "artifact", "ignore"]
LABEL_COLORS = {
    "eosinophil": "#e83e8c",
    "neutrophil": "#2f80ed",
    "basophil": "#7b2cbf",
    "mast_cell": "#f2994a",
    "lymphocyte": "#219653",
    "plasma_cell": "#56ccf2",
    "other_cell": "#6c757d",
    "artifact": "#8d6e63",
    "ignore": "#111827",
}
YOLO_CLASS_IDS = {
    "eosinophil": 0,
    "neutrophil": 1,
    "basophil": 2,
    "mast_cell": 3,
    "lymphocyte": 4,
    "plasma_cell": 5,
    "other_cell": 6,
    "artifact": 7,
    "ignore": 8,
}
CANDIDATE_SOURCES = [
    "manual",
    "imported_open_eoe",
    "imported_cellpose",
    "imported_custom_model",
    "model_v1",
]
CANDIDATE_IMPORT_SOURCES = [source for source in CANDIDATE_SOURCES if source != "manual"]
ANNOTATION_STATUSES = [
    "confirmed_by_human",
    "corrected_by_human",
    "candidate_unconfirmed",
    "rejected",
]
ANNOTATION_STATUS_FIELDS = [
    "candidate_source",
    "annotation_status",
    "used_for_training",
]

METADATA_FIELDS = [
    "project_template",
    "disease_context",
    "source_organ",
    "tissue_type",
    "tissue_region",
    "staining",
    "objective_magnification",
    "specimen_id",
    "slide_id",
    "annotator",
    "patient_id_hash",
    "anatomical_site",
    "scanner_or_microscope",
    "pixel_size_um",
    "hpf_area_mm2",
    "hpf_diameter_mm",
    "image_is_single_hpf",
    "section_quality",
    "reviewed",
    "exported",
    "source_wsi_name",
    "patch_id",
    "patch_x",
    "patch_y",
    "patch_width",
    "patch_height",
    "target_mpp",
    "mpp_x",
    "mpp_y",
    "notes",
]
MANIFEST_FIELDS = [
    "image_name",
    "original_image_path",
    "annotation_json_path",
    "annotation_csv_path",
    "count_csv_path",
    "yolo_label_path",
    "project_template",
    "disease_context",
    "source_organ",
    "tissue_type",
    "tissue_region",
    "staining",
    "objective_magnification",
    "source_wsi_name",
    "patch_id",
    "patch_x",
    "patch_y",
    "patch_width",
    "patch_height",
    "target_mpp",
    "mpp_x",
    "mpp_y",
    "pixel_size_um",
    "hpf_area_mm2",
    "annotator",
    "reviewed",
    "exported",
    "annotation_count",
    "eosinophil_count",
    "saved_at",
]
REQUIRED_METADATA_FIELDS = [
    "project_template",
    "disease_context",
    "tissue_type",
    "staining",
    "objective_magnification",
    "specimen_id",
    "slide_id",
    "annotator",
]
TEMPLATE_DEFAULTS = {
    "ECRS_nasal_polyp": {
        "project_template": "ECRS_nasal_polyp",
        "disease_context": "ECRS",
        "tissue_type": "nasal_polyp",
        "staining": "H&E",
        "objective_magnification": "40x",
        "anatomical_site": "unknown",
        "section_quality": "good",
    },
    "CRS_sinonasal_mucosa": {
        "project_template": "CRS_sinonasal_mucosa",
        "disease_context": "unknown",
        "tissue_type": "sinonasal_mucosa",
        "staining": "H&E",
        "objective_magnification": "40x",
        "anatomical_site": "unknown",
        "section_quality": "good",
    },
    "EoE_esophagus_reference": {
        "project_template": "EoE_esophagus_reference",
        "disease_context": "unknown",
        "tissue_type": "other",
        "staining": "H&E",
        "objective_magnification": "40x",
        "anatomical_site": "other",
        "section_quality": "good",
    },
    "GI_eosinophilia_reference": {
        "project_template": "GI_eosinophilia_reference",
        "disease_context": "unknown",
        "tissue_type": "other",
        "staining": "H&E",
        "objective_magnification": "40x",
        "anatomical_site": "other",
        "section_quality": "good",
    },
    "generic_eosinophil_reference": {
        "project_template": "generic_eosinophil_reference",
        "disease_context": "eosinophilic_inflammation",
        "source_organ": "unknown",
        "tissue_type": "other",
        "tissue_region": "unknown",
        "staining": "H&E",
        "objective_magnification": "40x",
        "anatomical_site": "unknown",
        "section_quality": "good",
    },
    "multi_tissue_eosinophil_reference": {
        "project_template": "multi_tissue_eosinophil_reference",
        "disease_context": "eosinophilic_inflammation",
        "source_organ": "unknown",
        "tissue_type": "other",
        "tissue_region": "unknown",
        "staining": "H&E",
        "objective_magnification": "40x",
        "anatomical_site": "unknown",
        "section_quality": "good",
    },
    "generic_granulocyte": {
        "project_template": "generic_granulocyte",
        "disease_context": "unknown",
        "source_organ": "unknown",
        "tissue_type": "unknown",
        "tissue_region": "unknown",
        "staining": "H&E",
        "objective_magnification": "unknown",
        "anatomical_site": "unknown",
        "section_quality": "good",
    },
    "custom": {
        "project_template": "custom",
        "disease_context": "unknown",
        "tissue_type": "unknown",
        "staining": "unknown",
        "objective_magnification": "unknown",
        "anatomical_site": "unknown",
        "section_quality": "good",
    },
}

DATA_DIR = Path("data")
IMAGE_DIR = DATA_DIR / "images"
ORIGINAL_NDPI_DIR = IMAGE_DIR / "original_ndpi"
ORIGINAL_WSI_DIR = IMAGE_DIR / "original_wsi"
CONVERTED_IMAGE_DIR = IMAGE_DIR / "converted"
PATCH_DIR = DATA_DIR / "patches"
PATCH_IMAGE_DIR = PATCH_DIR / "images"
ANNOTATION_DIR = DATA_DIR / "annotations"
EXPORT_DIR = DATA_DIR / "exports"
YOLO_DIR = EXPORT_DIR / "yolo_labels"
DATASET_DIR = DATA_DIR / "dataset"
DATASET_IMAGE_DIR = DATASET_DIR / "images"
DATASET_LABEL_DIR = DATASET_DIR / "labels"
MAX_DISPLAY_WIDTH = 1100
MAX_DISPLAY_HEIGHT = 900
NDPI_EXTENSIONS = {".ndpi"}
WSI_EXTENSIONS = {".ndpi", ".svs", ".scn", ".vms", ".vmu"}
MAX_NDPI_CONVERSION_PIXELS = 30_000_000
WSI_THUMBNAIL_MAX_SIZE = (1100, 700)
PATCH_SIZE_OPTIONS = [1024, 2048]

# Research TIFF files can be very large. The app still downscales for display,
# but Pillow needs permission to open the original dimensions first.
Image.MAX_IMAGE_PIXELS = None


def patch_drawable_canvas_for_streamlit() -> None:
    """Keep streamlit-drawable-canvas working with newer Streamlit versions."""

    def image_to_url(
        image: Image.Image,
        width: int,
        clamp: bool,
        channels: str,
        output_format: str,
        image_id: str,
    ) -> str:
        layout_config = LayoutConfig(width=width)
        return image_utils.image_to_url(
            image,
            layout_config,
            clamp,
            channels,
            output_format,
            image_id,
        )

    drawable_canvas.st_image.image_to_url = image_to_url


def disable_canvas_context_menu() -> None:
    components.html(
        """
        <script>
        const disableContextMenu = () => {
          const documents = [window.parent.document];
          window.parent.document.querySelectorAll("iframe").forEach((frame) => {
            try {
              if (frame.contentWindow && frame.contentWindow.document) {
                documents.push(frame.contentWindow.document);
              }
            } catch (error) {
              // Cross-origin frames are ignored.
            }
          });
          documents.forEach((doc) => doc.querySelectorAll("canvas").forEach((canvas) => {
            canvas.addEventListener("contextmenu", (event) => event.preventDefault());
          }));
        };
        disableContextMenu();
        setTimeout(disableContextMenu, 500);
        setTimeout(disableContextMenu, 1500);
        </script>
        """,
        height=0,
        width=0,
    )


def ensure_directories() -> None:
    for path in (
        IMAGE_DIR,
        ORIGINAL_NDPI_DIR,
        ORIGINAL_WSI_DIR,
        CONVERTED_IMAGE_DIR,
        PATCH_IMAGE_DIR,
        ANNOTATION_DIR,
        EXPORT_DIR,
        YOLO_DIR,
        DATASET_IMAGE_DIR,
        DATASET_LABEL_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def default_image_metadata(project_template: str = "ECRS_nasal_polyp") -> dict[str, str]:
    metadata = {
        "project_template": project_template,
        "disease_context": "unknown",
        "source_organ": "unknown",
        "tissue_type": "unknown",
        "tissue_region": "unknown",
        "staining": "unknown",
        "objective_magnification": "unknown",
        "specimen_id": "",
        "slide_id": "",
        "annotator": "",
        "patient_id_hash": "",
        "anatomical_site": "unknown",
        "scanner_or_microscope": "",
        "pixel_size_um": "",
        "hpf_area_mm2": "",
        "hpf_diameter_mm": "",
        "image_is_single_hpf": False,
        "section_quality": "good",
        "reviewed": False,
        "exported": False,
        "source_wsi_name": "",
        "patch_id": "",
        "patch_x": "",
        "patch_y": "",
        "patch_width": "",
        "patch_height": "",
        "target_mpp": "",
        "mpp_x": "",
        "mpp_y": "",
        "notes": "",
    }
    metadata.update(TEMPLATE_DEFAULTS.get(project_template, TEMPLATE_DEFAULTS["custom"]))
    return metadata


def default_region_annotations(region_type: str = "unknown") -> dict[str, Any]:
    return {
        "global_region_type": region_type,
        "regions": [],
    }


def init_session_state() -> None:
    defaults = {
        "image_name": None,
        "uploaded_source_name": None,
        "original_image_path": "",
        "image_original_size": None,
        "display_size": None,
        "scale_factor": 1.0,
        "canvas_objects": [],
        "saved_image_key": None,
        "restored_annotations_key": None,
        "annotation_table": [],
        "canvas_key_version": 0,
        "canvas_initial_drawing_pending": True,
        "last_saved_message": "",
        "candidate_import_key": None,
        "active_patch": None,
        "active_patch_source": None,
        "project_template": "ECRS_nasal_polyp",
        "image_metadata": default_image_metadata("ECRS_nasal_polyp"),
        "region_annotations": default_region_annotations(),
        "last_template": "ECRS_nasal_polyp",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def load_image(uploaded_file: Any) -> Image.Image:
    uploaded_file.seek(0)
    image = Image.open(uploaded_file)
    if getattr(image, "n_frames", 1) > 1:
        image.seek(0)
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    return image


def load_image_from_path(image_path: Path) -> Image.Image:
    image = Image.open(image_path)
    if getattr(image, "n_frames", 1) > 1:
        image.seek(0)
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    return image


def make_display_image(image: Image.Image) -> tuple[Image.Image, float]:
    width, height = image.size
    scale_factor = min(MAX_DISPLAY_WIDTH / width, MAX_DISPLAY_HEIGHT / height, 1.0)
    if scale_factor >= 1.0:
        return image.copy(), 1.0

    display_width = int(width * scale_factor)
    display_height = int(height * scale_factor)
    display_image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
    return display_image, scale_factor


def save_uploaded_image(uploaded_file: Any) -> Path:
    return save_uploaded_file(uploaded_file, IMAGE_DIR / uploaded_file.name)


def save_uploaded_file(uploaded_file: Any, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    uploaded_size = getattr(uploaded_file, "size", None)
    if destination.exists() and uploaded_size and destination.stat().st_size == uploaded_size:
        return destination
    uploaded_file.seek(0)
    with destination.open("wb") as output_file:
        shutil.copyfileobj(uploaded_file, output_file)
    return destination


def is_ndpi_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in NDPI_EXTENSIONS


def is_wsi_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in WSI_EXTENSIONS


def converted_ome_tiff_path(filename: str) -> Path:
    return CONVERTED_IMAGE_DIR / f"{safe_file_stem(Path(filename).stem)}.ome.tiff"


def select_openslide_level(level_dimensions: tuple[tuple[int, int], ...]) -> int:
    suitable_levels = [
        (index, width * height)
        for index, (width, height) in enumerate(level_dimensions)
        if width * height <= MAX_NDPI_CONVERSION_PIXELS
    ]
    if suitable_levels:
        return max(suitable_levels, key=lambda item: item[1])[0]
    return len(level_dimensions) - 1


def convert_ndpi_to_ome_tiff(ndpi_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists() and output_path.stat().st_mtime >= ndpi_path.stat().st_mtime:
        return {"converted": False, "output_path": str(output_path), "reason": "existing_ome_tiff_reused"}

    try:
        import numpy as np
        import openslide
        import tifffile
    except ImportError as error:
        raise RuntimeError(
            "NDPI変換には openslide-python, openslide-bin, tifffile, numpy が必要です。"
            "次を実行してください: pip install -r requirements.txt"
        ) from error

    output_path.parent.mkdir(parents=True, exist_ok=True)
    slide = openslide.OpenSlide(str(ndpi_path))
    try:
        level = select_openslide_level(tuple(slide.level_dimensions))
        width, height = slide.level_dimensions[level]
        downsample = float(slide.level_downsamples[level])
        region = slide.read_region((0, 0), level, (width, height)).convert("RGB")
        image_array = np.asarray(region)
    finally:
        slide.close()

    tifffile.imwrite(
        output_path,
        image_array,
        ome=True,
        photometric="rgb",
        compression="deflate",
        metadata={"axes": "YXS"},
    )
    return {
        "converted": True,
        "output_path": str(output_path),
        "openslide_level": level,
        "level_downsample": downsample,
        "converted_width": width,
        "converted_height": height,
    }


def prepare_uploaded_image(uploaded_file: Any) -> dict[str, Any]:
    if is_ndpi_file(uploaded_file.name):
        original_path = save_uploaded_file(uploaded_file, ORIGINAL_NDPI_DIR / uploaded_file.name)
        converted_path = converted_ome_tiff_path(uploaded_file.name)
        conversion = convert_ndpi_to_ome_tiff(original_path, converted_path)
        return {
            "image_name": converted_path.name,
            "image_path": converted_path,
            "source_image_path": original_path,
            "source_format": "ndpi",
            "conversion": conversion,
        }

    image_path = save_uploaded_image(uploaded_file)
    return {
        "image_name": uploaded_file.name,
        "image_path": image_path,
        "source_image_path": image_path,
        "source_format": Path(uploaded_file.name).suffix.lower().lstrip("."),
        "conversion": {},
    }


def open_wsi_slide(wsi_path: Path) -> Any:
    try:
        import openslide
    except ImportError as error:
        raise RuntimeError(
            "WSI patch作成には openslide-python と openslide-bin が必要です。"
            "次を実行してください: pip install -r requirements.txt"
        ) from error
    return openslide.OpenSlide(str(wsi_path))


def save_uploaded_wsi(uploaded_file: Any) -> Path:
    return save_uploaded_file(uploaded_file, ORIGINAL_WSI_DIR / uploaded_file.name)


def wsi_mpp(slide: Any) -> tuple[str, str]:
    properties = getattr(slide, "properties", {})
    return (
        str(properties.get("openslide.mpp-x", "")),
        str(properties.get("openslide.mpp-y", "")),
    )


def make_wsi_thumbnail(wsi_path: Path) -> tuple[Image.Image, dict[str, Any]]:
    slide = open_wsi_slide(wsi_path)
    try:
        width, height = slide.dimensions
        thumbnail = slide.get_thumbnail(WSI_THUMBNAIL_MAX_SIZE).convert("RGB")
        mpp_x, mpp_y = wsi_mpp(slide)
    finally:
        slide.close()

    thumb_width, thumb_height = thumbnail.size
    return thumbnail, {
        "wsi_width": width,
        "wsi_height": height,
        "thumbnail_width": thumb_width,
        "thumbnail_height": thumb_height,
        "scale_x": width / thumb_width,
        "scale_y": height / thumb_height,
        "mpp_x": mpp_x,
        "mpp_y": mpp_y,
    }


def roi_from_thumbnail_canvas(canvas_json: dict[str, Any] | None, thumbnail_info: dict[str, Any]) -> dict[str, int] | None:
    if not canvas_json:
        return None
    rectangles = [obj for obj in canvas_json.get("objects", []) if obj.get("type") == "rect"]
    if not rectangles:
        return None
    roi = rectangles[-1]
    left = safe_float(roi.get("left"), 0.0) or 0.0
    top = safe_float(roi.get("top"), 0.0) or 0.0
    width = (safe_float(roi.get("width"), 0.0) or 0.0) * (safe_float(roi.get("scaleX"), 1.0) or 1.0)
    height = (safe_float(roi.get("height"), 0.0) or 0.0) * (safe_float(roi.get("scaleY"), 1.0) or 1.0)
    if width <= 0 or height <= 0:
        return None
    return {
        "x": max(0, int(round(left * thumbnail_info["scale_x"]))),
        "y": max(0, int(round(top * thumbnail_info["scale_y"]))),
        "width": max(1, int(round(width * thumbnail_info["scale_x"]))),
        "height": max(1, int(round(height * thumbnail_info["scale_y"]))),
    }


def clamp_patch_origin(x: int, y: int, patch_size: int, wsi_width: int, wsi_height: int) -> tuple[int, int]:
    return (
        max(0, min(x, max(0, wsi_width - patch_size))),
        max(0, min(y, max(0, wsi_height - patch_size))),
    )


def patch_image_path(wsi_name: str, patch_id: str) -> Path:
    return PATCH_IMAGE_DIR / f"{safe_file_stem(Path(wsi_name).stem)}_{safe_file_stem(patch_id)}.png"


def create_wsi_patch(
    wsi_path: Path,
    wsi_name: str,
    patch_x: int,
    patch_y: int,
    patch_size: int,
    thumbnail_info: dict[str, Any],
    target_mpp: str,
) -> dict[str, Any]:
    patch_x, patch_y = clamp_patch_origin(
        patch_x,
        patch_y,
        patch_size,
        int(thumbnail_info["wsi_width"]),
        int(thumbnail_info["wsi_height"]),
    )
    patch_id = f"patch_x{patch_x}_y{patch_y}_{patch_size}"
    output_path = patch_image_path(wsi_name, patch_id)
    if not output_path.exists():
        slide = open_wsi_slide(wsi_path)
        try:
            patch = slide.read_region((patch_x, patch_y), 0, (patch_size, patch_size)).convert("RGB")
        finally:
            slide.close()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        patch.save(output_path)

    return {
        "image_name": output_path.name,
        "image_path": output_path,
        "source_image_path": wsi_path,
        "source_format": "wsi_patch",
        "patch_metadata": {
            "source_wsi_name": wsi_name,
            "patch_id": patch_id,
            "patch_x": patch_x,
            "patch_y": patch_y,
            "patch_width": patch_size,
            "patch_height": patch_size,
            "target_mpp": target_mpp,
            "mpp_x": thumbnail_info.get("mpp_x", ""),
            "mpp_y": thumbnail_info.get("mpp_y", ""),
        },
    }


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def safe_round(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def canvas_object_label(obj: dict[str, Any], fallback_label: str) -> str:
    label = obj.get("label")
    if label in LABELS:
        return label

    stroke = str(obj.get("stroke", "")).lower()
    fill = str(obj.get("fill", "")).lower()
    for label_name, color in LABEL_COLORS.items():
        if stroke == color.lower() or fill == color.lower():
            return label_name
    return fallback_label


def normalize_canvas_object(
    obj: dict[str, Any],
    image_name: str,
    scale_factor: float,
    fallback_label: str,
    region_type: str,
    created_at: str,
) -> dict[str, Any] | None:
    obj_type = obj.get("type")
    if obj_type not in {"circle", "rect"}:
        return None

    label = canvas_object_label(obj, fallback_label)
    left = safe_float(obj.get("left"))
    top = safe_float(obj.get("top"))
    scale_x = safe_float(obj.get("scaleX"), 1.0)
    scale_y = safe_float(obj.get("scaleY"), 1.0)

    if None in (left, top, scale_x, scale_y):
        return None

    if obj_type == "circle":
        radius = safe_float(obj.get("radius"))
        if radius is None:
            return None
        width_display = radius * 2 * scale_x
        height_display = radius * 2 * scale_y
    else:
        rect_width = safe_float(obj.get("width"))
        rect_height = safe_float(obj.get("height"))
        if None in (rect_width, rect_height):
            return None
        width_display = rect_width * scale_x
        height_display = rect_height * scale_y

    if width_display <= 0 or height_display <= 0:
        return None

    inverse_scale = 1 / scale_factor
    x_display = left + width_display / 2
    y_display = top + height_display / 2
    width_original = width_display * inverse_scale
    height_original = height_display * inverse_scale
    x_original = x_display * inverse_scale
    y_original = y_display * inverse_scale
    candidate_source = obj.get("candidate_source", "manual")
    if candidate_source not in CANDIDATE_SOURCES:
        candidate_source = "manual"
    default_status = "confirmed_by_human" if candidate_source == "manual" else "candidate_unconfirmed"
    annotation_status = obj.get("annotation_status", default_status)
    used_for_training = safe_bool(obj.get("used_for_training"), candidate_source == "manual")

    return {
        "image_name": image_name,
        "label": label,
        # Backward-compatible aliases.
        "x": safe_round(x_original),
        "y": safe_round(y_original),
        "width": safe_round(width_original),
        "height": safe_round(height_original),
        "x_original": safe_round(x_original),
        "y_original": safe_round(y_original),
        "bbox_width_original": safe_round(width_original),
        "bbox_height_original": safe_round(height_original),
        "x_in_display": safe_round(x_display),
        "y_in_display": safe_round(y_display),
        "scale_factor": safe_round(scale_factor, 6),
        "region_type": region_type,
        "candidate_source": candidate_source,
        "annotation_status": annotation_status,
        "used_for_training": used_for_training,
        "source_model": obj.get("source_model", ""),
        "source_image_name": obj.get("source_image_name", image_name),
        "confidence": safe_float(obj.get("confidence"), 1.0),
        "created_at": obj.get("created_at", created_at),
    }


def annotations_from_canvas(
    canvas_json: dict[str, Any] | None,
    image_name: str | None,
    scale_factor: float,
    fallback_label: str,
    region_type: str,
) -> list[dict[str, Any]]:
    if not canvas_json or not image_name:
        return []

    created_at = datetime.now().isoformat(timespec="seconds")
    annotations = []
    for obj in canvas_json.get("objects", []):
        annotation = normalize_canvas_object(
            obj,
            image_name,
            scale_factor,
            fallback_label,
            region_type,
            created_at,
        )
        if annotation:
            annotations.append(annotation)
    return annotations


def apply_context_to_annotations(
    annotations: list[dict[str, Any]],
    metadata: dict[str, Any],
    region_annotations: dict[str, Any],
) -> list[dict[str, Any]]:
    region_type = region_annotations.get("global_region_type", "unknown")
    return [
        apply_patch_coordinate_context(
            normalize_annotation_status({**item, **metadata, "region_type": item.get("region_type", region_type)}),
            metadata,
        )
        for item in annotations
    ]


def apply_patch_coordinate_context(annotation: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = annotation.copy()
    patch_x = safe_float(metadata.get("patch_x"))
    patch_y = safe_float(metadata.get("patch_y"))
    if patch_x is None or patch_y is None:
        return normalized

    x_in_patch = safe_float(normalized.get("x_original"), safe_float(normalized.get("x")))
    y_in_patch = safe_float(normalized.get("y_original"), safe_float(normalized.get("y")))
    if x_in_patch is None or y_in_patch is None:
        return normalized

    normalized["x_in_patch"] = safe_round(x_in_patch)
    normalized["y_in_patch"] = safe_round(y_in_patch)
    normalized["x_wsi"] = safe_round(patch_x + x_in_patch)
    normalized["y_wsi"] = safe_round(patch_y + y_in_patch)
    normalized["patch_x"] = metadata.get("patch_x", "")
    normalized["patch_y"] = metadata.get("patch_y", "")
    normalized["source_wsi_name"] = metadata.get("source_wsi_name", "")
    normalized["patch_id"] = metadata.get("patch_id", "")
    return normalized


def normalize_annotation_status(annotation: dict[str, Any]) -> dict[str, Any]:
    """Backfill AI-candidate status fields while preserving explicit human review decisions."""
    normalized = annotation.copy()
    source = normalized.get("candidate_source") or "manual"
    if source not in CANDIDATE_SOURCES:
        source = "manual"

    status = normalized.get("annotation_status")
    if status not in ANNOTATION_STATUSES:
        status = "confirmed_by_human" if source == "manual" else "candidate_unconfirmed"

    used_for_training = safe_bool(normalized.get("used_for_training"), source == "manual")
    if status == "rejected":
        used_for_training = False

    normalized["candidate_source"] = source
    normalized["annotation_status"] = status
    normalized["used_for_training"] = used_for_training
    return normalized


def training_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_annotation_status(item) for item in annotations]
    return [item for item in normalized if item.get("used_for_training") is True]


def exportable_annotations(annotations: list[dict[str, Any]], used_for_training_only: bool) -> list[dict[str, Any]]:
    if used_for_training_only:
        return training_annotations(annotations)
    normalized = [normalize_annotation_status(item) for item in annotations]
    return [item for item in normalized if item.get("annotation_status") != "rejected"]


def filter_annotations_by_objective(
    annotations: list[dict[str, Any]],
    objective_filter: str,
) -> list[dict[str, Any]]:
    if objective_filter == "all":
        return annotations
    return [
        item
        for item in annotations
        if item.get("objective_magnification", "unknown") == objective_filter
    ]


def fabric_object_from_annotation(annotation: dict[str, Any], scale_factor: float) -> dict[str, Any]:
    label = annotation.get("label", "ignore")
    color = LABEL_COLORS.get(label, LABEL_COLORS["ignore"])
    width = (
        safe_float(annotation.get("bbox_width_original"), safe_float(annotation.get("width"), 0.0))
        or 0.0
    ) * scale_factor
    height = (
        safe_float(annotation.get("bbox_height_original"), safe_float(annotation.get("height"), 0.0))
        or 0.0
    ) * scale_factor
    center_x = (
        safe_float(annotation.get("x_original"), safe_float(annotation.get("x"), 0.0))
        or 0.0
    ) * scale_factor
    center_y = (
        safe_float(annotation.get("y_original"), safe_float(annotation.get("y"), 0.0))
        or 0.0
    ) * scale_factor

    return {
        "type": "rect",
        "left": center_x - width / 2,
        "top": center_y - height / 2,
        "width": width,
        "height": height,
        "fill": "rgba(255, 255, 255, 0)",
        "stroke": color,
        "strokeWidth": 3,
        "scaleX": 1,
        "scaleY": 1,
        "label": label,
        "candidate_source": annotation.get("candidate_source", "manual"),
        "annotation_status": annotation.get("annotation_status", "confirmed_by_human"),
        "used_for_training": bool(annotation.get("used_for_training", True)),
        "source_model": annotation.get("source_model", ""),
        "source_image_name": annotation.get("source_image_name", annotation.get("image_name", "")),
        "confidence": safe_float(annotation.get("confidence"), 1.0),
        "created_at": annotation.get("created_at", datetime.now().isoformat(timespec="seconds")),
    }


def canvas_json_from_annotations(
    annotations: list[dict[str, Any]],
    width: int,
    height: int,
    scale_factor: float,
) -> dict[str, Any]:
    return {
        "version": "5.2.4",
        "objects": [fabric_object_from_annotation(item, scale_factor) for item in annotations],
        "background": "",
        "width": width,
        "height": height,
    }


def candidate_rows_from_file(uploaded_file: Any) -> list[dict[str, Any]]:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file).fillna("").to_dict(orient="records")

    payload = json.loads(uploaded_file.getvalue().decode("utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        candidates = payload.get("candidates", payload.get("annotations", []))
        if isinstance(candidates, list):
            return [row for row in candidates if isinstance(row, dict)]
    return []


def candidate_source_from_row(row: dict[str, Any], fallback_source: str) -> str:
    source_model = str(row.get("source_model", "")).lower()
    if "open" in source_model and "eoe" in source_model:
        return "imported_open_eoe"
    if "cellpose" in source_model:
        return "imported_cellpose"
    return fallback_source if fallback_source in CANDIDATE_IMPORT_SOURCES else "imported_custom_model"


def normalize_imported_candidate(
    row: dict[str, Any],
    image_name: str,
    metadata: dict[str, Any],
    fallback_source: str,
    imported_at: str,
) -> dict[str, Any] | None:
    source_model = str(row.get("source_model", "")).strip()
    source_image_name = str(row.get("source_image_name", "")).strip()
    if not source_model or not source_image_name:
        return None
    label = str(row.get("label", "eosinophil")).strip()
    if label not in LABELS:
        label = "other_cell"

    x_value = safe_float(row.get("x_in_patch"), safe_float(row.get("x_original")))
    y_value = safe_float(row.get("y_in_patch"), safe_float(row.get("y_original")))
    box_width = safe_float(
        row.get("bbox_width"),
        safe_float(row.get("bbox_width_original"), safe_float(row.get("width"))),
    )
    box_height = safe_float(
        row.get("bbox_height"),
        safe_float(row.get("bbox_height_original"), safe_float(row.get("height"))),
    )
    confidence = safe_float(row.get("confidence"), 0.0)
    if None in (x_value, y_value, box_width, box_height):
        return None
    if box_width <= 0 or box_height <= 0:
        return None

    patch_x = row.get("patch_x", metadata.get("patch_x", ""))
    patch_y = row.get("patch_y", metadata.get("patch_y", ""))
    patch_x_float = safe_float(patch_x)
    patch_y_float = safe_float(patch_y)
    x_wsi = safe_float(row.get("x_wsi"))
    y_wsi = safe_float(row.get("y_wsi"))
    if x_wsi is None and patch_x_float is not None:
        x_wsi = patch_x_float + x_value
    if y_wsi is None and patch_y_float is not None:
        y_wsi = patch_y_float + y_value

    return normalize_annotation_status(
        {
            "image_name": image_name,
            "source_model": source_model,
            "source_image_name": source_image_name,
            "label": label,
            "x": safe_round(x_value),
            "y": safe_round(y_value),
            "width": safe_round(box_width),
            "height": safe_round(box_height),
            "x_original": safe_round(x_value),
            "y_original": safe_round(y_value),
            "bbox_width_original": safe_round(box_width),
            "bbox_height_original": safe_round(box_height),
            "x_in_patch": safe_round(x_value),
            "y_in_patch": safe_round(y_value),
            "x_wsi": safe_round(x_wsi),
            "y_wsi": safe_round(y_wsi),
            "patch_id": row.get("patch_id", metadata.get("patch_id", "")),
            "patch_x": patch_x,
            "patch_y": patch_y,
            "source_wsi_name": metadata.get("source_wsi_name", ""),
            "candidate_source": candidate_source_from_row(row, fallback_source),
            "annotation_status": "candidate_unconfirmed",
            "used_for_training": False,
            "confidence": confidence,
            "created_at": imported_at,
        }
    )


def imported_candidate_annotations(
    uploaded_file: Any,
    image_name: str,
    metadata: dict[str, Any],
    fallback_source: str,
) -> list[dict[str, Any]]:
    imported_at = datetime.now().isoformat(timespec="seconds")
    annotations = []
    for row in candidate_rows_from_file(uploaded_file):
        annotation = normalize_imported_candidate(row, image_name, metadata, fallback_source, imported_at)
        if annotation:
            annotations.append(annotation)
    return annotations


def image_area_mm2_from_pixel_size(
    image_size: tuple[int, int] | None,
    pixel_size_um: Any,
) -> float | None:
    pixel_size = safe_float(pixel_size_um)
    if not image_size or not pixel_size or pixel_size <= 0:
        return None
    image_width, image_height = image_size
    return (image_width * pixel_size / 1000) * (image_height * pixel_size / 1000)


def calculate_ecrs_counts(
    annotations: list[dict[str, Any]],
    metadata: dict[str, Any],
    image_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    total_count = len([item for item in annotations if item.get("label") != "ignore"])
    eos_count = sum(1 for item in annotations if item.get("label") == "eosinophil")
    ratio = eos_count / total_count if total_count else 0.0
    hpf_area = safe_float(metadata.get("hpf_area_mm2"))
    image_area = image_area_mm2_from_pixel_size(image_size, metadata.get("pixel_size_um"))
    is_single_hpf = bool(metadata.get("image_is_single_hpf"))

    if image_area and image_area > 0:
        eos_per_mm2 = round(eos_count / image_area, 6)
        eos_per_hpf = (
            round(eos_per_mm2 * hpf_area, 6)
            if hpf_area and hpf_area > 0
            else "not_calculated"
        )
    else:
        eos_per_mm2 = "not_calculated"
        eos_per_hpf = eos_count if is_single_hpf else "not_calculated"

    return {
        "eosinophil_count": eos_count,
        "total_annotated_count": total_count,
        "eosinophil_ratio": round(ratio, 6),
        "eos_per_HPF": eos_per_hpf,
        "eos_per_mm2": eos_per_mm2,
    }


def count_annotations(
    annotations: list[dict[str, Any]],
    metadata: dict[str, Any],
    image_size: tuple[int, int] | None = None,
) -> pd.DataFrame:
    label_counts = {label: 0 for label in LABELS}
    for item in annotations:
        label = item.get("label")
        if label in label_counts:
            label_counts[label] += 1

    rows = [{"metric": f"label_{label}_count", "value": count} for label, count in label_counts.items()]
    ecrs_counts = calculate_ecrs_counts(annotations, metadata, image_size)
    rows.extend({"metric": key, "value": value} for key, value in ecrs_counts.items())
    return pd.DataFrame(rows)


def annotations_dataframe(annotations: list[dict[str, Any]]) -> pd.DataFrame:
    if not annotations:
        return pd.DataFrame()
    return pd.DataFrame(annotations)


def counts_with_metadata(
    counts_df: pd.DataFrame,
    metadata: dict[str, Any],
    region_annotations: dict[str, Any],
    objective_filter: str,
) -> pd.DataFrame:
    counts_with_context = counts_df.copy()
    for field in METADATA_FIELDS:
        counts_with_context[field] = metadata.get(field, "")
    counts_with_context["global_region_type"] = region_annotations.get("global_region_type", "unknown")
    counts_with_context["export_objective_filter"] = objective_filter
    return counts_with_context


def dataset_manifest_row(
    image_name: str,
    original_image_path: str,
    metadata: dict[str, Any],
    annotations: list[dict[str, Any]],
    saved_at: str,
    image_size: tuple[int, int] | None = None,
    export_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    ecrs_counts = calculate_ecrs_counts(annotations, metadata, image_size)
    export_paths = export_paths or image_export_paths(image_name, metadata)
    return {
        "image_name": image_name,
        "original_image_path": original_image_path,
        "annotation_json_path": str(export_paths["annotations_json"]),
        "annotation_csv_path": str(export_paths["annotations_csv"]),
        "count_csv_path": str(export_paths["counts_csv"]),
        "yolo_label_path": str(export_paths["yolo_labels"]),
        "project_template": metadata.get("project_template", ""),
        "disease_context": metadata.get("disease_context", ""),
        "source_organ": metadata.get("source_organ", ""),
        "tissue_type": metadata.get("tissue_type", ""),
        "tissue_region": metadata.get("tissue_region", ""),
        "staining": metadata.get("staining", ""),
        "objective_magnification": metadata.get("objective_magnification", ""),
        "source_wsi_name": metadata.get("source_wsi_name", ""),
        "patch_id": metadata.get("patch_id", ""),
        "patch_x": metadata.get("patch_x", ""),
        "patch_y": metadata.get("patch_y", ""),
        "patch_width": metadata.get("patch_width", ""),
        "patch_height": metadata.get("patch_height", ""),
        "target_mpp": metadata.get("target_mpp", ""),
        "mpp_x": metadata.get("mpp_x", ""),
        "mpp_y": metadata.get("mpp_y", ""),
        "pixel_size_um": metadata.get("pixel_size_um", ""),
        "hpf_area_mm2": metadata.get("hpf_area_mm2", ""),
        "annotator": metadata.get("annotator", ""),
        "reviewed": bool(metadata.get("reviewed", False)),
        "exported": bool(metadata.get("exported", False)),
        "annotation_count": len(annotations),
        "eosinophil_count": ecrs_counts["eosinophil_count"],
        "saved_at": saved_at,
    }


def yolo_lines(
    annotations: list[dict[str, Any]],
    image_size: tuple[int, int] | None,
    exclude_ignore: bool,
    used_for_training_only: bool = True,
) -> list[str]:
    if not image_size:
        return []
    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        return []

    lines = []
    for item in exportable_annotations(annotations, used_for_training_only):
        label = item.get("label")
        if exclude_ignore and label == "ignore":
            continue
        if label not in YOLO_CLASS_IDS:
            continue
        x_center = safe_float(item.get("x_original"), safe_float(item.get("x")))
        y_center = safe_float(item.get("y_original"), safe_float(item.get("y")))
        box_width = safe_float(item.get("bbox_width_original"), safe_float(item.get("width")))
        box_height = safe_float(item.get("bbox_height_original"), safe_float(item.get("height")))
        if None in (x_center, y_center, box_width, box_height):
            continue
        lines.append(
            " ".join(
                [
                    str(YOLO_CLASS_IDS[label]),
                    f"{x_center / image_width:.6f}",
                    f"{y_center / image_height:.6f}",
                    f"{box_width / image_width:.6f}",
                    f"{box_height / image_height:.6f}",
                ]
            )
        )
    return lines


def write_data_yaml() -> Path:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    class_names = [label for label, _ in sorted(YOLO_CLASS_IDS.items(), key=lambda item: item[1])]
    yaml_path = DATASET_DIR / "data.yaml"
    yaml_lines = [
        f"path: {DATASET_DIR.as_posix()}",
        "train: images",
        "val: images",
        "test: images",
        f"nc: {len(class_names)}",
        "names:",
    ]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(class_names))
    yaml_path.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    return yaml_path


def source_image_path(payload: dict[str, Any]) -> Path | None:
    candidates = [
        Path(str(payload.get("original_image_path", ""))),
        PATCH_IMAGE_DIR / str(payload.get("image_name", "")),
        IMAGE_DIR / str(payload.get("image_name", "")),
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    return None


def generate_yolo_training_dataset(
    only_reviewed_or_exported: bool,
    exclude_ignore: bool,
    used_for_training_only: bool,
) -> dict[str, Any]:
    ensure_directories()
    exported_images = 0
    exported_labels = 0
    skipped_images = []

    for payload in saved_annotation_payloads():
        metadata = payload.get("image_metadata", {})
        if only_reviewed_or_exported and not (metadata.get("reviewed") or metadata.get("exported")):
            skipped_images.append(payload.get("image_name", "unknown"))
            continue

        image_name = payload.get("image_name", "")
        image_size = image_size_from_payload(payload)
        image_source = source_image_path(payload)
        if not image_name or image_size is None or image_source is None:
            skipped_images.append(image_name or "unknown")
            continue

        stem = payload_export_stem(payload)
        image_destination = DATASET_IMAGE_DIR / f"{stem}{image_source.suffix.lower()}"
        label_destination = DATASET_LABEL_DIR / f"{stem}.txt"

        shutil.copy2(image_source, image_destination)
        label_destination.write_text(
            "\n".join(
                yolo_lines(
                    payload.get("annotations", []),
                    image_size,
                    exclude_ignore,
                    used_for_training_only,
                )
            ),
            encoding="utf-8",
        )
        exported_images += 1
        exported_labels += 1

    yaml_path = write_data_yaml()
    return {
        "images": exported_images,
        "labels": exported_labels,
        "skipped": skipped_images,
        "data_yaml": yaml_path,
    }


def safe_file_stem(value: str) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return safe_stem or "unknown"


def export_file_stem(image_name: str, metadata: dict[str, Any]) -> str:
    image_stem = safe_file_stem(Path(image_name).stem)
    specimen_id = safe_file_stem(str(metadata.get("specimen_id", "")))
    slide_id = safe_file_stem(str(metadata.get("slide_id", "")))
    if specimen_id != "unknown" and slide_id != "unknown":
        return f"{specimen_id}_{slide_id}_{image_stem}"
    if specimen_id != "unknown":
        return f"{specimen_id}_{image_stem}"
    if slide_id != "unknown":
        return f"{slide_id}_{image_stem}"
    return image_stem or "image"


def payload_export_stem(payload: dict[str, Any]) -> str:
    existing_stem = str(payload.get("export_file_stem", "")).strip()
    if existing_stem:
        return safe_file_stem(existing_stem)
    return export_file_stem(
        str(payload.get("image_name", "")),
        payload.get("image_metadata", {}),
    )


def image_export_paths(image_name: str, metadata: dict[str, Any]) -> dict[str, Path]:
    stem = export_file_stem(image_name, metadata)
    return {
        "annotations_json": ANNOTATION_DIR / f"{stem}_annotations.json",
        "annotations_csv": EXPORT_DIR / f"{stem}_annotations.csv",
        "counts_csv": EXPORT_DIR / f"{stem}_counts.csv",
        "yolo_labels": YOLO_DIR / f"{stem}.txt",
    }


def load_saved_annotation_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("annotations", []), list):
        return payload
    return None


def saved_annotation_payloads() -> list[dict[str, Any]]:
    payloads = []
    for path in sorted(ANNOTATION_DIR.glob("*_annotations.json")):
        payload = load_saved_annotation_payload(path)
        if payload:
            payloads.append(payload)
    return payloads


def image_size_from_payload(payload: dict[str, Any]) -> tuple[int, int] | None:
    image_size = payload.get("image_size")
    if not isinstance(image_size, dict):
        return None
    width = safe_float(image_size.get("width"))
    height = safe_float(image_size.get("height"))
    if not width or not height:
        return None
    return int(width), int(height)


def regenerate_dataset_exports() -> None:
    payloads = saved_annotation_payloads()
    manifest_rows = []
    annotation_rows = []
    count_frames = []

    for payload in payloads:
        image_name = payload.get("image_name", "")
        original_image_path = payload.get("original_image_path", "")
        metadata = payload.get("image_metadata", {})
        region_annotations = payload.get("region_annotations", default_region_annotations())
        annotations = payload.get("annotations", [])
        saved_at = payload.get("saved_at", "")
        image_size = image_size_from_payload(payload)
        export_paths = image_export_paths(image_name, metadata)

        manifest_rows.append(
            dataset_manifest_row(
                image_name,
                original_image_path,
                metadata,
                annotations,
                saved_at,
                image_size,
                export_paths,
            )
        )
        annotation_rows.extend(annotations)

        counts_df = count_annotations(annotations, metadata, image_size)
        counts_context = counts_with_metadata(
            counts_df,
            metadata,
            region_annotations,
            payload.get("export_objective_filter", "all"),
        )
        counts_context.insert(0, "image_name", image_name)
        counts_context["saved_at"] = saved_at
        count_frames.append(counts_context)

    pd.DataFrame(manifest_rows, columns=MANIFEST_FIELDS).to_csv(
        EXPORT_DIR / "dataset_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )
    annotation_export = annotations_dataframe(annotation_rows)
    annotation_export.to_csv(
        EXPORT_DIR / "annotations.csv",
        index=False,
        encoding="utf-8-sig",
    )
    annotation_export.to_csv(
        EXPORT_DIR / "metadata.csv",
        index=False,
        encoding="utf-8-sig",
    )
    if count_frames:
        pd.concat(count_frames, ignore_index=True).to_csv(
            EXPORT_DIR / "counts.csv",
            index=False,
            encoding="utf-8-sig",
        )
    else:
        pd.DataFrame().to_csv(EXPORT_DIR / "counts.csv", index=False, encoding="utf-8-sig")


def save_outputs(
    image_name: str,
    original_image_path: str,
    image_size: tuple[int, int] | None,
    annotations: list[dict[str, Any]],
    counts_df: pd.DataFrame,
    metadata: dict[str, Any],
    region_annotations: dict[str, Any],
    objective_filter: str,
    exclude_ignore_from_yolo: bool,
    used_for_training_only_export: bool,
) -> dict[str, Path]:
    saved_at = datetime.now().isoformat(timespec="seconds")
    paths = image_export_paths(image_name, metadata)
    export_stem = export_file_stem(image_name, metadata)
    manifest_path = EXPORT_DIR / "dataset_manifest.csv"
    aggregate_annotations_path = EXPORT_DIR / "annotations.csv"
    aggregate_counts_path = EXPORT_DIR / "counts.csv"
    metadata_path = EXPORT_DIR / "metadata.csv"

    payload = {
        "schema_version": "2.3",
        "image_name": image_name,
        "original_image_path": original_image_path,
        "export_file_stem": export_stem,
        "labels": LABELS,
        "primary_labels": PRIMARY_LABELS,
        "label_colors": LABEL_COLORS,
        "yolo_class_ids": YOLO_CLASS_IDS,
        "candidate_sources": CANDIDATE_SOURCES,
        "annotation_statuses": ANNOTATION_STATUSES,
        "annotation_status_fields": ANNOTATION_STATUS_FIELDS,
        "image_size": {
            "width": image_size[0] if image_size else None,
            "height": image_size[1] if image_size else None,
        },
        "image_metadata": metadata,
        "region_annotations": region_annotations,
        "export_objective_filter": objective_filter,
        "annotations": annotations,
        "saved_at": saved_at,
    }
    paths["annotations_json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    annotations_dataframe(annotations).to_csv(
        paths["annotations_csv"],
        index=False,
        encoding="utf-8-sig",
    )
    counts_with_metadata(counts_df, metadata, region_annotations, objective_filter).to_csv(
        paths["counts_csv"],
        index=False,
        encoding="utf-8-sig",
    )
    paths["yolo_labels"].write_text(
        "\n".join(
            yolo_lines(
                annotations,
                image_size,
                exclude_ignore_from_yolo,
                used_for_training_only_export,
            )
        ),
        encoding="utf-8",
    )
    regenerate_dataset_exports()

    return {
        "annotations_json": paths["annotations_json"],
        "annotations_csv": paths["annotations_csv"],
        "counts_csv": paths["counts_csv"],
        "aggregate_annotations_csv": aggregate_annotations_path,
        "aggregate_counts_csv": aggregate_counts_path,
        "metadata_csv": metadata_path,
        "dataset_manifest_csv": manifest_path,
        "yolo_labels": paths["yolo_labels"],
    }


def load_annotation_payload(uploaded_file: Any) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    payload = json.loads(uploaded_file.getvalue().decode("utf-8"))
    if isinstance(payload, list):
        return [normalize_annotation_status(item) for item in payload], {}, default_region_annotations()
    if isinstance(payload, dict):
        annotations = [normalize_annotation_status(item) for item in payload.get("annotations", [])]
        metadata = payload.get("image_metadata") or metadata_from_restored_annotations(annotations) or {}
        region_annotations = payload.get("region_annotations") or default_region_annotations()
        return annotations, metadata, region_annotations
    return [], {}, default_region_annotations()


def metadata_from_restored_annotations(annotations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not annotations:
        return None
    first_annotation = annotations[0]
    metadata = {field: first_annotation.get(field, "") for field in METADATA_FIELDS}
    if metadata.get("project_template"):
        return metadata
    return None


def select_index(options: list[str], value: Any, fallback: str) -> int:
    value = value if value in options else fallback
    return options.index(value)


def missing_required_metadata(metadata: dict[str, Any]) -> list[str]:
    missing = []
    for field in REQUIRED_METADATA_FIELDS:
        value = metadata.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def render_project_template() -> str:
    st.sidebar.subheader("プロジェクトテンプレート")
    current_template = st.session_state.project_template
    project_template = st.sidebar.selectbox(
        "project_template（保存値）",
        PROJECT_TEMPLATES,
        index=select_index(PROJECT_TEMPLATES, current_template, "ECRS_nasal_polyp"),
    )
    if project_template != st.session_state.last_template:
        existing = st.session_state.image_metadata.copy()
        defaults = default_image_metadata(project_template)
        # Preserve user-entered identifiers while applying template recommendations.
        for field in [
            "specimen_id",
            "slide_id",
            "annotator",
            "patient_id_hash",
            "source_wsi_name",
            "patch_id",
            "patch_x",
            "patch_y",
            "patch_width",
            "patch_height",
            "target_mpp",
            "mpp_x",
            "mpp_y",
            "notes",
        ]:
            defaults[field] = existing.get(field, defaults.get(field, ""))
        st.session_state.project_template = project_template
        st.session_state.image_metadata = defaults
        st.session_state.last_template = project_template
    return project_template


def render_metadata_inputs(project_template: str) -> dict[str, Any]:
    st.sidebar.subheader("画像メタデータ")
    current = st.session_state.image_metadata
    current["project_template"] = project_template

    metadata = {
        "project_template": project_template,
        "disease_context": st.sidebar.text_input(
            "疾患・研究背景 disease_context *",
            value=str(current.get("disease_context", "unknown")),
        ),
        "source_organ": st.sidebar.selectbox(
            "由来臓器 source_organ",
            SOURCE_ORGANS,
            index=select_index(SOURCE_ORGANS, current.get("source_organ"), "unknown"),
        ),
        "tissue_type": st.sidebar.selectbox(
            "組織種 tissue_type *",
            TISSUE_TYPES,
            index=select_index(TISSUE_TYPES, current.get("tissue_type"), "unknown"),
        ),
        "tissue_region": st.sidebar.selectbox(
            "組織領域 tissue_region",
            TISSUE_REGIONS,
            index=select_index(TISSUE_REGIONS, current.get("tissue_region"), "unknown"),
        ),
        "staining": st.sidebar.selectbox(
            "染色 staining *",
            STAINING_OPTIONS,
            index=select_index(STAINING_OPTIONS, current.get("staining"), "unknown"),
        ),
        "objective_magnification": st.sidebar.selectbox(
            "対物倍率 objective_magnification *",
            OBJECTIVE_MAGNIFICATIONS,
            index=select_index(
                OBJECTIVE_MAGNIFICATIONS,
                current.get("objective_magnification"),
                "unknown",
            ),
        ),
        "specimen_id": st.sidebar.text_input("標本ID specimen_id *", value=str(current.get("specimen_id", ""))),
        "slide_id": st.sidebar.text_input("スライドID slide_id *", value=str(current.get("slide_id", ""))),
        "annotator": st.sidebar.text_input("アノテーター annotator *", value=str(current.get("annotator", ""))),
        "patient_id_hash": st.sidebar.text_input("匿名化患者ID patient_id_hash", value=str(current.get("patient_id_hash", ""))),
        "anatomical_site": st.sidebar.selectbox(
            "採取部位 anatomical_site",
            ANATOMICAL_SITES,
            index=select_index(ANATOMICAL_SITES, current.get("anatomical_site"), "unknown"),
        ),
        "scanner_or_microscope": st.sidebar.text_input(
            "スキャナ/顕微鏡 scanner_or_microscope",
            value=str(current.get("scanner_or_microscope", "")),
        ),
        "pixel_size_um": st.sidebar.text_input("pixel_size_um（um/px）", value=str(current.get("pixel_size_um", ""))),
        "hpf_area_mm2": st.sidebar.text_input("hpf_area_mm2（mm2）", value=str(current.get("hpf_area_mm2", ""))),
        "hpf_diameter_mm": st.sidebar.text_input(
            "hpf_diameter_mm（mm）",
            value=str(current.get("hpf_diameter_mm", "")),
        ),
        "image_is_single_hpf": st.sidebar.checkbox(
            "画像全体を1 HPFとして扱う",
            value=bool(current.get("image_is_single_hpf", False)),
            help="画像全体がちょうど1 high-power fieldを表す場合のみ有効にしてください。",
        ),
        "section_quality": st.sidebar.selectbox(
            "切片/画像品質 section_quality",
            SECTION_QUALITY_OPTIONS,
            index=select_index(SECTION_QUALITY_OPTIONS, current.get("section_quality"), "good"),
        ),
        "reviewed": st.sidebar.checkbox(
            "確認済み reviewed",
            value=bool(current.get("reviewed", False)),
            help="人が確認済みで、学習用export候補にできる画像として扱います。",
        ),
        "exported": st.sidebar.checkbox(
            "export対象 exported",
            value=bool(current.get("exported", False)),
            help="dataset export対象として扱います。",
        ),
        "source_wsi_name": st.sidebar.text_input("親WSI名 source_wsi_name", value=str(current.get("source_wsi_name", ""))),
        "patch_id": st.sidebar.text_input("patch_id", value=str(current.get("patch_id", ""))),
        "patch_x": st.sidebar.text_input("patch_x", value=str(current.get("patch_x", ""))),
        "patch_y": st.sidebar.text_input("patch_y", value=str(current.get("patch_y", ""))),
        "patch_width": st.sidebar.text_input("patch_width", value=str(current.get("patch_width", ""))),
        "patch_height": st.sidebar.text_input("patch_height", value=str(current.get("patch_height", ""))),
        "target_mpp": st.sidebar.text_input("target_mpp", value=str(current.get("target_mpp", ""))),
        "mpp_x": st.sidebar.text_input("mpp_x", value=str(current.get("mpp_x", ""))),
        "mpp_y": st.sidebar.text_input("mpp_y", value=str(current.get("mpp_y", ""))),
        "notes": st.sidebar.text_area("メモ notes", value=str(current.get("notes", "")), height=80),
    }
    st.session_state.image_metadata = metadata
    return metadata


def render_region_type() -> dict[str, Any]:
    st.sidebar.subheader("領域タイプ")
    current_region = st.session_state.region_annotations.get("global_region_type", "unknown")
    region_type = st.sidebar.selectbox(
        "画像全体の領域 global_region_type",
        REGION_TYPES,
        index=select_index(REGION_TYPES, current_region, "unknown"),
    )
    region_annotations = {
        "global_region_type": region_type,
        "regions": st.session_state.region_annotations.get("regions", []),
    }
    st.session_state.region_annotations = region_annotations
    return region_annotations


def render_label_controls() -> tuple[str, str, str, int]:
    st.sidebar.subheader("現在のラベル")
    quick_label = st.sidebar.radio(
        "よく使うラベル",
        PRIMARY_LABELS,
        captions=[LABEL_COLORS[label] for label in PRIMARY_LABELS],
    )
    active_label = st.sidebar.selectbox(
        "全ラベル",
        LABELS,
        index=LABELS.index(quick_label),
        help="初期評価では eosinophil と other/ignore の区別を主対象にします。",
    )

    st.sidebar.subheader("描画モード")
    drawing_mode = st.sidebar.selectbox(
        "drawing_mode（描画/編集）",
        ["circle", "rect", "transform"],
        index=0,
        help="transformでは選択した図形の移動、サイズ変更、削除ができます。",
    )
    stroke_width = st.sidebar.slider("線の太さ", min_value=1, max_value=8, value=3)
    return active_label, drawing_mode, LABEL_COLORS[active_label], stroke_width


def reset_for_new_image() -> None:
    st.session_state.canvas_objects = []
    st.session_state.annotation_table = []
    st.session_state.restored_annotations_key = None
    st.session_state.saved_image_key = None
    st.session_state.image_metadata = default_image_metadata(st.session_state.project_template)
    st.session_state.region_annotations = default_region_annotations()
    st.session_state.canvas_key_version += 1
    st.session_state.canvas_initial_drawing_pending = True


def render_sidebar() -> tuple[
    Any,
    Any,
    Any,
    str,
    str,
    dict[str, Any],
    dict[str, Any],
    str,
    str,
    str,
    int,
    bool,
    bool,
    bool,
]:
    st.sidebar.subheader("画像アップロード")
    uploaded_image = st.sidebar.file_uploader(
        "組織画像をアップロード",
        type=["jpg", "jpeg", "png", "tif", "tiff", "ndpi", "svs", "scn", "vms", "vmu"],
    )
    if uploaded_image and st.session_state.uploaded_source_name != uploaded_image.name:
        reset_for_new_image()
        st.session_state.uploaded_source_name = uploaded_image.name

    project_template = render_project_template()
    metadata = render_metadata_inputs(project_template)
    region_annotations = render_region_type()
    active_label, drawing_mode, stroke_color, stroke_width = render_label_controls()

    st.sidebar.subheader("エクスポート設定")
    objective_filter = st.sidebar.selectbox(
        "対物倍率フィルタ objective_magnification",
        ["all", *OBJECTIVE_MAGNIFICATIONS],
        index=0,
    )
    exclude_ignore_from_yolo = st.sidebar.checkbox("YOLO出力から ignore を除外", value=True)
    used_for_training_only_export = st.sidebar.checkbox(
        "used_for_training=true のみ出力",
        value=True,
        help="学習用exportでは有効のままにしてください。未確認のimport候補は学習データから除外されます。",
    )
    only_reviewed_or_exported = st.sidebar.checkbox(
        "YOLO datasetは reviewed/exported のみ",
        value=True,
        help="確認済みまたはexport対象として明示された画像だけを学習datasetに使います。",
    )

    st.sidebar.subheader("保存/復元")
    uploaded_annotations = st.sidebar.file_uploader("annotations.json を復元", type=["json"])
    st.sidebar.subheader("AI候補bboxのインポート")
    uploaded_candidates = st.sidebar.file_uploader("候補bbox CSV/JSONを読み込む", type=["csv", "json"])
    candidate_import_source = st.sidebar.selectbox(
        "import候補の由来 candidate_source",
        CANDIDATE_IMPORT_SOURCES,
        index=CANDIDATE_IMPORT_SOURCES.index("imported_open_eoe"),
    )

    return (
        uploaded_image,
        uploaded_annotations,
        uploaded_candidates,
        candidate_import_source,
        objective_filter,
        metadata,
        region_annotations,
        active_label,
        drawing_mode,
        stroke_color,
        stroke_width,
        exclude_ignore_from_yolo,
        used_for_training_only_export,
        only_reviewed_or_exported,
    )


def render_ecrs_notice(project_template: str) -> None:
    if project_template == "ECRS_nasal_polyp":
        st.info(
            "研究用ツールです。H&E染色された鼻茸/副鼻腔粘膜画像の好酸球定量補助を目的とします。"
            "臨床診断目的では使用しないでください。"
        )


def apply_patch_metadata_to_session(patch_metadata: dict[str, Any]) -> None:
    st.session_state.image_metadata.update(patch_metadata)


def render_wsi_patch_workflow(uploaded_image: Any) -> dict[str, Any] | None:
    try:
        wsi_path = save_uploaded_wsi(uploaded_image)
        thumbnail, thumbnail_info = make_wsi_thumbnail(wsi_path)
    except RuntimeError as error:
        st.error(str(error))
        return None
    except Exception as error:
        st.error(f"patch作成用にWSIファイルを開けませんでした: {error}")
        return None

    source_key = f"{uploaded_image.name}:{uploaded_image.size}"
    active_patch = st.session_state.active_patch
    if active_patch and st.session_state.active_patch_source == source_key:
        st.success(f"アノテーション用patchを読み込みました: {active_patch['image_name']}")
        if st.button("このWSIから別のpatchを作成", use_container_width=True):
            st.session_state.active_patch = None
            st.session_state.active_patch_source = None
            st.rerun()
        apply_patch_metadata_to_session(active_patch.get("patch_metadata", {}))
        return active_patch

    st.subheader("WSI ROIパッチ作成")
    st.caption(
        "低倍率thumbnail上で矩形ROIを選び、アノテーション用patchを作成します。"
        "巨大WSI全体はannotation canvasに直接載せません。"
    )
    st.caption(
        f"WSIサイズ: {thumbnail_info['wsi_width']} x {thumbnail_info['wsi_height']} px | "
        f"thumbnail: {thumbnail_info['thumbnail_width']} x {thumbnail_info['thumbnail_height']} px | "
        f"mpp: {thumbnail_info.get('mpp_x', '')}, {thumbnail_info.get('mpp_y', '')}"
    )

    controls = st.columns(4)
    patch_size = controls[0].selectbox("patchサイズ", PATCH_SIZE_OPTIONS, index=0)
    target_mpp = controls[1].text_input("target_mpp", value=str(thumbnail_info.get("mpp_x") or ""))
    manual_x = controls[2].number_input("patch_x", min_value=0, value=0, step=256)
    manual_y = controls[3].number_input("patch_y", min_value=0, value=0, step=256)

    roi_canvas = st_canvas(
        fill_color="rgba(255, 255, 255, 0.15)",
        stroke_width=3,
        stroke_color="#ff2d55",
        background_image=thumbnail,
        update_streamlit=True,
        height=thumbnail.size[1],
        width=thumbnail.size[0],
        drawing_mode="rect",
        key=f"wsi_roi_{uploaded_image.name}",
    )

    selected_roi = roi_from_thumbnail_canvas(roi_canvas.json_data, thumbnail_info)
    if selected_roi:
        patch_x = selected_roi["x"]
        patch_y = selected_roi["y"]
        st.info(
            f"選択ROIの左上座標: x={patch_x}, y={patch_y}。"
            f"{patch_size} x {patch_size} px のpatchを作成します。"
        )
    else:
        patch_x = int(manual_x)
        patch_y = int(manual_y)
        st.info("ROI矩形が未選択です。手入力の patch_x / patch_y を使用します。")

    if st.button("WSI ROIからpatchを作成", use_container_width=True):
        existing_metadata = st.session_state.image_metadata.copy()
        patch = create_wsi_patch(
            wsi_path=wsi_path,
            wsi_name=uploaded_image.name,
            patch_x=int(patch_x),
            patch_y=int(patch_y),
            patch_size=int(patch_size),
            thumbnail_info=thumbnail_info,
            target_mpp=target_mpp,
        )
        st.session_state.active_patch = patch
        st.session_state.active_patch_source = source_key
        st.session_state.uploaded_source_name = uploaded_image.name
        reset_for_new_image()
        st.session_state.image_metadata.update(existing_metadata)
        st.session_state.active_patch = patch
        st.session_state.active_patch_source = source_key
        apply_patch_metadata_to_session(patch["patch_metadata"])
        st.rerun()

    return None


def process_upload(
    uploaded_image: Any,
    uploaded_annotations: Any,
    display_image: Image.Image,
    prepared_image: dict[str, Any],
) -> None:
    image_key = f"{uploaded_image.name}:{uploaded_image.size}:{prepared_image['image_name']}"
    if st.session_state.saved_image_key != image_key:
        st.session_state.original_image_path = str(prepared_image["image_path"])
        st.session_state.saved_image_key = image_key

    st.session_state.image_name = str(prepared_image["image_name"])
    if uploaded_annotations:
        restore_key = f"{prepared_image['image_name']}:{uploaded_annotations.name}:{uploaded_annotations.size}"
        if st.session_state.restored_annotations_key != restore_key:
            restored, restored_metadata, restored_regions = load_annotation_payload(uploaded_annotations)
            st.session_state.annotation_table = restored
            if restored_metadata:
                st.session_state.image_metadata.update(restored_metadata)
                template = st.session_state.image_metadata.get("project_template", st.session_state.project_template)
                if template in PROJECT_TEMPLATES:
                    st.session_state.project_template = template
                    st.session_state.last_template = template
            st.session_state.region_annotations = restored_regions
            st.session_state.canvas_objects = canvas_json_from_annotations(
                restored,
                display_image.size[0],
                display_image.size[1],
                st.session_state.scale_factor,
            )["objects"]
            st.session_state.restored_annotations_key = restore_key
            st.session_state.canvas_key_version += 1
            st.session_state.canvas_initial_drawing_pending = True


def process_candidate_import(
    uploaded_candidates: Any,
    candidate_import_source: str,
    display_image: Image.Image,
) -> None:
    if not uploaded_candidates or not st.session_state.image_name:
        return
    import_key = (
        f"{st.session_state.image_name}:{uploaded_candidates.name}:"
        f"{uploaded_candidates.size}:{candidate_import_source}"
    )
    if st.session_state.candidate_import_key == import_key:
        return

    imported = imported_candidate_annotations(
        uploaded_candidates,
        st.session_state.image_name,
        st.session_state.image_metadata,
        candidate_import_source,
    )
    if not imported:
        st.warning("有効な候補bboxを読み込めませんでした。必須列/項目を確認してください。")
        st.session_state.candidate_import_key = import_key
        return

    existing = st.session_state.annotation_table or []
    st.session_state.annotation_table = [*existing, *imported]
    st.session_state.canvas_objects = canvas_json_from_annotations(
        st.session_state.annotation_table,
        display_image.size[0],
        display_image.size[1],
        st.session_state.scale_factor,
    )["objects"]
    st.session_state.candidate_import_key = import_key
    st.session_state.canvas_key_version += 1
    st.session_state.canvas_initial_drawing_pending = True
    st.success(f"{len(imported)}件の候補bboxを未確認アノテーションとして読み込みました。")


def update_imported_candidate_status(annotation_status: str, used_for_training: bool) -> None:
    updated = []
    for item in st.session_state.annotation_table:
        if item.get("candidate_source", "manual") != "manual":
            updated.append(
                {
                    **item,
                    "annotation_status": annotation_status,
                    "used_for_training": used_for_training,
                }
            )
        else:
            updated.append(item)
    st.session_state.annotation_table = updated
    st.session_state.canvas_objects = canvas_json_from_annotations(
        updated,
        st.session_state.display_size[0],
        st.session_state.display_size[1],
        st.session_state.scale_factor,
    )["objects"]
    st.session_state.canvas_key_version += 1
    st.session_state.canvas_initial_drawing_pending = True


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    patch_drawable_canvas_for_streamlit()
    disable_canvas_context_menu()
    ensure_directories()
    init_session_state()

    (
        uploaded_image,
        uploaded_annotations,
        uploaded_candidates,
        candidate_import_source,
        objective_filter,
        metadata,
        region_annotations,
        active_label,
        drawing_mode,
        stroke_color,
        stroke_width,
        exclude_ignore_from_yolo,
        used_for_training_only_export,
        only_reviewed_or_exported,
    ) = render_sidebar()

    st.title(APP_TITLE)
    render_ecrs_notice(metadata.get("project_template", "custom"))

    if not uploaded_image:
        st.info("jpg / png / tif / tiff / ndpi / 対応WSI画像をアップロードしてください。")
        return

    if is_wsi_file(uploaded_image.name):
        prepared_image = render_wsi_patch_workflow(uploaded_image)
        if prepared_image is None:
            return
    else:
        try:
            prepared_image = prepare_uploaded_image(uploaded_image)
        except RuntimeError as error:
            st.error(str(error))
            return

    if prepared_image["source_format"] == "ndpi":
        conversion = prepared_image.get("conversion", {})
        st.info(
            "NDPIをアノテーション用OME-TIFFへ変換しました: "
            f"{prepared_image['source_image_path']} -> {prepared_image['image_path']} "
            f"(level={conversion.get('openslide_level', 'reused')}, "
            f"downsample={conversion.get('level_downsample', 'existing')})"
        )
    if prepared_image["source_format"] == "wsi_patch":
        patch_metadata = prepared_image.get("patch_metadata", {})
        st.info(
            "WSI patchをアノテーション中: "
            f"{prepared_image['image_path']} from {patch_metadata.get('source_wsi_name', '')} "
            f"at x={patch_metadata.get('patch_x', '')}, y={patch_metadata.get('patch_y', '')}"
        )

    image = load_image_from_path(prepared_image["image_path"])
    display_image, scale_factor = make_display_image(image)
    st.session_state.image_original_size = image.size
    st.session_state.display_size = display_image.size
    st.session_state.scale_factor = scale_factor
    process_upload(uploaded_image, uploaded_annotations, display_image, prepared_image)
    process_candidate_import(uploaded_candidates, candidate_import_source, display_image)

    canvas_width, canvas_height = display_image.size
    initial_json = None
    if st.session_state.canvas_initial_drawing_pending:
        initial_json = {
            "version": "5.2.4",
            "objects": st.session_state.canvas_objects,
            "background": "",
            "width": canvas_width,
            "height": canvas_height,
        }
        st.session_state.canvas_initial_drawing_pending = False

    st.caption(
        "画像上に直接アノテーションを描画してください。図形を描き終えると、カウントと保存対象が更新されます。"
    )
    canvas_result = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        background_image=display_image,
        initial_drawing=initial_json,
        update_streamlit=True,
        height=canvas_height,
        width=canvas_width,
        drawing_mode=drawing_mode,
        key=f"canvas_{st.session_state.image_name}_{st.session_state.canvas_key_version}",
    )

    if canvas_result.json_data:
        for obj in canvas_result.json_data.get("objects", []):
            obj.setdefault("label", active_label)
            obj.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))

        st.session_state.canvas_objects = canvas_result.json_data.get("objects", [])
        st.session_state.annotation_table = annotations_from_canvas(
            canvas_result.json_data,
            st.session_state.image_name,
            st.session_state.scale_factor,
            active_label,
            region_annotations.get("global_region_type", "unknown"),
        )

    annotations = apply_context_to_annotations(
        st.session_state.annotation_table,
        st.session_state.image_metadata,
        st.session_state.region_annotations,
    )
    export_annotations = filter_annotations_by_objective(annotations, objective_filter)
    counts_df = count_annotations(
        export_annotations,
        st.session_state.image_metadata,
        st.session_state.image_original_size,
    )

    metrics = calculate_ecrs_counts(
        export_annotations,
        st.session_state.image_metadata,
        st.session_state.image_original_size,
    )
    metric_cols = st.columns(5)
    metric_cols[0].metric("好酸球数", metrics["eosinophil_count"])
    metric_cols[1].metric("総アノテーション数", metrics["total_annotated_count"])
    metric_cols[2].metric("好酸球比率", f"{metrics['eosinophil_ratio']:.3f}")
    metric_cols[3].metric("eos/HPF", str(metrics["eos_per_HPF"]))
    metric_cols[4].metric("eos/mm2", str(metrics["eos_per_mm2"]))

    st.caption(
        f"元画像サイズ: {image.size[0]} x {image.size[1]} px | "
        f"表示倍率: {st.session_state.scale_factor:.6f} | "
        f"画像全体のregion_type: {st.session_state.region_annotations.get('global_region_type', 'unknown')}"
    )

    table_left, table_right = st.columns([2, 1])
    with table_left:
        st.subheader("アノテーション一覧")
        st.dataframe(annotations_dataframe(export_annotations), hide_index=True, use_container_width=True)
    with table_right:
        st.subheader("カウント")
        st.dataframe(counts_df, hide_index=True, use_container_width=True)

    save_disabled = not st.session_state.image_name
    if st.session_state.last_saved_message:
        st.success(st.session_state.last_saved_message)
        st.session_state.last_saved_message = ""

    missing_metadata = missing_required_metadata(st.session_state.image_metadata)
    if missing_metadata:
        st.warning(
            "必須メタデータが未入力です: "
            + ", ".join(missing_metadata)
            + "。MVPのため保存自体は可能です。"
        )

    imported_count = sum(1 for item in st.session_state.annotation_table if item.get("candidate_source", "manual") != "manual")
    if imported_count:
        st.caption(f"現在の画像に含まれるAI候補アノテーション: {imported_count}件")
        candidate_cols = st.columns(2)
        if candidate_cols[0].button("import候補をすべて確認済みにする", use_container_width=True):
            update_imported_candidate_status("confirmed_by_human", True)
            st.rerun()
        if candidate_cols[1].button("import候補をすべてrejectする", use_container_width=True):
            update_imported_candidate_status("rejected", False)
            st.rerun()

    if st.button("キャンバスを再読み込み", disabled=save_disabled, use_container_width=True):
        st.session_state.canvas_key_version += 1
        st.session_state.canvas_initial_drawing_pending = True
        st.rerun()

    if st.button("保存/export", disabled=save_disabled, use_container_width=True):
        paths = save_outputs(
            st.session_state.image_name,
            st.session_state.original_image_path,
            st.session_state.image_original_size,
            export_annotations,
            counts_df,
            st.session_state.image_metadata,
            st.session_state.region_annotations,
            objective_filter,
            exclude_ignore_from_yolo,
            used_for_training_only_export,
        )
        st.session_state.last_saved_message = "保存しました: " + " / ".join(str(path) for path in paths.values())
        st.rerun()

    if st.button("YOLO学習用datasetを生成", use_container_width=True):
        dataset_result = generate_yolo_training_dataset(
            only_reviewed_or_exported=only_reviewed_or_exported,
            exclude_ignore=exclude_ignore_from_yolo,
            used_for_training_only=used_for_training_only_export,
        )
        st.success(
            "YOLO datasetを生成しました: "
            f"画像 {dataset_result['images']}件、ラベル {dataset_result['labels']}件、"
            f"data.yaml: {dataset_result['data_yaml']}"
        )
        if dataset_result["skipped"]:
            st.warning("スキップした画像: " + ", ".join(dataset_result["skipped"]))

    download_payload = {
        "schema_version": "2.3",
        "image_name": st.session_state.image_name,
        "original_image_path": st.session_state.original_image_path,
        "labels": LABELS,
        "primary_labels": PRIMARY_LABELS,
        "yolo_class_ids": YOLO_CLASS_IDS,
        "candidate_sources": CANDIDATE_SOURCES,
        "annotation_statuses": ANNOTATION_STATUSES,
        "annotation_status_fields": ANNOTATION_STATUS_FIELDS,
        "image_metadata": st.session_state.image_metadata,
        "region_annotations": st.session_state.region_annotations,
        "export_objective_filter": objective_filter,
        "used_for_training_only_export": used_for_training_only_export,
        "annotations": export_annotations,
    }
    dl_cols = st.columns(4)
    dl_cols[0].download_button(
        "annotations.json をダウンロード",
        data=json.dumps(download_payload, ensure_ascii=False, indent=2),
        file_name="annotations.json",
        mime="application/json",
        disabled=save_disabled,
        use_container_width=True,
    )
    dl_cols[1].download_button(
        "annotations.csv をダウンロード",
        data=annotations_dataframe(export_annotations).to_csv(index=False).encode("utf-8-sig"),
        file_name="annotations.csv",
        mime="text/csv",
        disabled=save_disabled,
        use_container_width=True,
    )
    dl_cols[2].download_button(
        "counts.csv をダウンロード",
        data=counts_with_metadata(
            counts_df,
            st.session_state.image_metadata,
            st.session_state.region_annotations,
            objective_filter,
        ).to_csv(index=False).encode("utf-8-sig"),
        file_name="counts.csv",
        mime="text/csv",
        disabled=save_disabled,
        use_container_width=True,
    )
    dl_cols[3].download_button(
        "YOLO label をダウンロード",
        data="\n".join(
            yolo_lines(
                export_annotations,
                st.session_state.image_original_size,
                exclude_ignore_from_yolo,
                used_for_training_only_export,
            )
        ),
        file_name=f"{Path(st.session_state.image_name).stem}.txt",
        mime="text/plain",
        disabled=save_disabled,
        use_container_width=True,
    )


if __name__ == "__main__":
    main()

