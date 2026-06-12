from __future__ import annotations

import json
import hashlib
import re
import shutil
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import streamlit_drawable_canvas as drawable_canvas
from PIL import Image, ImageOps
from streamlit.elements.lib import image_utils
from streamlit.elements.lib.layout_utils import LayoutConfig
from streamlit_drawable_canvas import st_canvas


APP_TITLE = "手動好酸球アノテーションツール"
TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")

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
ANNOTATION_TRACKING_FIELDS = [
    "annotation_id",
    "annotation_created_at",
    "annotation_updated_at",
    "annotation_session_id",
]
EXCLUSION_REASONS = [
    "",
    "metadata_error",
    "wrong_label",
    "bad_patch",
    "artifact",
    "test_data",
    "duplicate",
    "other",
]
TRAINING_MANAGER_METADATA_FIELDS = [
    "project_template",
    "disease_context",
    "source_organ",
    "tissue_type",
    "tissue_region",
    "staining",
    "specimen_id",
    "slide_id",
    "patient_id_hash",
    "notes",
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
    "reviewed_at",
    "exported_at",
    "exclude_from_training",
    "exclusion_reason",
    "source_wsi_name",
    "patch_id",
    "patch_x",
    "patch_y",
    "patch_width",
    "patch_height",
    "patch_level",
    "patch_downsample",
    "patch_level0_width",
    "patch_level0_height",
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
    "reviewed_at",
    "exported_at",
    "exclude_from_training",
    "exclusion_reason",
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
PATCH_MANIFEST_PATH = PATCH_DIR / "patch_manifest.csv"
ANNOTATION_DIR = DATA_DIR / "annotations"
ANNOTATION_BACKUP_DIR = ANNOTATION_DIR / "backups"
EXPORT_DIR = DATA_DIR / "exports"
YOLO_DIR = EXPORT_DIR / "yolo_labels"
DATASET_DIR = DATA_DIR / "dataset"
DATASET_IMAGE_DIR = DATASET_DIR / "images"
DATASET_LABEL_DIR = DATASET_DIR / "labels"
CLAM_DIR = DATA_DIR / "clam"
CLAM_COORD_DIR = CLAM_DIR / "coords"
CLAM_FEATURE_DIR = CLAM_DIR / "features"
CLAM_DEEP_FEATURE_CSV_DIR = CLAM_DIR / "deep_features_csv"
CLAM_DEEP_FEATURE_PT_DIR = CLAM_DIR / "deep_features"
CLAM_MIL_BAGS_PATH = CLAM_DIR / "mil_bags.csv"
MAX_DISPLAY_WIDTH = 1100
MAX_DISPLAY_HEIGHT = 900
NDPI_EXTENSIONS = {".ndpi"}
WSI_EXTENSIONS = {".ndpi", ".svs", ".scn", ".vms", ".vmu"}
MAX_NDPI_CONVERSION_PIXELS = 30_000_000
WSI_THUMBNAIL_MAX_SIZE = (1100, 700)
PATCH_DIMENSION_OPTIONS = [512, 1024, 1536, 2048]
PATCH_QUEUE_SIZE_OPTIONS = [1024, 2048]
PATCH_QUEUE_STATUSES = [
    "not_started",
    "in_progress",
    "done",
    "reviewed_empty",
    "skipped",
    "flagged",
    "suspected_positive",
]
REVIEW_MODES = ["Standard review", "Positive exploration"]
POSITIVE_SORT_OPTIONS = [
    "priority_score desc",
    "tissue_ratio desc",
    "cluster_id then priority_score",
    "spatial",
    "random sample",
    "cluster-balanced",
]
PATCH_FEATURE_VERSION = "rgb_hsv_v1"
PATCH_FEATURE_FIELDS = [
    "brightness_mean",
    "saturation_mean",
    "hematoxylin_score",
    "eosin_score",
    "nuclei_density_proxy",
    "red_orange_score",
]
PATCH_QUEUE_SORT_OPTIONS = {
    "priority_score": "優先度が高い順",
    "cluster_id": "クラスタ順",
    "spatial": "WSI上の位置順",
    "tissue_ratio": "組織率が高い順",
}
PATCH_MANIFEST_FIELDS = [
    "source_wsi_name",
    "patch_id",
    "image_path",
    "patch_x",
    "patch_y",
    "patch_width",
    "patch_height",
    "patch_level",
    "patch_downsample",
    "target_mpp",
    "objective_magnification",
    "tissue_ratio",
    *PATCH_FEATURE_FIELDS,
    "cluster_id",
    "priority_score",
    "feature_version",
    "status",
    "annotation_count",
    "eosinophil_count",
    "created_at",
    "updated_at",
    "reviewed_at",
    "exported_at",
    "exclude_from_training",
    "exclusion_reason",
    "notes",
]
WSI_TILE_SIZE = 256
WSI_TILE_SERVER_PORT = 8765
WSI_TILE_SOURCES: dict[str, Path] = {}
WSI_TILE_SERVER_STARTED = False

# Research TIFF files can be very large. The app still downscales for display,
# but Pillow needs permission to open the original dimensions first.
Image.MAX_IMAGE_PIXELS = None


def tokyo_now_iso() -> str:
    return datetime.now(TOKYO_TIMEZONE).isoformat(timespec="seconds")


def normalize_tokyo_timestamp(value: Any, fallback: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback or tokyo_now_iso()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return fallback or tokyo_now_iso()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TOKYO_TIMEZONE)
    else:
        parsed = parsed.astimezone(TOKYO_TIMEZONE)
    return parsed.isoformat(timespec="seconds")


def new_annotation_session_id() -> str:
    return f"session_{uuid4().hex}"


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


def render_canvas_wheel_zoom() -> None:
    """Add display-only wheel zoom to the most recently rendered drawable canvas."""
    components.html(
        """
        <div style="display:flex;align-items:center;gap:8px;font-family:Arial,sans-serif;font-size:13px;">
          <button id="zoomOut" title="縮小">−</button>
          <button id="zoomReset" title="100%へ戻す">100%</button>
          <button id="zoomIn" title="拡大">＋</button>
          <span id="zoomLabel">倍率 100%</span>
          <span style="color:#666;">画像上でマウスホイール: 拡大縮小 / スクロールバー: 移動</span>
        </div>
        <script>
        (() => {
          const parentDoc = window.parent.document;
          const selfFrame = window.frameElement;
          const label = document.getElementById("zoomLabel");
          let targetFrame = null;
          let scrollHost = null;
          let zoom = 1;
          const minZoom = 1;
          const maxZoom = 4;

          const findCanvasFrame = () => {
            const frames = Array.from(parentDoc.querySelectorAll("iframe")).reverse();
            return frames.find((frame) => {
              if (frame === selfFrame) return false;
              try {
                return Boolean(frame.contentDocument?.querySelector("#canvas-to-streamlit"));
              } catch (error) {
                return false;
              }
            });
          };

          const applyZoom = (nextZoom, pointerX = 0, pointerY = 0) => {
            if (!targetFrame || !scrollHost) return;
            const previousZoom = zoom;
            zoom = Math.min(maxZoom, Math.max(minZoom, nextZoom));
            targetFrame.style.transformOrigin = "top left";
            targetFrame.style.transform = `scale(${zoom})`;
            targetFrame.style.marginRight = `${targetFrame.offsetWidth * (zoom - 1)}px`;
            targetFrame.style.marginBottom = `${targetFrame.offsetHeight * (zoom - 1)}px`;
            if (previousZoom !== zoom) {
              const ratio = zoom / previousZoom;
              scrollHost.scrollLeft = (scrollHost.scrollLeft + pointerX) * ratio - pointerX;
              scrollHost.scrollTop = (scrollHost.scrollTop + pointerY) * ratio - pointerY;
            }
            label.textContent = `倍率 ${Math.round(zoom * 100)}%`;
          };

          const install = () => {
            targetFrame = findCanvasFrame();
            if (!targetFrame) return false;
            scrollHost = targetFrame.parentElement;
            if (!scrollHost) return false;
            scrollHost.style.overflow = "auto";
            scrollHost.style.maxWidth = "100%";
            scrollHost.style.maxHeight = `${Math.min(targetFrame.offsetHeight, 900)}px`;

            const canvasDocument = targetFrame.contentDocument;
            if (!canvasDocument) return false;
            if (!targetFrame.dataset.wheelZoomInstalled) {
              canvasDocument.addEventListener(
                "wheel",
                (event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  const direction = event.deltaY < 0 ? 1 : -1;
                  const factor = direction > 0 ? 1.15 : 1 / 1.15;
                  applyZoom(zoom * factor, event.clientX, event.clientY);
                },
                { passive: false, capture: true }
              );
              targetFrame.dataset.wheelZoomInstalled = "true";
            }
            applyZoom(1);
            return true;
          };

          document.getElementById("zoomOut").onclick = () => applyZoom(zoom / 1.25);
          document.getElementById("zoomReset").onclick = () => {
            applyZoom(1);
            if (scrollHost) {
              scrollHost.scrollLeft = 0;
              scrollHost.scrollTop = 0;
            }
          };
          document.getElementById("zoomIn").onclick = () => applyZoom(zoom * 1.25);

          if (!install()) {
            setTimeout(install, 300);
            setTimeout(install, 900);
          }
        })();
        </script>
        """,
        height=38,
    )


def ensure_directories() -> None:
    for path in (
        IMAGE_DIR,
        ORIGINAL_NDPI_DIR,
        ORIGINAL_WSI_DIR,
        CONVERTED_IMAGE_DIR,
        PATCH_IMAGE_DIR,
        ANNOTATION_DIR,
        ANNOTATION_BACKUP_DIR,
        EXPORT_DIR,
        YOLO_DIR,
        DATASET_IMAGE_DIR,
        DATASET_LABEL_DIR,
        CLAM_COORD_DIR,
        CLAM_FEATURE_DIR,
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
        "reviewed_at": "",
        "exported_at": "",
        "exclude_from_training": False,
        "exclusion_reason": "",
        "source_wsi_name": "",
        "patch_id": "",
        "patch_x": "",
        "patch_y": "",
        "patch_width": "",
        "patch_height": "",
        "patch_level": "",
        "patch_downsample": "",
        "patch_level0_width": "",
        "patch_level0_height": "",
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
        "active_patch_queue_id": None,
        "active_wsi_name": "",
        "active_wsi_thumbnail_info": {},
        "patch_queue_index": 0,
        "patch_queue_sort_by": "priority_score",
        "patch_review_mode": "Standard review",
        "positive_candidate_index": 0,
        "positive_only_unreviewed": True,
        "positive_flagged_only": False,
        "positive_exclude_reviewed_empty": True,
        "positive_exclude_done": False,
        "positive_exclude_skipped": True,
        "positive_exclude_training": True,
        "positive_min_priority": 0.0,
        "positive_top_n": 100,
        "positive_cluster_filter": "all",
        "positive_status_filter": [],
        "positive_tissue_region_filter": "all",
        "positive_disease_context_filter": "all",
        "positive_source_organ_filter": "all",
        "positive_sort": "priority_score desc",
        "positive_per_cluster": 5,
        "positive_random_seed": 42,
        "annotation_session_id": new_annotation_session_id(),
        "project_template": "ECRS_nasal_polyp",
        "image_metadata": default_image_metadata("ECRS_nasal_polyp"),
        "region_annotations": default_region_annotations(),
        "last_template": "ECRS_nasal_polyp",
        "training_data_stale": False,
        "force_saved_annotation_reload": False,
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


@st.cache_data(show_spinner=False, max_entries=32)
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


@st.cache_data(show_spinner=False, max_entries=8)
def make_wsi_thumbnail(wsi_path: Path) -> tuple[Image.Image, dict[str, Any]]:
    slide = open_wsi_slide(wsi_path)
    try:
        width, height = slide.dimensions
        thumbnail = slide.get_thumbnail(WSI_THUMBNAIL_MAX_SIZE).convert("RGB")
        mpp_x, mpp_y = wsi_mpp(slide)
        level_dimensions = [tuple(item) for item in slide.level_dimensions]
        level_downsamples = [float(item) for item in slide.level_downsamples]
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
        "level_dimensions": level_dimensions,
        "level_downsamples": level_downsamples,
    }


def navigation_wsi_info(wsi_path: Path, source_wsi_name: str) -> dict[str, Any]:
    cached_name = str(st.session_state.get("active_wsi_name", ""))
    cached_info = st.session_state.get("active_wsi_thumbnail_info", {})
    if cached_name == source_wsi_name and cached_info:
        return dict(cached_info)

    slide = open_wsi_slide(wsi_path)
    try:
        width, height = slide.dimensions
        mpp_x, mpp_y = wsi_mpp(slide)
        level_dimensions = [tuple(item) for item in slide.level_dimensions]
        level_downsamples = [float(item) for item in slide.level_downsamples]
    finally:
        slide.close()
    return {
        "wsi_width": width,
        "wsi_height": height,
        "mpp_x": mpp_x,
        "mpp_y": mpp_y,
        "level_dimensions": level_dimensions,
        "level_downsamples": level_downsamples,
    }


class WSITileRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/tile":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        source_id = params.get("id", [""])[0]
        wsi_path = WSI_TILE_SOURCES.get(source_id)
        if not wsi_path:
            self.send_error(404)
            return

        try:
            level = int(params.get("level", ["0"])[0])
            tile_x = int(params.get("x", ["0"])[0])
            tile_y = int(params.get("y", ["0"])[0])
            tile_size = int(params.get("size", [str(WSI_TILE_SIZE)])[0])
            slide = open_wsi_slide(wsi_path)
            try:
                downsample = float(slide.level_downsamples[level])
                level_width, level_height = slide.level_dimensions[level]
                level_left = tile_x * tile_size
                level_top = tile_y * tile_size
                read_width = min(tile_size, max(1, level_width - level_left))
                read_height = min(tile_size, max(1, level_height - level_top))
                location = (int(level_left * downsample), int(level_top * downsample))
                tile = slide.read_region(location, level, (read_width, read_height))
            finally:
                slide.close()

            if tile.mode == "RGBA":
                background = Image.new("RGBA", tile.size, (255, 255, 255, 255))
                tile = Image.alpha_composite(background, tile)
            tile = tile.convert("RGB")
            output = BytesIO()
            tile.save(output, format="JPEG", quality=85)
            payload = output.getvalue()
        except Exception:
            self.send_error(500)
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        return


def ensure_wsi_tile_server() -> None:
    global WSI_TILE_SERVER_STARTED
    if WSI_TILE_SERVER_STARTED:
        return
    try:
        server = ThreadingHTTPServer(("127.0.0.1", WSI_TILE_SERVER_PORT), WSITileRequestHandler)
    except OSError as error:
        raise RuntimeError(
            f"WSIタイルビューア用ポート {WSI_TILE_SERVER_PORT} を開始できませんでした。"
            "別のStreamlitプロセスを終了してから再実行してください。"
        ) from error
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    WSI_TILE_SERVER_STARTED = True


def register_wsi_tile_source(wsi_path: Path) -> str:
    ensure_wsi_tile_server()
    source_id = safe_file_stem(f"{wsi_path.stem}_{wsi_path.stat().st_size}_{int(wsi_path.stat().st_mtime)}")
    WSI_TILE_SOURCES[source_id] = wsi_path
    return source_id


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


def clamp_patch_origin(
    x: int,
    y: int,
    patch_level0_width: int,
    patch_level0_height: int,
    wsi_width: int,
    wsi_height: int,
) -> tuple[int, int]:
    return (
        max(0, min(x, max(0, wsi_width - patch_level0_width))),
        max(0, min(y, max(0, wsi_height - patch_level0_height))),
    )


def patch_image_path(wsi_name: str, patch_id: str) -> Path:
    return PATCH_IMAGE_DIR / f"{safe_file_stem(Path(wsi_name).stem)}_{safe_file_stem(patch_id)}.png"


def read_wsi_region_rgb(
    wsi_path: Path,
    patch_x: int,
    patch_y: int,
    level: int,
    patch_width: int,
    patch_height: int,
) -> Image.Image:
    slide = open_wsi_slide(wsi_path)
    try:
        patch = slide.read_region((patch_x, patch_y), level, (patch_width, patch_height))
    finally:
        slide.close()
    if patch.mode == "RGBA":
        background = Image.new("RGBA", patch.size, (255, 255, 255, 255))
        patch = Image.alpha_composite(background, patch)
    return patch.convert("RGB")


def white_fraction(image: Image.Image) -> float:
    import numpy as np

    array = np.asarray(image.convert("L"))
    return float((array > 245).mean())


def render_wsi_scroll_viewer(
    wsi_path: Path,
    thumbnail_info: dict[str, Any],
    initial_level: int,
    patch_width: int,
    patch_height: int,
) -> None:
    source_id = register_wsi_tile_source(wsi_path)
    level_dimensions = thumbnail_info.get("level_dimensions", [])
    level_downsamples = thumbnail_info.get("level_downsamples", [])
    viewer_payload = {
        "tileUrl": f"http://127.0.0.1:{WSI_TILE_SERVER_PORT}/tile",
        "sourceId": source_id,
        "tileSize": WSI_TILE_SIZE,
        "levelDimensions": level_dimensions,
        "levelDownsamples": level_downsamples,
        "initialLevel": initial_level,
        "patchWidth": patch_width,
        "patchHeight": patch_height,
    }
    components.html(
        f"""
        <div style="font-family: sans-serif;">
          <div style="display:flex; gap:8px; align-items:center; margin-bottom:6px;">
            <button id="zoomIn">拡大</button>
            <button id="zoomOut">縮小</button>
            <button id="copyCoords">patch座標をコピー</button>
            <span id="coordText" style="font-size:13px;"></span>
          </div>
          <canvas id="wsiCanvas" width="980" height="560"
            style="width:100%; max-width:980px; height:560px; border:1px solid #d1d5db; background:#f9fafb; cursor:grab;">
          </canvas>
          <div style="font-size:12px; color:#4b5563; margin-top:4px;">
            マウスホイールでズーム、ドラッグで移動します。赤枠が保存予定patchの範囲です。
            表示されたpatch_x / patch_yをコピーして、下の入力欄に貼り付けてください。
          </div>
        </div>
        <script>
        const cfg = {json.dumps(viewer_payload)};
        const canvas = document.getElementById("wsiCanvas");
        const ctx = canvas.getContext("2d");
        const coordText = document.getElementById("coordText");
        const tileCache = new Map();
        let level = Math.min(cfg.initialLevel, cfg.levelDimensions.length - 1);
        let dims = cfg.levelDimensions[level];
        let downsample = cfg.levelDownsamples[level] || 1;
        let centerX = dims[0] / 2;
        let centerY = dims[1] / 2;
        let scale = Math.min(canvas.width / dims[0], canvas.height / dims[1]);
        let dragging = false;
        let lastX = 0;
        let lastY = 0;

        function setLevel(newLevel) {{
          newLevel = Math.max(0, Math.min(cfg.levelDimensions.length - 1, newLevel));
          if (newLevel === level) return;
          const center0X = centerX * downsample;
          const center0Y = centerY * downsample;
          level = newLevel;
          dims = cfg.levelDimensions[level];
          downsample = cfg.levelDownsamples[level] || 1;
          centerX = center0X / downsample;
          centerY = center0Y / downsample;
          scale = Math.min(Math.max(scale, 0.15), 6);
          draw();
        }}

        function clampCenter() {{
          const halfW = canvas.width / (2 * scale);
          const halfH = canvas.height / (2 * scale);
          centerX = Math.max(halfW, Math.min(dims[0] - halfW, centerX));
          centerY = Math.max(halfH, Math.min(dims[1] - halfH, centerY));
        }}

        function tileKey(z, x, y) {{
          return `${{z}}/${{x}}/${{y}}`;
        }}

        function loadTile(z, x, y) {{
          const key = tileKey(z, x, y);
          if (tileCache.has(key)) return tileCache.get(key);
          const img = new Image();
          img.crossOrigin = "anonymous";
          img.src = `${{cfg.tileUrl}}?id=${{encodeURIComponent(cfg.sourceId)}}&level=${{z}}&x=${{x}}&y=${{y}}&size=${{cfg.tileSize}}`;
          img.onload = draw;
          tileCache.set(key, img);
          return img;
        }}

        function currentPatchCoords() {{
          const x = Math.max(0, Math.round((centerX - cfg.patchWidth / 2) * downsample));
          const y = Math.max(0, Math.round((centerY - cfg.patchHeight / 2) * downsample));
          const w = Math.round(cfg.patchWidth * downsample);
          const h = Math.round(cfg.patchHeight * downsample);
          return {{ x, y, w, h }};
        }}

        function updateCoords() {{
          const p = currentPatchCoords();
          coordText.textContent = `level=${{level}}, downsample=${{downsample.toFixed(2)}}, patch_x=${{p.x}}, patch_y=${{p.y}}, level0範囲=${{p.w}}x${{p.h}}`;
        }}

        function draw() {{
          clampCenter();
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = "#f9fafb";
          ctx.fillRect(0, 0, canvas.width, canvas.height);

          const viewLeft = centerX - canvas.width / (2 * scale);
          const viewTop = centerY - canvas.height / (2 * scale);
          const startTileX = Math.max(0, Math.floor(viewLeft / cfg.tileSize));
          const startTileY = Math.max(0, Math.floor(viewTop / cfg.tileSize));
          const endTileX = Math.ceil((viewLeft + canvas.width / scale) / cfg.tileSize);
          const endTileY = Math.ceil((viewTop + canvas.height / scale) / cfg.tileSize);

          for (let ty = startTileY; ty <= endTileY; ty++) {{
            for (let tx = startTileX; tx <= endTileX; tx++) {{
              const img = loadTile(level, tx, ty);
              const sx = (tx * cfg.tileSize - viewLeft) * scale;
              const sy = (ty * cfg.tileSize - viewTop) * scale;
              const sw = cfg.tileSize * scale;
              const sh = cfg.tileSize * scale;
              if (img.complete && img.naturalWidth > 0) {{
                ctx.drawImage(img, sx, sy, sw, sh);
              }}
            }}
          }}

          const rectW = cfg.patchWidth * scale;
          const rectH = cfg.patchHeight * scale;
          ctx.strokeStyle = "#ff2d55";
          ctx.lineWidth = 3;
          ctx.strokeRect((canvas.width - rectW) / 2, (canvas.height - rectH) / 2, rectW, rectH);
          ctx.fillStyle = "rgba(255,45,85,0.08)";
          ctx.fillRect((canvas.width - rectW) / 2, (canvas.height - rectH) / 2, rectW, rectH);
          updateCoords();
        }}

        canvas.addEventListener("mousedown", (event) => {{
          dragging = true;
          lastX = event.clientX;
          lastY = event.clientY;
          canvas.style.cursor = "grabbing";
        }});
        window.addEventListener("mouseup", () => {{
          dragging = false;
          canvas.style.cursor = "grab";
        }});
        canvas.addEventListener("mousemove", (event) => {{
          if (!dragging) return;
          centerX -= (event.clientX - lastX) / scale;
          centerY -= (event.clientY - lastY) / scale;
          lastX = event.clientX;
          lastY = event.clientY;
          draw();
        }});
        canvas.addEventListener("wheel", (event) => {{
          event.preventDefault();
          const oldScale = scale;
          const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2;
          scale *= factor;
          if (scale > 2.8 && level > 0) {{
            scale = oldScale;
            setLevel(level - 1);
          }} else if (scale < 0.25 && level < cfg.levelDimensions.length - 1) {{
            scale = oldScale;
            setLevel(level + 1);
          }}
          draw();
        }}, {{ passive: false }});
        document.getElementById("zoomIn").onclick = () => setLevel(level - 1);
        document.getElementById("zoomOut").onclick = () => setLevel(level + 1);
        document.getElementById("copyCoords").onclick = async () => {{
          const p = currentPatchCoords();
          const text = `patch_x=${{p.x}}, patch_y=${{p.y}}, level=${{level}}`;
          try {{
            await navigator.clipboard.writeText(`${{p.x}},${{p.y}},${{level}}`);
            coordText.textContent = `${{text}} をコピーしました`;
          }} catch (error) {{
            coordText.textContent = text;
          }}
        }};
        draw();
        </script>
        """,
        height=650,
    )


def create_wsi_patch(
    wsi_path: Path,
    wsi_name: str,
    patch_x: int,
    patch_y: int,
    patch_width: int,
    patch_height: int,
    level: int,
    thumbnail_info: dict[str, Any],
    target_mpp: str,
) -> dict[str, Any]:
    level_downsamples = thumbnail_info.get("level_downsamples", [1.0])
    downsample = float(level_downsamples[level]) if level < len(level_downsamples) else 1.0
    patch_level0_width = int(round(patch_width * downsample))
    patch_level0_height = int(round(patch_height * downsample))
    patch_x, patch_y = clamp_patch_origin(
        patch_x,
        patch_y,
        patch_level0_width,
        patch_level0_height,
        int(thumbnail_info["wsi_width"]),
        int(thumbnail_info["wsi_height"]),
    )
    patch_id = f"patch_x{patch_x}_y{patch_y}_level{level}_{patch_width}x{patch_height}"
    output_path = patch_image_path(wsi_name, patch_id)
    if not output_path.exists():
        patch = read_wsi_region_rgb(wsi_path, patch_x, patch_y, level, patch_width, patch_height)
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
            "patch_width": patch_width,
            "patch_height": patch_height,
            "patch_level": level,
            "patch_downsample": downsample,
            "patch_level0_width": patch_level0_width,
            "patch_level0_height": patch_level0_height,
            "target_mpp": target_mpp,
            "mpp_x": thumbnail_info.get("mpp_x", ""),
            "mpp_y": thumbnail_info.get("mpp_y", ""),
        },
    }


def calculate_tissue_ratio(image: Image.Image, sample_size: int = 256) -> float:
    """Estimate the fraction of non-background H&E pixels in an image."""
    sample = image.convert("RGB")
    sample.thumbnail((sample_size, sample_size), Image.Resampling.BILINEAR)
    pixels = list(sample.getdata())
    if not pixels:
        return 0.0

    tissue_pixels = 0
    for red, green, blue in pixels:
        brightness = (red + green + blue) / 3
        saturation = max(red, green, blue) - min(red, green, blue)
        if brightness < 220 or (brightness < 245 and saturation > 8):
            tissue_pixels += 1
    return tissue_pixels / len(pixels)


def calculate_patch_features(image: Image.Image, sample_size: int = 256) -> dict[str, float]:
    """Calculate lightweight CLAM-inspired RGB/HSV patch descriptors."""
    sample = image.convert("RGB")
    sample.thumbnail((sample_size, sample_size), Image.Resampling.BILINEAR)
    rgb = np.asarray(sample, dtype=np.float32) / 255.0
    if rgb.size == 0:
        return {field: 0.0 for field in PATCH_FEATURE_FIELDS}

    hsv = np.asarray(sample.convert("HSV"), dtype=np.float32) / 255.0
    red = rgb[..., 0]
    green = rgb[..., 1]
    blue = rgb[..., 2]
    saturation = hsv[..., 1]
    brightness = hsv[..., 2]
    darkness = 1.0 - brightness
    tissue_mask = ((brightness < 0.86) | ((brightness < 0.96) & (saturation > 0.04))).astype(np.float32)

    purple_blue = np.clip(blue - green * 0.45 - red * 0.15, 0.0, 1.0)
    hematoxylin = (
        purple_blue
        * (0.35 + 0.65 * darkness)
        * (0.4 + 0.6 * saturation)
        * tissue_mask
    )

    pink_balance = np.clip(red - green * 0.55, 0.0, 1.0)
    eosin = (
        pink_balance
        * np.clip(blue - green * 0.15, 0.0, 1.0)
        * (0.3 + 0.7 * saturation)
        * tissue_mask
    )

    nuclei_mask = (
        (brightness < 0.72)
        & (blue > green * 0.85)
        & (red > green * 0.75)
        & (saturation > 0.12)
    )

    red_dominance = np.clip(red - np.maximum(green, blue) * 0.75, 0.0, 1.0)
    orange_balance = np.clip(red - blue * 0.55, 0.0, 1.0) * np.clip(green - blue * 0.25, 0.0, 1.0)
    red_orange = (
        np.maximum(red_dominance, orange_balance)
        * (0.25 + 0.75 * saturation)
        * tissue_mask
    )

    return {
        "brightness_mean": float(np.mean(brightness)),
        "saturation_mean": float(np.mean(saturation)),
        "hematoxylin_score": float(np.mean(hematoxylin)),
        "eosin_score": float(np.mean(eosin)),
        "nuclei_density_proxy": float(np.mean(nuclei_mask)),
        "red_orange_score": float(np.mean(red_orange)),
    }


def calculate_patch_priority(tissue_ratio: float, features: dict[str, float]) -> float:
    """Combine tissue, nuclei, eosin and red-orange signals into a temporary score."""
    score = (
        0.30 * min(max(tissue_ratio, 0.0), 1.0)
        + 0.30 * min(max(features.get("nuclei_density_proxy", 0.0) * 4.0, 0.0), 1.0)
        + 0.25 * min(max(features.get("eosin_score", 0.0) * 8.0, 0.0), 1.0)
        + 0.15 * min(max(features.get("red_orange_score", 0.0) * 6.0, 0.0), 1.0)
    )
    return min(max(score, 0.0), 1.0)


def cluster_patch_manifest(source_wsi_name: str, cluster_count: int) -> int:
    """Cluster feature-complete patches for one WSI and persist cluster_id."""
    from sklearn.cluster import MiniBatchKMeans
    from sklearn.preprocessing import StandardScaler

    manifest = load_patch_manifest()
    if manifest.empty:
        return 0
    source_mask = manifest["source_wsi_name"] == source_wsi_name
    source_rows = manifest.loc[source_mask].copy()
    if source_rows.empty:
        return 0

    feature_frame = source_rows[PATCH_FEATURE_FIELDS].apply(pd.to_numeric, errors="coerce")
    valid_mask = feature_frame.notna().all(axis=1)
    valid_features = feature_frame.loc[valid_mask]
    if valid_features.empty:
        return 0

    resolved_cluster_count = max(1, min(int(cluster_count), len(valid_features)))
    scaled_features = StandardScaler().fit_transform(valid_features)
    resolved_cluster_count = min(resolved_cluster_count, len(np.unique(scaled_features, axis=0)))
    if resolved_cluster_count == 1:
        labels = np.zeros(len(valid_features), dtype=int)
    else:
        labels = MiniBatchKMeans(
            n_clusters=resolved_cluster_count,
            random_state=42,
            batch_size=2048,
            n_init=10,
        ).fit_predict(scaled_features)

    manifest.loc[valid_features.index, "cluster_id"] = labels.astype(str)
    manifest.loc[source_mask, "updated_at"] = tokyo_now_iso()
    save_patch_manifest(manifest)
    return resolved_cluster_count


def recalculate_patch_features(source_wsi_name: str, cluster_count: int) -> dict[str, int]:
    """Backfill features and priority for existing saved patches."""
    manifest = load_patch_manifest()
    if manifest.empty:
        return {"updated": 0, "clusters": 0, "missing": 0}

    source_mask = manifest["source_wsi_name"] == source_wsi_name
    updated = 0
    missing = 0
    for index, row in manifest.loc[source_mask].iterrows():
        image_path = Path(str(row.get("image_path", "")))
        if not image_path.exists():
            image_path = patch_image_path(source_wsi_name, str(row["patch_id"]))
        if not image_path.exists():
            missing += 1
            continue
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
            tissue_ratio = calculate_tissue_ratio(rgb_image)
            features = calculate_patch_features(rgb_image)
        priority_score = calculate_patch_priority(tissue_ratio, features)
        manifest.loc[index, "tissue_ratio"] = f"{tissue_ratio:.6f}"
        for field, value in features.items():
            manifest.loc[index, field] = f"{value:.6f}"
        manifest.loc[index, "priority_score"] = f"{priority_score:.6f}"
        manifest.loc[index, "feature_version"] = PATCH_FEATURE_VERSION
        manifest.loc[index, "updated_at"] = tokyo_now_iso()
        updated += 1

    save_patch_manifest(manifest)
    clusters = cluster_patch_manifest(source_wsi_name, cluster_count) if updated else 0
    return {"updated": updated, "clusters": clusters, "missing": missing}


def load_patch_manifest() -> pd.DataFrame:
    if not PATCH_MANIFEST_PATH.exists():
        return pd.DataFrame(columns=PATCH_MANIFEST_FIELDS)
    try:
        manifest = pd.read_csv(PATCH_MANIFEST_PATH, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError):
        return pd.DataFrame(columns=PATCH_MANIFEST_FIELDS)
    for field in PATCH_MANIFEST_FIELDS:
        if field not in manifest.columns:
            manifest[field] = ""
    for field in ("created_at", "updated_at", "reviewed_at", "exported_at"):
        manifest[field] = manifest[field].map(
            lambda value: normalize_tokyo_timestamp(value, "") if str(value).strip() else ""
        )
    return manifest[PATCH_MANIFEST_FIELDS]


def save_patch_manifest(manifest: pd.DataFrame) -> None:
    PATCH_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized = manifest.copy()
    for field in PATCH_MANIFEST_FIELDS:
        if field not in normalized.columns:
            normalized[field] = ""
    normalized[PATCH_MANIFEST_FIELDS].to_csv(
        PATCH_MANIFEST_PATH,
        index=False,
        encoding="utf-8-sig",
    )


def patch_queue_rows(source_wsi_name: str, sort_by: str = "spatial") -> pd.DataFrame:
    manifest = load_patch_manifest()
    if manifest.empty:
        return manifest
    rows = manifest[manifest["source_wsi_name"] == source_wsi_name].copy()
    if rows.empty:
        return rows
    rows["_patch_y"] = pd.to_numeric(rows["patch_y"], errors="coerce").fillna(0)
    rows["_patch_x"] = pd.to_numeric(rows["patch_x"], errors="coerce").fillna(0)
    rows["_priority_score"] = pd.to_numeric(rows["priority_score"], errors="coerce").fillna(-1)
    rows["_cluster_id"] = pd.to_numeric(rows["cluster_id"], errors="coerce").fillna(999999)
    rows["_tissue_ratio"] = pd.to_numeric(rows["tissue_ratio"], errors="coerce").fillna(-1)

    if sort_by == "priority_score":
        sort_columns = ["_priority_score", "_cluster_id", "_patch_y", "_patch_x"]
        ascending = [False, True, True, True]
    elif sort_by == "cluster_id":
        sort_columns = ["_cluster_id", "_priority_score", "_patch_y", "_patch_x"]
        ascending = [True, False, True, True]
    elif sort_by == "tissue_ratio":
        sort_columns = ["_tissue_ratio", "_patch_y", "_patch_x"]
        ascending = [False, True, True]
    else:
        sort_columns = ["_patch_y", "_patch_x"]
        ascending = [True, True]
    helper_columns = ["_patch_y", "_patch_x", "_priority_score", "_cluster_id", "_tissue_ratio"]
    return rows.sort_values(sort_columns, ascending=ascending).drop(columns=helper_columns).reset_index(drop=True)


def patch_metadata_lookup() -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for payload in saved_annotation_payloads():
        metadata = payload.get("image_metadata", {})
        key = (
            str(metadata.get("source_wsi_name", "")).strip(),
            str(metadata.get("patch_id", "")).strip(),
        )
        if all(key):
            lookup[key] = metadata
    return lookup


def positive_exploration_rows(
    source_wsi_name: str,
    *,
    only_unreviewed: bool = True,
    flagged_only: bool = False,
    exclude_reviewed_empty: bool = True,
    exclude_done: bool = False,
    exclude_skipped: bool = True,
    exclude_from_training: bool = True,
    minimum_priority_score: float = 0.0,
    top_n: int = 100,
    cluster_id: str = "all",
    statuses: list[str] | None = None,
    tissue_region: str = "all",
    disease_context: str = "all",
    source_organ: str = "all",
    sort_by: str = "priority_score desc",
    per_cluster: int = 5,
    random_seed: int = 42,
) -> tuple[pd.DataFrame, list[str]]:
    """Build a filtered, read-only queue for finding likely positive patches."""
    manifest = load_patch_manifest()
    warnings: list[str] = []
    if manifest.empty:
        return manifest, warnings
    rows = manifest.loc[
        manifest["source_wsi_name"].eq(source_wsi_name)
    ].copy()
    if rows.empty:
        return rows, warnings

    metadata_by_patch = patch_metadata_lookup()
    slide_metadata = slide_metadata_by_wsi().get(source_wsi_name, {})
    for field in ("tissue_region", "disease_context", "source_organ"):
        rows[field] = [
            metadata_by_patch.get((source_wsi_name, str(patch_id)), {}).get(
                field,
                slide_metadata.get(field, ""),
            )
            for patch_id in rows["patch_id"]
        ]

    rows["_priority"] = pd.to_numeric(
        rows.get("priority_score", pd.Series(index=rows.index, dtype=str)),
        errors="coerce",
    )
    rows["_tissue"] = pd.to_numeric(
        rows.get("tissue_ratio", pd.Series(index=rows.index, dtype=str)),
        errors="coerce",
    ).fillna(-1)
    rows["_cluster_text"] = rows.get(
        "cluster_id", pd.Series("", index=rows.index)
    ).fillna("").astype(str).str.strip()
    rows["_cluster_number"] = pd.to_numeric(
        rows["_cluster_text"], errors="coerce"
    ).fillna(999999)
    rows["_patch_x"] = pd.to_numeric(rows["patch_x"], errors="coerce").fillna(0)
    rows["_patch_y"] = pd.to_numeric(rows["patch_y"], errors="coerce").fillna(0)

    if exclude_from_training and "exclude_from_training" in rows.columns:
        rows = rows.loc[~rows["exclude_from_training"].map(safe_bool)]
    if only_unreviewed:
        rows = rows.loc[
            rows["status"].isin(
                ["not_started", "in_progress", "flagged", "suspected_positive"]
            )
        ]
    if flagged_only:
        rows = rows.loc[
            rows["status"].isin(["flagged", "suspected_positive"])
        ]
    if exclude_reviewed_empty:
        rows = rows.loc[~rows["status"].eq("reviewed_empty")]
    if exclude_done:
        rows = rows.loc[~rows["status"].eq("done")]
    if exclude_skipped:
        rows = rows.loc[~rows["status"].eq("skipped")]
    if statuses:
        rows = rows.loc[rows["status"].isin(statuses)]
    if minimum_priority_score > 0:
        rows = rows.loc[rows["_priority"].fillna(-1).ge(minimum_priority_score)]
    if cluster_id != "all":
        rows = rows.loc[rows["_cluster_text"].eq(str(cluster_id))]
    for field, value in (
        ("tissue_region", tissue_region),
        ("disease_context", disease_context),
        ("source_organ", source_organ),
    ):
        if value != "all" and field in rows.columns:
            rows = rows.loc[rows[field].fillna("").astype(str).eq(value)]

    if sort_by == "tissue_ratio desc":
        rows = rows.sort_values(
            ["_tissue", "_priority"], ascending=[False, False], kind="stable"
        )
    elif sort_by == "cluster_id then priority_score":
        rows = rows.sort_values(
            ["_cluster_number", "_priority"],
            ascending=[True, False],
            kind="stable",
        )
    elif sort_by == "spatial":
        rows = rows.sort_values(
            ["_patch_y", "_patch_x"], ascending=[True, True], kind="stable"
        )
    elif sort_by == "random sample":
        rows = rows.sample(frac=1, random_state=random_seed)
    elif sort_by == "cluster-balanced":
        clustered = rows.loc[rows["_cluster_text"].ne("")].copy()
        if clustered.empty:
            warnings.append(
                "cluster_idがないためpriority_score順へfallbackしました。"
            )
            rows = rows.sort_values(
                ["_priority", "_tissue"],
                ascending=[False, False],
                kind="stable",
            )
        else:
            clustered = clustered.sort_values(
                ["_cluster_number", "_priority", "_tissue"],
                ascending=[True, False, False],
                kind="stable",
            )
            rows = (
                clustered.groupby("_cluster_text", sort=True, group_keys=False)
                .head(max(1, int(per_cluster)))
                .sort_values(
                    ["_priority", "_cluster_number"],
                    ascending=[False, True],
                    kind="stable",
                )
            )
    else:
        rows = rows.sort_values(
            ["_priority", "_tissue"],
            ascending=[False, False],
            kind="stable",
        )

    if top_n > 0:
        rows = rows.head(int(top_n))
    helper_columns = [
        "_priority",
        "_tissue",
        "_cluster_text",
        "_cluster_number",
        "_patch_x",
        "_patch_y",
    ]
    return rows.drop(columns=helper_columns).reset_index(drop=True), warnings


def current_review_queue_rows(source_wsi_name: str) -> tuple[pd.DataFrame, list[str]]:
    if st.session_state.get("patch_review_mode") != "Positive exploration":
        return (
            patch_queue_rows(
                source_wsi_name,
                str(st.session_state.get("patch_queue_sort_by", "priority_score")),
            ),
            [],
        )
    return positive_exploration_rows(
        source_wsi_name,
        only_unreviewed=bool(st.session_state.get("positive_only_unreviewed", True)),
        flagged_only=bool(st.session_state.get("positive_flagged_only", False)),
        exclude_reviewed_empty=bool(
            st.session_state.get("positive_exclude_reviewed_empty", True)
        ),
        exclude_done=bool(st.session_state.get("positive_exclude_done", False)),
        exclude_skipped=bool(st.session_state.get("positive_exclude_skipped", True)),
        exclude_from_training=bool(
            st.session_state.get("positive_exclude_training", True)
        ),
        minimum_priority_score=float(
            st.session_state.get("positive_min_priority", 0.0)
        ),
        top_n=int(st.session_state.get("positive_top_n", 100)),
        cluster_id=str(st.session_state.get("positive_cluster_filter", "all")),
        statuses=list(st.session_state.get("positive_status_filter", [])),
        tissue_region=str(
            st.session_state.get("positive_tissue_region_filter", "all")
        ),
        disease_context=str(
            st.session_state.get("positive_disease_context_filter", "all")
        ),
        source_organ=str(
            st.session_state.get("positive_source_organ_filter", "all")
        ),
        sort_by=str(
            st.session_state.get("positive_sort", "priority_score desc")
        ),
        per_cluster=int(st.session_state.get("positive_per_cluster", 5)),
        random_seed=int(st.session_state.get("positive_random_seed", 42)),
    )


def update_patch_manifest_status(
    source_wsi_name: str,
    patch_id: str,
    status: str,
    annotations: list[dict[str, Any]] | None = None,
) -> None:
    if status not in PATCH_QUEUE_STATUSES:
        raise ValueError(f"Unknown patch status: {status}")
    manifest = load_patch_manifest()
    if manifest.empty:
        return
    mask = (manifest["source_wsi_name"] == source_wsi_name) & (manifest["patch_id"] == patch_id)
    if not mask.any():
        return
    manifest.loc[mask, "status"] = status
    now = tokyo_now_iso()
    manifest.loc[mask, "updated_at"] = now
    if status in {"done", "reviewed_empty"}:
        manifest.loc[mask, "reviewed_at"] = now
    if annotations is not None:
        manifest.loc[mask, "annotation_count"] = str(len(annotations))
        manifest.loc[mask, "eosinophil_count"] = str(
            sum(1 for item in annotations if item.get("label") == "eosinophil")
        )
    save_patch_manifest(manifest)


def update_patch_manifest_counts(
    source_wsi_name: str,
    patch_id: str,
    annotations: list[dict[str, Any]],
) -> None:
    manifest = load_patch_manifest()
    if manifest.empty:
        return
    mask = (manifest["source_wsi_name"] == source_wsi_name) & (manifest["patch_id"] == patch_id)
    if not mask.any():
        return
    manifest.loc[mask, "annotation_count"] = str(len(annotations))
    manifest.loc[mask, "eosinophil_count"] = str(
        sum(1 for item in annotations if item.get("label") == "eosinophil")
    )
    manifest.loc[mask, "updated_at"] = tokyo_now_iso()
    save_patch_manifest(manifest)


def generate_wsi_patch_queue(
    wsi_path: Path,
    wsi_name: str,
    patch_size: int,
    level: int,
    thumbnail: Image.Image,
    thumbnail_info: dict[str, Any],
    target_mpp: str,
    objective_magnification: str,
    minimum_tissue_ratio: float,
    cluster_count: int,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Create non-overlapping tissue patches and upsert them into the queue manifest."""
    level_dimensions = thumbnail_info.get("level_dimensions", [])
    level_downsamples = thumbnail_info.get("level_downsamples", [])
    if level >= len(level_dimensions):
        raise ValueError("Selected OpenSlide level is unavailable.")

    level_width, level_height = level_dimensions[level]
    downsample = float(level_downsamples[level])
    base_mpp = safe_float(thumbnail_info.get("mpp_x"))
    resolved_target_mpp = (
        target_mpp
        or (f"{base_mpp * downsample:.6f}" if base_mpp is not None else "")
    )
    patch_level0_size = int(round(patch_size * downsample))
    x_positions = range(0, max(0, level_width - patch_size) + 1, patch_size)
    y_positions = range(0, max(0, level_height - patch_size) + 1, patch_size)
    grid = [(x, y) for y in y_positions for x in x_positions]
    existing_manifest = load_patch_manifest()
    existing_lookup = {
        (row["source_wsi_name"], row["patch_id"]): row
        for _, row in existing_manifest.iterrows()
    }
    generated_rows: list[dict[str, Any]] = []
    excluded = 0

    slide = open_wsi_slide(wsi_path)
    try:
        for index, (level_x, level_y) in enumerate(grid):
            patch_x = int(round(level_x * downsample))
            patch_y = int(round(level_y * downsample))
            thumb_left = int(patch_x / thumbnail_info["scale_x"])
            thumb_top = int(patch_y / thumbnail_info["scale_y"])
            thumb_right = max(
                thumb_left + 1,
                int((patch_x + patch_level0_size) / thumbnail_info["scale_x"]),
            )
            thumb_bottom = max(
                thumb_top + 1,
                int((patch_y + patch_level0_size) / thumbnail_info["scale_y"]),
            )
            thumbnail_crop = thumbnail.crop((thumb_left, thumb_top, thumb_right, thumb_bottom))
            thumbnail_ratio = calculate_tissue_ratio(thumbnail_crop)
            if thumbnail_ratio < minimum_tissue_ratio * 0.5:
                excluded += 1
                if progress_callback:
                    progress_callback(index + 1, len(grid))
                continue

            patch = slide.read_region((patch_x, patch_y), level, (patch_size, patch_size))
            if patch.mode == "RGBA":
                background = Image.new("RGBA", patch.size, (255, 255, 255, 255))
                patch = Image.alpha_composite(background, patch)
            patch = patch.convert("RGB")
            tissue_ratio = calculate_tissue_ratio(patch)
            if tissue_ratio < minimum_tissue_ratio:
                excluded += 1
                if progress_callback:
                    progress_callback(index + 1, len(grid))
                continue
            features = calculate_patch_features(patch)
            priority_score = calculate_patch_priority(tissue_ratio, features)

            patch_id = f"patch_x{patch_x}_y{patch_y}_level{level}_{patch_size}x{patch_size}"
            output_path = patch_image_path(wsi_name, patch_id)
            if not output_path.exists():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                patch.save(output_path)

            previous = existing_lookup.get((wsi_name, patch_id), {})
            generated_rows.append(
                {
                    "source_wsi_name": wsi_name,
                    "patch_id": patch_id,
                    "image_path": str(output_path),
                    "patch_x": patch_x,
                    "patch_y": patch_y,
                    "patch_width": patch_size,
                    "patch_height": patch_size,
                    "patch_level": level,
                    "patch_downsample": downsample,
                    "target_mpp": resolved_target_mpp,
                    "objective_magnification": objective_magnification,
                    "tissue_ratio": f"{tissue_ratio:.6f}",
                    **{field: f"{value:.6f}" for field, value in features.items()},
                    "cluster_id": previous.get("cluster_id", ""),
                    "priority_score": f"{priority_score:.6f}",
                    "feature_version": PATCH_FEATURE_VERSION,
                    "status": previous.get("status", "not_started"),
                    "annotation_count": previous.get("annotation_count", "0"),
                    "eosinophil_count": previous.get("eosinophil_count", "0"),
                    "created_at": previous.get("created_at", "") or tokyo_now_iso(),
                    "updated_at": tokyo_now_iso(),
                    "reviewed_at": previous.get("reviewed_at", ""),
                    "exported_at": previous.get("exported_at", ""),
                    "exclude_from_training": previous.get(
                        "exclude_from_training", ""
                    ),
                    "exclusion_reason": previous.get("exclusion_reason", ""),
                    "notes": previous.get("notes", ""),
                }
            )
            if progress_callback:
                progress_callback(index + 1, len(grid))
    finally:
        slide.close()

    other_rows = existing_manifest[existing_manifest["source_wsi_name"] != wsi_name].copy()
    generated_frame = pd.DataFrame(generated_rows, columns=PATCH_MANIFEST_FIELDS)
    combined = (
        generated_frame
        if other_rows.empty
        else pd.concat([other_rows, generated_frame], ignore_index=True)
    )
    save_patch_manifest(combined)
    clusters = cluster_patch_manifest(wsi_name, cluster_count) if generated_rows else 0
    return {
        "generated": len(generated_rows),
        "excluded": excluded,
        "total_tiles": len(grid),
        "clusters": clusters,
    }


def prepared_patch_from_manifest_row(
    row: dict[str, Any],
    wsi_path: Path,
    thumbnail_info: dict[str, Any],
) -> dict[str, Any]:
    patch_id = str(row["patch_id"])
    image_path = Path(str(row.get("image_path", "")))
    if not image_path.exists():
        image_path = patch_image_path(str(row["source_wsi_name"]), patch_id)
    if not image_path.exists():
        patch = read_wsi_region_rgb(
            wsi_path,
            int(float(row["patch_x"])),
            int(float(row["patch_y"])),
            int(float(row["patch_level"])),
            int(float(row["patch_width"])),
            int(float(row["patch_height"])),
        )
        image_path.parent.mkdir(parents=True, exist_ok=True)
        patch.save(image_path)

    downsample = float(row.get("patch_downsample") or 1.0)
    patch_width = int(float(row["patch_width"]))
    patch_height = int(float(row["patch_height"]))
    return {
        "image_name": image_path.name,
        "image_path": image_path,
        "source_image_path": wsi_path,
        "source_format": "wsi_patch",
        "patch_metadata": {
            "source_wsi_name": str(row["source_wsi_name"]),
            "patch_id": patch_id,
            "patch_x": int(float(row["patch_x"])),
            "patch_y": int(float(row["patch_y"])),
            "patch_width": patch_width,
            "patch_height": patch_height,
            "patch_level": int(float(row["patch_level"])),
            "patch_downsample": downsample,
            "patch_level0_width": int(round(patch_width * downsample)),
            "patch_level0_height": int(round(patch_height * downsample)),
            "target_mpp": row.get("target_mpp", ""),
            "mpp_x": thumbnail_info.get("mpp_x", ""),
            "mpp_y": thumbnail_info.get("mpp_y", ""),
            "reviewed_at": row.get("reviewed_at", ""),
            "exported_at": row.get("exported_at", ""),
            "patch_status": row.get("status", ""),
            "exclude_from_training": safe_bool(
                row.get("exclude_from_training", False)
            ),
            "exclusion_reason": row.get("exclusion_reason", ""),
            "notes": row.get("notes", ""),
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
    annotation_created_at = normalize_tokyo_timestamp(
        obj.get("annotation_created_at")
        or obj.get("created_at")
        or created_at,
        created_at,
    )

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
        "annotation_id": obj.get("annotation_id") or f"ann_{uuid4().hex}",
        "annotation_created_at": annotation_created_at,
        "annotation_updated_at": obj.get("annotation_updated_at", annotation_created_at),
        "annotation_session_id": (
            obj.get("annotation_session_id")
            or st.session_state.get("annotation_session_id", "")
        ),
        "created_at": annotation_created_at,
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

    created_at = tokyo_now_iso()
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
    patch_downsample = safe_float(metadata.get("patch_downsample"), 1.0) or 1.0

    normalized["x_in_patch"] = safe_round(x_in_patch)
    normalized["y_in_patch"] = safe_round(y_in_patch)
    normalized["x_wsi"] = safe_round(patch_x + x_in_patch * patch_downsample)
    normalized["y_wsi"] = safe_round(patch_y + y_in_patch * patch_downsample)
    normalized["patch_x"] = metadata.get("patch_x", "")
    normalized["patch_y"] = metadata.get("patch_y", "")
    normalized["patch_level"] = metadata.get("patch_level", "")
    normalized["patch_downsample"] = metadata.get("patch_downsample", "")
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
    fallback_time = normalize_tokyo_timestamp(
        normalized.get("annotation_created_at")
        or normalized.get("created_at")
        or tokyo_now_iso()
    )
    normalized["annotation_id"] = normalized.get("annotation_id") or f"ann_{uuid4().hex}"
    normalized["annotation_created_at"] = fallback_time
    normalized["annotation_updated_at"] = (
        normalize_tokyo_timestamp(normalized.get("annotation_updated_at"), fallback_time)
    )
    normalized["annotation_session_id"] = (
        normalized.get("annotation_session_id")
        or st.session_state.get("annotation_session_id", "")
        or new_annotation_session_id()
    )
    normalized["created_at"] = normalized.get("created_at") or fallback_time
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
        "annotation_id": annotation.get("annotation_id", ""),
        "annotation_created_at": annotation.get("annotation_created_at", annotation.get("created_at", "")),
        "annotation_updated_at": annotation.get("annotation_updated_at", ""),
        "annotation_session_id": annotation.get("annotation_session_id", ""),
        "created_at": annotation.get("created_at", tokyo_now_iso()),
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
    imported_at = tokyo_now_iso()
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
        return pd.DataFrame(columns=ANNOTATION_TRACKING_FIELDS)
    frame = pd.DataFrame(annotations)
    for field in ANNOTATION_TRACKING_FIELDS:
        if field not in frame.columns:
            frame[field] = ""
    return frame


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
    counts_with_context["reviewed_at"] = metadata.get("reviewed_at", "")
    counts_with_context["exported_at"] = metadata.get("exported_at", "")
    return counts_with_context


def patch_timestamps(source_wsi_name: str, patch_id: str) -> dict[str, str]:
    if not source_wsi_name or not patch_id:
        return {"created_at": "", "updated_at": "", "reviewed_at": "", "exported_at": ""}
    manifest = load_patch_manifest()
    if manifest.empty:
        return {"created_at": "", "updated_at": "", "reviewed_at": "", "exported_at": ""}
    mask = (manifest["source_wsi_name"] == source_wsi_name) & (manifest["patch_id"] == patch_id)
    if not mask.any():
        return {"created_at": "", "updated_at": "", "reviewed_at": "", "exported_at": ""}
    row = manifest.loc[mask].iloc[0]
    return {
        field: str(row.get(field, ""))
        for field in ("created_at", "updated_at", "reviewed_at", "exported_at")
    }


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
    timestamps = patch_timestamps(
        str(metadata.get("source_wsi_name", "")),
        str(metadata.get("patch_id", "")),
    )
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
        "reviewed_at": metadata.get("reviewed_at", "") or timestamps["reviewed_at"],
        "exported_at": metadata.get("exported_at", "") or timestamps["exported_at"],
        "exclude_from_training": safe_bool(
            metadata.get("exclude_from_training", False)
        ),
        "exclusion_reason": metadata.get("exclusion_reason", ""),
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
    only_completed_patch_queue: bool = False,
) -> dict[str, Any]:
    ensure_directories()
    exported_images = 0
    exported_labels = 0
    skipped_images = []
    patch_manifest = load_patch_manifest()
    patch_lookup = {
        (row["source_wsi_name"], row["patch_id"]): row
        for _, row in patch_manifest.iterrows()
    }

    for payload in saved_annotation_payloads():
        metadata = payload.get("image_metadata", {})
        metadata = metadata.copy()
        timestamps = patch_timestamps(
            str(metadata.get("source_wsi_name", "")),
            str(metadata.get("patch_id", "")),
        )
        metadata["reviewed_at"] = metadata.get("reviewed_at", "") or timestamps["reviewed_at"]
        metadata["exported_at"] = timestamps["exported_at"] or metadata.get("exported_at", "")
        if safe_bool(metadata.get("exclude_from_training", False)):
            skipped_images.append(payload.get("image_name", "unknown"))
            continue
        if only_reviewed_or_exported and not (metadata.get("reviewed") or metadata.get("exported")):
            skipped_images.append(payload.get("image_name", "unknown"))
            continue
        patch_key = (
            str(metadata.get("source_wsi_name", "")),
            str(metadata.get("patch_id", "")),
        )
        patch_row = patch_lookup.get(patch_key)
        queue_status = patch_row.get("status") if patch_row is not None else None
        if patch_row is not None and safe_bool(
            patch_row.get("exclude_from_training", False)
        ):
            skipped_images.append(payload.get("image_name", "unknown"))
            continue
        if (
            only_completed_patch_queue
            and queue_status is not None
            and queue_status not in {"done", "reviewed_empty"}
        ):
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
        exported_at = tokyo_now_iso()
        mark_patch_exported(
            str(metadata.get("source_wsi_name", "")),
            str(metadata.get("patch_id", "")),
            exported_at,
            str(metadata.get("reviewed_at", "")),
        )
        exported_images += 1
        exported_labels += 1

    yaml_path = write_data_yaml()
    regenerate_dataset_exports()
    return {
        "images": exported_images,
        "labels": exported_labels,
        "skipped": skipped_images,
        "data_yaml": yaml_path,
    }


def slide_metadata_by_wsi() -> dict[str, dict[str, Any]]:
    """Collect the latest saved image metadata for each source WSI."""
    metadata_lookup: dict[str, dict[str, Any]] = {}
    for payload in saved_annotation_payloads():
        metadata = payload.get("image_metadata", {})
        source_wsi_name = str(metadata.get("source_wsi_name", "")).strip()
        if source_wsi_name:
            metadata_lookup[source_wsi_name] = metadata
    return metadata_lookup


def generate_clam_compatible_export(
    only_completed_patches: bool = True,
) -> dict[str, Any]:
    """Export CSV staging data for later CLAM/MIL feature extraction."""
    ensure_directories()
    manifest = load_patch_manifest()
    if manifest.empty:
        return {
            "slides": 0,
            "patches": 0,
            "skipped": 0,
            "clam_dir": CLAM_DIR,
        }

    export_manifest = manifest.copy()
    skipped = 0
    excluded_mask = export_manifest["exclude_from_training"].map(safe_bool)
    skipped += int(excluded_mask.sum())
    export_manifest = export_manifest.loc[~excluded_mask].copy()
    if only_completed_patches:
        completed_mask = export_manifest["status"].isin(["done", "reviewed_empty"])
        skipped += int((~completed_mask).sum())
        export_manifest = export_manifest.loc[completed_mask].copy()

    clam_exported_at = tokyo_now_iso()
    if not export_manifest.empty:
        manifest.loc[export_manifest.index, "exported_at"] = clam_exported_at
        manifest.loc[export_manifest.index, "updated_at"] = clam_exported_at
        export_manifest.loc[:, "exported_at"] = clam_exported_at
        export_manifest.loc[:, "updated_at"] = clam_exported_at
        save_patch_manifest(manifest)

    metadata_lookup = slide_metadata_by_wsi()
    if not export_manifest.empty:
        slide_excluded = export_manifest["source_wsi_name"].map(
            lambda source_name: safe_bool(
                metadata_lookup.get(str(source_name), {}).get(
                    "exclude_from_training", False
                )
            )
        )
        skipped += int(slide_excluded.sum())
        export_manifest = export_manifest.loc[~slide_excluded].copy()
    patch_manifest_rows: list[dict[str, Any]] = []
    slide_label_rows: list[dict[str, Any]] = []
    process_rows: list[dict[str, Any]] = []

    for source_wsi_name, slide_rows in export_manifest.groupby("source_wsi_name", sort=True):
        metadata = metadata_lookup.get(source_wsi_name, {})
        slide_stem = safe_file_stem(Path(source_wsi_name).stem)
        slide_id = str(metadata.get("slide_id", "")).strip() or slide_stem
        specimen_id = str(metadata.get("specimen_id", "")).strip()
        patient_id_hash = str(metadata.get("patient_id_hash", "")).strip()
        case_id = patient_id_hash or specimen_id or slide_id
        label = str(metadata.get("disease_context", "")).strip() or "unknown"
        wsi_path = ORIGINAL_WSI_DIR / source_wsi_name

        coords = slide_rows[
            [
                "patch_id",
                "patch_x",
                "patch_y",
                "patch_width",
                "patch_height",
                "patch_level",
                "patch_downsample",
                "target_mpp",
                "status",
                "created_at",
                "updated_at",
                "reviewed_at",
                "exported_at",
            ]
        ].copy()
        coords = coords.rename(columns={"patch_x": "x", "patch_y": "y"})
        coords.insert(0, "slide_id", slide_id)
        coords.to_csv(
            CLAM_COORD_DIR / f"{slide_stem}.csv",
            index=False,
            encoding="utf-8-sig",
        )

        features = slide_rows[
            [
                "patch_id",
                "patch_x",
                "patch_y",
                *PATCH_FEATURE_FIELDS,
                "cluster_id",
                "priority_score",
                "feature_version",
                "reviewed_at",
                "exported_at",
            ]
        ].copy()
        features.insert(0, "slide_id", slide_id)
        features.to_csv(
            CLAM_FEATURE_DIR / f"{slide_stem}.csv",
            index=False,
            encoding="utf-8-sig",
        )

        slide_label_rows.append(
            {
                "case_id": case_id,
                "slide_id": slide_id,
                "source_wsi_name": source_wsi_name,
                "label": label,
                "project_template": metadata.get("project_template", ""),
                "source_organ": metadata.get("source_organ", ""),
                "tissue_type": metadata.get("tissue_type", ""),
                "specimen_id": specimen_id,
                "patient_id_hash": patient_id_hash,
                "wsi_path": str(wsi_path),
                "patch_count": len(slide_rows),
                "exclude_from_training": False,
                "exclusion_reason": "",
                "reviewed_at": max(
                    (str(value) for value in slide_rows["reviewed_at"] if str(value)),
                    default="",
                ),
                "exported_at": max(
                    (str(value) for value in slide_rows["exported_at"] if str(value)),
                    default="",
                ),
            }
        )
        process_rows.append(
            {
                "slide_id": slide_id,
                "source_wsi_name": source_wsi_name,
                "slide_path": str(wsi_path),
                "process": 1,
                "status": "tbp",
                "patch_count": len(slide_rows),
                "exclude_from_training": False,
                "exclusion_reason": "",
                "coords_csv": str(CLAM_COORD_DIR / f"{slide_stem}.csv"),
                "features_csv": str(CLAM_FEATURE_DIR / f"{slide_stem}.csv"),
                "reviewed_at": max(
                    (str(value) for value in slide_rows["reviewed_at"] if str(value)),
                    default="",
                ),
                "exported_at": max(
                    (str(value) for value in slide_rows["exported_at"] if str(value)),
                    default="",
                ),
            }
        )

        for _, patch_row in slide_rows.iterrows():
            exported_row = patch_row.to_dict()
            exported_row.update(
                {
                    "case_id": case_id,
                    "slide_id": slide_id,
                    "slide_label": label,
                    "wsi_path": str(wsi_path),
                    "coords_csv": str(CLAM_COORD_DIR / f"{slide_stem}.csv"),
                    "features_csv": str(CLAM_FEATURE_DIR / f"{slide_stem}.csv"),
                }
            )
            patch_manifest_rows.append(exported_row)

    pd.DataFrame(patch_manifest_rows).to_csv(
        CLAM_DIR / "patch_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(slide_label_rows).to_csv(
        CLAM_DIR / "slide_labels.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(process_rows).to_csv(
        CLAM_DIR / "process_list_autogen.csv",
        index=False,
        encoding="utf-8-sig",
    )
    regenerate_dataset_exports()
    return {
        "slides": len(slide_label_rows),
        "patches": len(patch_manifest_rows),
        "skipped": skipped,
        "clam_dir": CLAM_DIR,
        "patch_manifest": CLAM_DIR / "patch_manifest.csv",
        "slide_labels": CLAM_DIR / "slide_labels.csv",
        "process_list": CLAM_DIR / "process_list_autogen.csv",
    }


def read_validation_csv(path: Path) -> tuple[pd.DataFrame | None, str | None]:
    if not path.exists():
        return None, f"ファイルがありません: {path}"
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False), None
    except pd.errors.EmptyDataError:
        return pd.DataFrame(), f"CSVが空です: {path}"
    except (OSError, pd.errors.ParserError) as error:
        return None, f"CSVを読み込めません: {path} ({error})"


def validate_clam_export() -> dict[str, Any]:
    """Validate CLAM-compatible CSV staging files and patch_id relationships."""
    required_paths = {
        "patch_manifest": CLAM_DIR / "patch_manifest.csv",
        "slide_labels": CLAM_DIR / "slide_labels.csv",
        "process_list": CLAM_DIR / "process_list_autogen.csv",
    }
    errors: list[str] = []
    warnings: list[str] = []
    files_checked = 0
    for directory, label in (
        (CLAM_COORD_DIR, "coords"),
        (CLAM_FEATURE_DIR, "features"),
    ):
        if not directory.exists():
            errors.append(f"{label}ディレクトリがありません: {directory}")
        elif not list(directory.glob("*.csv")):
            warnings.append(f"{label}ディレクトリにCSVがありません: {directory}")

    loaded: dict[str, pd.DataFrame] = {}
    for name, path in required_paths.items():
        frame, error = read_validation_csv(path)
        if error:
            errors.append(error)
        if frame is not None:
            loaded[name] = frame
            files_checked += 1

    manifest = loaded.get("patch_manifest", pd.DataFrame())
    slide_labels = loaded.get("slide_labels", pd.DataFrame())
    process_list = loaded.get("process_list", pd.DataFrame())

    manifest_required = {"patch_id", "slide_id", "source_wsi_name", "status"}
    labels_required = {"slide_id", "patch_count"}
    process_required = {"slide_id", "patch_count", "coords_csv", "features_csv"}
    for name, frame, required_columns in (
        ("patch_manifest.csv", manifest, manifest_required),
        ("slide_labels.csv", slide_labels, labels_required),
        ("process_list_autogen.csv", process_list, process_required),
    ):
        missing_columns = sorted(required_columns - set(frame.columns))
        if missing_columns:
            errors.append(f"{name}に必須列がありません: {', '.join(missing_columns)}")

    patch_count = len(manifest)
    slide_ids = set(manifest["slide_id"]) if "slide_id" in manifest.columns else set()
    label_slide_ids = set(slide_labels["slide_id"]) if "slide_id" in slide_labels.columns else set()
    process_slide_ids = set(process_list["slide_id"]) if "slide_id" in process_list.columns else set()
    all_slide_ids = slide_ids | label_slide_ids | process_slide_ids
    status_counts = (
        manifest["status"].value_counts().to_dict()
        if "status" in manifest.columns
        else {}
    )

    if patch_count == 0:
        warnings.append("patch_manifest.csvのpatch数が0です。")
    if not all_slide_ids:
        warnings.append("CLAM exportにslideがありません。")
    if slide_ids != label_slide_ids:
        errors.append(
            "patch_manifest.csvとslide_labels.csvのslide_id集合が一致しません。"
        )
    if slide_ids != process_slide_ids:
        errors.append(
            "patch_manifest.csvとprocess_list_autogen.csvのslide_id集合が一致しません。"
        )

    duplicate_patch_ids = []
    if {"slide_id", "patch_id"}.issubset(manifest.columns):
        duplicate_mask = manifest.duplicated(["slide_id", "patch_id"], keep=False)
        duplicate_patch_ids = manifest.loc[duplicate_mask, ["slide_id", "patch_id"]].to_dict("records")
        if duplicate_patch_ids:
            errors.append(f"slide内で重複するpatch_idがあります: {len(duplicate_patch_ids)}件")

    slide_results: list[dict[str, Any]] = []
    for slide_id in sorted(all_slide_ids):
        manifest_rows = (
            manifest.loc[manifest["slide_id"] == slide_id]
            if "slide_id" in manifest.columns
            else pd.DataFrame()
        )
        expected_ids = set(manifest_rows["patch_id"]) if "patch_id" in manifest_rows.columns else set()

        process_rows = (
            process_list.loc[process_list["slide_id"] == slide_id]
            if "slide_id" in process_list.columns
            else pd.DataFrame()
        )
        if process_rows.empty:
            warnings.append(f"{slide_id}: process_listに行がありません。")
            coords_path = CLAM_COORD_DIR / f"{safe_file_stem(slide_id)}.csv"
            features_path = CLAM_FEATURE_DIR / f"{safe_file_stem(slide_id)}.csv"
        else:
            coords_path = Path(str(process_rows.iloc[0].get("coords_csv", "")))
            features_path = Path(str(process_rows.iloc[0].get("features_csv", "")))

        coords, coords_error = read_validation_csv(coords_path)
        features, features_error = read_validation_csv(features_path)
        for error in (coords_error, features_error):
            if error:
                errors.append(error)
        files_checked += int(coords is not None) + int(features is not None)

        coords_ids = set(coords["patch_id"]) if coords is not None and "patch_id" in coords.columns else set()
        feature_ids = (
            set(features["patch_id"])
            if features is not None and "patch_id" in features.columns
            else set()
        )
        if coords is not None and "patch_id" not in coords.columns:
            errors.append(f"{coords_path}: patch_id列がありません。")
        if features is not None and "patch_id" not in features.columns:
            errors.append(f"{features_path}: patch_id列がありません。")

        if expected_ids != coords_ids:
            errors.append(
                f"{slide_id}: coordsのpatch_idがmanifestと一致しません "
                f"(manifest={len(expected_ids)}, coords={len(coords_ids)})。"
            )
        if expected_ids != feature_ids:
            errors.append(
                f"{slide_id}: featuresのpatch_idがmanifestと一致しません "
                f"(manifest={len(expected_ids)}, features={len(feature_ids)})。"
            )

        label_rows = (
            slide_labels.loc[slide_labels["slide_id"] == slide_id]
            if "slide_id" in slide_labels.columns
            else pd.DataFrame()
        )
        declared_counts = []
        for frame in (label_rows, process_rows):
            if not frame.empty and "patch_count" in frame.columns:
                declared_counts.append(int(safe_float(frame.iloc[0]["patch_count"], -1) or -1))
        if any(count != len(expected_ids) for count in declared_counts):
            warnings.append(
                f"{slide_id}: CSVに記録されたpatch_countとmanifest件数が一致しません。"
            )
        if len(expected_ids) == 0:
            warnings.append(f"{slide_id}: patch数が0です。")

        slide_results.append(
            {
                "slide_id": slide_id,
                "manifest_patches": len(expected_ids),
                "coords_patches": len(coords_ids),
                "features_patches": len(feature_ids),
                "patch_ids_match": expected_ids == coords_ids == feature_ids,
            }
        )

    return {
        "valid": not errors,
        "patch_count": patch_count,
        "slide_count": len(all_slide_ids),
        "status_counts": status_counts,
        "files_checked": files_checked,
        "errors": errors,
        "warnings": warnings,
        "slides": slide_results,
    }


def resolve_project_data_path(value: Any) -> Path | None:
    """Resolve stored project-relative paths without requiring the file to exist."""
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw.replace("\\", "/")).expanduser()
    if candidate.is_absolute():
        return candidate
    return Path.cwd() / candidate


def deep_feature_mil_bag_status() -> dict[str, Any]:
    """Inspect existing deep feature and MIL bag artifacts without loading torch."""
    result: dict[str, Any] = {
        "exists": CLAM_MIL_BAGS_PATH.exists(),
        "bag_count": 0,
        "bags": [],
        "warnings": [],
        "errors": [],
    }
    if not result["exists"]:
        result["warnings"].append(
            "mil_bags.csvがありません。build_mil_bag_index.pyを実行してください。"
        )
        return result

    try:
        bags = pd.read_csv(
            CLAM_MIL_BAGS_PATH,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        result["errors"].append(f"mil_bags.csvを読み込めません: {error}")
        return result

    required_columns = {
        "slide_id",
        "label",
        "source_wsi_name",
        "feature_csv",
        "feature_pt",
        "patch_count",
        "feature_model",
        "feature_version",
    }
    missing_columns = sorted(required_columns - set(bags.columns))
    if missing_columns:
        result["errors"].append(
            "mil_bags.csvに必要な列がありません: " + ", ".join(missing_columns)
        )
        return result

    result["bag_count"] = len(bags)
    seen_random = False
    metadata_warning_slides: list[str] = []
    for _, row in bags.iterrows():
        slide_id = str(row.get("slide_id", "")).strip()
        label = str(row.get("label", "")).strip()
        source_wsi_name = str(row.get("source_wsi_name", "")).strip()
        feature_version = str(row.get("feature_version", "")).strip()
        feature_csv_path = resolve_project_data_path(row.get("feature_csv", ""))
        feature_pt_path = resolve_project_data_path(row.get("feature_pt", ""))
        feature_csv_exists = bool(feature_csv_path and feature_csv_path.is_file())
        feature_pt_exists = bool(feature_pt_path and feature_pt_path.is_file())
        declared_patch_count_value = safe_float(row.get("patch_count", ""), -1)
        declared_patch_count = int(
            -1 if declared_patch_count_value is None else declared_patch_count_value
        )
        feature_csv_rows: int | None = None
        patch_count_matches = False

        if feature_csv_exists and feature_csv_path:
            try:
                feature_csv_rows = len(
                    pd.read_csv(
                        feature_csv_path,
                        usecols=["patch_id"],
                        encoding="utf-8-sig",
                    )
                )
                patch_count_matches = feature_csv_rows == declared_patch_count
                if not patch_count_matches:
                    result["errors"].append(
                        f"{slide_id}: mil_bags.csvのpatch_count "
                        f"({declared_patch_count}) とdeep feature CSVの行数 "
                        f"({feature_csv_rows}) が一致しません。"
                    )
            except (OSError, ValueError, pd.errors.ParserError) as error:
                result["errors"].append(
                    f"{slide_id}: deep feature CSVを確認できません: {error}"
                )
        else:
            result["errors"].append(
                f"{slide_id}: feature_csvが見つかりません: "
                f"{feature_csv_path or '(空欄)'}"
            )

        if "random" in feature_version.lower():
            seen_random = True
        if (
            label.lower() in {"unknown", "ecrs"}
            and source_wsi_name.upper().startswith("JPAID")
        ):
            metadata_warning_slides.append(slide_id or source_wsi_name)

        result["bags"].append(
            {
                "slide_id": slide_id,
                "label": label,
                "patch_count": declared_patch_count,
                "feature_csv_rows": (
                    feature_csv_rows if feature_csv_rows is not None else ""
                ),
                "patch_count_match": patch_count_matches,
                "feature_model": str(row.get("feature_model", "")).strip(),
                "feature_version": feature_version,
                "feature_csv_exists": feature_csv_exists,
                "feature_pt_exists": feature_pt_exists,
            }
        )

    if seen_random:
        result["warnings"].append(
            "--no-pretrainedで作成された動作確認用featureです。"
            "学習・解析には使わないでください。"
        )
    if metadata_warning_slides:
        result["warnings"].append(
            "JPAID由来の肝臓候補に見えるslideでlabelがunknownまたはECRSです。"
            "source_organ、disease_context、slide labelを確認してください: "
            + ", ".join(metadata_warning_slides)
        )
    missing_pt_count = sum(
        1 for bag in result["bags"] if not bag["feature_pt_exists"]
    )
    if missing_pt_count:
        result["warnings"].append(
            f"feature_ptがないbagが{missing_pt_count}件あります。"
            "feature CSVがあればbag indexとしては利用できます。"
        )
    return result


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


def saved_annotation_records() -> list[tuple[Path, dict[str, Any]]]:
    records = []
    for path in sorted(ANNOTATION_DIR.glob("*_annotations.json")):
        payload = load_saved_annotation_payload(path)
        if payload:
            records.append((path, payload))
    return records


def find_saved_annotation_record(
    *,
    source_wsi_name: str = "",
    patch_id: str = "",
    image_name: str = "",
) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[float, Path, dict[str, Any]]] = []
    for path, payload in saved_annotation_records():
        metadata = payload.get("image_metadata", {})
        same_patch = (
            source_wsi_name
            and patch_id
            and str(metadata.get("source_wsi_name", "")) == source_wsi_name
            and str(metadata.get("patch_id", "")) == patch_id
        )
        same_image = image_name and str(payload.get("image_name", "")) == image_name
        if same_patch or same_image:
            try:
                modified = path.stat().st_mtime
            except OSError:
                modified = 0.0
            matches.append((modified, path, payload))
    if not matches:
        return None
    _, path, payload = max(matches, key=lambda item: item[0])
    return path, payload


def reset_saved_patch_annotations(
    source_wsi_name: str,
    patch_id: str,
) -> Path | None:
    record = find_saved_annotation_record(
        source_wsi_name=source_wsi_name,
        patch_id=patch_id,
    )
    if record is None:
        return None
    path, payload = record
    ANNOTATION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = ANNOTATION_BACKUP_DIR / (
        f"{path.stem}_{datetime.now(TOKYO_TIMEZONE).strftime('%Y%m%dT%H%M%S')}"
        f"{path.suffix}"
    )
    shutil.copy2(path, backup)

    now = tokyo_now_iso()
    payload["annotations"] = []
    payload["saved_at"] = now
    payload["schema_version"] = "2.5"
    metadata = payload.get("image_metadata", {})
    metadata["reviewed"] = False
    metadata["exported"] = False
    metadata["reviewed_at"] = ""
    metadata["exported_at"] = ""
    payload["image_metadata"] = metadata
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = load_patch_manifest()
    if not manifest.empty:
        mask = (
            manifest["source_wsi_name"].eq(source_wsi_name)
            & manifest["patch_id"].eq(patch_id)
        )
        if mask.any():
            manifest.loc[mask, "status"] = "not_started"
            manifest.loc[mask, "annotation_count"] = "0"
            manifest.loc[mask, "eosinophil_count"] = "0"
            manifest.loc[mask, "reviewed_at"] = ""
            manifest.loc[mask, "exported_at"] = ""
            manifest.loc[mask, "updated_at"] = now
            save_patch_manifest(manifest)
    regenerate_dataset_exports()
    return backup


def training_slide_inventory() -> list[dict[str, Any]]:
    slides: dict[str, dict[str, Any]] = {}
    for path, payload in saved_annotation_records():
        metadata = payload.get("image_metadata", {})
        source_wsi_name = str(metadata.get("source_wsi_name", "")).strip()
        slide_id = str(metadata.get("slide_id", "")).strip()
        key = source_wsi_name or slide_id or str(payload.get("image_name", "")).strip()
        if not key:
            continue
        row = slides.setdefault(
            key,
            {
                "slide_key": key,
                "source_wsi_name": source_wsi_name,
                "slide_id": slide_id,
                "annotation_files": 0,
                "patch_count": 0,
            },
        )
        row["annotation_files"] += 1
        for field in TRAINING_MANAGER_METADATA_FIELDS:
            value = metadata.get(field, "")
            if str(value).strip() or field not in row:
                row[field] = value
        row["exclude_from_training"] = safe_bool(
            metadata.get("exclude_from_training", False)
        )
        row["exclusion_reason"] = metadata.get("exclusion_reason", "")

    manifest = load_patch_manifest()
    if not manifest.empty:
        for source_wsi_name, rows in manifest.groupby("source_wsi_name", sort=True):
            key = str(source_wsi_name).strip()
            row = slides.setdefault(
                key,
                {
                    "slide_key": key,
                    "source_wsi_name": key,
                    "slide_id": Path(key).stem,
                    "annotation_files": 0,
                },
            )
            row["patch_count"] = len(rows)
            row["excluded_patches"] = int(
                rows["exclude_from_training"].map(safe_bool).sum()
            )
    for path, flag in (
        (CLAM_DIR / "slide_labels.csv", "in_clam_export"),
        (CLAM_MIL_BAGS_PATH, "in_mil_bags"),
    ):
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
            )
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue
        if "slide_id" not in frame.columns:
            continue
        for _, source_row in frame.iterrows():
            slide_id = str(source_row.get("slide_id", "")).strip()
            source_wsi_name = str(source_row.get("source_wsi_name", "")).strip()
            key = source_wsi_name or slide_id
            if not key:
                continue
            row = slides.setdefault(
                key,
                {
                    "slide_key": key,
                    "source_wsi_name": source_wsi_name,
                    "slide_id": slide_id,
                    "annotation_files": 0,
                    "patch_count": 0,
                },
            )
            row[flag] = True
            for field in TRAINING_MANAGER_METADATA_FIELDS:
                value = source_row.get(field, "")
                if str(value).strip() and not str(row.get(field, "")).strip():
                    row[field] = value
    for row in slides.values():
        row.setdefault("excluded_patches", 0)
        row.setdefault("in_clam_export", False)
        row.setdefault("in_mil_bags", False)
    return sorted(slides.values(), key=lambda row: str(row["slide_key"]))


def update_saved_slide_metadata(
    slide_key: str,
    updates: dict[str, Any],
) -> int:
    updated_files = 0
    saved_at = tokyo_now_iso()
    for path, payload in saved_annotation_records():
        metadata = payload.get("image_metadata", {}).copy()
        keys = {
            str(metadata.get("source_wsi_name", "")).strip(),
            str(metadata.get("slide_id", "")).strip(),
            str(payload.get("image_name", "")).strip(),
        }
        if slide_key not in keys:
            continue
        metadata.update(updates)
        payload["image_metadata"] = metadata
        for annotation in payload.get("annotations", []):
            for field in (*TRAINING_MANAGER_METADATA_FIELDS, "exclude_from_training", "exclusion_reason"):
                annotation[field] = metadata.get(field, "")
        payload["schema_version"] = "2.5"
        payload["saved_at"] = saved_at
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        updated_files += 1
    regenerate_dataset_exports()
    return updated_files


def update_training_patch(
    source_wsi_name: str,
    patch_id: str,
    updates: dict[str, Any],
) -> bool:
    manifest = load_patch_manifest()
    if manifest.empty:
        return False
    mask = (
        manifest["source_wsi_name"].eq(source_wsi_name)
        & manifest["patch_id"].eq(patch_id)
    )
    if not mask.any():
        return False
    for field, value in updates.items():
        if field in PATCH_MANIFEST_FIELDS:
            manifest.loc[mask, field] = value
    manifest.loc[mask, "updated_at"] = tokyo_now_iso()
    save_patch_manifest(manifest)

    for path, payload in saved_annotation_records():
        metadata = payload.get("image_metadata", {})
        if (
            str(metadata.get("source_wsi_name", "")) == source_wsi_name
            and str(metadata.get("patch_id", "")) == patch_id
        ):
            metadata.update(
                {
                    "exclude_from_training": safe_bool(
                        updates.get(
                            "exclude_from_training",
                            metadata.get("exclude_from_training", False),
                        )
                    ),
                    "exclusion_reason": updates.get(
                        "exclusion_reason",
                        metadata.get("exclusion_reason", ""),
                    ),
                    "notes": updates.get("notes", metadata.get("notes", "")),
                }
            )
            payload["image_metadata"] = metadata
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    regenerate_dataset_exports()
    return True


def safe_managed_delete(path: Path, allowed_root: Path) -> bool:
    try:
        resolved = path.resolve()
        root = allowed_root.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    if not resolved.is_file():
        return False
    resolved.unlink()
    return True


def delete_generated_training_artifacts(slide_id: str, delete_global: bool) -> list[Path]:
    deleted: list[Path] = []
    stem = safe_file_stem(slide_id)
    for directory, suffix in (
        (CLAM_DEEP_FEATURE_CSV_DIR, ".csv"),
        (CLAM_DEEP_FEATURE_PT_DIR, ".pt"),
    ):
        path = directory / f"{stem}{suffix}"
        if safe_managed_delete(path, directory):
            deleted.append(path)
    if delete_global:
        for path in (
            CLAM_MIL_BAGS_PATH,
            CLAM_DIR / "patch_manifest.csv",
            CLAM_DIR / "slide_labels.csv",
            CLAM_DIR / "process_list_autogen.csv",
        ):
            if safe_managed_delete(path, CLAM_DIR):
                deleted.append(path)
        for directory in (CLAM_COORD_DIR, CLAM_FEATURE_DIR):
            for path in directory.glob("*.csv"):
                if safe_managed_delete(path, directory):
                    deleted.append(path)
    return deleted


def delete_patch_annotation_and_image(
    source_wsi_name: str,
    patch_id: str,
) -> list[Path]:
    deleted: list[Path] = []
    for path, payload in saved_annotation_records():
        metadata = payload.get("image_metadata", {})
        if (
            str(metadata.get("source_wsi_name", "")) == source_wsi_name
            and str(metadata.get("patch_id", "")) == patch_id
            and safe_managed_delete(path, ANNOTATION_DIR)
        ):
            deleted.append(path)

    manifest = load_patch_manifest()
    if not manifest.empty:
        mask = (
            manifest["source_wsi_name"].eq(source_wsi_name)
            & manifest["patch_id"].eq(patch_id)
        )
        for value in manifest.loc[mask, "image_path"]:
            image_path = resolve_project_data_path(value)
            if image_path and safe_managed_delete(image_path, PATCH_IMAGE_DIR):
                deleted.append(image_path)
        save_patch_manifest(manifest.loc[~mask].copy())
    regenerate_dataset_exports()
    return deleted


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
        metadata = payload.get("image_metadata", {}).copy()
        timestamps = patch_timestamps(
            str(metadata.get("source_wsi_name", "")),
            str(metadata.get("patch_id", "")),
        )
        metadata["reviewed_at"] = metadata.get("reviewed_at", "") or timestamps["reviewed_at"]
        metadata["exported_at"] = timestamps["exported_at"] or metadata.get("exported_at", "")
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
        counts_context.to_csv(
            export_paths["counts_csv"],
            index=False,
            encoding="utf-8-sig",
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


def annotations_for_save(
    annotations: list[dict[str, Any]],
    saved_at: str,
) -> list[dict[str, Any]]:
    stamped = []
    for annotation in annotations:
        normalized = normalize_annotation_status(annotation)
        normalized["annotation_created_at"] = (
            normalized.get("annotation_created_at")
            or normalized.get("created_at")
            or saved_at
        )
        normalized["annotation_updated_at"] = saved_at
        normalized["annotation_session_id"] = (
            st.session_state.get("annotation_session_id", "")
            or normalized.get("annotation_session_id")
            or new_annotation_session_id()
        )
        normalized["created_at"] = (
            normalized.get("created_at")
            or normalized["annotation_created_at"]
        )
        stamped.append(normalized)
    return stamped


def mark_patch_exported(
    source_wsi_name: str,
    patch_id: str,
    exported_at: str,
    reviewed_at: str = "",
) -> None:
    if not source_wsi_name or not patch_id:
        return
    manifest = load_patch_manifest()
    if manifest.empty:
        return
    mask = (manifest["source_wsi_name"] == source_wsi_name) & (manifest["patch_id"] == patch_id)
    if not mask.any():
        return
    manifest.loc[mask, "updated_at"] = exported_at
    manifest.loc[mask, "exported_at"] = exported_at
    if reviewed_at:
        empty_reviewed = manifest.loc[mask, "reviewed_at"].eq("")
        manifest.loc[manifest.loc[mask].index[empty_reviewed], "reviewed_at"] = reviewed_at
    save_patch_manifest(manifest)


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
    saved_at = tokyo_now_iso()
    annotations = annotations_for_save(annotations, saved_at)
    metadata["exported_at"] = saved_at
    if metadata.get("reviewed") and not metadata.get("reviewed_at"):
        metadata["reviewed_at"] = saved_at
    mark_patch_exported(
        str(metadata.get("source_wsi_name", "")),
        str(metadata.get("patch_id", "")),
        saved_at,
        str(metadata.get("reviewed_at", "")),
    )
    paths = image_export_paths(image_name, metadata)
    export_stem = export_file_stem(image_name, metadata)
    manifest_path = EXPORT_DIR / "dataset_manifest.csv"
    aggregate_annotations_path = EXPORT_DIR / "annotations.csv"
    aggregate_counts_path = EXPORT_DIR / "counts.csv"
    metadata_path = EXPORT_DIR / "metadata.csv"

    payload = {
        "schema_version": "2.5",
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
    update_patch_manifest_counts(
        str(metadata.get("source_wsi_name", "")),
        str(metadata.get("patch_id", "")),
        annotations,
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
            "patch_level",
            "patch_downsample",
            "patch_level0_width",
            "patch_level0_height",
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
        "patch_level": st.sidebar.text_input("patch_level", value=str(current.get("patch_level", ""))),
        "patch_downsample": st.sidebar.text_input("patch_downsample", value=str(current.get("patch_downsample", ""))),
        "patch_level0_width": st.sidebar.text_input("patch_level0_width", value=str(current.get("patch_level0_width", ""))),
        "patch_level0_height": st.sidebar.text_input("patch_level0_height", value=str(current.get("patch_level0_height", ""))),
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
    st.session_state.annotation_session_id = new_annotation_session_id()
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
    upload_limit = st.get_option("server.maxUploadSize")
    st.sidebar.caption(f"現在のアップロード上限: {upload_limit} MB")
    if upload_limit < 2048:
        st.sidebar.warning(
            "アップロード上限が200MB付近のままです。run_app.bat または run_app.ps1 から起動してください。"
            "初回Email入力プロンプトを避けるため、起動スクリプトを使うのが確実です。"
        )
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
    st.sidebar.checkbox(
        "patch queueは done / reviewed_empty のみ",
        value=True,
        key="export_completed_patch_queue_only",
        help="queue管理されたpatchでは、確認完了または陰性確認済みのpatchだけを学習datasetへ出力します。",
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


def activate_wsi_patch(
    patch: dict[str, Any],
    source_key: str,
    queue_index: int | None = None,
) -> None:
    existing_metadata = st.session_state.image_metadata.copy()
    reset_for_new_image()
    st.session_state.image_metadata.update(existing_metadata)
    patch_status = patch.get("patch_metadata", {}).get("patch_status", "")
    st.session_state.image_metadata["reviewed"] = patch_status in {"done", "reviewed_empty"}
    st.session_state.image_metadata["exported"] = bool(
        patch.get("patch_metadata", {}).get("exported_at", "")
    )
    st.session_state.active_patch = patch
    st.session_state.active_patch_source = source_key
    st.session_state.active_patch_queue_id = patch.get("patch_metadata", {}).get("patch_id")
    if queue_index is not None:
        st.session_state.patch_queue_index = queue_index
    apply_patch_metadata_to_session(patch.get("patch_metadata", {}))


def activate_adjacent_queue_patch(
    source_wsi_name: str,
    current_patch_id: str,
    offset: int,
) -> bool:
    queue_rows, _ = current_review_queue_rows(source_wsi_name)
    matches = queue_rows.index[queue_rows["patch_id"] == current_patch_id].tolist()
    if not matches:
        return False
    target_index = int(matches[0]) + offset
    if target_index < 0 or target_index >= len(queue_rows):
        return False

    wsi_path = ORIGINAL_WSI_DIR / source_wsi_name
    if not wsi_path.exists():
        return False
    thumbnail_info = navigation_wsi_info(wsi_path, source_wsi_name)
    target_row = queue_rows.iloc[target_index].to_dict()
    patch = prepared_patch_from_manifest_row(target_row, wsi_path, thumbnail_info)
    if target_row["status"] == "not_started":
        update_patch_manifest_status(source_wsi_name, target_row["patch_id"], "in_progress")
    source_key = st.session_state.active_patch_source
    if not source_key:
        source_key = f"{source_wsi_name}:{wsi_path.stat().st_size}"
    activate_wsi_patch(patch, source_key, target_index)
    return True


def activate_review_queue_index(source_wsi_name: str, target_index: int) -> bool:
    queue_rows, _ = current_review_queue_rows(source_wsi_name)
    if queue_rows.empty:
        return False
    target_index = max(0, min(int(target_index), len(queue_rows) - 1))
    wsi_path = ORIGINAL_WSI_DIR / source_wsi_name
    if not wsi_path.exists():
        return False
    thumbnail_info = navigation_wsi_info(wsi_path, source_wsi_name)
    target_row = queue_rows.iloc[target_index].to_dict()
    patch = prepared_patch_from_manifest_row(target_row, wsi_path, thumbnail_info)
    if target_row["status"] == "not_started":
        update_patch_manifest_status(
            source_wsi_name,
            target_row["patch_id"],
            "in_progress",
        )
    source_key = st.session_state.active_patch_source
    if not source_key:
        source_key = f"{source_wsi_name}:{wsi_path.stat().st_size}"
    activate_wsi_patch(patch, source_key, target_index)
    return True


def render_positive_exploration_controls(
    source_wsi_name: str,
) -> tuple[pd.DataFrame, list[str]]:
    manifest = load_patch_manifest()
    source_rows = (
        manifest.loc[manifest["source_wsi_name"].eq(source_wsi_name)].copy()
        if not manifest.empty
        else manifest
    )
    st.info(
        "Positive explorationは陽性候補を探すための確認順です。"
        "priority_scoreは好酸球確率ではありません。"
    )
    filter_row = st.columns(5)
    filter_row[0].selectbox(
        "source_wsi_name",
        [source_wsi_name],
        key="positive_source_wsi_name",
        disabled=True,
    )
    filter_row[1].checkbox(
        "未確認のみ",
        key="positive_only_unreviewed",
    )
    filter_row[2].checkbox(
        "flaggedのみ",
        key="positive_flagged_only",
    )
    filter_row[3].checkbox(
        "reviewed_emptyを除外",
        key="positive_exclude_reviewed_empty",
    )
    filter_row[4].checkbox(
        "doneを除外",
        key="positive_exclude_done",
    )

    filter_row_2 = st.columns(4)
    filter_row_2[0].checkbox(
        "skippedを除外",
        key="positive_exclude_skipped",
    )
    filter_row_2[1].checkbox(
        "学習除外patchを除外",
        key="positive_exclude_training",
    )
    filter_row_2[2].number_input(
        "minimum priority_score",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        key="positive_min_priority",
    )
    filter_row_2[3].number_input(
        "top N candidates",
        min_value=1,
        max_value=max(100, len(source_rows)),
        step=10,
        key="positive_top_n",
    )

    cluster_values = sorted(
        {
            str(value).strip()
            for value in source_rows.get("cluster_id", pd.Series(dtype=str))
            if str(value).strip()
        }
    )
    patch_metadata = patch_metadata_lookup()
    slide_metadata = slide_metadata_by_wsi().get(source_wsi_name, {})

    def metadata_options(field: str) -> list[str]:
        values = {
            str(slide_metadata.get(field, "")).strip(),
            *{
                str(metadata.get(field, "")).strip()
                for (wsi_name, _), metadata in patch_metadata.items()
                if wsi_name == source_wsi_name
            },
        }
        return ["all", *sorted(value for value in values if value)]

    if st.session_state.get("positive_cluster_filter") not in {
        "all",
        *cluster_values,
    }:
        st.session_state.positive_cluster_filter = "all"
    for key, field in (
        ("positive_tissue_region_filter", "tissue_region"),
        ("positive_disease_context_filter", "disease_context"),
        ("positive_source_organ_filter", "source_organ"),
    ):
        if st.session_state.get(key) not in metadata_options(field):
            st.session_state[key] = "all"

    select_row = st.columns(4)
    select_row[0].selectbox(
        "cluster_id",
        ["all", *cluster_values],
        key="positive_cluster_filter",
        disabled=not cluster_values,
    )
    select_row[1].multiselect(
        "status",
        PATCH_QUEUE_STATUSES,
        key="positive_status_filter",
    )
    select_row[2].selectbox(
        "tissue_region",
        metadata_options("tissue_region"),
        key="positive_tissue_region_filter",
    )
    select_row[3].selectbox(
        "disease_context",
        metadata_options("disease_context"),
        key="positive_disease_context_filter",
    )
    select_row_2 = st.columns(4)
    select_row_2[0].selectbox(
        "source_organ",
        metadata_options("source_organ"),
        key="positive_source_organ_filter",
    )
    select_row_2[1].selectbox(
        "並び順",
        POSITIVE_SORT_OPTIONS,
        key="positive_sort",
    )
    select_row_2[2].number_input(
        "clusterごとの上位N枚",
        min_value=1,
        max_value=100,
        step=1,
        key="positive_per_cluster",
        disabled=st.session_state.get("positive_sort") != "cluster-balanced",
    )
    select_row_2[3].number_input(
        "random seed",
        min_value=0,
        max_value=999999,
        step=1,
        key="positive_random_seed",
        disabled=st.session_state.get("positive_sort") != "random sample",
    )

    rows, warnings = current_review_queue_rows(source_wsi_name)
    full_status_counts = (
        source_rows["status"].value_counts().to_dict()
        if not source_rows.empty
        else {}
    )
    metrics = st.columns(4)
    metrics[0].metric("candidate patch数", len(rows))
    metrics[1].metric("not_started", full_status_counts.get("not_started", 0))
    metrics[2].metric("flagged", full_status_counts.get("flagged", 0))
    metrics[3].metric(
        "suspected_positive",
        full_status_counts.get("suspected_positive", 0),
    )
    metrics_2 = st.columns(4)
    metrics_2[0].metric("done", full_status_counts.get("done", 0))
    metrics_2[1].metric(
        "reviewed_empty",
        full_status_counts.get("reviewed_empty", 0),
    )
    metrics_2[2].metric("skipped", full_status_counts.get("skipped", 0))
    metrics_2[3].metric(
        "excluded",
        int(
            source_rows.get(
                "exclude_from_training",
                pd.Series(False, index=source_rows.index),
            )
            .map(safe_bool)
            .sum()
        ),
    )
    for warning in warnings:
        st.warning(warning)
    st.caption(
        "運用: 好酸球なし=reviewed_empty、好酸球あり=annotation+done、"
        "迷う=flagged/suspected_positive、artifact=skippedまたは学習除外。"
    )
    return rows, warnings


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

    st.session_state.active_wsi_name = uploaded_image.name
    st.session_state.active_wsi_thumbnail_info = thumbnail_info
    source_key = f"{uploaded_image.name}:{uploaded_image.size}"
    st.radio(
        "Patch review mode",
        REVIEW_MODES,
        horizontal=True,
        key="patch_review_mode",
    )
    if st.session_state.patch_review_mode == "Positive exploration":
        with st.expander("陽性探索フィルタ", expanded=True):
            queue_rows, queue_warnings = render_positive_exploration_controls(
                uploaded_image.name
            )
    else:
        queue_rows, queue_warnings = current_review_queue_rows(uploaded_image.name)
    active_patch = st.session_state.active_patch
    if active_patch and st.session_state.active_patch_source == source_key:
        active_patch_id = active_patch.get("patch_metadata", {}).get("patch_id", "")
        queue_match = queue_rows.index[queue_rows["patch_id"] == active_patch_id].tolist()
        if queue_match:
            current_index = int(queue_match[0])
            st.session_state.patch_queue_index = current_index
            current_row = queue_rows.iloc[current_index]
            completed = int(queue_rows["status"].isin(["done", "reviewed_empty"]).sum())
            st.progress(
                completed / len(queue_rows) if len(queue_rows) else 0,
                text=f"patch queue: {current_index + 1}/{len(queue_rows)} | 完了 {completed}/{len(queue_rows)}",
            )
            st.caption(
                f"status: {current_row['status']} | priority: {current_row['priority_score']} | "
                f"cluster: {current_row['cluster_id']} | tissue_ratio: {current_row['tissue_ratio']} | "
                f"patch_id: {active_patch_id}"
            )
            if st.session_state.patch_review_mode == "Positive exploration":
                st.caption(
                    f"Positive candidate順位: {current_index + 1}/{len(queue_rows)}"
                )
            navigation = st.columns([1, 1, 2])
            previous_label = (
                "Previous candidate"
                if st.session_state.patch_review_mode == "Positive exploration"
                else "Previous patch"
            )
            next_label = (
                "Next positive candidate"
                if st.session_state.patch_review_mode == "Positive exploration"
                else "Next patch"
            )
            if navigation[0].button(previous_label, disabled=current_index <= 0, use_container_width=True):
                previous_row = queue_rows.iloc[current_index - 1].to_dict()
                previous = prepared_patch_from_manifest_row(
                    previous_row,
                    wsi_path,
                    thumbnail_info,
                )
                if previous_row["status"] == "not_started":
                    update_patch_manifest_status(uploaded_image.name, previous_row["patch_id"], "in_progress")
                activate_wsi_patch(previous, source_key, current_index - 1)
                st.rerun()
            if navigation[1].button(
                next_label,
                disabled=current_index >= len(queue_rows) - 1,
                use_container_width=True,
            ):
                following_row = queue_rows.iloc[current_index + 1].to_dict()
                following = prepared_patch_from_manifest_row(
                    following_row,
                    wsi_path,
                    thumbnail_info,
                )
                if following_row["status"] == "not_started":
                    update_patch_manifest_status(uploaded_image.name, following_row["patch_id"], "in_progress")
                activate_wsi_patch(following, source_key, current_index + 1)
                st.rerun()
            navigation[2].caption("移動前に必要なアノテーションを保存してください。")

        st.success(f"アノテーション用patchを読み込みました: {active_patch['image_name']}")
        if st.button("patch選択画面へ戻る", use_container_width=True):
            st.session_state.active_patch = None
            st.session_state.active_patch_source = None
            st.session_state.active_patch_queue_id = None
            st.rerun()
        apply_patch_metadata_to_session(active_patch.get("patch_metadata", {}))
        return active_patch

    if (
        st.session_state.patch_review_mode == "Positive exploration"
        and not queue_rows.empty
    ):
        if st.button(
            "陽性探索を開始 / 再開",
            type="primary",
            use_container_width=True,
        ):
            activate_review_queue_index(uploaded_image.name, 0)
            st.rerun()
        st.dataframe(
            queue_rows[
                [
                    "patch_id",
                    "priority_score",
                    "tissue_ratio",
                    "cluster_id",
                    "status",
                    "tissue_region",
                    "disease_context",
                    "source_organ",
                ]
            ],
            hide_index=True,
            use_container_width=True,
        )
    elif (
        st.session_state.patch_review_mode == "Positive exploration"
        and queue_rows.empty
    ):
        st.warning("現在のフィルタ条件に一致する陽性候補patchはありません。")

    st.subheader("WSIビューア / ROIパッチ作成")
    st.caption(
        "上のビューアでマウスホイールズームとドラッグ移動を行い、学習に使いたい場所を探します。"
        "巨大WSI全体はannotation canvasに直接載せません。"
    )
    st.caption(
        f"WSIサイズ: {thumbnail_info['wsi_width']} x {thumbnail_info['wsi_height']} px | "
        f"thumbnail: {thumbnail_info['thumbnail_width']} x {thumbnail_info['thumbnail_height']} px | "
        f"mpp: {thumbnail_info.get('mpp_x', '')}, {thumbnail_info.get('mpp_y', '')}"
    )

    level_dimensions = thumbnail_info.get("level_dimensions", [(thumbnail_info["wsi_width"], thumbnail_info["wsi_height"])])
    level_downsamples = thumbnail_info.get("level_downsamples", [1.0])
    level_options = list(range(len(level_dimensions)))

    with st.expander("自動patch queue", expanded=True):
        st.caption(
            "WSIを非重複tileに分割し、低倍率thumbnailと実patchの組織率で白背景を除外します。"
        )
        queue_controls = st.columns(4)
        queue_patch_size = queue_controls[0].selectbox(
            "patch_size_px",
            PATCH_QUEUE_SIZE_OPTIONS,
            index=0,
        )
        queue_level = queue_controls[1].selectbox(
            "queue level",
            level_options,
            index=0,
            format_func=lambda item: (
                f"level {item} "
                f"(downsample {level_downsamples[item]:.1f}, {level_dimensions[item][0]}x{level_dimensions[item][1]})"
            ),
        )
        base_mpp = safe_float(thumbnail_info.get("mpp_x"))
        suggested_target_mpp = (
            f"{base_mpp * float(level_downsamples[queue_level]):.6f}"
            if base_mpp is not None
            else ""
        )
        queue_target_mpp = queue_controls[2].text_input(
            "queue target_mpp",
            value=suggested_target_mpp,
            key=f"queue_target_mpp_{uploaded_image.name}_{queue_level}",
        )
        minimum_tissue_ratio = queue_controls[3].slider(
            "最小 tissue_ratio",
            min_value=0.01,
            max_value=0.90,
            value=0.10,
            step=0.01,
        )
        queue_options = st.columns(3)
        cluster_count = int(
            queue_options[0].number_input(
                "cluster数",
                min_value=2,
                max_value=20,
                value=6,
                step=1,
            )
        )
        queue_sort_by = queue_options[1].selectbox(
            "queueの並び順",
            list(PATCH_QUEUE_SORT_OPTIONS),
            format_func=lambda value: PATCH_QUEUE_SORT_OPTIONS[value],
            key="patch_queue_sort_by",
        )
        queue_rows = patch_queue_rows(uploaded_image.name, queue_sort_by)
        if queue_options[2].button(
            "特徴量・クラスタを再計算",
            disabled=queue_rows.empty,
            use_container_width=True,
        ):
            with st.spinner("保存済みpatchの特徴量とクラスタを計算しています..."):
                feature_result = recalculate_patch_features(uploaded_image.name, cluster_count)
            st.success(
                f"再計算しました: patch {feature_result['updated']}件 / "
                f"cluster {feature_result['clusters']} / 欠損画像 {feature_result['missing']}件"
            )
            st.rerun()
        queue_level_width, queue_level_height = level_dimensions[queue_level]
        estimated_tiles = (
            max(0, queue_level_width // int(queue_patch_size))
            * max(0, queue_level_height // int(queue_patch_size))
        )
        st.caption(f"生成前の最大tile数: {estimated_tiles}（空白除外前）")
        if estimated_tiles > 2000:
            st.warning(
                "候補tile数が多いため、生成に時間と保存容量が必要です。"
                "必要に応じてdownsampleの大きいlevelを選ぶか、patch_size_pxを2048にしてください。"
            )
        if st.button("Generate patch queue", type="primary", use_container_width=True):
            progress = st.progress(0.0, text="patch候補を探索しています...")

            def update_progress(current: int, total: int) -> None:
                progress.progress(
                    current / total if total else 1.0,
                    text=f"patch候補を探索しています: {current}/{total}",
                )

            result = generate_wsi_patch_queue(
                wsi_path=wsi_path,
                wsi_name=uploaded_image.name,
                patch_size=int(queue_patch_size),
                level=int(queue_level),
                thumbnail=thumbnail,
                thumbnail_info=thumbnail_info,
                target_mpp=queue_target_mpp,
                objective_magnification=str(
                    st.session_state.image_metadata.get("objective_magnification", "unknown")
                ),
                minimum_tissue_ratio=float(minimum_tissue_ratio),
                cluster_count=cluster_count,
                progress_callback=update_progress,
            )
            st.success(
                f"patch queueを生成しました: 採用 {result['generated']} / "
                f"除外 {result['excluded']} / 全tile {result['total_tiles']} / "
                f"cluster {result['clusters']}"
            )
            st.rerun()

        if not queue_rows.empty:
            completed = int(queue_rows["status"].isin(["done", "reviewed_empty"]).sum())
            st.progress(
                completed / len(queue_rows),
                text=f"完了 {completed}/{len(queue_rows)}",
            )
            status_counts = queue_rows["status"].value_counts().to_dict()
            st.caption(
                " | ".join(f"{status}: {status_counts.get(status, 0)}" for status in PATCH_QUEUE_STATUSES)
            )
            start_options = queue_rows.index[
                queue_rows["status"].isin(
                    [
                        "not_started",
                        "in_progress",
                        "flagged",
                        "suspected_positive",
                    ]
                )
            ].tolist()
            start_index = int(start_options[0]) if start_options else 0
            if st.button("queueを開始 / 再開", use_container_width=True):
                row = queue_rows.iloc[start_index].to_dict()
                patch = prepared_patch_from_manifest_row(row, wsi_path, thumbnail_info)
                if row["status"] == "not_started":
                    update_patch_manifest_status(uploaded_image.name, row["patch_id"], "in_progress")
                activate_wsi_patch(patch, source_key, start_index)
                st.rerun()
            st.dataframe(
                queue_rows[
                    [
                        "patch_id",
                        "tissue_ratio",
                        "priority_score",
                        "cluster_id",
                        "nuclei_density_proxy",
                        "eosin_score",
                        "status",
                        "annotation_count",
                        "eosinophil_count",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("このWSIのpatch queueはまだありません。")

    show_manual_roi = st.toggle(
        "手動ROI patchを表示",
        value=False,
        help="自動patch queueを使わず、任意の場所を手動で切り出す場合だけ有効にします。",
    )
    if not show_manual_roi:
        return None

    st.markdown("#### 手動ROI patch")
    st.caption("従来どおり、任意位置を確認して1枚ずつpatchを作成できます。")

    controls = st.columns(4)
    patch_width = controls[0].number_input("patch幅", min_value=256, max_value=4096, value=1024, step=256)
    patch_height = controls[1].number_input("patch高さ", min_value=256, max_value=4096, value=1024, step=256)
    level = controls[2].selectbox(
        "拡大率 level",
        level_options,
        index=0,
        format_func=lambda item: (
            f"level {item} "
            f"(downsample {level_downsamples[item]:.1f}, {level_dimensions[item][0]}x{level_dimensions[item][1]})"
        ),
    )
    target_mpp = controls[3].text_input("target_mpp", value=str(thumbnail_info.get("mpp_x") or ""))

    patch_downsample = float(level_downsamples[level])
    patch_level0_width = int(round(int(patch_width) * patch_downsample))
    patch_level0_height = int(round(int(patch_height) * patch_downsample))
    max_x = max(0, int(thumbnail_info["wsi_width"]) - patch_level0_width)
    max_y = max(0, int(thumbnail_info["wsi_height"]) - patch_level0_height)

    try:
        render_wsi_scroll_viewer(wsi_path, thumbnail_info, int(level), int(patch_width), int(patch_height))
    except RuntimeError as error:
        st.error(str(error))

    st.caption("低倍率thumbnailで大まかなROI候補を選ぶこともできます。細かい位置決めは上のビューアで確認してください。")
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
        default_x = min(selected_roi["x"], max_x)
        default_y = min(selected_roi["y"], max_y)
        st.info(
            f"thumbnailで選択したROI候補: x={default_x}, y={default_y}。"
            "下の座標を動かすと、切り出し前にプレビューできます。"
        )
    else:
        default_x = min(max_x, int(safe_float(st.session_state.image_metadata.get("patch_x"), 0) or 0))
        default_y = min(max_y, int(safe_float(st.session_state.image_metadata.get("patch_y"), 0) or 0))
        st.info("ROI矩形を選ぶか、下のpatch_x / patch_yを直接調整してください。")

    xy_controls = st.columns(2)
    patch_x = int(
        xy_controls[0].number_input(
            "patch_x（WSI level 0 左上X）",
            min_value=0,
            max_value=max_x,
            value=default_x,
            step=max(1, patch_level0_width // 4),
        )
    )
    patch_y = int(
        xy_controls[1].number_input(
            "patch_y（WSI level 0 左上Y）",
            min_value=0,
            max_value=max_y,
            value=default_y,
            step=max(1, patch_level0_height // 4),
        )
    )

    preview = read_wsi_region_rgb(wsi_path, patch_x, patch_y, level, int(patch_width), int(patch_height))
    st.image(
        preview,
        caption=(
            f"patchプレビュー: x={patch_x}, y={patch_y}, level={level}, "
            f"downsample={patch_downsample:.2f}, level0範囲={patch_level0_width}x{patch_level0_height}"
        ),
        use_container_width=True,
    )
    if white_fraction(preview) > 0.95:
        st.warning(
            "このpatchプレビューはほぼ白背景です。patch_x / patch_y または level を調整して、"
            "組織が見える位置を選んでください。"
        )

    if st.button("このプレビューをアノテーション用patchとして確定", use_container_width=True):
        patch = create_wsi_patch(
            wsi_path=wsi_path,
            wsi_name=uploaded_image.name,
            patch_x=int(patch_x),
            patch_y=int(patch_y),
            patch_width=int(patch_width),
            patch_height=int(patch_height),
            level=int(level),
            thumbnail_info=thumbnail_info,
            target_mpp=target_mpp,
        )
        st.session_state.uploaded_source_name = uploaded_image.name
        activate_wsi_patch(patch, source_key)
        st.rerun()

    return None


def process_upload(
    uploaded_image: Any,
    uploaded_annotations: Any,
    display_image: Image.Image,
    prepared_image: dict[str, Any],
) -> None:
    image_key = f"{uploaded_image.name}:{uploaded_image.size}:{prepared_image['image_name']}"
    image_changed = st.session_state.saved_image_key != image_key
    if image_changed:
        st.session_state.original_image_path = str(prepared_image["image_path"])
        st.session_state.saved_image_key = image_key

    st.session_state.image_name = str(prepared_image["image_name"])
    if uploaded_annotations:
        annotation_digest = hashlib.sha256(
            uploaded_annotations.getvalue()
        ).hexdigest()
        restore_key = (
            f"{prepared_image['image_name']}:{uploaded_annotations.name}:"
            f"{annotation_digest}"
        )
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
    elif image_changed or st.session_state.get("force_saved_annotation_reload"):
        patch_metadata = prepared_image.get("patch_metadata", {})
        record = find_saved_annotation_record(
            source_wsi_name=str(
                patch_metadata.get(
                    "source_wsi_name",
                    st.session_state.image_metadata.get("source_wsi_name", ""),
                )
            ),
            patch_id=str(
                patch_metadata.get(
                    "patch_id",
                    st.session_state.image_metadata.get("patch_id", ""),
                )
            ),
            image_name=str(prepared_image["image_name"]),
        )
        if record:
            saved_path, payload = record
            restored = [
                normalize_annotation_status(item)
                for item in payload.get("annotations", [])
            ]
            st.session_state.annotation_table = restored
            st.session_state.image_metadata.update(payload.get("image_metadata", {}))
            st.session_state.region_annotations = payload.get(
                "region_annotations",
                default_region_annotations(),
            )
            st.session_state.canvas_objects = canvas_json_from_annotations(
                restored,
                display_image.size[0],
                display_image.size[1],
                st.session_state.scale_factor,
            )["objects"]
            st.session_state.restored_annotations_key = (
                f"{saved_path}:{saved_path.stat().st_mtime_ns}"
            )
            st.session_state.canvas_key_version += 1
            st.session_state.canvas_initial_drawing_pending = True
        elif image_changed:
            st.session_state.annotation_table = []
            st.session_state.canvas_objects = []
        st.session_state.force_saved_annotation_reload = False


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


def render_training_data_manager() -> None:
    if not st.toggle(
        "学習データ管理を開く",
        value=False,
        key="show_training_data_manager",
        help="開いた時だけ保存済みannotation JSONとmanifestを読み込みます。",
    ):
        return
    with st.expander("学習データ管理", expanded=True):
        st.caption(
            "物理削除より、まずexclude_from_trainingによるsoft exclusionを推奨します。"
            "元NDPI/WSIはこの画面から削除しません。"
        )
        slides = training_slide_inventory()
        manifest = load_patch_manifest()
        if not slides and manifest.empty:
            st.info("管理対象の保存済みannotationまたはpatchがありません。")
            return

        if slides:
            st.dataframe(
                pd.DataFrame(slides),
                hide_index=True,
                use_container_width=True,
            )

        slide_options = [str(row["slide_key"]) for row in slides]
        selected_slide = st.selectbox(
            "編集するslide",
            slide_options,
            key="training_manager_slide",
        ) if slide_options else ""
        selected_row = next(
            (row for row in slides if row["slide_key"] == selected_slide),
            {},
        )

        if selected_slide:
            st.subheader("Slide metadata")
            with st.form("training_manager_slide_form"):
                project_template = st.selectbox(
                    "project_template",
                    PROJECT_TEMPLATES,
                    index=select_index(
                        PROJECT_TEMPLATES,
                        selected_row.get("project_template"),
                        "custom",
                    ),
                )
                disease_context = st.text_input(
                    "disease_context",
                    value=str(selected_row.get("disease_context", "unknown")),
                )
                source_organ = st.selectbox(
                    "source_organ",
                    SOURCE_ORGANS,
                    index=select_index(
                        SOURCE_ORGANS,
                        selected_row.get("source_organ"),
                        "unknown",
                    ),
                )
                tissue_type = st.selectbox(
                    "tissue_type",
                    TISSUE_TYPES,
                    index=select_index(
                        TISSUE_TYPES,
                        selected_row.get("tissue_type"),
                        "unknown",
                    ),
                )
                tissue_region = st.selectbox(
                    "tissue_region",
                    TISSUE_REGIONS,
                    index=select_index(
                        TISSUE_REGIONS,
                        selected_row.get("tissue_region"),
                        "unknown",
                    ),
                )
                staining = st.selectbox(
                    "staining",
                    STAINING_OPTIONS,
                    index=select_index(
                        STAINING_OPTIONS,
                        selected_row.get("staining"),
                        "unknown",
                    ),
                )
                specimen_id = st.text_input(
                    "specimen_id",
                    value=str(selected_row.get("specimen_id", "")),
                )
                slide_id = st.text_input(
                    "slide_id",
                    value=str(selected_row.get("slide_id", "")),
                )
                patient_id_hash = st.text_input(
                    "patient_id_hash",
                    value=str(selected_row.get("patient_id_hash", "")),
                )
                notes = st.text_area(
                    "notes",
                    value=str(selected_row.get("notes", "")),
                )
                exclude_slide = st.checkbox(
                    "このslideを学習から除外",
                    value=safe_bool(
                        selected_row.get("exclude_from_training", False)
                    ),
                )
                exclusion_reason = st.selectbox(
                    "除外理由",
                    EXCLUSION_REASONS,
                    index=select_index(
                        EXCLUSION_REASONS,
                        selected_row.get("exclusion_reason"),
                        "",
                    ),
                    disabled=not exclude_slide,
                )
                save_slide = st.form_submit_button(
                    "Slide metadataを保存",
                    use_container_width=True,
                )
            if save_slide:
                updated = update_saved_slide_metadata(
                    selected_slide,
                    {
                        "project_template": project_template,
                        "disease_context": disease_context,
                        "source_organ": source_organ,
                        "tissue_type": tissue_type,
                        "tissue_region": tissue_region,
                        "staining": staining,
                        "specimen_id": specimen_id,
                        "slide_id": slide_id,
                        "patient_id_hash": patient_id_hash,
                        "notes": notes,
                        "exclude_from_training": exclude_slide,
                        "exclusion_reason": (
                            exclusion_reason if exclude_slide else ""
                        ),
                    },
                )
                st.session_state.training_data_stale = True
                if selected_slide in {
                    str(st.session_state.image_metadata.get("source_wsi_name", "")),
                    str(st.session_state.image_metadata.get("slide_id", "")),
                    str(st.session_state.image_name or ""),
                }:
                    st.session_state.force_saved_annotation_reload = True
                st.success(f"{updated}件のannotation JSONを更新しました。")
                st.warning(
                    "metadataが変更されました。CLAM export、deep feature、"
                    "mil_bagsは古い可能性があります。必要な生成物を削除し、"
                    "CLAM exportから順に再生成してください。"
                )

        patch_rows = manifest.copy()
        if selected_slide and not patch_rows.empty:
            source_wsi_name = str(
                selected_row.get("source_wsi_name", selected_slide)
            )
            patch_rows = patch_rows.loc[
                patch_rows["source_wsi_name"].eq(source_wsi_name)
            ].copy()
        if not patch_rows.empty:
            st.subheader("Patch管理")
            patch_view_columns = [
                "source_wsi_name",
                "patch_id",
                "status",
                "reviewed_at",
                "exclude_from_training",
                "exclusion_reason",
                "notes",
            ]
            st.dataframe(
                patch_rows[patch_view_columns],
                hide_index=True,
                use_container_width=True,
            )
            patch_labels = [
                f"{row['patch_id']} | {row['status']}"
                for _, row in patch_rows.iterrows()
            ]
            selected_patch_label = st.selectbox(
                "編集するpatch",
                patch_labels,
                key="training_manager_patch",
            )
            selected_patch_index = patch_labels.index(selected_patch_label)
            patch_row = patch_rows.iloc[selected_patch_index]
            with st.form("training_manager_patch_form"):
                patch_status = st.selectbox(
                    "status",
                    PATCH_QUEUE_STATUSES,
                    index=select_index(
                        PATCH_QUEUE_STATUSES,
                        patch_row.get("status"),
                        "not_started",
                    ),
                )
                reviewed_at = st.text_input(
                    "reviewed_at (ISO 8601)",
                    value=str(patch_row.get("reviewed_at", "")),
                )
                exclude_patch = st.checkbox(
                    "このpatchを学習から除外",
                    value=safe_bool(
                        patch_row.get("exclude_from_training", False)
                    ),
                )
                patch_reason = st.selectbox(
                    "exclusion_reason",
                    EXCLUSION_REASONS,
                    index=select_index(
                        EXCLUSION_REASONS,
                        patch_row.get("exclusion_reason"),
                        "",
                    ),
                    disabled=not exclude_patch,
                )
                patch_notes = st.text_area(
                    "patch notes",
                    value=str(patch_row.get("notes", "")),
                )
                save_patch = st.form_submit_button(
                    "Patch設定を保存",
                    use_container_width=True,
                )
            if save_patch:
                normalized_reviewed_at = (
                    normalize_tokyo_timestamp(reviewed_at)
                    if reviewed_at.strip()
                    else ""
                )
                update_training_patch(
                    str(patch_row["source_wsi_name"]),
                    str(patch_row["patch_id"]),
                    {
                        "status": patch_status,
                        "reviewed_at": normalized_reviewed_at,
                        "exclude_from_training": exclude_patch,
                        "exclusion_reason": (
                            patch_reason if exclude_patch else ""
                        ),
                        "notes": patch_notes,
                    },
                )
                st.session_state.training_data_stale = True
                if (
                    str(st.session_state.image_metadata.get("source_wsi_name", ""))
                    == str(patch_row["source_wsi_name"])
                    and str(st.session_state.image_metadata.get("patch_id", ""))
                    == str(patch_row["patch_id"])
                ):
                    st.session_state.force_saved_annotation_reload = True
                st.success("Patch設定を保存しました。")
                st.warning(
                    "既存のCLAM/deep feature/mil_bagsは古い可能性があります。"
                )

            st.subheader("生成物の削除")
            st.caption(
                "選択slideのdeep featureと、必要に応じて再生成可能なCLAM CSVを削除します。"
            )
            st.markdown("#### アノテーションを最初からやり直す")
            st.caption(
                "patch画像と元WSIは残し、保存済みannotationだけを空にします。"
                "実行前のJSONはdata/annotations/backups/へ退避します。"
            )
            restart_confirm = st.checkbox(
                "このpatchのannotationをリセットする",
                key="confirm_annotation_restart",
            )
            restart_patch_id = st.text_input(
                "リセット確認のためpatch_idを入力",
                key="annotation_restart_patch_id",
            )
            if st.button(
                "バックアップしてannotationをリセット",
                disabled=not (
                    restart_confirm
                    and restart_patch_id == str(patch_row["patch_id"])
                ),
                use_container_width=True,
            ):
                backup = reset_saved_patch_annotations(
                    str(patch_row["source_wsi_name"]),
                    str(patch_row["patch_id"]),
                )
                if backup:
                    if (
                        str(st.session_state.image_metadata.get("source_wsi_name", ""))
                        == str(patch_row["source_wsi_name"])
                        and str(st.session_state.image_metadata.get("patch_id", ""))
                        == str(patch_row["patch_id"])
                    ):
                        st.session_state.annotation_table = []
                        st.session_state.canvas_objects = []
                        st.session_state.force_saved_annotation_reload = True
                        st.session_state.canvas_key_version += 1
                        st.session_state.canvas_initial_drawing_pending = True
                    st.session_state.training_data_stale = True
                    st.success(f"annotationをリセットしました。backup: {backup}")
                    st.rerun()
                else:
                    st.warning("対象patchの保存済みannotation JSONがありません。")

            delete_global = st.checkbox(
                "CLAM再生成系CSVとmil_bags.csvも削除する",
                key="delete_global_clam_artifacts",
            )
            confirm_generated = st.checkbox(
                "生成物を削除することを確認しました",
                key="confirm_generated_delete",
            )
            generated_phrase = st.text_input(
                "確認文字: DELETE GENERATED",
                key="generated_delete_phrase",
            )
            if st.button(
                "選択slideの生成物を削除",
                disabled=not (
                    confirm_generated
                    and generated_phrase == "DELETE GENERATED"
                ),
                use_container_width=True,
            ):
                deleted = delete_generated_training_artifacts(
                    str(selected_row.get("slide_id") or Path(selected_slide).stem),
                    delete_global,
                )
                st.success(f"{len(deleted)}件の生成物を削除しました。")

            st.subheader("Annotation JSON / patch imageの物理削除")
            st.error(
                "この操作は元に戻せません。通常は学習除外を使用してください。"
            )
            physical_confirm = st.checkbox(
                "物理削除が必要であることを確認しました",
                key="confirm_physical_delete",
            )
            patch_id_text = st.text_input(
                "確認のためpatch_idを入力",
                key="physical_delete_patch_id",
            )
            if st.button(
                "選択patchのannotationとpatch画像を物理削除",
                disabled=not (
                    physical_confirm
                    and patch_id_text == str(patch_row["patch_id"])
                ),
                use_container_width=True,
            ):
                deleted = delete_patch_annotation_and_image(
                    str(patch_row["source_wsi_name"]),
                    str(patch_row["patch_id"]),
                )
                st.success(f"{len(deleted)}件を削除しました。元WSIは保持されています。")

        if st.session_state.get("training_data_stale"):
            st.warning(
                "学習データ管理で変更が行われています。CLAM-compatible export、"
                "deep feature extraction、validation、MIL bag indexを順に再実行してください。"
            )


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
    render_training_data_manager()

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
    if prepared_image["source_format"] == "wsi_patch":
        render_canvas_wheel_zoom()

    if canvas_result.json_data:
        for obj in canvas_result.json_data.get("objects", []):
            obj.setdefault("label", active_label)
            created_at = tokyo_now_iso()
            obj.setdefault("annotation_id", f"ann_{uuid4().hex}")
            obj.setdefault("annotation_created_at", obj.get("created_at", created_at))
            obj.setdefault("annotation_updated_at", obj["annotation_created_at"])
            obj.setdefault(
                "annotation_session_id",
                st.session_state.annotation_session_id,
            )
            obj.setdefault("created_at", obj["annotation_created_at"])

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

    current_wsi_name = str(st.session_state.image_metadata.get("source_wsi_name", ""))
    current_patch_id = str(st.session_state.image_metadata.get("patch_id", ""))
    queue_manifest = load_patch_manifest()
    queue_mask = (
        (queue_manifest["source_wsi_name"] == current_wsi_name)
        & (queue_manifest["patch_id"] == current_patch_id)
        if not queue_manifest.empty
        else pd.Series(dtype=bool)
    )
    if not queue_manifest.empty and queue_mask.any():
        current_queue_status = str(queue_manifest.loc[queue_mask, "status"].iloc[0])
        source_queue, source_queue_warnings = current_review_queue_rows(
            current_wsi_name
        )
        queue_matches = source_queue.index[source_queue["patch_id"] == current_patch_id].tolist()
        current_queue_index = int(queue_matches[0]) if queue_matches else 0
        completed = int(source_queue["status"].isin(["done", "reviewed_empty"]).sum())
        positive_mode = (
            st.session_state.get("patch_review_mode") == "Positive exploration"
        )

        st.markdown("#### Patch queue操作")
        st.progress(
            completed / len(source_queue) if len(source_queue) else 0,
            text=(
                f"{current_queue_index + 1}/{len(source_queue)} | 完了 {completed}/{len(source_queue)} | "
                f"status: {current_queue_status}"
            ),
        )
        reload_col, _ = st.columns([1, 3])
        if reload_col.button(
            "保存済みannotationを再読み込み",
            use_container_width=True,
            key="reload_saved_patch_annotation",
        ):
            st.session_state.force_saved_annotation_reload = True
            st.session_state.saved_image_key = None
            st.rerun()

        if positive_mode:
            positive_navigation = st.columns(4)
            if positive_navigation[0].button(
                "Previous candidate",
                disabled=current_queue_index <= 0,
                use_container_width=True,
                key="positive_previous_candidate",
            ):
                activate_adjacent_queue_patch(
                    current_wsi_name, current_patch_id, -1
                )
                st.rerun()
            if positive_navigation[1].button(
                "Next positive candidate",
                disabled=current_queue_index >= len(source_queue) - 1,
                use_container_width=True,
                key="positive_next_candidate",
            ):
                activate_adjacent_queue_patch(
                    current_wsi_name, current_patch_id, 1
                )
                st.rerun()
            if positive_navigation[2].button(
                "Mark reviewed_empty",
                use_container_width=True,
                key="positive_mark_empty",
            ):
                update_patch_manifest_status(
                    current_wsi_name,
                    current_patch_id,
                    "reviewed_empty",
                    [
                        item
                        for item in export_annotations
                        if item.get("label") != "eosinophil"
                    ],
                )
                activate_review_queue_index(
                    current_wsi_name, current_queue_index
                )
                st.rerun()
            if positive_navigation[3].button(
                "Mark done",
                use_container_width=True,
                key="positive_mark_done",
            ):
                update_patch_manifest_status(
                    current_wsi_name,
                    current_patch_id,
                    "done",
                    export_annotations,
                )
                activate_review_queue_index(
                    current_wsi_name, current_queue_index
                )
                st.rerun()

            positive_status_actions = st.columns(4)
            if positive_status_actions[0].button(
                "Flag for review",
                use_container_width=True,
                key="positive_flag_review",
            ):
                update_patch_manifest_status(
                    current_wsi_name,
                    current_patch_id,
                    "flagged",
                    export_annotations,
                )
                activate_review_queue_index(
                    current_wsi_name, current_queue_index
                )
                st.rerun()
            if positive_status_actions[1].button(
                "Mark suspected_positive",
                use_container_width=True,
                key="positive_suspected",
            ):
                update_patch_manifest_status(
                    current_wsi_name,
                    current_patch_id,
                    "suspected_positive",
                    export_annotations,
                )
                st.session_state.training_data_stale = True
                activate_review_queue_index(
                    current_wsi_name, current_queue_index
                )
                st.rerun()
            if positive_status_actions[2].button(
                "Skip",
                use_container_width=True,
                key="positive_skip",
            ):
                update_patch_manifest_status(
                    current_wsi_name,
                    current_patch_id,
                    "skipped",
                    export_annotations,
                )
                activate_review_queue_index(
                    current_wsi_name, current_queue_index
                )
                st.rerun()
            if positive_status_actions[3].button(
                "Exclude from training",
                use_container_width=True,
                key="positive_exclude",
            ):
                update_training_patch(
                    current_wsi_name,
                    current_patch_id,
                    {
                        "exclude_from_training": True,
                        "exclusion_reason": "bad_patch",
                    },
                )
                st.session_state.training_data_stale = True
                activate_review_queue_index(
                    current_wsi_name, current_queue_index
                )
                st.rerun()
            st.warning(
                "statusや除外設定を変更した場合、CLAM export / deep feature / "
                "mil_bagsは古くなる可能性があります。"
            )

        primary_actions = st.columns(4)
        if primary_actions[0].button(
            "保存して次へ",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.image_metadata["reviewed"] = True
            st.session_state.image_metadata["exported"] = True
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
            update_patch_manifest_status(
                current_wsi_name,
                current_patch_id,
                "done",
                export_annotations,
            )
            moved = (
                activate_review_queue_index(current_wsi_name, current_queue_index)
                if positive_mode
                else activate_adjacent_queue_patch(
                    current_wsi_name, current_patch_id, 1
                )
            )
            st.session_state.last_saved_message = (
                "保存して次のpatchへ移動しました。"
                if moved
                else "保存しました。queueの最後のpatchです。"
            )
            st.rerun()
        if primary_actions[1].button("好酸球なしで保存して次へ", use_container_width=True):
            st.session_state.image_metadata["reviewed"] = True
            st.session_state.image_metadata["exported"] = True
            eos_negative_annotations = [
                item for item in export_annotations if item.get("label") != "eosinophil"
            ]
            eos_negative_counts = count_annotations(
                eos_negative_annotations,
                st.session_state.image_metadata,
                st.session_state.image_original_size,
            )
            save_outputs(
                st.session_state.image_name,
                st.session_state.original_image_path,
                st.session_state.image_original_size,
                eos_negative_annotations,
                eos_negative_counts,
                st.session_state.image_metadata,
                st.session_state.region_annotations,
                objective_filter,
                exclude_ignore_from_yolo,
                used_for_training_only_export,
            )
            update_patch_manifest_status(
                current_wsi_name,
                current_patch_id,
                "reviewed_empty",
                eos_negative_annotations,
            )
            moved = (
                activate_review_queue_index(current_wsi_name, current_queue_index)
                if positive_mode
                else activate_adjacent_queue_patch(
                    current_wsi_name, current_patch_id, 1
                )
            )
            if not moved:
                st.session_state.annotation_table = []
                st.session_state.canvas_objects = []
                st.session_state.canvas_key_version += 1
                st.session_state.canvas_initial_drawing_pending = True
            st.session_state.last_saved_message = (
                "好酸球0件の確認済みpatchとして保存し、次へ移動しました。"
                if moved
                else "好酸球0件の確認済みpatchとして保存しました。queueの最後です。"
            )
            st.rerun()
        if primary_actions[2].button(
            "前のpatch",
            disabled=current_queue_index <= 0,
            use_container_width=True,
        ):
            activate_adjacent_queue_patch(current_wsi_name, current_patch_id, -1)
            st.rerun()
        if primary_actions[3].button(
            "次のpatch",
            disabled=current_queue_index >= len(source_queue) - 1,
            help="未保存の変更は保存されません。",
            use_container_width=True,
        ):
            activate_adjacent_queue_patch(current_wsi_name, current_patch_id, 1)
            st.rerun()

        secondary_actions = st.columns(3)
        if secondary_actions[0].button("このpatchを保存のみ", use_container_width=True):
            st.session_state.image_metadata["reviewed"] = True
            st.session_state.image_metadata["exported"] = True
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
            update_patch_manifest_status(
                current_wsi_name,
                current_patch_id,
                "done",
                export_annotations,
            )
            st.session_state.last_saved_message = "patchを保存しました: " + str(paths["annotations_json"])
            st.rerun()
        if secondary_actions[1].button("Skipして次へ", use_container_width=True):
            update_patch_manifest_status(current_wsi_name, current_patch_id, "skipped", export_annotations)
            activate_adjacent_queue_patch(current_wsi_name, current_patch_id, 1)
            st.rerun()
        if secondary_actions[2].button("要確認にして次へ", use_container_width=True):
            update_patch_manifest_status(current_wsi_name, current_patch_id, "flagged", export_annotations)
            activate_adjacent_queue_patch(current_wsi_name, current_patch_id, 1)
            st.rerun()

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
            only_completed_patch_queue=bool(
                st.session_state.get("export_completed_patch_queue_only", True)
            ),
        )
        st.success(
            "YOLO datasetを生成しました: "
            f"画像 {dataset_result['images']}件、ラベル {dataset_result['labels']}件、"
            f"data.yaml: {dataset_result['data_yaml']}"
        )
        if dataset_result["skipped"]:
            st.warning("スキップした画像: " + ", ".join(dataset_result["skipped"]))

    if st.button("CLAM-compatibleデータを生成", use_container_width=True):
        clam_result = generate_clam_compatible_export(
            only_completed_patches=bool(
                st.session_state.get("export_completed_patch_queue_only", True)
            )
        )
        st.success(
            "CLAM-compatibleデータを生成しました: "
            f"slide {clam_result['slides']}件、patch {clam_result['patches']}件、"
            f"出力先: {clam_result['clam_dir']}"
        )
        if clam_result["skipped"]:
            st.caption(f"未完了のため除外したpatch: {clam_result['skipped']}件")

    if st.button("Validate CLAM export", use_container_width=True):
        validation = validate_clam_export()
        if validation["valid"]:
            st.success("CLAM-compatible CSV stagingの整合性を確認しました。")
        else:
            st.error("CLAM-compatible CSV stagingに不整合があります。")

        validation_metrics = st.columns(3)
        validation_metrics[0].metric("slide数", validation["slide_count"])
        validation_metrics[1].metric("patch数", validation["patch_count"])
        validation_metrics[2].metric("確認ファイル数", validation["files_checked"])

        if validation["status_counts"]:
            st.caption("status別patch数")
            st.dataframe(
                pd.DataFrame(
                    [
                        {"status": status, "patch_count": count}
                        for status, count in validation["status_counts"].items()
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
        if validation["slides"]:
            st.caption("slide別patch_id整合性")
            st.dataframe(
                pd.DataFrame(validation["slides"]),
                hide_index=True,
                use_container_width=True,
            )
        for error in validation["errors"]:
            st.error(error)
        for warning in validation["warnings"]:
            st.warning(warning)

    with st.expander("Deep feature / MIL bag status", expanded=True):
        mil_status = deep_feature_mil_bag_status()
        if not mil_status["exists"]:
            st.info(
                "data/clam/mil_bags.csv はまだ作成されていません。"
                "deep feature抽出・検証後にbuild_mil_bag_index.pyを実行してください。"
            )
        else:
            status_metrics = st.columns(3)
            status_metrics[0].metric("bag数", mil_status["bag_count"])
            status_metrics[1].metric(
                "feature CSV確認済み",
                sum(
                    1
                    for bag in mil_status["bags"]
                    if bag["feature_csv_exists"]
                ),
            )
            status_metrics[2].metric(
                "feature PTあり",
                sum(
                    1
                    for bag in mil_status["bags"]
                    if bag["feature_pt_exists"]
                ),
            )
            if mil_status["bags"]:
                st.dataframe(
                    pd.DataFrame(mil_status["bags"]),
                    hide_index=True,
                    use_container_width=True,
                )
        for error in mil_status["errors"]:
            st.error(error)
        for warning in mil_status["warnings"]:
            st.warning(warning)

    download_payload = {
        "schema_version": "2.5",
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

