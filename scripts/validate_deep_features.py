"""Validate CLAM/MIL deep feature staging outputs."""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAM_DIR = PROJECT_ROOT / "data" / "clam"
DEFAULT_PATCH_MANIFEST = CLAM_DIR / "patch_manifest.csv"
DEFAULT_PROCESS_LIST = CLAM_DIR / "process_list_autogen.csv"
DEFAULT_COORDS_DIR = CLAM_DIR / "coords"
DEFAULT_FEATURE_CSV_DIR = CLAM_DIR / "deep_features_csv"
DEFAULT_FEATURE_PT_DIR = CLAM_DIR / "deep_features"
EXPECTED_FEATURE_COUNTS = {"resnet18": 512, "resnet50": 2048}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate deep feature CSV/PT files against CLAM patch staging."
    )
    parser.add_argument("--patch-manifest", type=Path, default=DEFAULT_PATCH_MANIFEST)
    parser.add_argument("--process-list", type=Path, default=DEFAULT_PROCESS_LIST)
    parser.add_argument("--coords-dir", type=Path, default=DEFAULT_COORDS_DIR)
    parser.add_argument(
        "--feature-csv-dir",
        type=Path,
        default=DEFAULT_FEATURE_CSV_DIR,
    )
    parser.add_argument(
        "--feature-pt-dir",
        type=Path,
        default=DEFAULT_FEATURE_PT_DIR,
    )
    parser.add_argument(
        "--require-pt",
        action="store_true",
        help="Treat a missing .pt file as an error.",
    )
    return parser.parse_args()


def safe_output_stem(value: Any) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip()).strip("._")
    return stem or "slide"


def read_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV: {path}")
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = required_columns.difference(frame.columns)
    if missing:
        raise ValueError(
            f"{path} is missing columns: {', '.join(sorted(missing))}"
        )
    return frame


def process_enabled(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).eq(1)


def string_ids(series: pd.Series) -> list[str]:
    return series.fillna("").astype(str).str.strip().tolist()


def expected_feature_count(model: str) -> int | None:
    normalized = model.strip().lower()
    for name, count in EXPECTED_FEATURE_COUNTS.items():
        if normalized == name or name in normalized:
            return count
    return None


def validate_numeric_features(
    features: pd.DataFrame,
    feature_columns: list[str],
) -> str | None:
    if not feature_columns:
        return "feature_ columns are missing."
    numeric = features[feature_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        return "feature columns contain NaN, empty, or non-numeric values."
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        return "feature columns contain inf or -inf."
    return None


def load_pt(path: Path) -> dict[str, Any]:
    try:
        import torch
    except ImportError as error:
        raise RuntimeError(
            f"{path} exists but PyTorch is unavailable. "
            "Run: pip install -r requirements-ml.txt"
        ) from error

    payload = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict):
        raise ValueError("PT payload must be a dictionary.")
    return payload


def validate_pt(
    path: Path,
    csv_patch_ids: list[str],
    csv_feature_count: int,
) -> list[str]:
    errors: list[str] = []
    try:
        payload = load_pt(path)
    except Exception as error:
        return [str(error)]

    tensor = payload.get("features")
    pt_patch_ids = [str(value) for value in payload.get("patch_id", [])]
    if tensor is None or not hasattr(tensor, "shape"):
        errors.append("PT payload has no features tensor.")
        return errors
    shape = tuple(int(value) for value in tensor.shape)
    expected_shape = (len(csv_patch_ids), csv_feature_count)
    if shape != expected_shape:
        errors.append(f"PT features shape={shape}, expected={expected_shape}.")
    if len(pt_patch_ids) != len(csv_patch_ids):
        errors.append(
            f"PT patch_id count={len(pt_patch_ids)}, CSV count={len(csv_patch_ids)}."
        )
    elif pt_patch_ids != csv_patch_ids:
        errors.append("PT patch_id order does not match the feature CSV.")
    return errors


def validate_slide(
    slide_id: str,
    process_row: pd.Series,
    manifest: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    stem = safe_output_stem(slide_id)
    coords_path = args.coords_dir.resolve() / f"{stem}.csv"
    feature_csv_path = args.feature_csv_dir.resolve() / f"{stem}.csv"
    feature_pt_path = args.feature_pt_dir.resolve() / f"{stem}.pt"

    try:
        coords = read_csv(coords_path, {"patch_id"})
    except Exception as error:
        errors.append(str(error))
        coords = pd.DataFrame(columns=["patch_id"])
    try:
        features = read_csv(
            feature_csv_path,
            {"slide_id", "patch_id", "feature_model", "feature_version"},
        )
    except Exception as error:
        errors.append(str(error))
        features = pd.DataFrame()

    coords_ids = string_ids(coords["patch_id"]) if "patch_id" in coords else []
    coords_set = set(coords_ids)
    if len(coords_ids) != len(coords_set):
        errors.append("coords CSV contains duplicate patch_id values.")

    slide_manifest = manifest.loc[
        manifest["slide_id"].fillna("").astype(str).str.strip().eq(slide_id)
    ]
    manifest_ids = (
        string_ids(slide_manifest["patch_id"])
        if "patch_id" in slide_manifest
        else []
    )
    if not manifest_ids:
        errors.append("patch manifest has no rows for this slide.")
    elif set(manifest_ids) != coords_set:
        errors.append(
            "patch manifest and coords CSV patch_id sets do not match "
            f"(manifest={len(set(manifest_ids))}, coords={len(coords_set)})."
        )

    feature_count = 0
    feature_model = ""
    feature_version = ""
    feature_ids: list[str] = []
    if not features.empty:
        feature_ids = string_ids(features["patch_id"])
        feature_set = set(feature_ids)
        if len(feature_ids) != len(feature_set):
            errors.append("deep feature CSV contains duplicate patch_id values.")
        if feature_set != coords_set:
            errors.append(
                "coords and deep feature CSV patch_id sets do not match "
                f"(coords={len(coords_set)}, features={len(feature_set)})."
            )
        if len(features) != len(coords):
            errors.append(
                f"patch count mismatch: coords={len(coords)}, features={len(features)}."
            )

        slide_values = {
            value for value in string_ids(features["slide_id"]) if value
        }
        if slide_values != {slide_id}:
            errors.append(
                f"feature CSV slide_id values are invalid: {sorted(slide_values)}."
            )

        model_values = {
            value for value in string_ids(features["feature_model"]) if value
        }
        version_values = {
            value for value in string_ids(features["feature_version"]) if value
        }
        if len(model_values) != 1:
            errors.append("feature_model must contain one non-empty value per slide.")
        else:
            feature_model = next(iter(model_values))
        if len(version_values) != 1:
            errors.append("feature_version must contain one non-empty value per slide.")
        else:
            feature_version = next(iter(version_values))

        feature_columns = sorted(
            (
                column
                for column in features.columns
                if re.fullmatch(r"feature_\d+", column)
            ),
            key=lambda column: int(column.removeprefix("feature_")),
        )
        feature_count = len(feature_columns)
        numeric_error = validate_numeric_features(features, feature_columns)
        if numeric_error:
            errors.append(numeric_error)
        expected = expected_feature_count(feature_model)
        if expected is None:
            errors.append(f"Unsupported or unknown feature_model: {feature_model!r}.")
        elif feature_count != expected:
            errors.append(
                f"{feature_model} has {feature_count} feature columns; expected {expected}."
            )

    process_patch_count = pd.to_numeric(
        pd.Series([process_row.get("patch_count", math.nan)]),
        errors="coerce",
    ).iloc[0]
    if not pd.isna(process_patch_count) and int(process_patch_count) != len(coords):
        errors.append(
            f"process list patch_count={int(process_patch_count)}, coords={len(coords)}."
        )

    if feature_pt_path.exists() and not features.empty:
        errors.extend(validate_pt(feature_pt_path, feature_ids, feature_count))
    elif args.require_pt:
        errors.append(f"Missing PT file: {feature_pt_path}")
    else:
        warnings.append("PT file is absent; CSV-only bag remains valid.")

    summary = {
        "slide_id": slide_id,
        "coords": len(coords),
        "features": len(features),
        "feature_count": feature_count,
        "feature_model": feature_model,
        "pt": feature_pt_path.exists(),
        "result": "ERROR" if errors else "OK",
    }
    return errors, warnings, summary


def main() -> int:
    args = parse_args()
    args.patch_manifest = args.patch_manifest.expanduser().resolve()
    args.process_list = args.process_list.expanduser().resolve()
    args.coords_dir = args.coords_dir.expanduser().resolve()
    args.feature_csv_dir = args.feature_csv_dir.expanduser().resolve()
    args.feature_pt_dir = args.feature_pt_dir.expanduser().resolve()

    try:
        manifest = read_csv(args.patch_manifest, {"slide_id", "patch_id"})
        process_list = read_csv(
            args.process_list,
            {"slide_id", "process", "patch_count"},
        )
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    selected = process_list.loc[process_enabled(process_list["process"])].copy()
    if selected.empty:
        print("ERROR: No slides have process=1.", file=sys.stderr)
        return 1

    total_errors = 0
    total_warnings = 0
    print(f"Validating {len(selected)} slide(s)...")
    for _, process_row in selected.iterrows():
        slide_id = str(process_row["slide_id"]).strip()
        errors, warnings, summary = validate_slide(
            slide_id,
            process_row,
            manifest,
            args,
        )
        print(
            f"[{summary['result']}] {slide_id}: coords={summary['coords']}, "
            f"features={summary['features']}, dims={summary['feature_count']}, "
            f"model={summary['feature_model'] or '-'}, pt={summary['pt']}"
        )
        for message in errors:
            print(f"  ERROR: {message}", file=sys.stderr)
        for message in warnings:
            print(f"  WARNING: {message}")
        total_errors += len(errors)
        total_warnings += len(warnings)

    print(
        f"Validation finished: slides={len(selected)}, "
        f"errors={total_errors}, warnings={total_warnings}"
    )
    return 1 if total_errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
