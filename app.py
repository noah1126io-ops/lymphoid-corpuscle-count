from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit.elements.lib import image_utils
from streamlit.elements.lib.layout_utils import LayoutConfig
from PIL import Image, ImageOps
import streamlit_drawable_canvas as drawable_canvas
from streamlit_drawable_canvas import st_canvas


APP_TITLE = "Manual Granulocyte Annotation Tool"
LABELS = ["eosinophil", "neutrophil", "basophil", "other"]
LABEL_COLORS = {
    "eosinophil": "#e83e8c",
    "neutrophil": "#2f80ed",
    "basophil": "#7b2cbf",
    "other": "#6c757d",
}
DATA_DIR = Path("data")
IMAGE_DIR = DATA_DIR / "images"
ANNOTATION_DIR = DATA_DIR / "annotations"
EXPORT_DIR = DATA_DIR / "exports"
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
    for path in (IMAGE_DIR, ANNOTATION_DIR, EXPORT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def init_session_state() -> None:
    defaults = {
        "image_name": None,
        "image_original_size": None,
        "display_size": None,
        "scale_factor": 1.0,
        "canvas_objects": [],
        "saved_image_key": None,
        "restored_annotations_key": None,
        "annotation_table": [],
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


def save_uploaded_image(uploaded_file: Any, image: Image.Image) -> Path:
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
        width = radius * 2 * scale_x
        height = radius * 2 * scale_y
    elif obj_type == "rect":
        rect_width = safe_float(obj.get("width"))
        rect_height = safe_float(obj.get("height"))
        if None in (rect_width, rect_height):
            return None
        width = rect_width * scale_x
        height = rect_height * scale_y

    if width <= 0 or height <= 0:
        return None

    inverse_scale = 1 / scale_factor
    return {
        "image_name": image_name,
        "label": label,
        "x": round((left + width / 2) * inverse_scale, 3),
        "y": round((top + height / 2) * inverse_scale, 3),
        "width": round(width * inverse_scale, 3),
        "height": round(height * inverse_scale, 3),
        "confidence": 1.0,
        "created_at": obj.get("created_at", created_at),
    }


def annotations_from_canvas(
    canvas_json: dict[str, Any] | None,
    image_name: str | None,
    scale_factor: float,
    fallback_label: str,
) -> list[dict[str, Any]]:
    if not canvas_json or not image_name:
        return []

    created_at = datetime.now().isoformat(timespec="seconds")
    annotations = []
    for obj in canvas_json.get("objects", []):
        annotation = normalize_canvas_object(obj, image_name, scale_factor, fallback_label, created_at)
        if annotation:
            annotations.append(annotation)
    return annotations


def fabric_object_from_annotation(annotation: dict[str, Any], scale_factor: float) -> dict[str, Any]:
    label = annotation.get("label", "other")
    color = LABEL_COLORS.get(label, LABEL_COLORS["other"])
    width = (safe_float(annotation.get("width"), 0.0) or 0.0) * scale_factor
    height = (safe_float(annotation.get("height"), 0.0) or 0.0) * scale_factor
    center_x = (safe_float(annotation.get("x"), 0.0) or 0.0) * scale_factor
    center_y = (safe_float(annotation.get("y"), 0.0) or 0.0) * scale_factor

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


def count_annotations(annotations: list[dict[str, Any]]) -> pd.DataFrame:
    counts = {label: 0 for label in LABELS}
    for item in annotations:
        label = item.get("label")
        if label in counts:
            counts[label] += 1
    counts["total"] = sum(counts.values())
    return pd.DataFrame([{"label": label, "count": count} for label, count in counts.items()])


def save_outputs(image_name: str, annotations: list[dict[str, Any]], counts_df: pd.DataFrame) -> tuple[Path, Path]:
    annotation_path = ANNOTATION_DIR / "annotations.json"
    count_path = EXPORT_DIR / "counts.csv"

    payload = {
        "image_name": image_name,
        "labels": LABELS,
        "label_colors": LABEL_COLORS,
        "annotations": annotations,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    annotation_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    counts_df.to_csv(count_path, index=False, encoding="utf-8-sig")
    return annotation_path, count_path


def load_annotation_file(uploaded_file: Any) -> list[dict[str, Any]]:
    payload = json.loads(uploaded_file.getvalue().decode("utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("annotations", [])
    return []


def render_controls() -> tuple[str, str, str, int]:
    st.subheader("Annotation")
    label = st.radio("Active label", LABELS, captions=[LABEL_COLORS[item] for item in LABELS])
    mode = st.selectbox(
        "Drawing mode",
        ["circle", "rect", "transform"],
        index=0,
        help="Use transform to move, resize, or delete selected objects.",
    )
    stroke_width = st.slider("Stroke width", min_value=1, max_value=8, value=3)
    return label, mode, LABEL_COLORS[label], stroke_width


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    patch_drawable_canvas_for_streamlit()
    disable_canvas_context_menu()
    ensure_directories()
    init_session_state()

    st.title(APP_TITLE)
    st.caption("Research-use manual annotation app for eosinophils, neutrophils, basophils, and other cells.")

    left, right = st.columns([3, 1], gap="large")

    with right:
        st.subheader("Data")
        uploaded_image = st.file_uploader("Upload tissue image", type=["jpg", "jpeg", "png", "tif", "tiff"])
        uploaded_annotations = st.file_uploader("Restore annotations.json", type=["json"])
        active_label, drawing_mode, stroke_color, stroke_width = render_controls()

        count_container = st.container()
        image_info_container = st.container()
        action_container = st.container()

        if uploaded_image:
            image = load_image(uploaded_image)
            display_image, scale_factor = make_display_image(image)

            if st.session_state.image_name != uploaded_image.name:
                st.session_state.canvas_objects = []
                st.session_state.annotation_table = []
                st.session_state.restored_annotations_key = None
                st.session_state.saved_image_key = None

            st.session_state.image_name = uploaded_image.name
            st.session_state.image_original_size = image.size
            st.session_state.display_size = display_image.size
            st.session_state.scale_factor = scale_factor

            image_key = f"{uploaded_image.name}:{uploaded_image.size}"
            if st.session_state.saved_image_key != image_key:
                save_uploaded_image(uploaded_image, image)
                st.session_state.saved_image_key = image_key

            if uploaded_annotations:
                restore_key = f"{uploaded_image.name}:{uploaded_annotations.name}:{uploaded_annotations.size}"
            else:
                restore_key = None

            if uploaded_annotations and st.session_state.restored_annotations_key != restore_key:
                restored = load_annotation_file(uploaded_annotations)
                st.session_state.annotation_table = restored
                st.session_state.canvas_objects = canvas_json_from_annotations(
                    restored,
                    display_image.size[0],
                    display_image.size[1],
                    scale_factor,
                )["objects"]
                st.session_state.restored_annotations_key = restore_key

    with left:
        if not uploaded_image:
            st.info("Upload a jpg, png, tif, or tiff image to begin annotation.")
        else:
            display_image, _ = make_display_image(load_image(uploaded_image))
            canvas_width, canvas_height = display_image.size
            initial_json = {
                "version": "5.2.4",
                "objects": st.session_state.canvas_objects,
                "background": "",
                "width": canvas_width,
                "height": canvas_height,
            }

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
                key=f"canvas_{st.session_state.image_name}",
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
                )

            st.subheader("Annotations")
            st.dataframe(pd.DataFrame(st.session_state.annotation_table), hide_index=True, use_container_width=True)

    annotations = st.session_state.annotation_table
    counts_df = count_annotations(annotations)
    save_disabled = not st.session_state.image_name

    with count_container:
        st.subheader("Counts")
        st.dataframe(counts_df, hide_index=True, use_container_width=True)

    with image_info_container:
        if st.session_state.image_original_size:
            original_width, original_height = st.session_state.image_original_size
            st.metric("Original size", f"{original_width} x {original_height}px")
            st.metric("Display scale", f"{st.session_state.scale_factor:.4f}")

    with action_container:
        if st.button("Save JSON / CSV", disabled=save_disabled, use_container_width=True):
            annotation_path, count_path = save_outputs(st.session_state.image_name, annotations, counts_df)
            st.success(f"Saved: {annotation_path} / {count_path}")

        st.download_button(
            "Download annotations.json",
            data=json.dumps(
                {"image_name": st.session_state.image_name, "annotations": annotations},
                ensure_ascii=False,
                indent=2,
            ),
            file_name="annotations.json",
            mime="application/json",
            disabled=save_disabled,
            use_container_width=True,
        )
        st.download_button(
            "Download counts.csv",
            data=counts_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="counts.csv",
            mime="text/csv",
            disabled=save_disabled,
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
