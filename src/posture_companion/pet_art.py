"""Draw the same articulated pet for the overlay and the settings preview."""

import math

from PIL import Image, ImageDraw


SIZE = (212, 180)


def draw_pet(kind: str, lean: float = 0, phase: float = 0,
             action: str = "idle", sleepy: bool = False) -> Image.Image:
    scale = 3
    image = Image.new("RGBA", tuple(n * scale for n in SIZE))
    draw = ImageDraw.Draw(image)
    cat = kind == "cat"
    ink = "#714C3F" if cat else "#594337"
    fur = "#F6B979" if cat else "#BB8A64"
    shade = "#DE9056" if cat else "#9A6548"
    cream = "#FFF0DA"

    def box(x, y, w, h):
        return tuple(round(n * scale) for n in (x, y, x + w, y + h))

    def oval(x, y, w, h, color, edge=None):
        draw.ellipse(box(x, y, w, h), fill=color, outline=edge, width=2 * scale)

    def path(points, color, width=2):
        coords = [(round(x * scale), round(y * scale)) for x, y in points]
        draw.line(coords, fill=color, width=round(width * scale), joint="curve")
        radius = width / 2
        for x, y in (points[0], points[-1]):
            oval(x - radius, y - radius, width, width, color)

    def curve(start, handle1, handle2, end):
        points = []
        for i in range(25):
            t = i / 24
            s = 1 - t
            points.append(tuple(s**3 * a + 3*s*s*t * b + 3*s*t*t * c + t**3 * d
                                for a, b, c, d in zip(start, handle1, handle2, end)))
        return points

    def polygon(points, color):
        draw.polygon([(round(x * scale), round(y * scale)) for x, y in points], fill=color)

    breath = math.sin(phase * 2.4) * 1.5
    motion = (1 - math.cos(phase * 3)) / 2
    stretch = motion if action == "stretch" else 0
    sip = motion if action == "drink" else 0
    hips_x = 93 - 12 * stretch
    body_y = 78 + 12 * lean + 15 * stretch
    head_x = 105 + 23 * lean + 28 * stretch + 4 * sip
    head_y = 57 + 24 * lean + 24 * stretch + 6 * sip + breath

    # Start the tail inside the haunch and paint it behind the body.
    wag = math.sin(phase * (4.8 if cat else 7.2)) * (4 if cat else 7)
    root = (hips_x - 16, body_y + 45)
    if cat:
        tail = curve(root, (24, 160), (18 + wag, 103), (45 + wag, 108))
    else:
        tail = curve(root, (44, 145), (32 + wag, 123), (30 + wag, 103))
    path(tail, ink, 15 if cat else 19)
    path(tail, shade, 11 if cat else 15)
    path(tail[-6:], cream, 10 if cat else 13)

    oval(hips_x - 31, body_y, 70 + 36 * stretch, 75 - 16 * stretch, fur, ink)
    oval(hips_x - 19, body_y + 21, 38 + 25 * stretch, 49 - 12 * stretch, cream)
    for x in (hips_x - 25, hips_x + 16 + 26 * stretch):
        oval(x, 141, 28, 17, fur, ink)
        path([(x + 10, 151), (x + 10, 154)], shade)
        path([(x + 16, 151), (x + 16, 154)], shade)

    if cat:
        for side in (-1, 1):
            ear = [(head_x + side*43, head_y-8), (head_x + side*38, head_y-43),
                   (head_x + side*13, head_y-24)]
            polygon(ear, fur)
            path(ear, ink, 2.5)
            polygon([(head_x + side*36, head_y-15), (head_x + side*34, head_y-34),
                     (head_x + side*20, head_y-23)], "#E68F86")
    else:
        oval(head_x - 55, head_y - 22, 28, 56, shade, ink)
        oval(head_x + 27, head_y - 22, 28, 56, shade, ink)

    oval(head_x - 44, head_y - 29, 88, 68, fur, ink)
    if cat:
        for dx in (-9, 0, 9):
            path([(head_x+dx, head_y-25), (head_x+dx*0.7, head_y-16)], shade, 3)
    else:
        oval(head_x - 12, head_y - 24, 23, 32, cream)
    oval(head_x - 24, head_y + 5, 48, 29, cream)
    blink = sleepy or phase % 5.3 > 5.12
    for side in (-1, 1):
        x = head_x + side * 20
        if blink:
            path([(x-5, head_y+1), (x, head_y+4), (x+5, head_y+1)], ink)
        else:
            oval(x-4.5, head_y-5, 9, 12, "#352B2C")
            oval(x-2, head_y-4, 3, 3, "#FFFFFF")
        oval(head_x + side*31 - 5, head_y + 10, 10, 5, "#E8988A")
        if cat:
            for offset in (0, 6):
                path([(head_x+side*31, head_y+15+offset),
                      (head_x+side*47, head_y+13+offset*1.4)], ink, 1.3)
    oval(head_x - 4, head_y + 11, 8, 5, "#865451" if cat else "#453332")
    path([(head_x-7, head_y+20), (head_x-3, head_y+23), (head_x, head_y+18),
          (head_x+3, head_y+23), (head_x+7, head_y+20)], ink, 1.6)

    if action == "drink":
        x = min(171, head_x + 24)
        y = 119 - 23 * sip + 9 * lean
        path([(hips_x+22, body_y+46), (x+1, y+17)], ink, 15)
        path([(hips_x+22, body_y+46), (x+1, y+17)], fur, 11)
        path([(x+12, y+5), (x+9, y-12), (head_x+5, head_y+18)], "#346C74", 3)
        polygon([(x, y), (x+25, y), (x+21, y+28), (x+4, y+28)], "#70C7C1")
        oval(x-1, y-4, 27, 8, "#D8F2EB", "#346C74")
    elif action == "wave":
        x, y = 151 + 7 * motion, 97 - 10 * motion
        path([(hips_x+25, body_y+44), (x, y)], ink, 16)
        path([(hips_x+25, body_y+44), (x, y)], fur, 12)
        oval(x-6, y-8, 12, 12, cream, ink)

    return image.resize(SIZE, Image.Resampling.LANCZOS)
