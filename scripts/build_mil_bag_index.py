"""Build a slide-level MIL bag index from validated deep feature files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAM_DIR = PROJECT_ROOT / "data" / "clam"
DEFAULT_SLIDE_LABELS = CLAM_DIR / "slide_labels.csv"
DEFAULT_PROCESS_LIST = CLAM_DIR / "process_list_autogen.csv"
DEFAULT_FEATURE_CSV_DIR = CLAM_DIR / "deep_features_csv"
DEFAULT_FEATURE_PT_DIR = CLAM_DIR / "deep_features"
DEFAULT_OUTPUT = CLAM_DIR / "mil_bags.csv"
OUTPUT_COLUMNS = [
    "case_id",
    "slide_id",
    "label",
    "source_wsi_name",
    "patient_id_hash",
    "specimen_id",
    "feature_csv",
    "feature_pt",
    "patch_count",
    "feature_model",
    "feature_version",
    "reviewed_at",
    "exported_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a MIL/CLAM slide bag index from deep feature files."
    )
    parser.add_argument("--slide-labels", type=Path, default=DEFAULT_SLIDE_LABELS)
    parser.add_argument("--process-list", type=Path, default=DEFAULT_PROCESS_LIST)
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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


def cell(row: pd.Series, name: str) -> str:
    value = row.get(name, "")
    return "" if pd.isna(value) else str(value).strip()


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def one_value(frame: pd.DataFrame, column: str, slide_id: str) -> str:
    if column not in frame.columns:
        raise ValueError(f"{slide_id}: deep feature CSV has no {column} column.")
    values = {
        value
        for value in frame[column].fillna("").astype(str).str.strip()
        if value
    }
    if len(values) != 1:
        raise ValueError(
            f"{slide_id}: {column} must contain one non-empty value."
        )
    return next(iter(values))


def relative_output_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def warn_group_leakage(bags: pd.DataFrame, column: str) -> int:
    if column not in bags.columns:
        return 0
    warnings = 0
    populated = bags.copy()
    populated[column] = populated[column].fillna("").astype(str).str.strip()
    populated = populated.loc[populated[column].ne("")]
    for value, group in populated.groupby(column):
        if group["slide_id"].nunique() > 1:
            print(
                f"WARNING: {column}={value!r} spans "
                f"{group['slide_id'].nunique()} slides. Keep these slides in the "
                "same train/val/test split to avoid leakage."
            )
            warnings += 1
    return warnings


def main() -> int:
    args = parse_args()
    slide_labels_path = args.slide_labels.expanduser().resolve()
    process_list_path = args.process_list.expanduser().resolve()
    feature_csv_dir = args.feature_csv_dir.expanduser().resolve()
    feature_pt_dir = args.feature_pt_dir.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    try:
        labels = read_csv(
            slide_labels_path,
            {"slide_id", "case_id", "label", "source_wsi_name"},
        )
        process_list = read_csv(process_list_path, {"slide_id", "process"})
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if labels["slide_id"].fillna("").astype(str).str.strip().duplicated().any():
        print("ERROR: slide_labels.csv contains duplicate slide_id values.", file=sys.stderr)
        return 1

    enabled_slide_ids = set(
        process_list.loc[
            pd.to_numeric(process_list["process"], errors="coerce").fillna(0).eq(1),
            "slide_id",
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    rows: list[dict[str, Any]] = []
    warnings = 0
    errors = 0
    for _, label_row in labels.iterrows():
        slide_id = cell(label_row, "slide_id")
        if slide_id not in enabled_slide_ids:
            continue
        if truthy(label_row.get("exclude_from_training", False)):
            print(f"SKIP: {slide_id}: slide is excluded from training.")
            continue

        process_rows = process_list.loc[
            process_list["slide_id"].fillna("").astype(str).str.strip().eq(slide_id)
        ]
        if (
            not process_rows.empty
            and "exclude_from_training" in process_rows.columns
            and process_rows["exclude_from_training"].map(truthy).any()
        ):
            print(f"SKIP: {slide_id}: process list marks it excluded from training.")
            continue

        stem = safe_output_stem(slide_id)
        feature_csv_path = feature_csv_dir / f"{stem}.csv"
        feature_pt_path = feature_pt_dir / f"{stem}.pt"
        if not feature_csv_path.exists():
            print(f"WARNING: {slide_id}: deep feature CSV is missing; skipped.")
            warnings += 1
            continue

        try:
            features = read_csv(
                feature_csv_path,
                {"slide_id", "patch_id", "feature_model", "feature_version"},
            )
            if features.empty:
                raise ValueError("deep feature CSV has no patches.")
            feature_slide_ids = {
                value
                for value in features["slide_id"]
                .fillna("")
                .astype(str)
                .str.strip()
                if value
            }
            if feature_slide_ids != {slide_id}:
                raise ValueError(
                    f"deep feature CSV slide_id values are {sorted(feature_slide_ids)}."
                )
            feature_model = one_value(features, "feature_model", slide_id)
            feature_version = one_value(features, "feature_version", slide_id)
        except Exception as error:
            print(f"ERROR: {slide_id}: {error}", file=sys.stderr)
            errors += 1
            continue

        label = cell(label_row, "label") or "unknown"
        if label.lower() == "unknown":
            print(f"WARNING: {slide_id}: label is unknown.")
            warnings += 1

        rows.append(
            {
                "case_id": cell(label_row, "case_id") or slide_id,
                "slide_id": slide_id,
                "label": label,
                "source_wsi_name": cell(label_row, "source_wsi_name"),
                "patient_id_hash": cell(label_row, "patient_id_hash"),
                "specimen_id": cell(label_row, "specimen_id"),
                "feature_csv": relative_output_path(feature_csv_path),
                "feature_pt": (
                    relative_output_path(feature_pt_path)
                    if feature_pt_path.exists()
                    else ""
                ),
                "patch_count": len(features),
                "feature_model": feature_model,
                "feature_version": feature_version,
                "reviewed_at": cell(label_row, "reviewed_at"),
                "exported_at": cell(label_row, "exported_at"),
            }
        )

    bags = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if bags.empty:
        print("ERROR: No valid MIL bags were found.", file=sys.stderr)
        return 1

    warnings += warn_group_leakage(bags, "case_id")
    warnings += warn_group_leakage(bags, "patient_id_hash")
    bags = bags.sort_values(["case_id", "slide_id"], kind="stable")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bags.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(
        f"Wrote {len(bags)} MIL bag(s) to {output_path} "
        f"(warnings={warnings}, errors={errors})."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
