"""Stage 4: build the center cross from YX | YZ | XZ input views."""

import argparse
from collections import Counter
import math
from pathlib import Path

from PIL import Image, ImageDraw


GRID_SIZE = 5
CENTER_INDEX = GRID_SIZE // 2
GRID_LAYOUT = (
    "PPBPP",
    "PPVPP",
    "AHCHA",
    "PPVPP",
    "PPBPP",
)
VIEW_GUIDE_COLORS = {
    (136, 0, 21),   # X guide
    (255, 242, 0),  # Y guide
    (0, 162, 232),  # Z guide
}
MARKER_BLACK = (0, 0, 0)


def load_view(input_path, view_index):
    """Load and center one frame from the YX | YZ | XZ input strip."""
    if view_index not in (0, 1, 2):
        raise ValueError("view_index must be 0 (YX), 1 (YZ), or 2 (XZ).")

    input_path = Path(input_path)
    with Image.open(input_path) as source:
        if source.format != "PNG":
            raise ValueError("Input must be a PNG image.")
        image = source.convert("RGBA")

    width, height = image.size
    if width <= 0 or height <= 0 or width % 3:
        raise ValueError("Expected three equal-width views in YX | YZ | XZ order.")

    frame_width = width // 3
    view_names = ("YX", "YZ", "XZ")
    view_positions = ("first", "second", "third (last)")
    view_name = view_names[view_index]
    view = image.crop((
        view_index * frame_width,
        0,
        (view_index + 1) * frame_width,
        height,
    ))
    pixels = [
        [view.getpixel((x, y)) for x in range(frame_width)]
        for y in range(height)
    ]

    has_transparency = any(
        pixel[3] == 0 for row in pixels for pixel in row
    )
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
            is_background = pixel[3] == 0 or pixel[:3] in VIEW_GUIDE_COLORS
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

    bounds = view.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"The {view_name} view has no visible pixels after cleanup.")

    left, top, right, bottom = bounds
    def nearest_whole_pixel(value):
        return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)

    offset_x = nearest_whole_pixel(
        (frame_width - 1) / 2 - (left + right - 1) / 2
    )
    offset_y = nearest_whole_pixel(
        (height - 1) / 2 - (top + bottom - 1) / 2
    )

    centered_view = Image.new(
        "RGBA", (frame_width, height), (0, 0, 0, 0)
    )
    source_left = max(0, -offset_x)
    source_top = max(0, -offset_y)
    target_left = max(0, offset_x)
    target_top = max(0, offset_y)
    copy_width = min(frame_width - source_left, frame_width - target_left)
    copy_height = min(height - source_top, height - target_top)
    if copy_width > 0 and copy_height > 0:
        crop = view.crop((
            source_left,
            source_top,
            source_left + copy_width,
            source_top + copy_height,
        ))
        centered_view.alpha_composite(crop, (target_left, target_top))

    return centered_view, {
        "source_view": view_name,
        "source_position": view_positions[view_index],
        "source_bounds_inclusive_px": {
            "left": left,
            "top": top,
            "right": right - 1,
            "bottom": bottom - 1,
        },
        "centering_offset_px": {"x": offset_x, "y": offset_y},
    }


def rotate_in_image_plane(sprite, angle_degrees):
    """Rotate within the sprite cell; positive Pillow angles turn left."""
    nearest = getattr(Image, "Resampling", Image).NEAREST
    return sprite.rotate(
        angle_degrees,
        resample=nearest,
        expand=False,
        fillcolor=(0, 0, 0, 0),
    )


def fit_square_cell(sprite, cell_size):
    """Center a view in a square cell without resizing or changing its ratio."""
    cell = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    x = (cell_size - sprite.width) // 2
    y = (cell_size - sprite.height) // 2
    cell.alpha_composite(sprite, (x, y))
    return cell


def skip_sprite(sprite_code):
    """Return True for an empty cell marked with P in GRID_LAYOUT."""
    return sprite_code == "P"


def build_centered_volume(yx_view, yz_view, xz_view):
    """Intersect centered silhouettes; X/Z span the center view's columns/rows."""
    size = xz_view.width
    yx = yx_view.getchannel("A")
    yz = yz_view.getchannel("A")
    xz = xz_view.getchannel("A")
    center = (size - 1) / 2
    volume = []
    for z in range(size):
        for y in range(size):
            # +Z is up in the center view and right in the YZ source.
            if not yz.getpixel((size - 1 - z, y)):
                continue
            for x in range(size):
                if yx.getpixel((x, y)) and xz.getpixel((x, z)):
                    volume.append((x - center, center - y, center - z))
    if not volume:
        raise ValueError("Centered silhouettes have no common 3D volume.")
    occupied = set(volume)
    return [
        point for point in volume
        if any(
            tuple(point[i] + offset[i] for i in range(3)) not in occupied
            for offset in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                           (0, -1, 0), (0, 0, 1), (0, 0, -1))
        )
    ]


def cross_product(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def normalized(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return tuple(value / length for value in vector)


def intermediate_camera(source_code):
    """Aim halfway (45 degrees) from the center camera to a source camera."""
    # Each pair contains screen-right and screen-down world vectors.
    center_right, center_down = (1, 0, 0), (0, 0, -1)
    source_right, source_down = {
        "A": ((1, 0, 0), (0, -1, 0)),
        "B": ((0, 0, 1), (0, -1, 0)),
    }[source_code]
    center_normal = cross_product(center_right, center_down)
    source_normal = cross_product(source_right, source_down)
    normal = normalized(tuple(a + b for a, b in zip(center_normal, source_normal)))
    right_hint = tuple(a + b for a, b in zip(center_right, source_right))
    along_normal = sum(a * b for a, b in zip(right_hint, normal))
    right = normalized(tuple(a - along_normal * b for a, b in zip(right_hint, normal)))
    return right, cross_product(normal, right)


def project_intermediate(volume, cell_size, source_code, roll_degrees):
    """Rasterize voxel faces at 45 degrees, with roll toward the existing anchor."""
    right, down = intermediate_camera(source_code)
    roll = math.radians(roll_degrees)
    cos_roll, sin_roll = math.cos(roll), math.sin(roll)
    center = (cell_size - 1) / 2

    def project(point):
        u = sum(a * b for a, b in zip(point, right))
        v = sum(a * b for a, b in zip(point, down))
        return (center + cos_roll * u + sin_roll * v,
                center - sin_roll * u + cos_roll * v)

    sprite = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    # Drawing all six faces gives the solid silhouette without connecting
    # separate voxels or filling concavities with one global convex hull.
    for voxel in volume:
        for fixed_axis in range(3):
            free_axes = [axis for axis in range(3) if axis != fixed_axis]
            for side in (-0.5, 0.5):
                polygon = []
                for first, second in ((-0.5, -0.5), (0.5, -0.5),
                                      (0.5, 0.5), (-0.5, 0.5)):
                    corner = list(voxel)
                    corner[fixed_axis] += side
                    corner[free_axes[0]] += first
                    corner[free_axes[1]] += second
                    polygon.append(tuple(round(value) for value in project(corner)))
                draw.polygon(polygon, fill=(0, 0, 0, 255))
    return sprite


def create_cross_stage(input_path, output_path):
    """Fill the 5x5 sheet by iterating columns and spans."""
    yx_view, yx_details = load_view(input_path, 0)
    yz_view, yz_details = load_view(input_path, 1)
    xz_view, xz_details = load_view(input_path, 2)
    cell_size = max(
        yx_view.width, yx_view.height,
        yz_view.width, yz_view.height,
        xz_view.width, xz_view.height,
    )
    views = {
        "A": fit_square_cell(yx_view, cell_size),
        "B": fit_square_cell(yz_view, cell_size),
        "C": fit_square_cell(xz_view, cell_size),
    }
    volume = build_centered_volume(views["A"], views["B"], views["C"])
    sheet = Image.new(
        "RGBA",
        (GRID_SIZE * cell_size, GRID_SIZE * cell_size),
        (0, 0, 0, 0),
    )

    # Walk each column, then each span (row). P cells stay transparent.
    for col in range(GRID_SIZE):
        for span in range(GRID_SIZE):
            sprite_code = GRID_LAYOUT[span][col]
            if skip_sprite(sprite_code):
                continue

            if sprite_code in ("H", "V"):
                if sprite_code == "H":
                    source_code = "A"
                    roll = 45 if col < CENTER_INDEX else -45
                else:
                    source_code = "B"
                    roll = 0 if span < CENTER_INDEX else 90
                view = project_intermediate(volume, cell_size, source_code, roll)
                sheet.alpha_composite(view, (col * cell_size, span * cell_size))
                continue

            view = views[sprite_code]
            angle = 0
            if sprite_code == "A":
                angle = 90 if col < CENTER_INDEX else -90
            elif sprite_code == "B":
                if span > CENTER_INDEX:
                    angle = 180

            if angle:
                view = rotate_in_image_plane(view, angle)

            sheet.alpha_composite(
                view,
                (col * cell_size, span * cell_size),
            )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG")
    print(
        f"Created grid from layout {GRID_LAYOUT}: A=YX, B=YZ, C=XZ; "
        f"H/V=intermediate 3D projections; "
        f"{output_path} ({sheet.width}x{sheet.height}; other cells are transparent)."
    )
    print(f"Left YX source bounds: {yx_details['source_bounds_inclusive_px']}")
    print(f"Center YZ source bounds: {yz_details['source_bounds_inclusive_px']}")
    print(f"Right XZ source bounds: {xz_details['source_bounds_inclusive_px']}")
    return output_path


def main():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Stage 4: build the center cross from input ordered YX | YZ | XZ."
    )
    parser.add_argument("input", type=Path, help="PNG strip ordered YX | YZ | XZ")
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "stage_04_center_cross.png",
        help="output PNG path",
    )
    args = parser.parse_args()
    try:
        create_cross_stage(args.input, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
