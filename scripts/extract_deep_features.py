"""Extract patch embeddings from WSI files for later CLAM/MIL training.

This script is intentionally separate from the Streamlit application so the
manual annotation workflow does not require PyTorch.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESS_LIST = PROJECT_ROOT / "data" / "clam" / "process_list_autogen.csv"
DEFAULT_CSV_DIR = PROJECT_ROOT / "data" / "clam" / "deep_features_csv"
DEFAULT_PT_DIR = PROJECT_ROOT / "data" / "clam" / "deep_features"
REQUIRED_COORD_COLUMNS = {
    "patch_id",
    "x",
    "y",
    "patch_width",
    "patch_height",
    "patch_level",
    "patch_downsample",
    "target_mpp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read selected WSI patches with OpenSlide and extract pretrained "
            "ResNet embeddings for CLAM/MIL staging."
        )
    )
    parser.add_argument(
        "--process-list",
        type=Path,
        default=DEFAULT_PROCESS_LIST,
        help="Path to process_list_autogen.csv.",
    )
    parser.add_argument(
        "--encoder",
        choices=("resnet18", "resnet50"),
        default="resnet18",
        help="Torchvision image encoder.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Torch device such as cpu, cuda, or auto.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Number of patches encoded per batch.",
    )
    parser.add_argument(
        "--csv-output-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help="Directory for per-slide feature CSV files.",
    )
    parser.add_argument(
        "--pt-output-dir",
        type=Path,
        default=DEFAULT_PT_DIR,
        help="Directory for per-slide PyTorch feature files.",
    )
    parser.add_argument(
        "--no-pt",
        action="store_true",
        help="Do not write the optional .pt output.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output files.",
    )
    parser.add_argument(
        "--no-pretrained",
        action="store_true",
        help="Use randomly initialized weights. Intended only for pipeline tests.",
    )
    return parser.parse_args()


def resolve_input_path(value: Any, process_list_path: Path) -> Path:
    """Resolve CSV paths written relative to either the project or CSV folder."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Empty path in process list.")

    candidate = Path(raw.replace("\\", "/")).expanduser()
    if candidate.is_absolute():
        return candidate

    options = (
        PROJECT_ROOT / candidate,
        process_list_path.parent / candidate,
        Path.cwd() / candidate,
    )
    for option in options:
        if option.exists():
            return option.resolve()
    return options[0].resolve()


def safe_output_stem(value: Any) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip()).strip("._")
    return stem or "slide"


def require_runtime_dependencies() -> tuple[Any, Any, Any]:
    try:
        import openslide
        import torch
        from torchvision import models, transforms
    except ImportError as error:
        raise RuntimeError(
            "ML dependencies are missing. Run: "
            "pip install -r requirements-ml.txt"
        ) from error
    return openslide, torch, (models, transforms)


def select_device(torch: Any, requested: str) -> Any:
    requested = requested.strip().lower()
    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is False.")
    return torch.device(requested)


def build_encoder(
    encoder_name: str,
    no_pretrained: bool,
    device: Any,
    torch: Any,
    models: Any,
    transforms: Any,
) -> tuple[Any, Any, int, str]:
    if encoder_name == "resnet18":
        weights = None if no_pretrained else models.ResNet18_Weights.DEFAULT
        model = models.resnet18(weights=weights)
        embedding_size = int(model.fc.in_features)
    else:
        weights = None if no_pretrained else models.ResNet50_Weights.DEFAULT
        model = models.resnet50(weights=weights)
        embedding_size = int(model.fc.in_features)

    model.fc = torch.nn.Identity()
    model.eval()
    model.to(device)

    preprocess = transforms.Compose(
        [
            transforms.Resize((224, 224), antialias=True),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225),
            ),
        ]
    )
    weights_name = "random" if weights is None else weights.__class__.__name__ + "." + weights.name
    feature_version = f"torchvision_{encoder_name}_{weights_name.lower()}"
    return model, preprocess, embedding_size, feature_version


def read_patch_rgb(slide: Any, row: pd.Series) -> Image.Image:
    x = int(float(row["x"]))
    y = int(float(row["y"]))
    width = int(float(row["patch_width"]))
    height = int(float(row["patch_height"]))
    level = int(float(row["patch_level"]))
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid patch size: {width}x{height}")
    if level < 0 or level >= int(slide.level_count):
        raise ValueError(f"Invalid OpenSlide level: {level}")

    patch = slide.read_region((x, y), level, (width, height))
    if patch.mode == "RGBA":
        white = Image.new("RGBA", patch.size, (255, 255, 255, 255))
        patch = Image.alpha_composite(white, patch)
    return patch.convert("RGB")


def validate_coords(coords: pd.DataFrame, coords_path: Path) -> None:
    missing = REQUIRED_COORD_COLUMNS.difference(coords.columns)
    if missing:
        raise ValueError(
            f"{coords_path} is missing required columns: {', '.join(sorted(missing))}"
        )
    if coords.empty:
        raise ValueError(f"{coords_path} has no patches.")
    if coords["patch_id"].astype(str).duplicated().any():
        raise ValueError(f"{coords_path} contains duplicate patch_id values.")
    numeric_columns = [
        "x",
        "y",
        "patch_width",
        "patch_height",
        "patch_level",
        "patch_downsample",
    ]
    for column in numeric_columns:
        numeric = pd.to_numeric(coords[column], errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"{coords_path} contains invalid values in {column}.")
        coords[column] = numeric


def encode_slide(
    slide_id: str,
    slide_path: Path,
    coords_path: Path,
    model: Any,
    preprocess: Any,
    embedding_size: int,
    feature_model: str,
    feature_version: str,
    device: Any,
    batch_size: int,
    torch: Any,
    openslide: Any,
) -> tuple[pd.DataFrame, Any]:
    coords = pd.read_csv(coords_path, encoding="utf-8-sig")
    validate_coords(coords, coords_path)
    total = len(coords)
    feature_batches: list[Any] = []

    slide = openslide.OpenSlide(str(slide_path))
    try:
        for start in range(0, total, batch_size):
            stop = min(start + batch_size, total)
            batch_rows = coords.iloc[start:stop]
            tensors = []
            for _, row in batch_rows.iterrows():
                patch = read_patch_rgb(slide, row)
                tensors.append(preprocess(patch))

            batch = torch.stack(tensors).to(device)
            with torch.inference_mode():
                features = model(batch)
            feature_batches.append(features.detach().cpu())
            print(f"  {slide_id}: {stop}/{total} patches", flush=True)
    finally:
        slide.close()

    feature_tensor = torch.cat(feature_batches, dim=0)
    if feature_tensor.ndim != 2 or feature_tensor.shape[1] != embedding_size:
        raise RuntimeError(
            f"Unexpected feature shape {tuple(feature_tensor.shape)}; "
            f"expected (*, {embedding_size})."
        )

    metadata_columns = [
        "patch_id",
        "x",
        "y",
        "patch_width",
        "patch_height",
        "patch_level",
        "target_mpp",
    ]
    output = pd.DataFrame({"slide_id": [slide_id] * total})
    for column in metadata_columns:
        output[column] = coords[column] if column in coords.columns else ""
    output["feature_model"] = feature_model
    output["feature_version"] = feature_version

    feature_frame = pd.DataFrame(
        feature_tensor.numpy(),
        columns=[f"feature_{index}" for index in range(embedding_size)],
    )
    output = pd.concat([output.reset_index(drop=True), feature_frame], axis=1)
    return output, feature_tensor


def save_outputs(
    output: pd.DataFrame,
    feature_tensor: Any,
    csv_path: Path,
    pt_path: Path,
    write_pt: bool,
    torch: Any,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(csv_path, index=False, encoding="utf-8-sig")
    if write_pt:
        pt_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "features": feature_tensor,
                "patch_id": output["patch_id"].astype(str).tolist(),
                "coords": torch.as_tensor(
                    output[["x", "y"]].to_numpy(dtype="int64")
                ),
                "slide_id": str(output["slide_id"].iloc[0]),
                "feature_model": str(output["feature_model"].iloc[0]),
                "feature_version": str(output["feature_version"].iloc[0]),
            },
            pt_path,
        )


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1.")

    process_list_path = args.process_list.expanduser().resolve()
    if not process_list_path.exists():
        raise FileNotFoundError(f"Process list not found: {process_list_path}")

    process_list = pd.read_csv(process_list_path, encoding="utf-8-sig")
    required = {"slide_id", "slide_path", "process"}
    missing = required.difference(process_list.columns)
    if missing:
        raise ValueError(
            "Process list is missing required columns: "
            + ", ".join(sorted(missing))
        )

    selected = process_list.loc[
        pd.to_numeric(process_list["process"], errors="coerce").fillna(0).eq(1)
    ].copy()
    if selected.empty:
        print("No slides have process=1.")
        return 0

    openslide, torch, vision = require_runtime_dependencies()
    models, transforms = vision
    device = select_device(torch, args.device)
    model, preprocess, embedding_size, feature_version = build_encoder(
        args.encoder,
        args.no_pretrained,
        device,
        torch,
        models,
        transforms,
    )
    print(
        f"Encoder={args.encoder}, features={embedding_size}, device={device}, "
        f"slides={len(selected)}",
        flush=True,
    )

    completed = 0
    skipped = 0
    failed = 0
    for _, process_row in selected.iterrows():
        slide_id = str(process_row["slide_id"]).strip()
        output_stem = safe_output_stem(slide_id)
        csv_path = args.csv_output_dir.expanduser().resolve() / f"{output_stem}.csv"
        pt_path = args.pt_output_dir.expanduser().resolve() / f"{output_stem}.pt"
        expected_outputs = [csv_path] + ([] if args.no_pt else [pt_path])
        if not args.overwrite and any(path.exists() for path in expected_outputs):
            print(f"SKIP {slide_id}: output already exists (use --overwrite).")
            skipped += 1
            continue

        try:
            slide_path = resolve_input_path(process_row["slide_path"], process_list_path)
            if "coords_csv" in process_list.columns and str(process_row.get("coords_csv", "")).strip():
                coords_path = resolve_input_path(
                    process_row["coords_csv"],
                    process_list_path,
                )
            else:
                coords_path = (
                    process_list_path.parent / "coords" / f"{output_stem}.csv"
                ).resolve()
            if not slide_path.exists():
                raise FileNotFoundError(f"WSI not found: {slide_path}")
            if not coords_path.exists():
                raise FileNotFoundError(f"Coords CSV not found: {coords_path}")

            print(f"START {slide_id}: {slide_path.name}", flush=True)
            output, feature_tensor = encode_slide(
                slide_id=slide_id,
                slide_path=slide_path,
                coords_path=coords_path,
                model=model,
                preprocess=preprocess,
                embedding_size=embedding_size,
                feature_model=args.encoder,
                feature_version=feature_version,
                device=device,
                batch_size=args.batch_size,
                torch=torch,
                openslide=openslide,
            )
            save_outputs(
                output=output,
                feature_tensor=feature_tensor,
                csv_path=csv_path,
                pt_path=pt_path,
                write_pt=not args.no_pt,
                torch=torch,
            )
            print(f"DONE {slide_id}: {len(output)} patches -> {csv_path}", flush=True)
            completed += 1
        except Exception as error:
            print(f"ERROR {slide_id}: {error}", file=sys.stderr, flush=True)
            failed += 1

    print(
        f"Finished: completed={completed}, skipped={skipped}, failed={failed}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
