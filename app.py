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


APP_TITLE = "Manual Granulocyte Annotation Tool"

PROJECT_TEMPLATES = [
    "ECRS_nasal_polyp",
    "CRS_sinonasal_mucosa",
    "EoE_esophagus_reference",
    "GI_eosinophilia_reference",
    "generic_granulocyte",
    "custom",
]
DISEASE_CONTEXTS = ["ECRS", "CRSwNP", "CRSsNP", "control", "unknown"]
TISSUE_TYPES = [
    "nasal_polyp",
    "sinonasal_mucosa",
    "inferior_turbinate",
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

METADATA_FIELDS = [
    "project_template",
    "disease_context",
    "tissue_type",
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
    "notes",
]
MANIFEST_FIELDS = [
    "image_name",
    "original_image_path",
    "project_template",
    "disease_context",
    "tissue_type",
    "staining",
    "objective_magnification",
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
    "generic_granulocyte": {
        "project_template": "generic_granulocyte",
        "disease_context": "unknown",
        "tissue_type": "unknown",
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
ANNOTATION_DIR = DATA_DIR / "annotations"
EXPORT_DIR = DATA_DIR / "exports"
YOLO_DIR = EXPORT_DIR / "yolo_labels"
DATASET_DIR = DATA_DIR / "dataset"
DATASET_IMAGE_DIR = DATASET_DIR / "images"
DATASET_LABEL_DIR = DATASET_DIR / "labels"
MAX_DISPLAY_WIDTH = 1100
MAX_DISPLAY_HEIGHT = 900

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
    for path in (IMAGE_DIR, ANNOTATION_DIR, EXPORT_DIR, YOLO_DIR, DATASET_IMAGE_DIR, DATASET_LABEL_DIR):
        path.mkdir(parents=True, exist_ok=True)


def default_image_metadata(project_template: str = "ECRS_nasal_polyp") -> dict[str, str]:
    metadata = {
        "project_template": project_template,
        "disease_context": "unknown",
        "tissue_type": "unknown",
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
    destination = IMAGE_DIR / uploaded_file.name
    uploaded_file.seek(0)
    with destination.open("wb") as output_file:
        shutil.copyfileobj(uploaded_file, output_file)
    return destination


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
        "confidence": 1.0,
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
    return [{**item, **metadata, "region_type": item.get("region_type", region_type)} for item in annotations]


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
) -> dict[str, Any]:
    ecrs_counts = calculate_ecrs_counts(annotations, metadata, image_size)
    return {
        "image_name": image_name,
        "original_image_path": original_image_path,
        "project_template": metadata.get("project_template", ""),
        "disease_context": metadata.get("disease_context", ""),
        "tissue_type": metadata.get("tissue_type", ""),
        "staining": metadata.get("staining", ""),
        "objective_magnification": metadata.get("objective_magnification", ""),
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
) -> list[str]:
    if not image_size:
        return []
    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        return []

    lines = []
    for item in annotations:
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
        IMAGE_DIR / str(payload.get("image_name", "")),
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    return None


def generate_yolo_training_dataset(
    only_reviewed_or_exported: bool,
    exclude_ignore: bool,
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

        stem = safe_file_stem(image_name)
        image_destination = DATASET_IMAGE_DIR / image_source.name
        label_destination = DATASET_LABEL_DIR / f"{stem}.txt"

        shutil.copy2(image_source, image_destination)
        label_destination.write_text(
            "\n".join(yolo_lines(payload.get("annotations", []), image_size, exclude_ignore)),
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


def safe_file_stem(image_name: str) -> str:
    stem = Path(image_name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    return safe_stem or "image"


def image_export_paths(image_name: str) -> dict[str, Path]:
    stem = safe_file_stem(image_name)
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

        manifest_rows.append(
            dataset_manifest_row(
                image_name,
                original_image_path,
                metadata,
                annotations,
                saved_at,
                image_size,
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
    annotations_dataframe(annotation_rows).to_csv(
        EXPORT_DIR / "annotations.csv",
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
) -> dict[str, Path]:
    saved_at = datetime.now().isoformat(timespec="seconds")
    paths = image_export_paths(image_name)
    manifest_path = EXPORT_DIR / "dataset_manifest.csv"
    aggregate_annotations_path = EXPORT_DIR / "annotations.csv"
    aggregate_counts_path = EXPORT_DIR / "counts.csv"

    payload = {
        "schema_version": "2.0",
        "image_name": image_name,
        "original_image_path": original_image_path,
        "labels": LABELS,
        "primary_labels": PRIMARY_LABELS,
        "label_colors": LABEL_COLORS,
        "yolo_class_ids": YOLO_CLASS_IDS,
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
        "\n".join(yolo_lines(annotations, image_size, exclude_ignore_from_yolo)),
        encoding="utf-8",
    )
    regenerate_dataset_exports()

    return {
        "annotations_json": paths["annotations_json"],
        "annotations_csv": paths["annotations_csv"],
        "counts_csv": paths["counts_csv"],
        "aggregate_annotations_csv": aggregate_annotations_path,
        "aggregate_counts_csv": aggregate_counts_path,
        "dataset_manifest_csv": manifest_path,
        "yolo_labels": paths["yolo_labels"],
    }


def load_annotation_payload(uploaded_file: Any) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    payload = json.loads(uploaded_file.getvalue().decode("utf-8"))
    if isinstance(payload, list):
        return payload, {}, default_region_annotations()
    if isinstance(payload, dict):
        annotations = payload.get("annotations", [])
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
    st.sidebar.subheader("Project Template")
    current_template = st.session_state.project_template
    project_template = st.sidebar.selectbox(
        "project_template",
        PROJECT_TEMPLATES,
        index=select_index(PROJECT_TEMPLATES, current_template, "ECRS_nasal_polyp"),
    )
    if project_template != st.session_state.last_template:
        existing = st.session_state.image_metadata.copy()
        defaults = default_image_metadata(project_template)
        # Preserve user-entered identifiers while applying template recommendations.
        for field in ["specimen_id", "slide_id", "annotator", "patient_id_hash", "notes"]:
            defaults[field] = existing.get(field, defaults.get(field, ""))
        st.session_state.project_template = project_template
        st.session_state.image_metadata = defaults
        st.session_state.last_template = project_template
    return project_template


def render_metadata_inputs(project_template: str) -> dict[str, Any]:
    st.sidebar.subheader("Image Metadata")
    current = st.session_state.image_metadata
    current["project_template"] = project_template

    metadata = {
        "project_template": project_template,
        "disease_context": st.sidebar.selectbox(
            "disease_context *",
            DISEASE_CONTEXTS,
            index=select_index(DISEASE_CONTEXTS, current.get("disease_context"), "unknown"),
        ),
        "tissue_type": st.sidebar.selectbox(
            "tissue_type *",
            TISSUE_TYPES,
            index=select_index(TISSUE_TYPES, current.get("tissue_type"), "unknown"),
        ),
        "staining": st.sidebar.selectbox(
            "staining *",
            STAINING_OPTIONS,
            index=select_index(STAINING_OPTIONS, current.get("staining"), "unknown"),
        ),
        "objective_magnification": st.sidebar.selectbox(
            "objective_magnification *",
            OBJECTIVE_MAGNIFICATIONS,
            index=select_index(
                OBJECTIVE_MAGNIFICATIONS,
                current.get("objective_magnification"),
                "unknown",
            ),
        ),
        "specimen_id": st.sidebar.text_input("specimen_id *", value=str(current.get("specimen_id", ""))),
        "slide_id": st.sidebar.text_input("slide_id *", value=str(current.get("slide_id", ""))),
        "annotator": st.sidebar.text_input("annotator *", value=str(current.get("annotator", ""))),
        "patient_id_hash": st.sidebar.text_input("patient_id_hash", value=str(current.get("patient_id_hash", ""))),
        "anatomical_site": st.sidebar.selectbox(
            "anatomical_site",
            ANATOMICAL_SITES,
            index=select_index(ANATOMICAL_SITES, current.get("anatomical_site"), "unknown"),
        ),
        "scanner_or_microscope": st.sidebar.text_input(
            "scanner_or_microscope",
            value=str(current.get("scanner_or_microscope", "")),
        ),
        "pixel_size_um": st.sidebar.text_input("pixel_size_um", value=str(current.get("pixel_size_um", ""))),
        "hpf_area_mm2": st.sidebar.text_input("hpf_area_mm2", value=str(current.get("hpf_area_mm2", ""))),
        "hpf_diameter_mm": st.sidebar.text_input(
            "hpf_diameter_mm",
            value=str(current.get("hpf_diameter_mm", "")),
        ),
        "image_is_single_hpf": st.sidebar.checkbox(
            "Image is exactly 1 HPF",
            value=bool(current.get("image_is_single_hpf", False)),
            help="Use only when the whole image represents exactly one high-power field.",
        ),
        "section_quality": st.sidebar.selectbox(
            "section_quality",
            SECTION_QUALITY_OPTIONS,
            index=select_index(SECTION_QUALITY_OPTIONS, current.get("section_quality"), "good"),
        ),
        "reviewed": st.sidebar.checkbox(
            "reviewed",
            value=bool(current.get("reviewed", False)),
            help="Mark this image as human-confirmed for training export.",
        ),
        "exported": st.sidebar.checkbox(
            "exported",
            value=bool(current.get("exported", False)),
            help="Mark this image as eligible for dataset export.",
        ),
        "notes": st.sidebar.text_area("notes", value=str(current.get("notes", "")), height=80),
    }
    st.session_state.image_metadata = metadata
    return metadata


def render_region_type() -> dict[str, Any]:
    st.sidebar.subheader("Region Type")
    current_region = st.session_state.region_annotations.get("global_region_type", "unknown")
    region_type = st.sidebar.selectbox(
        "global_region_type",
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
    st.sidebar.subheader("Active Label")
    quick_label = st.sidebar.radio(
        "Common labels",
        PRIMARY_LABELS,
        captions=[LABEL_COLORS[label] for label in PRIMARY_LABELS],
    )
    active_label = st.sidebar.selectbox(
        "All labels",
        LABELS,
        index=LABELS.index(quick_label),
        help="Initial ECRS evaluation focuses on eosinophil vs other/ignore.",
    )

    st.sidebar.subheader("Drawing Mode")
    drawing_mode = st.sidebar.selectbox(
        "drawing_mode",
        ["circle", "rect", "transform"],
        index=0,
        help="Use transform to move, resize, or delete selected objects.",
    )
    stroke_width = st.sidebar.slider("Stroke width", min_value=1, max_value=8, value=3)
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


def render_sidebar() -> tuple[Any, Any, str, dict[str, Any], dict[str, Any], str, str, str, int, bool, bool]:
    st.sidebar.subheader("Upload tissue image")
    uploaded_image = st.sidebar.file_uploader(
        "Upload tissue image",
        type=["jpg", "jpeg", "png", "tif", "tiff"],
    )
    if uploaded_image and st.session_state.image_name != uploaded_image.name:
        reset_for_new_image()

    project_template = render_project_template()
    metadata = render_metadata_inputs(project_template)
    region_annotations = render_region_type()
    active_label, drawing_mode, stroke_color, stroke_width = render_label_controls()

    st.sidebar.subheader("Export Settings")
    objective_filter = st.sidebar.selectbox(
        "objective_magnification filter",
        ["all", *OBJECTIVE_MAGNIFICATIONS],
        index=0,
    )
    exclude_ignore_from_yolo = st.sidebar.checkbox("Exclude ignore from YOLO export", value=True)
    only_reviewed_or_exported = st.sidebar.checkbox(
        "YOLO dataset: reviewed/exported only",
        value=True,
        help="Use only human-confirmed or explicitly exported images for the training dataset.",
    )

    st.sidebar.subheader("Save / Restore")
    uploaded_annotations = st.sidebar.file_uploader("Restore annotations.json", type=["json"])

    return (
        uploaded_image,
        uploaded_annotations,
        objective_filter,
        metadata,
        region_annotations,
        active_label,
        drawing_mode,
        stroke_color,
        stroke_width,
        exclude_ignore_from_yolo,
        only_reviewed_or_exported,
    )


def render_ecrs_notice(project_template: str) -> None:
    if project_template == "ECRS_nasal_polyp":
        st.info(
            "For research use only. This project supports eosinophil quantification in "
            "H&E-stained nasal polyp / sinonasal mucosa images. Not intended for clinical diagnosis."
        )


def process_upload(uploaded_image: Any, uploaded_annotations: Any, display_image: Image.Image) -> None:
    image_key = f"{uploaded_image.name}:{uploaded_image.size}"
    if st.session_state.saved_image_key != image_key:
        image_path = save_uploaded_image(uploaded_image)
        st.session_state.original_image_path = str(image_path)
        st.session_state.saved_image_key = image_key

    st.session_state.image_name = uploaded_image.name
    if uploaded_annotations:
        restore_key = f"{uploaded_image.name}:{uploaded_annotations.name}:{uploaded_annotations.size}"
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


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    patch_drawable_canvas_for_streamlit()
    disable_canvas_context_menu()
    ensure_directories()
    init_session_state()

    (
        uploaded_image,
        uploaded_annotations,
        objective_filter,
        metadata,
        region_annotations,
        active_label,
        drawing_mode,
        stroke_color,
        stroke_width,
        exclude_ignore_from_yolo,
        only_reviewed_or_exported,
    ) = render_sidebar()

    st.title(APP_TITLE)
    render_ecrs_notice(metadata.get("project_template", "custom"))

    if not uploaded_image:
        st.info("Upload a jpg, png, tif, or tiff image to begin annotation.")
        return

    image = load_image(uploaded_image)
    display_image, scale_factor = make_display_image(image)
    st.session_state.image_original_size = image.size
    st.session_state.display_size = display_image.size
    st.session_state.scale_factor = scale_factor
    process_upload(uploaded_image, uploaded_annotations, display_image)

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
        "Draw annotations directly on the image. Counts and exports update after each completed shape."
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
    metric_cols[0].metric("eosinophil_count", metrics["eosinophil_count"])
    metric_cols[1].metric("total_annotated_count", metrics["total_annotated_count"])
    metric_cols[2].metric("eosinophil_ratio", f"{metrics['eosinophil_ratio']:.3f}")
    metric_cols[3].metric("eos_per_HPF", str(metrics["eos_per_HPF"]))
    metric_cols[4].metric("eos_per_mm2", str(metrics["eos_per_mm2"]))

    st.caption(
        f"Original size: {image.size[0]} x {image.size[1]} px | "
        f"Display scale: {st.session_state.scale_factor:.6f} | "
        f"Global region_type: {st.session_state.region_annotations.get('global_region_type', 'unknown')}"
    )

    table_left, table_right = st.columns([2, 1])
    with table_left:
        st.subheader("Annotations")
        st.dataframe(annotations_dataframe(export_annotations), hide_index=True, use_container_width=True)
    with table_right:
        st.subheader("Counts")
        st.dataframe(counts_df, hide_index=True, use_container_width=True)

    save_disabled = not st.session_state.image_name
    if st.session_state.last_saved_message:
        st.success(st.session_state.last_saved_message)
        st.session_state.last_saved_message = ""

    missing_metadata = missing_required_metadata(st.session_state.image_metadata)
    if missing_metadata:
        st.warning(
            "Missing required metadata: "
            + ", ".join(missing_metadata)
            + ". Saving is still allowed for this MVP."
        )

    if st.button("Refresh canvas", disabled=save_disabled, use_container_width=True):
        st.session_state.canvas_key_version += 1
        st.session_state.canvas_initial_drawing_pending = True
        st.rerun()

    if st.button("Save exports", disabled=save_disabled, use_container_width=True):
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
        )
        st.session_state.last_saved_message = "Saved: " + " / ".join(str(path) for path in paths.values())
        st.rerun()

    if st.button("Generate YOLO training dataset", use_container_width=True):
        dataset_result = generate_yolo_training_dataset(
            only_reviewed_or_exported=only_reviewed_or_exported,
            exclude_ignore=exclude_ignore_from_yolo,
        )
        st.success(
            "YOLO dataset generated: "
            f"{dataset_result['images']} images, {dataset_result['labels']} label files, "
            f"data.yaml at {dataset_result['data_yaml']}"
        )
        if dataset_result["skipped"]:
            st.warning("Skipped images: " + ", ".join(dataset_result["skipped"]))

    download_payload = {
        "schema_version": "2.0",
        "image_name": st.session_state.image_name,
        "original_image_path": st.session_state.original_image_path,
        "labels": LABELS,
        "primary_labels": PRIMARY_LABELS,
        "yolo_class_ids": YOLO_CLASS_IDS,
        "image_metadata": st.session_state.image_metadata,
        "region_annotations": st.session_state.region_annotations,
        "export_objective_filter": objective_filter,
        "annotations": export_annotations,
    }
    dl_cols = st.columns(4)
    dl_cols[0].download_button(
        "Download annotations.json",
        data=json.dumps(download_payload, ensure_ascii=False, indent=2),
        file_name="annotations.json",
        mime="application/json",
        disabled=save_disabled,
        use_container_width=True,
    )
    dl_cols[1].download_button(
        "Download annotations.csv",
        data=annotations_dataframe(export_annotations).to_csv(index=False).encode("utf-8-sig"),
        file_name="annotations.csv",
        mime="text/csv",
        disabled=save_disabled,
        use_container_width=True,
    )
    dl_cols[2].download_button(
        "Download counts.csv",
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
        "Download YOLO label",
        data="\n".join(yolo_lines(export_annotations, st.session_state.image_original_size, exclude_ignore_from_yolo)),
        file_name=f"{Path(st.session_state.image_name).stem}.txt",
        mime="text/plain",
        disabled=save_disabled,
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
