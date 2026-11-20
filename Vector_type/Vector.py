import argparse
import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

SPRITE_SIZE = 128
COLS = 5
ROWS = 5
MIN_SPRITE_SIZE = 16
MAX_SPRITE_SIZE = 512
MIN_GRID_DIMENSION = 1
MAX_GRID_DIMENSION = 100
MAX_GRID_CELLS = 100
YAW_RANGE = (-90, 90)
PITCH_RANGE = (-45, 45)

COLOR_GREEN = (0, 255, 0, 255)
COLOR_RED = (255, 0, 0, 255)
COLOR_LINE_GREEN = (0, 120, 0, 255)
COLOR_LINE_RED = (120, 0, 0, 255)
COLOR_BLUE = (0, 0, 255, 255)
COLOR_BLACK_PIXEL = (0, 0, 0, 255)

def visual_scale(size):
    """Match line and marker scaling documented for the project's sprites."""
    return max(1, (size + 16) // 32)


def unique_output_path(filename):
    """Keep earlier generated sheets instead of overwriting them."""
    path = Path(filename)
    candidate = path
    suffix = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{suffix}{path.suffix}")
        suffix += 1
    return candidate


def record_generated_file(path):
    """Add generated sheets to the project file history."""
    ledger = Path(__file__).resolve().with_name("FILE_LIST.txt")
    try:
        needs_header = not ledger.exists() or ledger.stat().st_size == 0
        with ledger.open("a", encoding="utf-8", newline="") as history:
            if needs_header:
                history.write("TIME\tACTION\tPATH_1\tPATH_2\tPATH_3\tPATH_4\n")
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            history.write(
                f"{timestamp}\tVECTOR_HEAD\t{Path(path).resolve()}\t\t\t\n"
            )
    except OSError as error:
        print(f"Warning: could not update {ledger.name}: {error}")


def blend_pixel(image, draw, x, y, new_color, size):
    if not (0 <= x < size and 0 <= y < size):
        return

    current_color = image.getpixel((x, y))
    if current_color[3] != 0:
        r_cur, g_cur, b_cur, _ = current_color
        r_new, g_new, b_new, _ = new_color
        draw.point((x, y), fill=(min(255, r_cur + r_new),
                                 min(255, g_cur + g_new),
                                 min(255, b_cur + b_new), 255))
    else:
        draw.point((x, y), fill=new_color)


def draw_dot_block(image, draw, start_x, start_y, color, size):
    dot_size = visual_scale(size)
    for dx in range(dot_size):
        for dy in range(dot_size):
            blend_pixel(image, draw, start_x + dx, start_y + dy, color, size)


def draw_straight_line(image, draw, x0, y0, x1, y1, color, size):
    x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
    line_width = visual_scale(size)
    if x0 == x1:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for dx in range(line_width):
                blend_pixel(image, draw, x0 + dx, y, color, size)
    elif y0 == y1:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for dy in range(line_width):
                blend_pixel(image, draw, x, y0 + dy, color, size)


def draw_vector_sprite(yaw_deg, pitch_deg, size):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    cx, cy = size // 2, size // 2
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    dir_x = math.sin(yaw) * math.cos(pitch)
    dir_y = -math.sin(pitch)

    line_scale = visual_scale(size)
    head_radius = max(1, int(size * 0.375))
    offset_scale = size * 0.28
    head_cx = cx + dir_x * (size * 0.06)
    head_cy = cy + dir_y * (size * 0.06)

    for px in range(size):
        for py in range(size):
            dx = px - head_cx
            dy = py - head_cy
            distance = math.sqrt(dx * dx + dy * dy)
            if abs(distance - head_radius) < max(0.5, line_scale / 2):
                blend_pixel(image, draw, px, py, COLOR_BLUE, size)

    left_wall = round(head_cx - head_radius)
    right_wall = round(head_cx + head_radius)
    top_wall = round(head_cy - head_radius)
    bottom_wall = round(head_cy + head_radius)

    green_x = round(head_cx)
    green_y = round(head_cy)
    draw_dot_block(image, draw, green_x, green_y, COLOR_GREEN, size)
    draw_straight_line(image, draw, green_x, green_y, green_x, top_wall, COLOR_LINE_GREEN, size)
    draw_straight_line(image, draw, green_x, green_y, left_wall, green_y, COLOR_LINE_GREEN, size)

    red_x = round(head_cx + dir_x * offset_scale)
    red_y = round(head_cy + dir_y * offset_scale)
    draw_dot_block(image, draw, red_x, red_y, COLOR_RED, size)
    draw_straight_line(image, draw, red_x, red_y, red_x, bottom_wall, COLOR_LINE_RED, size)
    draw_straight_line(image, draw, red_x, red_y, right_wall, red_y, COLOR_LINE_RED, size)

    max_index = size - 1
    marker_points = (
        (size // 2, 0), (0, 0), (0, max_index),
        (max_index, 0), (max_index, max_index),
    )
    for marker_x, marker_y in marker_points:
        marker_x = max(0, min(size - line_scale, marker_x - line_scale // 2))
        marker_y = max(0, min(size - line_scale, marker_y - line_scale // 2))
        draw_dot_block(
            image, draw, marker_x, marker_y, COLOR_BLACK_PIXEL, size
        )
    return image


def grid_angles(rows, cols):
    yaw_min, yaw_max = YAW_RANGE
    pitch_min, pitch_max = PITCH_RANGE
    for row in range(rows):
        pitch = pitch_min + (row / (rows - 1)) * (pitch_max - pitch_min) if rows > 1 else 0
        for col in range(cols):
            yaw = yaw_min + (col / (cols - 1)) * (yaw_max - yaw_min) if cols > 1 else 0
            yield yaw, pitch


def prompt_sprite_size(default=SPRITE_SIZE):
    """Ask for a square sprite size; C cancels and Enter keeps the default."""
    while True:
        raw_size = input(
            f"Sprite size in pixels ({MIN_SPRITE_SIZE}-{MAX_SPRITE_SIZE}, "
            f"Enter for {default}, C cancels): "
        ).strip()
        if raw_size.casefold() == "c":
            return None
        if not raw_size:
            return default
        try:
            sprite_size = int(raw_size)
        except ValueError:
            print("Enter a whole number, for example 64.")
            continue
        if MIN_SPRITE_SIZE <= sprite_size <= MAX_SPRITE_SIZE:
            return sprite_size
        print(
            f"Sprite size must be between {MIN_SPRITE_SIZE} and "
            f"{MAX_SPRITE_SIZE} pixels."
        )


def generate_sheet(sprite_size=None, cols=COLS, rows=ROWS):
    """Create one grid of the same head sprite at different angles."""
    if sprite_size is None:
        sprite_size = prompt_sprite_size()
        if sprite_size is None:
            print("Vector head generation cancelled.")
            return None
    if not MIN_GRID_DIMENSION <= cols <= MAX_GRID_DIMENSION:
        raise ValueError(
            f"Columns must be between {MIN_GRID_DIMENSION} and {MAX_GRID_DIMENSION}."
        )
    if not MIN_GRID_DIMENSION <= rows <= MAX_GRID_DIMENSION:
        raise ValueError(
            f"Rows must be between {MIN_GRID_DIMENSION} and {MAX_GRID_DIMENSION}."
        )
    if cols * rows > MAX_GRID_CELLS:
        raise ValueError(f"The grid can contain at most {MAX_GRID_CELLS} sprites.")

    sheet = Image.new(
        "RGBA", (cols * sprite_size, rows * sprite_size), (0, 0, 0, 0)
    )
    for index, (yaw, pitch) in enumerate(grid_angles(rows, cols)):
        col = index % cols
        row = index // cols
        sprite = draw_vector_sprite(yaw, pitch, sprite_size)
        sheet.paste(sprite, (col * sprite_size, row * sprite_size), sprite)

    filename = f"Vector_type_C{cols}R{rows}S{sprite_size}.png"
    output_path = unique_output_path(Path(__file__).resolve().parent / filename)
    sheet.save(output_path, format="PNG")
    record_generated_file(output_path)
    print(f"Generated one vector-head sheet: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate one vector-head sprite grid.")
    parser.add_argument(
        "--size", type=int,
        help=f"square sprite size in pixels ({MIN_SPRITE_SIZE}-{MAX_SPRITE_SIZE})",
    )
    parser.add_argument(
        "--cols", type=int, default=COLS,
        help=f"number of columns ({MIN_GRID_DIMENSION}-{MAX_GRID_DIMENSION}; default: {COLS})",
    )
    parser.add_argument(
        "--rows", type=int, default=ROWS,
        help=f"number of rows ({MIN_GRID_DIMENSION}-{MAX_GRID_DIMENSION}; default: {ROWS})",
    )
    args = parser.parse_args()
    sprite_size = args.size if args.size is not None else prompt_sprite_size()
    if sprite_size is None:
        print("Vector head generation cancelled.")
        return 0
    if not MIN_SPRITE_SIZE <= sprite_size <= MAX_SPRITE_SIZE:
        parser.error(
            f"sprite size must be between {MIN_SPRITE_SIZE} and {MAX_SPRITE_SIZE} pixels"
        )
    if not MIN_GRID_DIMENSION <= args.cols <= MAX_GRID_DIMENSION:
        parser.error(
            f"columns must be between {MIN_GRID_DIMENSION} and {MAX_GRID_DIMENSION}"
        )
    if not MIN_GRID_DIMENSION <= args.rows <= MAX_GRID_DIMENSION:
        parser.error(
            f"rows must be between {MIN_GRID_DIMENSION} and {MAX_GRID_DIMENSION}"
        )
    if args.cols * args.rows > MAX_GRID_CELLS:
        parser.error(f"the grid can contain at most {MAX_GRID_CELLS} sprites")
    generate_sheet(sprite_size, args.cols, args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
