import math
from PIL import Image, ImageDraw

SPRITE_SIZE = 16
COLS = 5
ROWS = 5

TOTAL_WIDTH = COLS * SPRITE_SIZE
TOTAL_HEIGHT = ROWS * SPRITE_SIZE

sheet = Image.new('RGBA', (TOTAL_WIDTH, TOTAL_HEIGHT), (0, 0, 0, 0))

COLOR_GREEN = (0, 255, 0, 255)
COLOR_RED = (255, 0, 0, 255)
COLOR_LINE_GREEN = (0, 120, 0, 255)
COLOR_LINE_RED = (120, 0, 0, 255)
COLOR_BLUE = (0, 0, 255, 255)
COLOR_BLACK_PIXEL = (0, 0, 0, 255)

HEAD_RADIUS = int(SPRITE_SIZE * 0.375)
DOT_SIZE = max(2, int(SPRITE_SIZE * 0.0625))
OFFSET_SCALE = SPRITE_SIZE * 0.28

angles = []
for r in range(ROWS):
    pitch = -45 + (r / (ROWS - 1)) * 90 if ROWS > 1 else 0
    for c in range(COLS):
        yaw = -90 + (c / (COLS - 1)) * 180 if COLS > 1 else 0
        angles.append((yaw, pitch))

def blend_pixel(img_draw, x, y, new_color, size):
    if 0 <= x < size and 0 <= y < size:
        current_color = img_draw._image.getpixel((x, y))
        if current_color != (0, 0, 0, 0):
            r_cur, g_cur, b_cur, a_cur = current_color
            r_new, g_new, b_new, a_new = new_color
            
            r = min(255, r_cur + r_new)
            g = min(255, g_cur + g_new)
            b = min(255, b_cur + b_new)
            
            img_draw.point((x, y), fill=(r, g, b, 255))
        else:
            img_draw.point((x, y), fill=new_color)

def draw_dot_block(img_draw, start_x, start_y, color, size):
    for dx in range(DOT_SIZE):
        for dy in range(DOT_SIZE):
            blend_pixel(img_draw, start_x + dx, start_y + dy, color, size)

def draw_straight_line(img_draw, x0, y0, x1, y1, color, size):
    x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
    if x0 == x1:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            blend_pixel(img_draw, x0, y, color, size)
    elif y0 == y1:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            blend_pixel(img_draw, x, y0, color, size)

def draw_vector_sprite(yaw_deg, pitch_deg, size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    cx, cy = size // 2, size // 2
    
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    
    dir_x = math.sin(yaw) * math.cos(pitch)
    dir_y = -math.sin(pitch)
    
    head_cx = cx + dir_x * (size * 0.06)
    head_cy = cy + dir_y * (size * 0.06)
    
    for px in range(size):
        for py in range(size):
            dx = px - head_cx
            dy = py - head_cy
            dist = math.sqrt(dx*dx + dy*dy)
            if abs(dist - HEAD_RADIUS) < max(0.7, size * 0.02):
                blend_pixel(draw, px, py, COLOR_BLUE, size)
    
    left_wall = round(head_cx - HEAD_RADIUS)
    right_wall = round(head_cx + HEAD_RADIUS)
    top_wall = round(head_cy - HEAD_RADIUS)
    bottom_wall = round(head_cy + HEAD_RADIUS)

    g_x = round(head_cx)
    g_y = round(head_cy)
    draw_dot_block(draw, g_x, g_y, COLOR_GREEN, size)
    
    draw_straight_line(draw, g_x, g_y, g_x, top_wall, COLOR_LINE_GREEN, size)
    draw_straight_line(draw, g_x, g_y, left_wall, g_y, COLOR_LINE_GREEN, size)

    dot_x = round(head_cx + dir_x * OFFSET_SCALE)
    dot_y = round(head_cy + dir_y * OFFSET_SCALE)
    draw_dot_block(draw, dot_x, dot_y, COLOR_RED, size)

    draw_straight_line(draw, dot_x, dot_y, dot_x, bottom_wall, COLOR_LINE_RED, size)
    draw_straight_line(draw, dot_x, dot_y, right_wall, dot_y, COLOR_LINE_RED, size)

    max_idx = size - 1
    draw.point((size // 2, 0), fill=COLOR_BLACK_PIXEL)
    draw.point((0, 0), fill=COLOR_BLACK_PIXEL)
    draw.point((0, max_idx), fill=COLOR_BLACK_PIXEL)
    draw.point((max_idx, 0), fill=COLOR_BLACK_PIXEL)
    draw.point((max_idx, max_idx), fill=COLOR_BLACK_PIXEL)

    return img

for idx, (yaw, pitch) in enumerate(angles):
    col = idx % COLS
    row = idx // COLS
    
    x_pos = col * SPRITE_SIZE
    y_pos = row * SPRITE_SIZE
    
    sprite_img = draw_vector_sprite(yaw, pitch, SPRITE_SIZE)
    sheet.paste(sprite_img, (x_pos, y_pos), sprite_img)

output_filename = f"Vector_type_C{COLS}R{ROWS}S{SPRITE_SIZE}.png"
sheet.save(output_filename, format="PNG")