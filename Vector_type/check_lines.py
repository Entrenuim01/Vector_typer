"""Check the YX | YZ | ZX sprite strip and draw alignment guides."""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import tempfile

from PIL import Image, ImageDraw


VIEW_ORDER = ("YX", "YZ", "ZX")

# Guide colors in the input file M1: X=red, Y=yellow, Z=cyan-blue.
INPUT_AXIS_COLOR = {
    "X": (136, 0, 21),
    "Y": (255, 242, 0),
    "Z": (0, 162, 232),
}

# Result colors match the palette in Pokaz_V1_001.png.
COLOR_AXIS_OK = {
    "X": (163, 73, 164, 255),  # purple: valid X
    "Y": (34, 177, 76, 255),   # green: valid Y
    "Z": (0, 162, 232, 255),  # cyan: valid Z
}
COLOR_ERROR = (237, 28, 36, 255)
COLOR_CORRECTION = (0, 0, 255, 255)
COLOR_CENTER = (255, 242, 0, 255)
COLOR_BLACK_PIXEL = (0, 0, 0, 255)
DROP_BASE = (181, 230, 29)
DROP_GREEN_STEP = 6
CENTER_TOLERANCE = 1
MAX_FRAME_DIMENSION = 2048
FILE_LIST_PATH = Path(__file__).resolve().with_name("FILE_LIST.txt")


def record_file_action(action, *paths):
    """Append file moves and generated outputs to the human-readable ledger."""
    try:
        needs_header = not FILE_LIST_PATH.exists() or FILE_LIST_PATH.stat().st_size == 0
        with FILE_LIST_PATH.open("a", encoding="utf-8", newline="") as file_list:
            if needs_header:
                file_list.write("TIME\tACTION\tPATH_1\tPATH_2\tPATH_3\tPATH_4\n")
            resolved_paths = [
                str(Path(path).resolve()) if path else ""
                for path in paths
            ]
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            resolved_paths = (resolved_paths + [""] * 4)[:4]
            file_list.write(
                f"{timestamp}\t{action}\t" + "\t".join(resolved_paths) + "\n"
            )
    except OSError as error:
        print(f"Warning: could not update {FILE_LIST_PATH.name}: {error}")


@dataclass(frozen=True)
class Segment:
    frame: int
    axis: str
    orientation: str
    start: int
    end: int
    cross: int
    from_guide: bool
    thickness: int = 1

    @property
    def length(self):
        return self.end - self.start + 1

    @property
    def center(self):
        return (self.start + self.end) / 2


def contiguous_runs(values):
    values = sorted(set(values))
    if not values:
        return []
    runs = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            runs.append((start, previous))
            start = value
        previous = value
    runs.append((start, previous))
    return runs


def find_frame_markers(image, frame, frame_width, frame_height, guide_pixels, marker_size):
    """Ignore small isolated black frame dots at the sprite-cell border."""
    cell_left = frame * frame_width
    black_pixels = set()
    border_pixels = set()
    for y in range(frame_height):
        for x in range(frame_width):
            if (frame, x, y) in guide_pixels:
                continue
            red, green, blue, alpha = image.getpixel((cell_left + x, y))
            if alpha and (red, green, blue) == (0, 0, 0):
                black_pixels.add((x, y))
                if x in (0, frame_width - 1) or y in (0, frame_height - 1):
                    border_pixels.add((x, y))

    frame_markers = set()
    visited = set()
    max_marker_pixels = marker_size * marker_size
    for seed in border_pixels:
        if seed in visited:
            continue
        component = set()
        pending = [seed]
        while pending:
            point = pending.pop()
            if point in component:
                continue
            component.add(point)
            x, y = point
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = neighbor
                    if 0 <= nx < frame_width and 0 <= ny < frame_height \
                            and neighbor in black_pixels and neighbor not in component:
                        pending.append(neighbor)
        visited.update(component)
        if len(component) > max_marker_pixels:
            continue

        min_x = min(x for x, _ in component)
        max_x = max(x for x, _ in component)
        min_y = min(y for _, y in component)
        max_y = max(y for _, y in component)
        if max_x - min_x + 1 > marker_size or max_y - min_y + 1 > marker_size:
            continue

        touches_art = False
        for x, y in component:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    nx, ny = neighbor
                    if dx == 0 and dy == 0 or neighbor in component:
                        continue
                    if not (0 <= nx < frame_width and 0 <= ny < frame_height):
                        continue
                    if (frame, nx, ny) in guide_pixels:
                        continue
                    if image.getpixel((cell_left + nx, ny))[3] != 0:
                        touches_art = True
                        break
                if touches_art:
                    break
            if touches_art:
                break
        if not touches_art:
            frame_markers.update(component)
    return frame_markers


def get_art_pixels(
    image, frame, frame_width, frame_height, guide_pixels, marker_size=1
):
    """Return opaque sprite pixels, preserving all artwork colors."""
    left = frame * frame_width
    frame_markers = find_frame_markers(
        image, frame, frame_width, frame_height, guide_pixels, marker_size
    )
    pixels = set()
    for y in range(frame_height):
        for x in range(frame_width):
            red, green, blue, alpha = image.getpixel((left + x, y))
            if alpha == 0 or (frame, x, y) in guide_pixels or (x, y) in frame_markers:
                continue
            pixels.add((x, y))
    return pixels


def find_guide_segment(
    image, frame, axis, orientation, frame_width, frame_height, line_scale=1
):
    """Find the longest solid guide in the input color for this axis."""
    color = INPUT_AXIS_COLOR[axis]
    left = frame * frame_width
    candidates = []

    if orientation == "horizontal":
        for y in range(frame_height):
            xs = [
                x for x in range(frame_width)
                if image.getpixel((left + x, y))[:3] == color
                and image.getpixel((left + x, y))[3] != 0
            ]
            candidates.extend(
                Segment(frame, axis, orientation, start, end, y, True)
                for start, end in contiguous_runs(xs)
            )
    else:
        for x in range(frame_width):
            ys = [
                y for y in range(frame_height)
                if image.getpixel((left + x, y))[:3] == color
                and image.getpixel((left + x, y))[3] != 0
            ]
            candidates.extend(
                Segment(frame, axis, orientation, start, end, x, True)
                for start, end in contiguous_runs(ys)
            )

    if not candidates:
        return None
    selected = max(
        candidates,
        key=lambda item: (
            item.length,
            -abs(item.cross - ((frame_height if orientation == "horizontal" else frame_width) - 1) / 2),
        ),
    )
    matching_tracks = sorted({
        item.cross for item in candidates
        if item.start == selected.start and item.end == selected.end
    })
    band = next(
        (run for run in contiguous_runs(matching_tracks)
         if run[0] <= selected.cross <= run[1]),
        (selected.cross, selected.cross),
    )
    thickness = min(line_scale, band[1] - band[0] + 1)
    return Segment(
        selected.frame, selected.axis, selected.orientation,
        selected.start, selected.end, band[0], True, thickness,
    )


def find_silhouette_segment(
    pixels, frame, axis, orientation, frame_width
):
    """Measure the full projected span and put its guide outside the sprite."""
    if not pixels:
        return None
    if orientation == "horizontal":
        xs = [x for x, _ in pixels]
        top = min(y for _, y in pixels)
        # X/Z horizontal measurements use the whole width, drawn above the
        # highest sprite pixel so the dotted guide remains visible.
        return Segment(
            frame, axis, orientation, min(xs), max(xs), max(0, top - 1), False
        )

    ys = [y for _, y in pixels]
    left = min(x for x, _ in pixels)
    right = max(x for x, _ in pixels)
    # The ZX depth measurement is the full top-to-bottom span. Put it just
    # right of the silhouette (falling back to the left only at the border).
    cross = right if right < frame_width - 1 else max(0, left - 1)
    return Segment(frame, axis, orientation, min(ys), max(ys), cross, False)


def pixel_center(segment):
    """Choose the nearest whole pixel to an inclusive range's geometric center."""
    return (segment.start + segment.end + 1) // 2


def center_offset_pixels(segment, axis_length):
    """Return integer center offset from the middle pixel of an axis."""
    return pixel_center(segment) - axis_length // 2


def target_interval(reference, reference_axis_length, target_axis_length):
    """Map a reference range and its center offset onto another frame axis."""
    length = min(reference.length, target_axis_length)
    reference_offset = center_offset_pixels(reference, reference_axis_length)
    target_center = target_axis_length // 2 + reference_offset
    start = target_center - length // 2
    end = start + length - 1
    if start < 0:
        end -= start
        start = 0
    if end >= target_axis_length:
        start -= end - (target_axis_length - 1)
        end = target_axis_length - 1
    return max(0, start), min(target_axis_length - 1, end)


def pixel_is_clear(original, x, y):
    if not (0 <= x < original.width and 0 <= y < original.height):
        return False
    return original.getpixel((x, y))[3] == 0


def visual_scale(sprite_size):
    """Scale guide thickness, dots and gaps to the nearest 32-pixel tier."""
    return max(1, (sprite_size + 16) // 32)


def draw_brush_pixel(
    original, draw, x, y, color, scale=1, clip_box=None,
    brush_width=None, brush_height=None,
):
    """Draw a scaled brush without covering artwork or leaving a view."""
    left, top, right, bottom = clip_box or (0, 0, original.width, original.height)
    brush_width = scale if brush_width is None else brush_width
    brush_height = scale if brush_height is None else brush_height
    for dy in range(brush_height):
        for dx in range(brush_width):
            px, py = x + dx, y + dy
            if left <= px < right and top <= py < bottom \
                    and pixel_is_clear(original, px, py):
                draw.point((px, py), fill=color)


def draw_safe_line(original, draw, start, end, color, dotted=False,
                   scale=1, clip_box=None):
    """Draw a straight safe line, optionally dotted, skipping sprite pixels."""
    x0, y0 = map(round, start)
    x1, y1 = map(round, end)
    if dotted or (x0 != x1 and y0 != y1):
        brush_width = brush_height = scale
    elif y0 == y1:
        brush_width, brush_height = 1, scale
    else:
        brush_width, brush_height = scale, 1
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    step = 0
    while True:
        dash_on = not dotted or step % (2 * scale) == 0
        if dash_on:
            draw_brush_pixel(
                original, draw, x0, y0, color, scale, clip_box,
                brush_width, brush_height,
            )
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy
        step += 1


def draw_segment(original, draw, segment, color, dotted=False, cross=None, scale=1):
    cross = segment.cross if cross is None else cross
    frame_width = original.width // len(VIEW_ORDER)
    frame_height = original.height
    cell_left = segment.frame * frame_width
    clip_box = (cell_left, 0, cell_left + frame_width, frame_height)
    for position in range(segment.start, segment.end + 1):
        if dotted and (position - segment.start) % (2 * scale):
            continue
        if segment.orientation == "horizontal":
            point = (cell_left + position, cross)
        else:
            point = (cell_left + cross, position)
        brush_width = scale if dotted or segment.orientation == "vertical" else 1
        brush_height = scale if dotted or segment.orientation == "horizontal" else 1
        draw_brush_pixel(
            original, draw, *point, color, scale, clip_box,
            brush_width, brush_height,
        )


def correction_display_segment(segment):
    """Apply the one-pixel upward display correction for Z in the ZX view."""
    if segment.axis == "Z" and segment.frame == 2 and segment.orientation == "vertical":
        return Segment(
            segment.frame, segment.axis, segment.orientation,
            max(0, segment.start - 1), max(0, segment.end - 1),
            segment.cross, segment.from_guide,
        )
    return segment


def move_to_outer_track(segment, pixels, frame_width, frame_height):
    """Keep measured endpoints, but render the guide outside the silhouette."""
    if not pixels:
        return segment
    if segment.orientation == "horizontal":
        cross = max(0, min(frame_height - 1, min(y for _, y in pixels) - 1))
    else:
        left = min(x for x, _ in pixels)
        right = max(x for x, _ in pixels)
        # Anchor the vertical guide at the outermost occupied column itself;
        # safe drawing skips opaque sprite pixels instead of shifting it out.
        cross = right if right < frame_width - 1 else max(0, left - 1)
    return Segment(
        segment.frame, segment.axis, segment.orientation,
        segment.start, segment.end, cross, segment.from_guide,
    )


def clear_input_guide(image, segment, frame_width):
    """Remove the old measurement line before rendering its result."""
    if not segment.from_guide:
        return
    color = INPUT_AXIS_COLOR[segment.axis]
    left = segment.frame * frame_width
    for position in range(segment.start, segment.end + 1):
        for offset in range(segment.thickness):
            x, y = (left + position, segment.cross + offset) \
                if segment.orientation == "horizontal" \
                else (left + segment.cross + offset, position)
            if image.getpixel((x, y))[:3] == color:
                image.putpixel((x, y), (0, 0, 0, 0))


def draw_axis_comparison(
    original, draw, reference, actual, frame_width, frame_height,
    dotted=False, check_center=True, line_scale=1,
):
    """Compare one axis in two views and draw valid/error/correction marks."""
    length_delta = actual.length - reference.length
    reference_axis_length = (
        frame_width if reference.orientation == "horizontal" else frame_height
    )
    actual_axis_length = (
        frame_width if actual.orientation == "horizontal" else frame_height
    )
    center_delta = (
        center_offset_pixels(actual, actual_axis_length)
        - center_offset_pixels(reference, reference_axis_length)
        if length_delta == 0 else None
    )
    target_start, target_end = target_interval(
        reference, reference_axis_length, actual_axis_length
    )
    target = Segment(
        actual.frame, actual.axis, actual.orientation,
        target_start, target_end, actual.cross, False,
    )

    draw_segment(
        original, draw, reference, COLOR_AXIS_OK[reference.axis], dotted,
        scale=line_scale,
    )
    if length_delta == 0 and (not check_center or center_delta == 0):
        draw_segment(
            original, draw, actual, COLOR_AXIS_OK[actual.axis], dotted,
            scale=line_scale,
        )
        return "ok"

    if check_center and length_delta == 0 and 0 < abs(center_delta) <= CENTER_TOLERANCE:
        draw_segment(
            original, draw, actual, COLOR_AXIS_OK[actual.axis], dotted,
            scale=line_scale,
        )
        # Keep the expected span visible even for an allowed offset; this is
        # especially useful for the depth measurement in the ZX view.
        cross_limit = frame_height if actual.orientation == "horizontal" else frame_width
        correction_cross = actual.cross - 1 if actual.cross > 0 else actual.cross + 1
        if actual.orientation == "vertical":
            correction_cross = actual.cross + 1 if actual.cross < cross_limit - 1 else actual.cross - 1
        correction = correction_display_segment(target)
        draw_segment(
            original, draw, correction, COLOR_CORRECTION, dotted,
            correction_cross, line_scale,
        )
        return "allowed-center-offset"

    draw_segment(
        original, draw, actual, COLOR_ERROR, dotted, scale=line_scale
    )
    # Offset the correction guide away from the sprite and the measured line.
    if actual.orientation == "horizontal":
        correction_cross = actual.cross - 1 if actual.cross > 0 else actual.cross + 1
    else:
        correction_cross = actual.cross + 1 if actual.cross < frame_width - 1 else actual.cross - 1
    correction = correction_display_segment(target)
    draw_segment(
        original, draw, correction, COLOR_CORRECTION, dotted,
        correction_cross, line_scale,
    )

    if actual.axis == "Z" and length_delta < 0:
        # Count the missing Z samples along the expected span, fading green
        # by six for each successive dot as described in the project notes.
        actual_positions = set(range(actual.start, actual.end + 1))
        missing = [p for p in range(target.start, target.end + 1) if p not in actual_positions]
        last_dot_position = None
        dot_index = 0
        for position in missing:
            if last_dot_position is not None \
                    and position - last_dot_position < 2 * line_scale:
                continue
            green = max(0, DROP_BASE[1] - dot_index * DROP_GREEN_STEP)
            color = (DROP_BASE[0], green, DROP_BASE[2], 255)
            if actual.orientation == "horizontal":
                point = (actual.frame * frame_width + position, actual.cross)
            else:
                point = (actual.frame * frame_width + actual.cross, position)
            clip_box = (
                actual.frame * frame_width, 0,
                (actual.frame + 1) * frame_width, frame_height,
            )
            draw_brush_pixel(original, draw, *point, color, line_scale, clip_box)
            last_dot_position = position
            dot_index += 1

    return "error"


def edge_point(pixels, edge, side):
    """Get the rightmost/leftmost silhouette point on its top/bottom row."""
    if not pixels:
        return None
    edge_y = min(y for _, y in pixels) if edge == "top" else max(y for _, y in pixels)
    row_x = [x for x, y in pixels if y == edge_y]
    edge_x = max(row_x) if side == "right" else min(row_x)
    return edge_x, edge_y


def draw_y_edge_transfers(
    original, draw, art_pixels, frame_width, diagnostics=None, line_scale=1,
):
    """Check Y once by connecting top/bottom silhouette points from YX to YZ."""
    edge_deltas = []
    edge_measurements = {}
    for edge in ("top", "bottom"):
        source_point = edge_point(art_pixels[0], edge, "right")
        target_point = edge_point(art_pixels[1], edge, "left")
        if source_point is None or target_point is None:
            continue

        source_x, source_y = source_point
        target_x, target_y = target_point
        start = (source_x + 1, source_y)
        end = (frame_width + target_x - 1, target_y)
        delta = target_y - source_y
        edge_deltas.append(delta)
        edge_measurements[edge] = {
            "source_y": source_y,
            "target_y": target_y,
            "delta": delta,
        }

        if source_y == target_y:
            draw_safe_line(
                original, draw, start, end, COLOR_AXIS_OK["Y"], scale=line_scale
            )
            continue

        # The measured connector follows the actual endpoint; blue marks the
        # target height from the first view. A one-pixel shared shift is allowed.
        allowed_shift = abs(target_y - source_y) <= CENTER_TOLERANCE
        actual_color = COLOR_AXIS_OK["Y"] if allowed_shift else COLOR_ERROR
        draw_safe_line(
            original, draw, start, end, actual_color, scale=line_scale
        )
        draw_safe_line(
            original, draw, start,
            (frame_width + target_x - 1, source_y), COLOR_CORRECTION,
            scale=line_scale,
        )

    if not edge_deltas or all(delta == 0 for delta in edge_deltas):
        status = "ok"
    elif len(edge_deltas) == 2 and edge_deltas[0] == edge_deltas[1] \
            and abs(edge_deltas[0]) <= CENTER_TOLERANCE:
        status = "allowed-center-offset"
    else:
        status = "error"

    if diagnostics is not None:
        diagnostics.update({"status": status, "edges": edge_measurements})
    return status


def draw_centering_margins(
    original, draw, art_pixels, frame_width, frame_height, line_scale=1
):
    """Draw only left/top dotted centering guides for each sprite cell."""
    for frame in range(3):
        pixels = art_pixels[frame]
        if not pixels:
            continue
        cell_left = frame * frame_width
        left = min(x for x, _ in pixels)
        top = min(y for _, y in pixels)
        left_y = min(y for x, y in pixels if x == left)
        top_x = min(x for x, y in pixels if y == top)

        # Horizontal centering guide: from the cell's left edge toward the
        # highest pixel on the sprite's leftmost surface.
        if left > 0:
            draw_safe_line(
                original, draw, (cell_left, left_y),
                (cell_left + left - 1, left_y), COLOR_CENTER, dotted=True,
                scale=line_scale,
                clip_box=(cell_left, 0, cell_left + frame_width, frame_height),
            )

        # Vertical centering guide: from the cell's top edge to the leftmost
        # pixel on the sprite's highest surface.
        if top > 0:
            global_top_x = cell_left + top_x
            draw_safe_line(
                original, draw, (global_top_x, 0),
                (global_top_x, top - 1), COLOR_CENTER, dotted=True,
                scale=line_scale,
                clip_box=(cell_left, 0, cell_left + frame_width, frame_height),
            )


def process_image(input_path, output_path=None, quiet=False, diagnostics=None):
    input_path = Path(input_path)
    if output_path is not None:
        output_path = Path(output_path)
        if input_path.resolve().as_posix().casefold() == output_path.resolve().as_posix().casefold():
            raise ValueError("Output file must differ from input file.")

    with Image.open(input_path) as source:
        if source.format != "PNG":
            raise ValueError("Input must be a PNG image.")
        image = source.convert("RGBA")

    width, frame_height = image.size
    if frame_height <= 0 or width <= 0 or width % len(VIEW_ORDER) != 0:
        raise ValueError(
            "Expected one row of three equal-size rectangular views: "
            "total width must be three times frame width (YX | YZ | ZX)."
        )

    frame_width = width // len(VIEW_ORDER)
    if frame_width <= 0:
        raise ValueError("Each sprite frame must be at least one pixel wide.")
    line_scale = visual_scale(max(frame_width, frame_height))
    # Compare X in YX/ZX and Z in YZ/ZX. Y is checked once by the top/bottom
    # silhouette transfers between YX and YZ, so no duplicate side bars are drawn.
    axis_views = {
        "X": ((0, "horizontal"), (2, "horizontal"), True),
        "Z": ((1, "horizontal"), (2, "vertical"), True),
    }
    guide_measurements = {}
    complete_guides = True
    for axis, (first_view, second_view, dotted) in axis_views.items():
        reference = find_guide_segment(
            image, first_view[0], axis, first_view[1],
            frame_width, frame_height, line_scale,
        )
        actual = find_guide_segment(
            image, second_view[0], axis, second_view[1],
            frame_width, frame_height, line_scale,
        )
        guide_measurements[axis] = (reference, actual, dotted)
        complete_guides = complete_guides and reference is not None and actual is not None

    y_guides = (
        find_guide_segment(
            image, 0, "Y", "vertical", frame_width, frame_height, line_scale
        ),
        find_guide_segment(
            image, 1, "Y", "vertical", frame_width, frame_height, line_scale
        ),
    )
    guides_to_clear = [
        segment
        for pair in guide_measurements.values()
        for segment in pair[:2]
        if segment is not None
    ]
    guides_to_clear.extend(segment for segment in y_guides if segment is not None)

    # Exclude only the exact guide strokes detected in this image. Other
    # opaque colors, including green/purple artwork, remain part of the sprite.
    guide_pixels = set()
    for segment in guides_to_clear:
        for position in range(segment.start, segment.end + 1):
            for offset in range(segment.thickness):
                x, y = (position, segment.cross + offset) \
                    if segment.orientation == "horizontal" \
                    else (segment.cross + offset, position)
                guide_pixels.add((segment.frame, x, y))

    art_pixels = [
        get_art_pixels(
            image, frame, frame_width, frame_height, guide_pixels,
            min(line_scale, frame_width, frame_height),
        )
        for frame in range(3)
    ]
    if any(not pixels for pixels in art_pixels):
        raise ValueError("Each view must contain visible sprite pixels.")

    # Do not mix a few colored guides with silhouette guesses: use all four
    # X/Z guides together, or measure those axes from silhouettes.
    measurements = {}
    for axis, (first_view, second_view, dotted) in axis_views.items():
        if complete_guides:
            reference, actual, _ = guide_measurements[axis]
        else:
            reference = find_silhouette_segment(
                art_pixels[first_view[0]], first_view[0], axis, first_view[1],
                frame_width,
            )
            actual = find_silhouette_segment(
                art_pixels[second_view[0]], second_view[0], axis, second_view[1],
                frame_width,
            )
        if reference is None or actual is None:
            raise ValueError(f"Could not find both measurements for axis {axis}.")
        measurements[axis] = (reference, actual, dotted)

    # Clear detected input guides, then use the remaining alpha mask as the
    # protection layer. No artwork color is treated as transparent.
    for segment in guides_to_clear:
        clear_input_guide(image, segment, frame_width)
    original = image.copy()
    draw = ImageDraw.Draw(image)

    # Output X/Z guides share one placement rule: use the measured endpoint
    # span, but draw it at the highest clear track (horizontal) or to the
    # right of the silhouette (vertical). This makes Z visible in ZX too.
    visible_measurements = {}
    for axis in ("X", "Z"):
        reference, actual, dotted = measurements[axis]
        reference = move_to_outer_track(
            reference, art_pixels[reference.frame], frame_width, frame_height
        )
        actual = move_to_outer_track(
            actual, art_pixels[actual.frame], frame_width, frame_height
        )
        visible_measurements[axis] = (reference, actual, dotted)

    results = {}
    for axis in ("X", "Z"):
        reference, actual, dotted = visible_measurements[axis]
        results[axis] = draw_axis_comparison(
            original, draw, reference, actual, frame_width, frame_height, dotted,
            check_center=complete_guides,
            line_scale=line_scale,
        )

    # Draw the two silhouette transfers last so they stay continuous where
    # they meet an X/Z measurement or correction guide at a sprite edge.
    y_diagnostics = {}
    results["Y"] = draw_y_edge_transfers(
        original, draw, art_pixels, frame_width,
        diagnostics=y_diagnostics,
        line_scale=line_scale,
    )
    draw_centering_margins(
        original, draw, art_pixels, frame_width, frame_height, line_scale
    )

    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update({
            "image_size": image.size,
            "measurement_mode": "colored axis guides" if complete_guides else "sprite silhouettes",
            "axes": {},
            "Y": y_diagnostics,
        })
        for axis in ("X", "Z"):
            reference, actual, _ = measurements[axis]
            diagnostics["axes"][axis] = {
                "status": results[axis],
                "reference_length": reference.length,
                "actual_length": actual.length,
                "length_delta": actual.length - reference.length,
                "reference_start": reference.start,
                "reference_end": reference.end,
                "actual_start": actual.start,
                "actual_end": actual.end,
                "center_checked": complete_guides,
                "reference_center_offset": center_offset_pixels(
                    reference,
                    frame_width if reference.orientation == "horizontal" else frame_height,
                ),
                "actual_center_offset": center_offset_pixels(
                    actual,
                    frame_width if actual.orientation == "horizontal" else frame_height,
                ),
                "center_shift_pixels": (
                    center_offset_pixels(
                        actual,
                        frame_width if actual.orientation == "horizontal" else frame_height,
                    )
                    - center_offset_pixels(
                        reference,
                        frame_width if reference.orientation == "horizontal" else frame_height,
                    )
                    if actual.length == reference.length else None
                ),
            }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG")
        if not quiet:
            record_file_action("IMAGE_OUTPUT", output_path)
            print(f"Saved image: {output_path}")
    elif not quiet:
        print(f"Checked image: {input_path}")
    if not quiet:
        print(
            f"Measurements: {'colored axis guides' if complete_guides else 'sprite silhouettes'}"
            f" | frame: {frame_width}x{frame_height} px"
            f" | line/dot scale: {line_scale}x"
        )
        if not complete_guides:
            print("Center alignment: not checked without complete colored axis guides.")
        for axis in ("X", "Z"):
            reference, actual, _ = measurements[axis]
            shift = (
                center_offset_pixels(
                    actual,
                    frame_width if actual.orientation == "horizontal" else frame_height,
                )
                - center_offset_pixels(
                    reference,
                    frame_width if reference.orientation == "horizontal" else frame_height,
                )
                if actual.length == reference.length else None
            )
            shift_text = (
                f" | pixel shift {shift:+d}"
                if shift is not None and complete_guides else ""
            )
            print(
                f"{axis}: {results[axis]} | spans {reference.start}-{reference.end}"
                f" ({reference.length}px)->{actual.start}-{actual.end}"
                f" ({actual.length}px){shift_text}"
            )
        print(f"Y: {results['Y']} | checked by top/bottom silhouette transfers")
    return results


def unique_checked_pair(checked_dir, input_path):
    """Find a non-overwriting pair of names inside checked/."""
    suffix = input_path.suffix
    stem = input_path.stem
    index = 1
    while True:
        candidate_stem = stem if index == 1 else f"{stem}_{index}"
        source = checked_dir / f"{candidate_stem}{suffix}"
        preview = checked_dir / f"{candidate_stem}_checked.png"
        if not source.exists() and not preview.exists():
            return source, preview
        index += 1


def unique_file_path(directory, filename):
    """Return a free path by adding a numeric suffix instead of overwriting."""
    path = Path(filename)
    index = 1
    while True:
        stem = path.stem if index == 1 else f"{path.stem}_{index}"
        candidate = directory / f"{stem}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def read_checked_file_list(file_list_path=FILE_LIST_PATH):
    """Read active checked source/preview pairs recorded by the checker."""
    active = {}
    if not file_list_path.exists():
        return active
    try:
        with file_list_path.open("r", encoding="utf-8") as file_list:
            for line in file_list:
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) < 3:
                    continue
                action = fields[1]
                if action == "CHECKED" and len(fields) >= 5:
                    source_path, preview_path = fields[2], fields[3]
                    active[source_path.casefold()] = (
                        Path(source_path), Path(preview_path) if preview_path else None
                    )
                elif action == "RETURNED" and len(fields) >= 4:
                    checked_source_path = fields[3]
                    active.pop(checked_source_path.casefold(), None)
    except (OSError, UnicodeError) as error:
        print(f"Warning: could not read {file_list_path.name}: {error}")
    return active


def return_all_files(check_dir, checked_dir, errors_dir):
    """Return passing originals to check/ and clear generated error artifacts."""
    check_dir = Path(check_dir)
    checked_dir = Path(checked_dir)
    errors_dir = Path(errors_dir)
    for directory in (check_dir, checked_dir, errors_dir):
        directory.mkdir(parents=True, exist_ok=True)
    if len({path.resolve() for path in (check_dir, checked_dir, errors_dir)}) != 3:
        raise ValueError("The check, checked and errors folders must be different.")

    active_pairs = read_checked_file_list()
    checked_pngs = sorted(
        (path for path in checked_dir.iterdir()
         if path.is_file() and path.suffix.lower() == ".png"),
        key=lambda path: path.name.casefold(),
    )
    source_pairs = {}
    preview_keys = set()
    for key, (source_path, preview_path) in active_pairs.items():
        if preview_path is not None:
            preview_keys.add(str(preview_path.resolve()).casefold())
        if source_path.exists():
            source_pairs[key] = (source_path, preview_path)

    # Import pairs from older runs that predate FILE_LIST.txt. The naming rule
    # is <source>_checked.png; originals with their own preview remain sources.
    for path in checked_pngs:
        key = str(path.resolve()).casefold()
        if key in source_pairs:
            continue
        own_preview = checked_dir / f"{path.stem}_checked.png"
        if key in preview_keys:
            if own_preview.exists():
                source_pairs[key] = (path, own_preview)
                preview_keys.add(str(own_preview.resolve()).casefold())
            continue
        is_preview_name = path.stem.casefold().endswith("_checked")
        matching_source = (
            checked_dir / f"{path.stem[:-8]}{path.suffix}"
            if is_preview_name else None
        )
        if is_preview_name and matching_source.exists() and not own_preview.exists():
            preview_keys.add(key)
            continue
        source_pairs[key] = (path, own_preview if own_preview.exists() else None)
        if own_preview.exists():
            preview_keys.add(str(own_preview.resolve()).casefold())

    error_files = sorted(
        (path for path in errors_dir.iterdir() if path.is_file()
         and (path.suffix.lower() == ".png" or path.name.lower().endswith("_errors.txt"))),
        key=lambda path: path.name.casefold(),
    )
    print(
        f"Return All will move {len(source_pairs)} checked source file(s) to check/ "
        f"and delete {len(error_files)} error file(s)."
    )
    if input("Type RETURN ALL to continue (anything else cancels): ").strip() != "RETURN ALL":
        print("Return All cancelled; no files were changed.")
        return {"returned": 0, "deleted": 0, "cancelled": True}

    moved_sources = {}
    removable_previews = set()
    for key, (source_path, preview_path) in source_pairs.items():
        if not source_path.exists():
            continue
        destination = unique_file_path(check_dir, source_path.name)
        try:
            source_path.rename(destination)
        except OSError as error:
            print(f"Could not return {source_path.name}: {error}")
            continue
        moved_sources[key] = destination
        print(f"Returned: {source_path.name} -> {destination}")
        record_file_action("RETURNED", destination, source_path, preview_path or "")
        if preview_path is not None and str(preview_path.resolve()).casefold() not in source_pairs:
            removable_previews.add(preview_path)

    for key, (source_path, preview_path) in source_pairs.items():
        if preview_path is not None and key not in moved_sources \
                and not source_path.exists() \
                and str(preview_path.resolve()).casefold() not in source_pairs:
            removable_previews.add(preview_path)

    removed_previews = 0
    for preview_path in sorted(removable_previews, key=lambda path: path.name.casefold()):
        if not preview_path.exists():
            continue
        try:
            preview_path.unlink()
            removed_previews += 1
            record_file_action("PREVIEW_REMOVED", preview_path)
        except OSError as error:
            print(f"Could not remove generated preview {preview_path.name}: {error}")

    deleted_errors = 0
    for error_path in error_files:
        if not error_path.exists():
            continue
        try:
            error_path.unlink()
            deleted_errors += 1
            record_file_action("ERROR_REMOVED", error_path)
        except OSError as error:
            print(f"Could not remove error file {error_path.name}: {error}")

    print(
        f"Return All complete: {len(moved_sources)} source file(s) returned, "
        f"{removed_previews} preview(s) removed, {deleted_errors} error file(s) deleted."
    )
    return {
        "returned": len(moved_sources),
        "previews_removed": removed_previews,
        "deleted": deleted_errors,
    }


def create_sprite_template(frame_width, frame_height, templates_dir=None):
    """Create a transparent YX | YZ | ZX strip with a black upper-right frame dot."""
    if not isinstance(frame_width, int) or not isinstance(frame_height, int):
        raise ValueError("Frame width and height must be whole numbers.")
    if not (1 <= frame_width <= MAX_FRAME_DIMENSION):
        raise ValueError(f"Frame width must be between 1 and {MAX_FRAME_DIMENSION} pixels.")
    if not (1 <= frame_height <= MAX_FRAME_DIMENSION):
        raise ValueError(f"Frame height must be between 1 and {MAX_FRAME_DIMENSION} pixels.")

    output_dir = Path(templates_dir) if templates_dir else Path(__file__).resolve().parent / "templates"
    output_dir.mkdir(parents=True, exist_ok=True)
    line_scale = visual_scale(max(frame_width, frame_height))
    marker_size = min(line_scale, frame_width, frame_height)
    image = Image.new(
        "RGBA", (len(VIEW_ORDER) * frame_width, frame_height), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(image)
    for frame in range(len(VIEW_ORDER)):
        cell_left = frame * frame_width
        right = cell_left + frame_width - 1
        draw.rectangle(
            (right - marker_size + 1, 0, right, marker_size - 1),
            fill=COLOR_BLACK_PIXEL,
        )

    filename = f"SpriteTemplate_{frame_width}x{frame_height}.png"
    output_path = unique_file_path(output_dir, filename)
    image.save(output_path, format="PNG")
    record_file_action("TEMPLATE", output_path)
    print(f"Created transparent template: {output_path}")
    return output_path


def prompt_template_dimension(label):
    while True:
        raw_value = input(
            f"Frame {label} in pixels (1-{MAX_FRAME_DIMENSION}; C=cancel): "
        ).strip()
        if raw_value.casefold() == "c":
            return None
        try:
            value = int(raw_value)
        except ValueError:
            print("Enter a whole number, for example 24.")
            continue
        if 1 <= value <= MAX_FRAME_DIMENSION:
            return value
        print(f"Value must be between 1 and {MAX_FRAME_DIMENSION}.")


def make_template_interactive():
    print("Create a transparent three-view template (YX | YZ | ZX).")
    try:
        frame_width = prompt_template_dimension("width")
        if frame_width is None:
            print("Template creation cancelled.")
            return False
        frame_height = prompt_template_dimension("height")
        if frame_height is None:
            print("Template creation cancelled.")
            return False
        create_sprite_template(frame_width, frame_height)
        return True
    except (EOFError, KeyboardInterrupt):
        print("Template creation cancelled.")
        return False


def unique_error_paths(errors_dir, input_path):
    """Find unused names for a failed source, its preview and its report."""
    suffix = input_path.suffix
    stem = input_path.stem
    index = 1
    while True:
        candidate_stem = stem if index == 1 else f"{stem}_{index}"
        source = errors_dir / f"{candidate_stem}{suffix}"
        preview = errors_dir / f"{candidate_stem}_checked.png"
        report = errors_dir / f"{candidate_stem}_errors.txt"
        if not source.exists() and not preview.exists() and not report.exists():
            return source, preview, report
        index += 1


def format_failure_report(input_path, results, diagnostics, validation_error=None):
    """Explain which projections failed and what a person should adjust."""
    lines = [
        "SPRITE PROJECTION CHECK — NEEDS FIXING",
        f"Input: {input_path.name}",
    ]
    if validation_error:
        lines.extend([
            "",
            f"Could not analyze this PNG: {validation_error}",
            "",
            "Expected input: one PNG strip with three equal-size rectangular cells in this order: YX | YZ | ZX.",
            "Total image width must be 3 times one cell's width; all cells must contain visible sprite pixels.",
            "Keep empty background transparent and use solid guide colors if providing axis guides.",
        ])
        return "\n".join(lines) + "\n"

    lines.extend([
        f"Image size: {diagnostics.get('image_size')}",
        f"Measurement source: {diagnostics.get('measurement_mode')}",
    ])
    if diagnostics.get("measurement_mode") == "colored axis guides":
        lines.append(
            "Axis positions are compared as whole-pixel ranges; a one-pixel centering difference is allowed."
        )
    else:
        lines.append(
            "Without a complete set of colored axis guides, silhouette mode checks projected lengths only. "
            "It cannot confirm center alignment; yellow dotted margins are visual references."
        )
    lines.extend(["", "Axis results (view order is YX | YZ | ZX):"])
    axes = diagnostics.get("axes", {})
    for axis in ("X", "Z"):
        detail = axes.get(axis, {})
        status = detail.get("status", results.get(axis, "unknown"))
        matching_views = "YX vs ZX" if axis == "X" else "YZ vs ZX"
        lines.append(f"- {axis} ({matching_views}): {status}")
        if status == "error":
            reference_length = detail.get("reference_length")
            actual_length = detail.get("actual_length")
            length_delta = detail.get("length_delta")
            reference_center = detail.get("reference_center_offset")
            actual_center = detail.get("actual_center_offset")
            center_shift = detail.get("center_shift_pixels")
            if length_delta:
                lines.append(
                    f"  Projected span is {actual_length}px; matching view is {reference_length}px "
                    f"(difference {length_delta:+d}px). Adjust the sprite's extreme pixels along {axis}."
                )
            if detail.get("center_checked") and center_shift is not None \
                    and abs(center_shift) > CENTER_TOLERANCE:
                lines.append(
                    f"  Center offset is {actual_center:+d}px; the matching view is "
                    f"{reference_center:+d}px (difference {center_shift:+d} whole pixels). "
                    f"Recenter that axis to match the reference view."
                )

    y_detail = diagnostics.get("Y", {})
    lines.append(f"- Y: {y_detail.get('status', results.get('Y', 'unknown'))}")
    if y_detail.get("status") == "error":
        for edge in ("top", "bottom"):
            point = y_detail.get("edges", {}).get(edge)
            if point is not None:
                lines.append(
                    f"  {edge.capitalize()} edge: YX row {point['source_y']}, "
                    f"YZ row {point['target_y']} (difference {point['delta']:+d}px). "
                    "Align the corresponding height edge in YX and YZ."
                )
    lines.extend([
        "",
        "For measurement failures, the annotated preview is saved beside this report. "
        "Fix the named view(s), then put the corrected source PNG back in check/.",
    ])
    return "\n".join(lines) + "\n"


def process_check_folder(check_dir, checked_dir, errors_dir):
    """Check every top-level PNG; route passing and failed files to their folders."""
    check_dir = Path(check_dir)
    checked_dir = Path(checked_dir)
    errors_dir = Path(errors_dir)
    check_dir.mkdir(parents=True, exist_ok=True)
    checked_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)
    resolved_dirs = {
        path.resolve() for path in (check_dir, checked_dir, errors_dir)
    }
    if len(resolved_dirs) != 3:
        raise ValueError("The check, checked and errors folders must be different.")

    inputs = sorted(
        (path for path in check_dir.iterdir() if path.is_file() and path.suffix.lower() == ".png"),
        key=lambda path: path.name.casefold(),
    )
    if not inputs:
        print(f"No PNG files found in: {check_dir}")
        return {"checked": 0, "errors": 0, "remaining": 0}

    checked_count = 0
    error_count = 0
    remaining = 0
    for input_path in inputs:
        print(f"\nChecking: {input_path.name}")

        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=".sprite_check_", suffix=".png", dir=checked_dir
        )
        os.close(file_descriptor)
        temp_output = Path(temp_name)

        try:
            diagnostics = {}
            validation_error = None
            results = {}
            try:
                results = process_image(
                    input_path, temp_output, quiet=True, diagnostics=diagnostics
                )
            # Isolate per-image failures so one bad PNG does not stop the batch.
            except Exception as error:
                validation_error = f"{type(error).__name__}: {error}"

            failed_axes = [axis for axis, status in results.items() if status == "error"]
            for axis, status in results.items():
                print(f"{axis}: {status}")

            if validation_error or failed_axes:
                destination_input, destination_preview, destination_report = \
                    unique_error_paths(errors_dir, input_path)
                report_text = format_failure_report(
                    input_path, results, diagnostics, validation_error
                )
                report_created = False
                moved_files = []
                try:
                    with destination_report.open("x", encoding="utf-8") as report_file:
                        report_file.write(report_text)
                    report_created = True
                    input_path.rename(destination_input)
                    moved_files.append((destination_input, input_path))
                    has_preview = temp_output.exists() and temp_output.stat().st_size > 0
                    if has_preview:
                        temp_output.rename(destination_preview)
                        moved_files.append((destination_preview, temp_output))
                    moved_items = "source, preview and report" if has_preview else "source and report"
                    record_file_action(
                        "ERROR", destination_input,
                        destination_preview if has_preview else "",
                        destination_report, input_path,
                    )
                    print(f"Failed; {moved_items} moved to {errors_dir}.")
                    error_count += 1
                except OSError:
                    for moved_path, original_path in reversed(moved_files):
                        if moved_path.exists():
                            moved_path.rename(original_path)
                    if report_created and destination_report.exists():
                        destination_report.unlink()
                    raise
                continue

            destination_input, destination_preview = unique_checked_pair(
                checked_dir, input_path
            )
            destination_label = "checked/"
            if destination_input.stem != input_path.stem:
                destination_label += f" (name conflict; saved as {destination_input.name})"

            # Allowed one-pixel centering offsets pass; only explicit errors
            # prevent promotion to checked/.
            input_path.rename(destination_input)
            try:
                temp_output.rename(destination_preview)
            except OSError:
                destination_input.rename(input_path)
                raise
            record_file_action(
                "CHECKED", destination_input, destination_preview, input_path
            )
            print(f"Passed; moved source and preview to {destination_label}.")
            checked_count += 1
        except (OSError, ValueError) as error:
            print(f"Could not check/move {input_path.name}: {error}")
            remaining += 1
        finally:
            if temp_output.exists():
                temp_output.unlink()

    print(
        f"\nBatch complete: {checked_count} passed, {error_count} moved to errors/, "
        f"{remaining} left in check/."
    )
    return {"checked": checked_count, "errors": error_count, "remaining": remaining}


def main():
    parser = argparse.ArgumentParser(
        description="Check a YX | YZ | ZX sprite strip and draw axis guides."
    )
    parser.add_argument("input", nargs="?", type=Path, help="one three-view PNG sprite strip")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="output PNG (default: <input>_checked.png)",
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="check top-level PNGs in check/; route passes to checked/ and failures to errors/",
    )
    parser.add_argument(
        "--make-template", action="store_true",
        help="interactively create a transparent three-view template",
    )
    parser.add_argument(
        "--return-all", action="store_true",
        help="return checked originals to check/ and delete generated error files",
    )
    parser.add_argument("--check-dir", type=Path, help="input folder for --batch")
    parser.add_argument("--checked-dir", type=Path, help="passing files folder for --batch")
    parser.add_argument("--errors-dir", type=Path, help="failed files and reports folder for --batch")
    args = parser.parse_args()

    batch_paths = (args.check_dir, args.checked_dir, args.errors_dir)
    if args.make_template:
        if args.batch or args.return_all or args.input is not None \
                or args.output is not None or any(batch_paths):
            parser.error("--make-template cannot be combined with other commands or paths.")
        return 0 if make_template_interactive() else 10

    if args.return_all:
        if args.batch or args.input is not None or args.output is not None:
            parser.error("--return-all cannot be combined with --batch, input or --output.")
        project_dir = Path(__file__).resolve().parent
        check_dir = args.check_dir or project_dir / "check"
        checked_dir = args.checked_dir or project_dir / "checked"
        errors_dir = args.errors_dir or project_dir / "errors"
        try:
            result = return_all_files(check_dir, checked_dir, errors_dir)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        return 10 if result.get("cancelled") else 0

    if args.batch or args.input is None:
        if args.input is not None or args.output is not None:
            parser.error("Use --batch without an input file or --output.")
        project_dir = Path(__file__).resolve().parent
        check_dir = args.check_dir or project_dir / "check"
        checked_dir = args.checked_dir or project_dir / "checked"
        errors_dir = args.errors_dir or project_dir / "errors"
        try:
            process_check_folder(check_dir, checked_dir, errors_dir)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        return 0

    if (args.check_dir is not None or args.checked_dir is not None
            or args.errors_dir is not None):
        parser.error("Batch folder options can only be used with --batch.")

    output = args.output or args.input.with_name(f"{args.input.stem}_checked.png")
    try:
        if output.exists():
            replacement = unique_file_path(output.parent, output.name)
            print(f"Output already exists; saving without overwrite to: {replacement}")
            output = replacement
        process_image(args.input, output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    
