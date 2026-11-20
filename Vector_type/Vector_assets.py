"""Build 5x5 projected-sprite PNGs from checked three-view source assets.

Input layout follows the project convention: YX | YZ | ZX in one horizontal
strip. The source frame dimensions set each output cell's size. Originals move
from checked/ to assets/ after a successful export.
"""

import argparse
from collections import Counter
from datetime import datetime
import math
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_DIR / "checked"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "assets"
FILE_LIST_PATH = PROJECT_DIR / "FILE_LIST.txt"
VIEW_ORDER = "YX | YZ | ZX"
COLS = 5
ROWS = 5
YAW_RANGE = (-90, 90)
PITCH_RANGE = (-45, 45)
INPUT_GUIDE_COLORS = {
    (136, 0, 21),    # X
    (255, 242, 0),   # Y
    (0, 162, 232),   # Z
}


def record_file_action(action, *paths):
    """Append source/output paths to the shared project file history."""
    try:
        needs_header = not FILE_LIST_PATH.exists() or FILE_LIST_PATH.stat().st_size == 0
        with FILE_LIST_PATH.open("a", encoding="utf-8", newline="") as history:
            if needs_header:
                history.write("TIME\tACTION\tPATH_1\tPATH_2\tPATH_3\tPATH_4\n")
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            resolved_paths = [str(Path(path).resolve()) if path else "" for path in paths]
            resolved_paths = (resolved_paths + [""] * 4)[:4]
            history.write(
                f"{timestamp}\t{action}\t" + "\t".join(resolved_paths) + "\n"
            )
    except OSError as error:
        print(f"Warning: could not update {FILE_LIST_PATH.name}: {error}")


def unique_output_path(output_dir, source_stem):
    """Choose an unused PNG name so a previous projection map is preserved."""
    candidate = output_dir / f"{source_stem}_vector.png"
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{source_stem}_vector_{suffix}.png"
        suffix += 1
    return candidate


def source_view_mask(image, frame, frame_width, frame_height):
    """Read one view as a silhouette, excluding known guide colors and frame dot."""
    left = frame * frame_width
    pixels = [
        [image.getpixel((left + x, y)) for x in range(frame_width)]
        for y in range(frame_height)
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

    mask = []
    for row in pixels:
        mask.append([
            pixel[3] > 0
            and pixel[:3] not in INPUT_GUIDE_COLORS
            and (background is None or pixel[:3] != background)
            for pixel in row
        ])

    marker_size = min(max(1, (max(frame_width, frame_height) + 16) // 32),
                      frame_width, frame_height)
    marker_pixels = [
        pixels[y][x]
        for y in range(marker_size)
        for x in range(frame_width - marker_size, frame_width)
    ]
    if marker_pixels and all(
        pixel[3] > 0 and pixel[:3] == (0, 0, 0) for pixel in marker_pixels
    ):
        for y in range(marker_size):
            for x in range(frame_width - marker_size, frame_width):
                mask[y][x] = False

    return mask


def build_visual_hull(image, frame_width, frame_height):
    """Intersect the three orthographic silhouettes into an approximate volume."""
    view_yx = source_view_mask(image, 0, frame_width, frame_height)
    view_yz_source = source_view_mask(image, 1, frame_width, frame_height)
    view_zx = source_view_mask(image, 2, frame_width, frame_height)

    # Z is vertical in ZX and horizontal in YZ. In this convention +Z points
    # up in ZX and right in YZ, so the corresponding YZ column is reversed.
    # Resample that axis to the ZX voxel count when a frame is rectangular.
    z_size = frame_height
    view_yz = []
    for y in range(frame_height):
        row = []
        for z in range(z_size):
            source_z = (
                round((z_size - 1 - z) * (frame_width - 1) / (z_size - 1))
                if z_size > 1 and frame_width > 1 else 0
            )
            row.append(view_yz_source[y][source_z])
        view_yz.append(row)

    occupied = []
    for z in range(z_size):
        for y in range(frame_height):
            if not view_yz[y][z]:
                continue
            for x in range(frame_width):
                if view_yx[y][x] and view_zx[z][x]:
                    occupied.append((x, y, z))
    if not occupied:
        raise ValueError(
            "The three views do not overlap at their supplied axis coordinates. "
            "No pixels were shifted; the source remains in checked/."
        )
    return occupied, frame_width, frame_height, z_size


def convex_hull(points):
    """Return the 2D convex hull of a small set of projected voxel corners."""
    points = sorted(set(points))
    if len(points) <= 2:
        return points

    def cross(origin, first, second):
        return ((first[0] - origin[0]) * (second[1] - origin[1])
                - (first[1] - origin[1]) * (second[0] - origin[0]))

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def rotate_project(point, yaw, pitch):
    """Rotate a world point; +X is screen-right and +Y is screen-up."""
    world_x, world_y, world_z = point
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    cos_pitch, sin_pitch = math.cos(pitch), math.sin(pitch)

    rotated_x = cos_yaw * world_x + sin_yaw * world_z
    rotated_z = -sin_yaw * world_x + cos_yaw * world_z
    rotated_y = cos_pitch * world_y - sin_pitch * rotated_z
    # Screen Y grows down, while world +Y points up. Keep X unmirrored so the
    # zero-angle projection preserves the source YX view's left/right layout.
    return rotated_x, -rotated_y


def voxel_corners(x, y, z, frame_width, frame_height, z_size, scale_unit):
    """Return corners of one voxel in centered world coordinates."""
    center_x = x - (frame_width - 1) / 2
    center_y = (frame_height - 1) / 2 - y
    center_z = (z_size - 1) / 2 - z
    half = 0.5
    return [
        ((center_x + dx * half) / scale_unit,
         (center_y + dy * half) / scale_unit,
         (center_z + dz * half) / scale_unit)
        for dx in (-1, 1)
        for dy in (-1, 1)
        for dz in (-1, 1)
    ]


def draw_volume_projection(draw, cell_left, cell_top, frame_width, frame_height,
                           occupied, yaw_deg, pitch_deg):
    """Project the occupied voxels into one cell as a solid black silhouette."""
    occupied_set = set(occupied)
    surface_voxels = []
    for x, y, z in occupied:
        if any(neighbor not in occupied_set for neighbor in (
            (x - 1, y, z), (x + 1, y, z), (x, y - 1, z), (x, y + 1, z),
            (x, y, z - 1), (x, y, z + 1),
        )):
            surface_voxels.append((x, y, z))

    scale_unit = max(frame_width, frame_height)
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    projected_hulls = []
    for x, y, z in surface_voxels:
        projected = [
            rotate_project(point, yaw, pitch)
            for point in voxel_corners(
                x, y, z, frame_width, frame_height, frame_height, scale_unit
            )
        ]
        hull = convex_hull(projected)
        if hull:
            projected_hulls.append(hull)

    all_points = [point for hull in projected_hulls for point in hull]
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    available_width = max(1, frame_width - 2)
    available_height = max(1, frame_height - 2)
    range_x = max_x - min_x
    range_y = max_y - min_y
    fit_x = available_width / range_x if range_x > 1e-9 else float("inf")
    fit_y = available_height / range_y if range_y > 1e-9 else float("inf")
    # Keep the source pixel scale whenever the projection fits. Only shrink a
    # view if its rotated silhouette would otherwise be clipped by the cell.
    fit_scale = min(scale_unit, fit_x, fit_y)
    center_x = cell_left + (frame_width - 1) / 2
    center_y = cell_top + (frame_height - 1) / 2
    midpoint_x = (min_x + max_x) / 2
    midpoint_y = (min_y + max_y) / 2

    for hull in projected_hulls:
        polygon = [
            (
                round(center_x + (x - midpoint_x) * fit_scale),
                round(center_y + (y - midpoint_y) * fit_scale),
            )
            for x, y in hull
        ]
        if len(polygon) >= 3:
            draw.polygon(polygon, fill=(0, 0, 0, 255))
        elif polygon:
            x, y = polygon[0]
            draw.point((x, y), fill=(0, 0, 0, 255))


def convert_png_to_projection(input_path, output_dir):
    """Project a silhouette volume built from a checked YX|YZ|ZX source."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    with Image.open(input_path) as source:
        if source.format != "PNG":
            raise ValueError("Input must be a PNG image.")
        image = source.convert("RGBA")

    width, frame_height = image.size
    if width <= 0 or frame_height <= 0 or width % 3 != 0:
        raise ValueError(
            "Expected one horizontal strip of three equal-width views: "
            "YX | YZ | ZX."
        )
    frame_width = width // 3
    if frame_width <= 0:
        raise ValueError("Each source view must be at least one pixel wide.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, input_path.stem)
    occupied, frame_width, frame_height, _ = build_visual_hull(
        image, frame_width, frame_height
    )
    projection_sheet = Image.new(
        "RGBA", (COLS * frame_width, ROWS * frame_height), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(projection_sheet)
    yaw_min, yaw_max = YAW_RANGE
    pitch_min, pitch_max = PITCH_RANGE
    for row in range(ROWS):
        pitch = (
            pitch_max - row * (pitch_max - pitch_min) / (ROWS - 1)
            if ROWS > 1 else 0
        )
        for col in range(COLS):
            yaw = (
                yaw_min + col * (yaw_max - yaw_min) / (COLS - 1)
                if COLS > 1 else 0
            )
            draw_volume_projection(
                draw, col * frame_width, row * frame_height,
                frame_width, frame_height, occupied, yaw, pitch,
            )

    projection_sheet.save(output_path, format="PNG")
    return output_path


def unique_source_path(output_dir, filename):
    """Choose an unused destination for the original PNG."""
    path = Path(filename)
    candidate = output_dir / path.name
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{path.stem}_{suffix}{path.suffix}"
        suffix += 1
    return candidate


def convert_folder(input_dir=DEFAULT_INPUT_DIR, output_dir=DEFAULT_OUTPUT_DIR):
    """Vectorize ordinary PNGs, then move each successful source into assets/."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder does not exist: {input_dir}")
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("Input and assets folders must be different.")

    inputs = sorted(
        (
            path for path in input_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".png"
            and not path.stem.casefold().endswith("_checked")
        ),
        key=lambda path: path.name.casefold(),
    )
    if not inputs:
        print(f"No ordinary PNG files found in: {input_dir}")
        return 0, 0

    converted = 0
    failed = 0
    for input_path in inputs:
        projection_path = None
        try:
            projection_path = convert_png_to_projection(input_path, output_dir)
            asset_source = unique_source_path(output_dir, input_path.name)
            input_path.rename(asset_source)
            record_file_action("ASSET_VECTOR", input_path, asset_source, projection_path)
            converted += 1
            print(f"Vector projection PNG: {projection_path}")
            print(f"Original moved to assets: {asset_source}")
        except Exception as error:
            if projection_path is not None and projection_path.exists() and input_path.exists():
                try:
                    projection_path.unlink()
                except OSError as cleanup_error:
                    print(
                        f"Could not remove incomplete output {projection_path}: "
                        f"{cleanup_error}"
                    )
            failed += 1
            print(f"Skipped {input_path.name}: {type(error).__name__}: {error}")
    print(f"Asset vector export complete: {converted} created, {failed} skipped.")
    return converted, failed


def main():
    parser = argparse.ArgumentParser(
        description=f"Create 5x5 vector projection PNGs from source views ({VIEW_ORDER})."
    )
    parser.add_argument(
        "--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
        help="folder with ordinary source PNGs (default: checked/)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="assets folder for projection PNGs and moved originals (default: assets/)",
    )
    args = parser.parse_args()
    try:
        _, failed = convert_folder(args.input_dir, args.output_dir)
    except Exception as error:
        print(f"Asset vector export could not start: {type(error).__name__}: {error}")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
