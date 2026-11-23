"""
Font Engine for AnoDragonDisplay
Procedural and Vision-derived geometry synthesizer for fontTools.
"""

import math
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

K_CIRCLE = 0.5522847498307935

def add_circle_cw(pen, cx, cy, r):
    """Outer circle in Clockwise order (TTF). Top -> Right -> Bottom -> Left -> Top"""
    k = r * K_CIRCLE
    pen.moveTo((cx, cy + r))
    pen.curveTo((cx + k, cy + r), (cx + r, cy + k), (cx + r, cy))
    pen.curveTo((cx + r, cy - k), (cx + k, cy - r), (cx, cy - r))
    pen.curveTo((cx - k, cy - r), (cx - r, cy - k), (cx - r, cy))
    pen.curveTo((cx - r, cy + k), (cx - k, cy + r), (cx, cy + r))
    pen.closePath()

def add_circle_ccw(pen, cx, cy, r):
    """Inner hole circle in Counter-Clockwise order (TTF). Top -> Left -> Bottom -> Right -> Top"""
    k = r * K_CIRCLE
    pen.moveTo((cx, cy + r))
    pen.curveTo((cx - k, cy + r), (cx - r, cy + k), (cx - r, cy))
    pen.curveTo((cx - r, cy - k), (cx - k, cy - r), (cx, cy - r))
    pen.curveTo((cx + k, cy - r), (cx + r, cy - k), (cx + r, cy))
    pen.curveTo((cx + r, cy + k), (cx + k, cy + r), (cx, cy + r))
    pen.closePath()

def add_ellipse_cw(pen, cx, cy, rx, ry):
    """Outer ellipse in Clockwise order."""
    kx = rx * K_CIRCLE
    ky = ry * K_CIRCLE
    pen.moveTo((cx, cy + ry))
    pen.curveTo((cx + kx, cy + ry), (cx + rx, cy + ky), (cx + rx, cy))
    pen.curveTo((cx + rx, cy - ky), (cx + kx, cy - ry), (cx, cy - ry))
    pen.curveTo((cx - kx, cy - ry), (cx - rx, cy - ky), (cx - rx, cy))
    pen.curveTo((cx - rx, cy + ky), (cx - kx, cy + ry), (cx, cy + ry))
    pen.closePath()

def add_ellipse_ccw(pen, cx, cy, rx, ry):
    """Inner hole ellipse in Counter-Clockwise order."""
    kx = rx * K_CIRCLE
    ky = ry * K_CIRCLE
    pen.moveTo((cx, cy + ry))
    pen.curveTo((cx - kx, cy + ry), (cx - rx, cy + ky), (cx - rx, cy))
    pen.curveTo((cx - rx, cy - ky), (cx - kx, cy - ry), (cx, cy - ry))
    pen.curveTo((cx + kx, cy - ry), (cx + rx, cy - ky), (cx + rx, cy))
    pen.curveTo((cx + rx, cy + ky), (cx + kx, cy + ry), (cx, cy + ry))
    pen.closePath()

def add_round_rect_cw(pen, x, y, w, h, r):
    """Rounded rectangle in Clockwise order."""
    r = min(r, w / 2.0, h / 2.0)
    k = r * K_CIRCLE
    x1, y1 = x, y
    x2, y2 = x + w, y + h

    # Start at top edge after top-left corner
    pen.moveTo((x1 + r, y2))
    pen.lineTo((x2 - r, y2))
    pen.curveTo((x2 - r + k, y2), (x2, y2 - r + k), (x2, y2 - r))
    pen.lineTo((x2, y1 + r))
    pen.curveTo((x2, y1 + r - k), (x2 - r + k, y1), (x2 - r, y1))
    pen.lineTo((x1 + r, y1))
    pen.curveTo((x1 + r - k, y1), (x1, y1 + r - k), (x1, y1 + r))
    pen.lineTo((x1, y2 - r))
    pen.curveTo((x1, y2 - r + k), (x1 + r - k, y2), (x1 + r, y2))
    pen.closePath()

def add_round_rect_ccw(pen, x, y, w, h, r):
    """Rounded rectangle hole in Counter-Clockwise order."""
    r = min(r, w / 2.0, h / 2.0)
    k = r * K_CIRCLE
    x1, y1 = x, y
    x2, y2 = x + w, y + h

    # Start at top edge before top-right corner, moving left
    pen.moveTo((x2 - r, y2))
    pen.lineTo((x1 + r, y2))
    pen.curveTo((x1 + r - k, y2), (x1, y2 - r + k), (x1, y2 - r))
    pen.lineTo((x1, y1 + r))
    pen.curveTo((x1, y1 + r - k), (x1 + r - k, y1), (x1 + r, y1))
    pen.lineTo((x2 - r, y1))
    pen.curveTo((x2 - r + k, y1), (x2, y1 + r - k), (x2, y1 + r))
    pen.lineTo((x2, y2 - r))
    pen.curveTo((x2, y2 - r + k), (x2 - r + k, y2), (x2 - r, y2))
    pen.closePath()

def add_capsule_cw(pen, x1, y1, x2, y2, radius):
    """Pill/capsule between two points with radius r in Clockwise order."""
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 1e-4:
        add_circle_cw(pen, x1, y1, radius)
        return
    nx = -dy / dist * radius
    ny = dx / dist * radius

    pen.moveTo((x1 + nx, y1 + ny))
    pen.lineTo((x2 + nx, y2 + ny))
    # Semicircle around p2
    k = radius * K_CIRCLE
    # 2 bezier arcs for semicircle
    ux = dx / dist * radius
    uy = dy / dist * radius
    pen.curveTo((x2 + nx + ux * 0.55, y2 + ny + uy * 0.55),
                (x2 + ux + nx * 0.55, y2 + uy + ny * 0.55),
                (x2 + ux, y2 + uy))
    pen.curveTo((x2 + ux - nx * 0.55, y2 + uy - ny * 0.55),
                (x2 - nx + ux * 0.55, y2 - ny + uy * 0.55),
                (x2 - nx, y2 - ny))
    pen.lineTo((x1 - nx, y1 - ny))
    # Semicircle around p1
    pen.curveTo((x1 - nx - ux * 0.55, y1 - ny - uy * 0.55),
                (x1 - ux - nx * 0.55, y1 - uy - ny * 0.55),
                (x1 - ux, y1 - uy))
    pen.curveTo((x1 - ux + nx * 0.55, y1 - uy + ny * 0.55),
                (x1 + nx - ux * 0.55, y1 + ny - uy * 0.55),
                (x1 + nx, y1 + ny))
    pen.closePath()

def add_polygon_cw(pen, points):
    """Add a polygon ensuring Clockwise orientation."""
    # Check signed area
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    # If area > 0, points are CCW in standard math (y-up). So reverse for CW!
    if area > 0:
        points = list(reversed(points))

    pen.moveTo(points[0])
    for pt in points[1:]:
        pen.lineTo(pt)
    pen.closePath()

def add_polygon_ccw(pen, points):
    """Add a polygon hole ensuring Counter-Clockwise orientation."""
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    # If area < 0, points are CW in standard math (y-up). So reverse for CCW!
    if area < 0:
        points = list(reversed(points))

    pen.moveTo(points[0])
    for pt in points[1:]:
        pen.lineTo(pt)
    pen.closePath()
