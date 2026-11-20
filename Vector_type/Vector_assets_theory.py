"""Theory prototype: project percentage-driven rotations from three views.

This deliberately does not modify Vector.py or Vector_assets.py and does not
move any input files. Input order is XZ | XY | YZ. The center uses the last,
YZ view as its dot/reference point. Signed row/column percentages drive the
intermediate orientations; the other anchors use their source views.
This is a 2D projection experiment, not a reconstructed solid.
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from PIL import Image


COLS = 5
ROWS = 5
# Approximate axis-angle offsets read from the hand-drawn 5x5 reference.
# Positive values lean down to the right in image coordinates. They are
# relative rotations for XZ-derived cells and periodic over 180°.
REFERENCE_AXIS_ANGLES_DEG = (
    (-54.7, -59.3, -90.0, 59.3, 54.7),
    (-28.1, -36.5, 90.0, 36.5, 28.1),
    (1.7, 8.3, 0.0, -8.3, -1.7),
    (28.1, 36.5, 90.0, -36.5, -28.1),
    (54.7, 59.3, -90.0, -59.3, -54.7),
)
INPUT_GUIDE_COLORS = {
    (136, 0, 21),    # X
    (255, 242, 0),   # Y
    (0, 162, 232),   # Z
}
MARKER_BLACK = (0, 0, 0)


def extract_view_sprite(input_path, view_index):
    """Take one frame from an XZ | XY | YZ PNG and remove guides/marker."""
    if view_index not in (0, 1, 2):
        raise ValueError("view_index must be 0 (XZ), 1 (XY), or 2 (YZ).")

    input_path = Path(input_path)
    with Image.open(input_path) as source:
        if source.format != "PNG":
            raise ValueError("Input must be a PNG image.")
        image = source.convert("RGBA")

    width, height = image.size
    if width <= 0 or height <= 0 or width % 3:
        raise ValueError("Expected three equal-width views in XZ | XY | YZ order.")
    frame_width = width // 3
    view = image.crop((view_index * frame_width, 0, (view_index + 1) * frame_width, height))
    pixels = [
        [view.getpixel((x, y)) for x in range(frame_width)]
        for y in range(height)
    ]

    has_transparency = any(pixel[3] == 0 for row in pixels for pixel in row)
    background = None
    if not has_transparency:
        border = (
            pixels[0]
            + pixels[-1]
            + [row[0] for row in pixels]
            + [row[-1] for row in pixels]
        )
        background = Counter(pixel[:3] for pixel in border).most_common(1)[0][0]

    for y, row in enumerate(pixels):
        for x, pixel in enumerate(row):
            is_background = pixel[3] == 0 or pixel[:3] in INPUT_GUIDE_COLORS
            if background is not None and pixel[:3] == background:
                is_background = True
            if is_background:
                view.putpixel((x, y), (0, 0, 0, 0))

    marker_size = min(
        max(1, (max(frame_width, height) + 16) // 32),
        frame_width,
        height,
    )
    marker = [
        pixels[y][x]
        for y in range(marker_size)
        for x in range(frame_width - marker_size, frame_width)
    ]
    if marker and all(
        pixel[3] > 0 and pixel[:3] == MARKER_BLACK for pixel in marker
    ):
        for y in range(marker_size):
            for x in range(frame_width - marker_size, frame_width):
                view.putpixel((x, y), (0, 0, 0, 0))

    return view


def extract_zx_sprite(input_path):
    """Backward-compatible helper for callers that only need the ZX view."""
    return extract_view_sprite(input_path, 0)


def grid_percentages(row, col):
    """Return signed vertical and horizontal percentages from ZX center."""
    center_row = (ROWS - 1) / 2
    center_col = (COLS - 1) / 2
    max_vertical = max(center_row, 1)
    max_horizontal = max(center_col, 1)
    vertical = (center_row - row) / max_vertical * 100
    horizontal = (col - center_col) / max_horizontal * 100
    return vertical, horizontal


def rotate_view_sprite(sprite, angle_deg):
    """Rotate a view with nearest-neighbor sampling and transparent fill."""
    nearest = getattr(Image, "Resampling", Image).NEAREST
    return sprite.rotate(
        angle_deg,
        resample=nearest,
        expand=False,
        fillcolor=(0, 0, 0, 0),
    )


def _interpolate_axis_angle(start_deg, end_deg, amount):
    """Interpolate undirected sprite axes along the shorter 180° arc."""
    delta = (end_deg - start_deg + 90) % 180 - 90
    return start_deg + delta * amount


def percentage_rotation(vertical_percent, horizontal_percent):
    """Map signed grid percentages to the hand-drawn reference orientation."""
    row_position = (100 - vertical_percent) / 50
    col_position = (horizontal_percent + 100) / 50
    row_position = min(max(row_position, 0.0), ROWS - 1)
    col_position = min(max(col_position, 0.0), COLS - 1)

    row0 = math.floor(row_position)
    col0 = math.floor(col_position)
    row1 = min(row0 + 1, ROWS - 1)
    col1 = min(col0 + 1, COLS - 1)
    row_fraction = row_position - row0
    col_fraction = col_position - col0

    top_angle = _interpolate_axis_angle(
        REFERENCE_AXIS_ANGLES_DEG[row0][col0],
        REFERENCE_AXIS_ANGLES_DEG[row0][col1],
        col_fraction,
    )
    bottom_angle = _interpolate_axis_angle(
        REFERENCE_AXIS_ANGLES_DEG[row1][col0],
        REFERENCE_AXIS_ANGLES_DEG[row1][col1],
        col_fraction,
    )
    target_axis = _interpolate_axis_angle(
        top_angle, bottom_angle, row_fraction
    )

    # Pillow's positive rotation is counter-clockwise. The reference angles
    # are measured in image coordinates, where positive Y points down.
    rotation = -target_axis
    return (rotation + 90) % 180 - 90


def center_sprite(sprite, view_name="sprite"):
    """Center opaque pixels in the frame without changing their pixel scale."""
    width, height = sprite.size
    alpha = sprite.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError(
            f"The {view_name} view has no visible asset pixels after filtering."
        )

    left, top, right, bottom = bounds
    source_center_x = (left + right - 1) / 2
    source_center_y = (top + bottom - 1) / 2
    target_center_x = (width - 1) / 2
    target_center_y = (height - 1) / 2

    def nearest_whole_pixel(value):
        return (
            math.floor(value + 0.5)
            if value >= 0
            else math.ceil(value - 0.5)
        )

    offset_x = nearest_whole_pixel(target_center_x - source_center_x)
    offset_y = nearest_whole_pixel(target_center_y - source_center_y)

    centered = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    source_left = max(0, -offset_x)
    source_top = max(0, -offset_y)
    target_left = max(0, offset_x)
    target_top = max(0, offset_y)
    copy_width = min(width - source_left, width - target_left)
    copy_height = min(height - source_top, height - target_top)
    if copy_width > 0 and copy_height > 0:
        cropped = sprite.crop((
            source_left,
            source_top,
            source_left + copy_width,
            source_top + copy_height,
        ))
        centered.alpha_composite(cropped, (target_left, target_top))

    metadata = {
        "method": "opaque-pixel-bounds",
        "source_bbox_inclusive_px": {
            "left": left,
            "top": top,
            "right": right - 1,
            "bottom": bottom - 1,
        },
        "applied_offset_px": {"x": offset_x, "y": offset_y},
        "offset_direction": "positive x moves right; positive y moves down",
    }
    return centered, metadata


def bitmap_rows(sprite):
    """Encode the centered alpha mask as one 0/1 string per image row."""
    width, height = sprite.size
    alpha = sprite.getchannel("A")
    return [
        "".join("1" if alpha.getpixel((x, y)) else "0" for x in range(width))
        for y in range(height)
    ]


def next_version_paths(output_dir):
    """Return the next unused V_01..V_100 PNG and center-JSON pair."""
    output_dir = Path(output_dir)
    for number in range(1, 101):
        stem = f"V_{number:02d}"
        image_path = output_dir / f"{stem}.png"
        metadata_path = output_dir / f"{stem}_center.json"
        if not image_path.exists() and not metadata_path.exists():
            return image_path, metadata_path
    raise ValueError("All test labels V_01 through V_100 are already in use.")


def create_theory_sheet(input_path, output_path=None):
    """Create a 5x5 sheet using the supplied XZ, XY, and YZ anchor views."""
    source_path = Path(input_path)
    views = {}
    centering = {}
    for view_index, view_name in enumerate(("XZ", "XY", "YZ")):
        extracted = extract_view_sprite(source_path, view_index)
        views[view_name], centering[view_name] = center_sprite(
            extracted, view_name
        )

    sprite = views["XZ"]
    width, height = sprite.size
    sheet = Image.new(
        "RGBA", (COLS * width, ROWS * height), (0, 0, 0, 0)
    )
    percentage_grid = []
    for row in range(ROWS):
        percentage_row = []
        for col in range(COLS):
            vertical_percent, horizontal_percent = grid_percentages(row, col)
            rotation_deg = percentage_rotation(
                vertical_percent, horizontal_percent
            )

            # The center is always a direct copy of the last input view (YZ),
            # which carries the dot/reference point for the whole sheet.
            if (row, col) == (2, 2):
                sheet.alpha_composite(views["YZ"], (2 * width, 2 * height))
                percentage_row.append({
                    "vertical_percent": round(vertical_percent, 2),
                    "horizontal_percent": round(horizontal_percent, 2),
                    "rotation_deg": 0.0,
                    "source_view": "YZ",
                })
                continue

            # Keep the five axis-defining positions straight. The other cells
            # rotate from the percentage offset around the ZX center.
            if (row, col) == (0, 2):
                source_name = "YZ"
                source_view, rotation_deg, flip_x, flip_y = views["YZ"], 0, False, False
            elif (row, col) == (4, 2):
                source_name = "YZ"
                source_view, rotation_deg, flip_x, flip_y = views["YZ"], 0, False, True
            elif (row, col) == (2, 0):
                source_name = "XY"
                source_view, rotation_deg, flip_x, flip_y = views["XY"], 0, True, False
            elif (row, col) == (2, 4):
                source_name = "XY"
                source_view, rotation_deg, flip_x, flip_y = views["XY"], 0, False, False
            else:
                source_name = "XZ"
                source_view, flip_x, flip_y = sprite, False, False

            transpose = getattr(Image, "Transpose", Image)
            if flip_x:
                source_view = source_view.transpose(transpose.FLIP_LEFT_RIGHT)
            if flip_y:
                source_view = source_view.transpose(transpose.FLIP_TOP_BOTTOM)
            view = rotate_view_sprite(source_view, rotation_deg)
            sheet.alpha_composite(view, (col * width, row * height))
            percentage_row.append({
                "vertical_percent": round(vertical_percent, 2),
                "horizontal_percent": round(horizontal_percent, 2),
                "rotation_deg": round(rotation_deg, 4),
                "source_view": source_name,
            })
        percentage_grid.append(percentage_row)

    if output_path is None:
        output_dir = Path(__file__).resolve().parent / "theory_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path, metadata_path = next_version_paths(output_dir)
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = output_path.with_name(f"{output_path.stem}_center.json")
        if output_path.exists() or metadata_path.exists():
            raise FileExistsError(
                f"Output pair already exists: {output_path.name} / {metadata_path.name}"
            )

    sheet.save(output_path, format="PNG")
    metadata = {
        "format_version": 8,
        "source_file": source_path.name,
        "source_view_order": ["XZ", "XY", "YZ"],
        "centered_sprite_size_px": {"width": width, "height": height},
        "centering": centering,
        "percentage_model": {
            "vertical_axis_change": "X -> Y; top is positive, bottom is negative",
            "horizontal_axis_change": "Z -> X; left is negative, right is positive",
            "reference_axis_angles_deg": [
                list(row) for row in REFERENCE_AXIS_ANGLES_DEG
            ],
            "center_view": "last input view: YZ (dot/reference point)",
            "center_copy_mode": "direct centered YZ sprite; no rotation or flip",
            "side_and_bottom_anchors_stay_upright": True,
            "interpolation": "signed row/column percentages interpolate 180-degree-periodic relative axis-angle offsets calibrated from the hand-drawn 5x5 reference; the five axis anchors use their source views directly",
            "cells": percentage_grid,
        },
        "anchors": {
            "center": {"cell_row": 3, "cell_col": 3, "source_view": "YZ", "input_position": "third (last)", "role": "dot/reference point"},
            "top": {"cell_row": 1, "cell_col": 3, "source_view": "YZ", "horizontal_flip": False, "vertical_flip": False},
            "bottom": {"cell_row": 5, "cell_col": 3, "source_view": "YZ", "horizontal_flip": False, "vertical_flip": True},
            "left": {"cell_row": 3, "cell_col": 1, "source_view": "XY", "horizontal_flip": True, "vertical_flip": False},
            "right": {"cell_row": 3, "cell_col": 5, "source_view": "XY", "horizontal_flip": False, "vertical_flip": False},
        },
        "views": {
            name: {
                "encoding": "one string per row; 1=visible pixel, 0=transparent",
                "width": width,
                "height": height,
                "rows": bitmap_rows(view),
            }
            for name, view in views.items()
        },
    }
    with metadata_path.open("x", encoding="utf-8", newline="\n") as metadata_file:
        json.dump(metadata, metadata_file, ensure_ascii=False, indent=2)
        metadata_file.write("\n")

    print(f"Created percentage-interpolated three-view sheet: {output_path}")
    print(f"Created centering data and bitmap: {metadata_path}")
    return output_path, metadata_path


def main():
    parser = argparse.ArgumentParser(
        description="Create a theoretical 5x5 sheet from XZ | XY | YZ views."
    )
    parser.add_argument("input", type=Path, help="checked XZ | XY | YZ PNG")
    parser.add_argument("--output", type=Path, help="output PNG path")
    args = parser.parse_args()
    try:
        create_theory_sheet(args.input, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
