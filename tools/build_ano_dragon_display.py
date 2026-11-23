#!/usr/bin/env python3
"""
AnoDragonDisplay Font Generator
Full pipeline: Computer Vision extraction -> Vector Synthesis -> Font Compilation (.otf, .ttf, .woff2)
"""

import os
import sys
import math
import cv2
import numpy as np

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0

# Add tools directory to path
sys.path.insert(0, os.path.dirname(__file__))
from font_engine import (
    add_circle_cw, add_circle_ccw,
    add_ellipse_cw, add_ellipse_ccw,
    add_round_rect_cw, add_round_rect_ccw,
    add_capsule_cw,
    add_polygon_cw, add_polygon_ccw
)

# Typography Constants
UPM = 1000
ASCENDER = 800
CAP_HEIGHT = 720
X_HEIGHT = 520
BASELINE = 0
DESCENDER = -200
PINPOINT_R = 25  # Signature micro-counter radius

# Smooth contour helper from OpenCV
def smooth_contour_points(contour, factor=3):
    pts = [p[0] for p in contour]
    n = len(pts)
    if n < 5:
        return pts
    # Moving average smoothing
    smoothed = []
    for i in range(n):
        avg_x = sum(pts[(i + j) % n][0] for j in range(-factor, factor + 1)) / (2 * factor + 1)
        avg_y = sum(pts[(i + j) % n][1] for j in range(-factor, factor + 1)) / (2 * factor + 1)
        smoothed.append((avg_x, avg_y))
    return smoothed

def extract_vision_glyphs(image_path):
    """Phase 1: Computer Vision extraction of A, N, O and the symbol."""
    print("-> Phase 1: Analyzing image and extracting reference letterforms...")
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read {image_path}")

    # Extract patches:
    # Symbol at y: 440..505, x: 395..440
    # ANO at y: 510..655, x: 355..545
    symbol_patch = img[440:505, 395:440]
    ano_patch = img[510:655, 355:545]

    scale = 4
    ano_4x = cv2.resize(ano_patch, (ano_patch.shape[1] * scale, ano_patch.shape[0] * scale), interpolation=cv2.INTER_LANCZOS4)
    sym_4x = cv2.resize(symbol_patch, (symbol_patch.shape[1] * scale, symbol_patch.shape[0] * scale), interpolation=cv2.INTER_LANCZOS4)

    # Masks
    def make_mask_pair(im4x):
        hsv = cv2.cvtColor(im4x, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        red_whisker = ((h < 15) | (h > 165)) & (s > 100) & (v > 50)
        non_bg = (v > 25) & (~red_whisker)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask_a = cv2.morphologyEx(non_bg.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
        green_core = ((h >= 20) & (h <= 85) & (s >= 40) & (v >= 20) & (v <= 110) & (~red_whisker)).astype(np.uint8) * 255
        mask_b = cv2.morphologyEx(green_core, cv2.MORPH_OPEN, kernel)
        return mask_a, mask_b

    ano_a, ano_b = make_mask_pair(ano_4x)
    sym_a, sym_b = make_mask_pair(sym_4x)

    os.makedirs("sources/drawings", exist_ok=True)
    cv2.imwrite("sources/drawings/ano_mask_a.png", ano_a)
    cv2.imwrite("sources/drawings/ano_mask_b.png", ano_b)
    cv2.imwrite("sources/drawings/sym_mask_a.png", sym_a)
    cv2.imwrite("sources/drawings/sym_mask_b.png", sym_b)

    # Separate letter regions in ANO:
    # A: x: 15..260, N: x: 240..530, O: x: 510..745
    def extract_dict(crops_dict):
        vdata = {}
        for key, mask in crops_dict.items():
            contours, hier = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)
            main_c = max(contours, key=cv2.contourArea)
            bx, by, bw, bh = cv2.boundingRect(main_c)
            scale_f = CAP_HEIGHT / float(bh) if key != 'Symbol' else 240.0 / float(bh)

            def to_font_coords(pts):
                res = []
                for p in pts:
                    fx = (p[0] - bx) * scale_f + 40
                    fy = (bh - (p[1] - by)) * scale_f
                    res.append((round(fx, 1), round(fy, 1)))
                return res

            smooth_main = smooth_contour_points(main_c, factor=2)
            outer = to_font_coords(smooth_main)

            holes = []
            if hier is not None:
                for i, c in enumerate(contours):
                    if hier[0][i][3] >= 0 and cv2.contourArea(c) > 40:
                        sh = smooth_contour_points(c, factor=2)
                        holes.append(to_font_coords(sh))

            adv_w = int(bw * scale_f + 80)
            vdata[key] = {
                'outer': outer,
                'holes': holes,
                'adv_w': adv_w
            }
        return vdata

    crops_a = {
        'A': ano_a[:, 15:260],
        'N': ano_a[:, 240:530],
        'O': ano_a[:, 510:745],
        'Symbol': sym_a
    }
    crops_b = {
        'A': ano_b[:, 15:260],
        'N': ano_b[:, 240:530],
        'O': ano_b[:, 510:745],
        'Symbol': sym_b
    }

    vision_data_a = extract_dict(crops_a)
    vision_data_b = extract_dict(crops_b)

    print("✓ Phase 1 complete: A, N, O and symbol extracted (Silhueta Completa + Núcleo Interno).")
    return vision_data_a, vision_data_b

class GlyphBuilder:
    """Phase 3: Complete procedural vector synthesizer for all glyphs."""

    def __init__(self, vision_data, variant="Regular"):
        self.vision = vision_data
        self.variant = variant
        self.glyphs = {}
        self.metrics = {}
        self.cmap = {}
        self.draw_fns = {}

    def add_glyph(self, name, unicode_val, adv_w, draw_fn):
        self.draw_fns[name] = draw_fn
        tt_pen = TTGlyphPen(None)
        cu_pen = Cu2QuPen(tt_pen, max_err=1.0)
        draw_fn(cu_pen)
        self.glyphs[name] = tt_pen.glyph()
        self.metrics[name] = (adv_w, 40)
        if unicode_val is not None:
            if isinstance(unicode_val, list):
                for u in unicode_val:
                    self.cmap[u] = name
            else:
                self.cmap[unicode_val] = name

    def build_all(self):
        print("-> Phase 2 & 3: Building complete glyph set matching typography DNA...")
        self.build_notdef_and_space()
        self.build_vision_anchors()
        self.build_uppercase()
        self.build_lowercase()
        self.build_numbers()
        self.build_punctuation_and_symbols()
        self.build_arrows()
        self.build_emojis_and_ornaments()
        self.build_accented_variants()
        print(f"✓ Total synthesized glyphs: {len(self.glyphs)}, Unicodes mapped: {len(self.cmap)}")

    def build_notdef_and_space(self):
        # .notdef
        def draw_notdef(pen):
            add_round_rect_cw(pen, 60, 0, 480, CAP_HEIGHT, 80)
            add_round_rect_ccw(pen, 160, 100, 280, CAP_HEIGHT - 200, 40)
        self.add_glyph('.notdef', None, 600, draw_notdef)

        # space
        def draw_space(pen):
            pass
        self.add_glyph('space', 0x0020, 280, draw_space)
        self.cmap[0x00A0] = 'space'  # non-breaking space

    def build_vision_anchors(self):
        # A
        data_a = self.vision['A']
        def draw_a(pen):
            add_polygon_cw(pen, data_a['outer'])
            for h in data_a['holes']:
                add_polygon_ccw(pen, h)
        self.add_glyph('A', 0x0041, data_a['adv_w'], draw_a)

        # N
        data_n = self.vision['N']
        def draw_n(pen):
            add_polygon_cw(pen, data_n['outer'])
        self.add_glyph('N', 0x004E, data_n['adv_w'], draw_n)

        # O
        data_o = self.vision['O']
        def draw_o(pen):
            add_polygon_cw(pen, data_o['outer'])
            for h in data_o['holes']:
                add_polygon_ccw(pen, h)
        self.add_glyph('O', 0x004F, data_o['adv_w'], draw_o)

    def build_uppercase(self):
        W = 560
        SW = 200  # stroke width

        # B: 2 bulging lobes with 2 pinpoint counters
        def draw_b(pen):
            add_round_rect_cw(pen, 50, 0, W - 40, CAP_HEIGHT, 150)
            add_circle_ccw(pen, 320, 500, PINPOINT_R)
            add_circle_ccw(pen, 320, 220, PINPOINT_R)
        self.add_glyph('B', 0x0042, W + 80, draw_b)

        # C: massive horseshoe
        def draw_c(pen):
            # Outer bubble arc
            add_ellipse_cw(pen, 320, 360, 260, 360)
            # Inner cutout as CCW round rect on right
            add_round_rect_ccw(pen, 280, 240, 300, 240, 100)
        self.add_glyph('C', 0x0043, W + 60, draw_c)

        # D: rounded stem + huge belly + 1 pinpoint counter
        def draw_d(pen):
            add_round_rect_cw(pen, 60, 0, W - 40, CAP_HEIGHT, 220)
            add_circle_ccw(pen, 330, 420, PINPOINT_R)
        self.add_glyph('D', 0x0044, W + 80, draw_d)

        # E: trunk + 3 arms
        def draw_e(pen):
            add_round_rect_cw(pen, 60, 0, 190, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 180, CAP_HEIGHT - 170, 320, 170, 70)
            add_round_rect_cw(pen, 180, 280, 250, 160, 60)
            add_round_rect_cw(pen, 180, 0, 330, 170, 70)
        self.add_glyph('E', 0x0045, W + 40, draw_e)

        # F: trunk + 2 upper arms
        def draw_f(pen):
            add_round_rect_cw(pen, 60, 0, 190, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 180, CAP_HEIGHT - 170, 330, 170, 70)
            add_round_rect_cw(pen, 180, 300, 260, 160, 60)
        self.add_glyph('F', 0x0046, W + 30, draw_f)

        # G: like C with inward shelf
        def draw_g(pen):
            add_ellipse_cw(pen, 330, 360, 270, 360)
            add_round_rect_ccw(pen, 290, 280, 300, 220, 80)
            add_round_rect_cw(pen, 330, 180, 220, 170, 70)
        self.add_glyph('G', 0x0047, W + 80, draw_g)

        # H: 2 pillars + crossbar
        def draw_h(pen):
            add_round_rect_cw(pen, 60, 0, 180, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, W - 180, 0, 180, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 180, 270, W - 300, 180, 60)
        self.add_glyph('H', 0x0048, W + 60, draw_h)

        # I: single pill
        def draw_i(pen):
            add_round_rect_cw(pen, 60, 0, 210, CAP_HEIGHT, 90)
        self.add_glyph('I', 0x0049, 330, draw_i)

        # J: pillar ending in hook
        def draw_j(pen):
            add_round_rect_cw(pen, 180, 140, 200, CAP_HEIGHT - 140, 90)
            add_ellipse_cw(pen, 200, 160, 180, 160)
            add_round_rect_ccw(pen, 140, 140, 180, 180, 60)
        self.add_glyph('J', 0x004A, 440, draw_j)

        # K: trunk + 2 diagonal branches
        def draw_k(pen):
            add_round_rect_cw(pen, 60, 0, 180, CAP_HEIGHT, 80)
            add_capsule_cw(pen, 180, 360, W - 60, CAP_HEIGHT - 60, 90)
            add_capsule_cw(pen, 210, 340, W - 50, 70, 95)
        self.add_glyph('K', 0x004B, W + 50, draw_k)

        # L: trunk + foot
        def draw_l(pen):
            add_round_rect_cw(pen, 60, 0, 190, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 170, 0, 310, 180, 75)
        self.add_glyph('L', 0x004C, 530, draw_l)

        # M: wide double-arch bubble
        def draw_m(pen):
            MW = 680
            add_round_rect_cw(pen, 50, 0, 170, CAP_HEIGHT, 75)
            add_round_rect_cw(pen, MW - 160, 0, 170, CAP_HEIGHT, 75)
            add_capsule_cw(pen, 120, CAP_HEIGHT - 80, MW // 2, 140, 85)
            add_capsule_cw(pen, MW - 120, CAP_HEIGHT - 80, MW // 2, 140, 85)
        self.add_glyph('M', 0x004D, 760, draw_m)

        # P: trunk + upper bowl with pinpoint counter
        def draw_p(pen):
            add_round_rect_cw(pen, 60, 0, 180, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 160, 280, 340, CAP_HEIGHT - 280, 150)
            add_circle_ccw(pen, 330, 500, PINPOINT_R)
        self.add_glyph('P', 0x0050, 560, draw_p)

        # Q: O + stout tail
        def draw_q(pen):
            data_o = self.vision['O']
            add_polygon_cw(pen, data_o['outer'])
            for h in data_o['holes']:
                add_polygon_ccw(pen, h)
            add_capsule_cw(pen, data_o['adv_w'] - 160, 180, data_o['adv_w'] - 20, -50, 80)
        self.add_glyph('Q', 0x0051, self.vision['O']['adv_w'] + 60, draw_q)

        # R: P + kick leg
        def draw_r(pen):
            add_round_rect_cw(pen, 60, 0, 180, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 160, 280, 330, CAP_HEIGHT - 280, 140)
            add_circle_ccw(pen, 320, 500, PINPOINT_R)
            add_capsule_cw(pen, 260, 320, 480, 70, 95)
        self.add_glyph('R', 0x0052, 580, draw_r)

        # S: double-curved bubble S
        def draw_s(pen):
            add_capsule_cw(pen, 420, 610, 180, 560, 85)
            add_capsule_cw(pen, 180, 560, 360, 380, 95)
            add_capsule_cw(pen, 360, 380, 150, 180, 95)
            add_capsule_cw(pen, 150, 180, 380, 100, 85)
        self.add_glyph('S', 0x0053, 530, draw_s)

        # T: pillar + top crossbar
        def draw_t(pen):
            add_round_rect_cw(pen, (W - 190) // 2, 0, 190, CAP_HEIGHT - 150, 80)
            add_round_rect_cw(pen, 40, CAP_HEIGHT - 170, W, 170, 75)
        self.add_glyph('T', 0x0054, W + 80, draw_t)

        # U: horseshoe cup
        def draw_u(pen):
            add_round_rect_cw(pen, 60, 0, W, CAP_HEIGHT, 220)
            add_round_rect_ccw(pen, 230, 200, W - 340, CAP_HEIGHT, 80)
        self.add_glyph('U', 0x0055, W + 120, draw_u)

        # V: 2 diagonal legs meeting at rounded vertex
        def draw_v(pen):
            add_capsule_cw(pen, 120, CAP_HEIGHT - 60, (W + 60) // 2, 70, 95)
            add_capsule_cw(pen, W - 20, CAP_HEIGHT - 60, (W + 60) // 2, 70, 95)
        self.add_glyph('V', 0x0056, W + 80, draw_v)

        # W: double V
        def draw_w(pen):
            WW = 740
            q1 = WW // 4
            q2 = WW // 2
            q3 = 3 * WW // 4
            add_capsule_cw(pen, 100, CAP_HEIGHT - 60, q1, 70, 85)
            add_capsule_cw(pen, q2, CAP_HEIGHT - 90, q1, 70, 85)
            add_capsule_cw(pen, q2, CAP_HEIGHT - 90, q3, 70, 85)
            add_capsule_cw(pen, WW - 40, CAP_HEIGHT - 60, q3, 70, 85)
        self.add_glyph('W', 0x0057, 820, draw_w)

        # X: crossing diagonals
        def draw_x(pen):
            add_capsule_cw(pen, 100, 70, W - 20, CAP_HEIGHT - 70, 100)
            add_capsule_cw(pen, 100, CAP_HEIGHT - 70, W - 20, 70, 100)
        self.add_glyph('X', 0x0058, W + 80, draw_x)

        # Y: upper V + vertical stem
        def draw_y(pen):
            mid_x = (W + 60) // 2
            add_capsule_cw(pen, 100, CAP_HEIGHT - 60, mid_x, 320, 95)
            add_capsule_cw(pen, W - 20, CAP_HEIGHT - 60, mid_x, 320, 95)
            add_round_rect_cw(pen, mid_x - 90, 0, 180, 360, 80)
        self.add_glyph('Y', 0x0059, W + 80, draw_y)

        # Z: top bar, diagonal, bottom bar
        def draw_z(pen):
            add_round_rect_cw(pen, 60, CAP_HEIGHT - 160, W - 40, 160, 70)
            add_capsule_cw(pen, W - 80, CAP_HEIGHT - 90, 100, 80, 100)
            add_round_rect_cw(pen, 60, 0, W - 40, 160, 70)
        self.add_glyph('Z', 0x005A, W + 80, draw_z)

    def build_lowercase(self):
        LW = 460
        X = X_HEIGHT

        # a: bubble bowl + right stem + pinpoint counter
        def draw_a_lc(pen):
            add_round_rect_cw(pen, 50, 0, LW, X, 160)
            add_circle_ccw(pen, 240, 320, PINPOINT_R)
        self.add_glyph('a', 0x0061, LW + 80, draw_a_lc)

        # b: tall left stem + lower bowl with pinpoint counter
        def draw_b_lc(pen):
            add_round_rect_cw(pen, 50, 0, 160, ASCENDER, 75)
            add_round_rect_cw(pen, 140, 0, LW - 100, X, 150)
            add_circle_ccw(pen, 290, 280, PINPOINT_R)
        self.add_glyph('b', 0x0062, LW + 80, draw_b_lc)

        # c: small bubble C
        def draw_c_lc(pen):
            add_ellipse_cw(pen, 250, X // 2, 210, X // 2)
            add_round_rect_ccw(pen, 220, X // 2 - 80, 240, 160, 60)
        self.add_glyph('c', 0x0063, LW + 40, draw_c_lc)

        # d: lower bowl + tall right stem with pinpoint counter
        def draw_d_lc(pen):
            add_round_rect_cw(pen, 50, 0, LW - 100, X, 150)
            add_round_rect_cw(pen, LW - 140, 0, 160, ASCENDER, 75)
            add_circle_ccw(pen, 190, 280, PINPOINT_R)
        self.add_glyph('d', 0x0064, LW + 80, draw_d_lc)

        # e: bubble with horizontal bar + pinpoint in upper eye
        def draw_e_lc(pen):
            add_ellipse_cw(pen, 250, X // 2, 210, X // 2)
            add_round_rect_ccw(pen, 200, 100, 240, 120, 50)
            add_circle_ccw(pen, 250, 360, PINPOINT_R - 5)
        self.add_glyph('e', 0x0065, LW + 60, draw_e_lc)

        # f: arched ascender + crossbar
        def draw_f_lc(pen):
            add_round_rect_cw(pen, 90, 0, 160, ASCENDER - 60, 75)
            add_capsule_cw(pen, 170, ASCENDER - 100, 320, ASCENDER - 70, 75)
            add_round_rect_cw(pen, 30, X - 120, 280, 130, 60)
        self.add_glyph('f', 0x0066, 380, draw_f_lc)

        # g: top bowl + pinpoint + descender loop
        def draw_g_lc(pen):
            add_round_rect_cw(pen, 50, 0, LW, X, 150)
            add_circle_ccw(pen, 250, 320, PINPOINT_R)
            add_round_rect_cw(pen, 120, DESCENDER + 40, LW - 70, 180, 80)
            add_round_rect_cw(pen, LW - 120, DESCENDER + 40, 160, X - 80, 75)
        self.add_glyph('g', 0x0067, LW + 80, draw_g_lc)

        # h: tall left stem + rounded right arch
        def draw_h_lc(pen):
            add_round_rect_cw(pen, 50, 0, 160, ASCENDER, 75)
            add_round_rect_cw(pen, 150, 0, LW - 110, X, 140)
            add_round_rect_ccw(pen, 180, 0, LW - 260, X - 140, 60)
        self.add_glyph('h', 0x0068, LW + 70, draw_h_lc)

        # i: short stem + circular dot
        def draw_i_lc(pen):
            add_round_rect_cw(pen, 60, 0, 160, X, 75)
            add_circle_cw(pen, 140, ASCENDER - 110, 75)
        self.add_glyph('i', 0x0069, 280, draw_i_lc)

        # j: hooked descender + circular dot
        def draw_j_lc(pen):
            add_round_rect_cw(pen, 140, DESCENDER + 100, 160, X - (DESCENDER + 100), 75)
            add_capsule_cw(pen, 220, DESCENDER + 120, 60, DESCENDER + 140, 70)
            add_circle_cw(pen, 220, ASCENDER - 110, 75)
        self.add_glyph('j', 0x006A, 360, draw_j_lc)

        # k: tall stem + small diagonal branches
        def draw_k_lc(pen):
            add_round_rect_cw(pen, 50, 0, 160, ASCENDER, 75)
            add_capsule_cw(pen, 150, 240, LW - 40, X - 40, 75)
            add_capsule_cw(pen, 180, 220, LW - 30, 50, 80)
        self.add_glyph('k', 0x006B, LW + 60, draw_k_lc)

        # l: tall pillar
        def draw_l_lc(pen):
            add_round_rect_cw(pen, 60, 0, 160, ASCENDER, 75)
        self.add_glyph('l', 0x006C, 280, draw_l_lc)

        # m: trunk + double arch
        def draw_m_lc(pen):
            MW = 660
            add_round_rect_cw(pen, 50, 0, 150, X, 70)
            add_round_rect_cw(pen, 150, 0, 250, X, 110)
            add_round_rect_ccw(pen, 175, 0, 90, X - 120, 45)
            add_round_rect_cw(pen, 350, 0, 250, X, 110)
            add_round_rect_ccw(pen, 375, 0, 90, X - 120, 45)
        self.add_glyph('m', 0x006D, 740, draw_m_lc)

        # n: trunk + single arch
        def draw_n_lc(pen):
            add_round_rect_cw(pen, 50, 0, 150, X, 70)
            add_round_rect_cw(pen, 150, 0, LW - 100, X, 130)
            add_round_rect_ccw(pen, 180, 0, LW - 240, X - 130, 55)
        self.add_glyph('n', 0x006E, LW + 70, draw_n_lc)

        # o: small bubble oval with pinpoint counter
        def draw_o_lc(pen):
            add_ellipse_cw(pen, 240, X // 2, 200, X // 2)
            add_circle_ccw(pen, 240, 320, PINPOINT_R)
        self.add_glyph('o', 0x006F, LW + 60, draw_o_lc)

        # p: left descender + upper bowl with pinpoint counter
        def draw_p_lc(pen):
            add_round_rect_cw(pen, 50, DESCENDER, 160, X - DESCENDER, 75)
            add_round_rect_cw(pen, 140, 0, LW - 90, X, 150)
            add_circle_ccw(pen, 290, 320, PINPOINT_R)
        self.add_glyph('p', 0x0070, LW + 80, draw_p_lc)

        # q: upper bowl with pinpoint + right descender
        def draw_q_lc(pen):
            add_round_rect_cw(pen, 50, 0, LW - 90, X, 150)
            add_circle_ccw(pen, 190, 320, PINPOINT_R)
            add_round_rect_cw(pen, LW - 130, DESCENDER, 160, X - DESCENDER, 75)
        self.add_glyph('q', 0x0071, LW + 80, draw_q_lc)

        # r: short stem + right ear
        def draw_r_lc(pen):
            add_round_rect_cw(pen, 50, 0, 150, X, 70)
            add_capsule_cw(pen, 160, X - 90, 320, X - 70, 75)
        self.add_glyph('r', 0x0072, 380, draw_r_lc)

        # s: small bubble S
        def draw_s_lc(pen):
            add_capsule_cw(pen, 340, X - 80, 150, X - 120, 75)
            add_capsule_cw(pen, 150, X - 120, 300, 200, 80)
            add_capsule_cw(pen, 300, 200, 130, 80, 80)
            add_capsule_cw(pen, 130, 80, 330, 70, 75)
        self.add_glyph('s', 0x0073, LW + 40, draw_s_lc)

        # t: crossbar + stem curving right
        def draw_t_lc(pen):
            add_round_rect_cw(pen, 130, 0, 160, ASCENDER - 100, 75)
            add_round_rect_cw(pen, 40, X - 120, 310, 130, 60)
            add_capsule_cw(pen, 210, 70, 320, 80, 70)
        self.add_glyph('t', 0x0074, 420, draw_t_lc)

        # u: small cup
        def draw_u_lc(pen):
            add_round_rect_cw(pen, 50, 0, LW, X, 180)
            add_round_rect_ccw(pen, 190, 140, LW - 280, X, 60)
        self.add_glyph('u', 0x0075, LW + 80, draw_u_lc)

        # v: small V
        def draw_v_lc(pen):
            add_capsule_cw(pen, 100, X - 50, (LW + 40) // 2, 50, 80)
            add_capsule_cw(pen, LW - 20, X - 50, (LW + 40) // 2, 50, 80)
        self.add_glyph('v', 0x0076, LW + 60, draw_v_lc)

        # w: small W
        def draw_w_lc(pen):
            WW = 620
            q1, q2, q3 = WW // 4, WW // 2, 3 * WW // 4
            add_capsule_cw(pen, 80, X - 50, q1, 50, 70)
            add_capsule_cw(pen, q2, X - 70, q1, 50, 70)
            add_capsule_cw(pen, q2, X - 70, q3, 50, 70)
            add_capsule_cw(pen, WW - 40, X - 50, q3, 50, 70)
        self.add_glyph('w', 0x0077, 700, draw_w_lc)

        # x: small X
        def draw_x_lc(pen):
            add_capsule_cw(pen, 80, 50, LW - 20, X - 50, 80)
            add_capsule_cw(pen, 80, X - 50, LW - 20, 50, 80)
        self.add_glyph('x', 0x0078, LW + 60, draw_x_lc)

        # y: small V + descender tail curving left
        def draw_y_lc(pen):
            add_capsule_cw(pen, 80, X - 50, 240, 80, 80)
            add_capsule_cw(pen, LW - 20, X - 50, 100, DESCENDER + 70, 80)
        self.add_glyph('y', 0x0079, LW + 60, draw_y_lc)

        # z: small Z
        def draw_z_lc(pen):
            add_round_rect_cw(pen, 50, X - 130, LW - 30, 130, 55)
            add_capsule_cw(pen, LW - 60, X - 70, 80, 60, 85)
            add_round_rect_cw(pen, 50, 0, LW - 30, 130, 55)
        self.add_glyph('z', 0x007A, LW + 60, draw_z_lc)

    def build_numbers(self):
        NW = 540
        # 0: oval with pinpoint counter
        def draw_0(pen):
            add_ellipse_cw(pen, NW // 2 + 30, CAP_HEIGHT // 2, 230, CAP_HEIGHT // 2)
            add_circle_ccw(pen, NW // 2 + 30, 430, PINPOINT_R)
        self.add_glyph('zero', 0x0030, NW + 60, draw_0)

        # 1: pillar with top rounded beak
        def draw_1(pen):
            add_round_rect_cw(pen, 180, 0, 190, CAP_HEIGHT, 85)
            add_capsule_cw(pen, 240, CAP_HEIGHT - 90, 80, CAP_HEIGHT - 210, 80)
        self.add_glyph('one', 0x0031, 460, draw_1)

        # 2: rounded arch, diagonal, bottom bar
        def draw_2(pen):
            add_round_rect_cw(pen, 60, CAP_HEIGHT - 220, NW - 40, 220, 100)
            add_round_rect_ccw(pen, 120, CAP_HEIGHT - 240, NW - 280, 120, 50)
            add_capsule_cw(pen, NW - 50, CAP_HEIGHT - 160, 90, 80, 95)
            add_round_rect_cw(pen, 50, 0, NW, 160, 75)
        self.add_glyph('two', 0x0032, NW + 70, draw_2)

        # 3: two bulging lobes
        def draw_3(pen):
            add_round_rect_cw(pen, 60, CAP_HEIGHT // 2 - 40, NW - 30, CAP_HEIGHT // 2 + 40, 140)
            add_round_rect_ccw(pen, 120, CAP_HEIGHT // 2 + 40, NW - 260, CAP_HEIGHT // 2 - 120, 60)
            add_round_rect_cw(pen, 60, 0, NW, CAP_HEIGHT // 2 + 40, 150)
            add_round_rect_ccw(pen, 120, 80, NW - 240, CAP_HEIGHT // 2 - 120, 60)
        self.add_glyph('three', 0x0033, NW + 70, draw_3)

        # 4: triangle with pinpoint counter + crossbar & stem
        def draw_4(pen):
            add_round_rect_cw(pen, 60, 180, NW - 40, CAP_HEIGHT - 180, 130)
            add_circle_ccw(pen, 260, 480, PINPOINT_R)
            add_round_rect_cw(pen, NW - 170, 0, 180, CAP_HEIGHT, 80)
            add_round_rect_cw(pen, 40, 180, NW + 20, 160, 70)
        self.add_glyph('four', 0x0034, NW + 80, draw_4)

        # 5: top bar + short stem + lower bowl
        def draw_5(pen):
            add_round_rect_cw(pen, 70, CAP_HEIGHT - 160, NW - 40, 160, 70)
            add_round_rect_cw(pen, 70, 300, 170, CAP_HEIGHT - 360, 70)
            add_round_rect_cw(pen, 60, 0, NW + 10, 360, 160)
            add_round_rect_ccw(pen, 140, 90, NW - 220, 180, 60)
        self.add_glyph('five', 0x0035, NW + 70, draw_5)

        # 6: curved outer + lower bowl with pinpoint counter
        def draw_6(pen):
            add_ellipse_cw(pen, NW // 2 + 30, 240, 240, 240)
            add_circle_ccw(pen, NW // 2 + 30, 260, PINPOINT_R)
            add_capsule_cw(pen, NW // 2 + 30, 440, 120, CAP_HEIGHT - 80, 100)
        self.add_glyph('six', 0x0036, NW + 60, draw_6)

        # 7: top bar + strong diagonal leg
        def draw_7(pen):
            add_round_rect_cw(pen, 50, CAP_HEIGHT - 160, NW, 160, 70)
            add_capsule_cw(pen, NW - 60, CAP_HEIGHT - 80, 150, 70, 100)
        self.add_glyph('seven', 0x0037, NW + 60, draw_7)

        # 8: two stacked lobes with 2 pinpoint counters
        def draw_8(pen):
            add_ellipse_cw(pen, NW // 2 + 20, 520, 210, 200)
            add_circle_ccw(pen, NW // 2 + 20, 530, PINPOINT_R)
            add_ellipse_cw(pen, NW // 2 + 20, 220, 240, 220)
            add_circle_ccw(pen, NW // 2 + 20, 220, PINPOINT_R)
        self.add_glyph('eight', 0x0038, NW + 60, draw_8)

        # 9: upper bowl with pinpoint counter + descender tail
        def draw_9(pen):
            add_ellipse_cw(pen, NW // 2 + 20, 480, 240, 240)
            add_circle_ccw(pen, NW // 2 + 20, 480, PINPOINT_R)
            add_capsule_cw(pen, NW // 2 + 180, 460, 160, 80, 100)
        self.add_glyph('nine', 0x0039, NW + 60, draw_9)

        # Fractions and superscripts: ½, ¼, ¾, ¹, ², ³
        self.build_superscripts_and_fractions()

    def build_superscripts_and_fractions(self):
        # Superscript 1, 2, 3
        for sup, u, base in [('onesuperior', 0x00B9, 'one'), ('twosuperior', 0x00B2, 'two'), ('threesuperior', 0x00B3, 'three')]:
            def draw_sup(pen, b=base):
                add_round_rect_cw(pen, 80, 360, 220, 340, 70)
            self.add_glyph(sup, u, 360, draw_sup)

        # Fractions: onehalf, onequarter, threequarters
        for frac, u in [('onehalf', 0x00BD), ('onequarter', 0x00BC), ('threequarters', 0x00BE)]:
            def draw_fr(pen):
                add_capsule_cw(pen, 400, 650, 120, 50, 50)
                add_round_rect_cw(pen, 60, 380, 180, 280, 50)
                add_round_rect_cw(pen, 280, 40, 200, 280, 50)
            self.add_glyph(frac, u, 540, draw_fr)

    def build_punctuation_and_symbols(self):
        # Period
        def draw_dot(pen):
            add_circle_cw(pen, 140, 90, 80)
        self.add_glyph('period', 0x002E, 280, draw_dot)

        # Comma
        def draw_comma(pen):
            add_circle_cw(pen, 140, 90, 80)
            add_capsule_cw(pen, 140, 80, 80, -60, 50)
        self.add_glyph('comma', 0x002C, 280, draw_comma)

        # Colon & Semicolon
        def draw_colon(pen):
            add_circle_cw(pen, 140, 90, 70)
            add_circle_cw(pen, 140, 380, 70)
        self.add_glyph('colon', 0x003A, 280, draw_colon)

        def draw_semicolon(pen):
            add_circle_cw(pen, 140, 380, 70)
            add_circle_cw(pen, 140, 90, 70)
            add_capsule_cw(pen, 140, 80, 80, -60, 45)
        self.add_glyph('semicolon', 0x003B, 280, draw_semicolon)

        # Exclamations: ! and ¡
        def draw_exclam(pen):
            add_round_rect_cw(pen, 110, 240, 180, CAP_HEIGHT - 240, 80)
            add_circle_cw(pen, 200, 90, 80)
        self.add_glyph('exclam', 0x0021, 400, draw_exclam)

        def draw_exclamdown(pen):
            add_round_rect_cw(pen, 110, 0, 180, CAP_HEIGHT - 240, 80)
            add_circle_cw(pen, 200, CAP_HEIGHT - 90, 80)
        self.add_glyph('exclamdown', 0x00A1, 400, draw_exclamdown)

        # Question marks: ? and ¿
        def draw_question(pen):
            add_round_rect_cw(pen, 80, 440, 340, CAP_HEIGHT - 440, 140)
            add_round_rect_ccw(pen, 150, 480, 200, 120, 50)
            add_capsule_cw(pen, 340, 480, 220, 260, 80)
            add_circle_cw(pen, 220, 90, 80)
        self.add_glyph('question', 0x003F, 480, draw_question)

        def draw_questiondown(pen):
            add_round_rect_cw(pen, 80, 0, 340, CAP_HEIGHT - 440, 140)
            add_round_rect_ccw(pen, 150, 80, 200, 120, 50)
            add_capsule_cw(pen, 140, 200, 260, 420, 80)
            add_circle_cw(pen, 260, CAP_HEIGHT - 90, 80)
        self.add_glyph('questiondown', 0x00BF, 480, draw_questiondown)

        # Quotes and apostrophes
        def draw_quote(pen):
            add_capsule_cw(pen, 120, CAP_HEIGHT - 50, 110, CAP_HEIGHT - 220, 65)
        self.add_glyph('quotesingle', 0x0027, 240, draw_quote)

        def draw_quotedbl(pen):
            add_capsule_cw(pen, 110, CAP_HEIGHT - 50, 100, CAP_HEIGHT - 220, 60)
            add_capsule_cw(pen, 250, CAP_HEIGHT - 50, 240, CAP_HEIGHT - 220, 60)
        self.add_glyph('quotedbl', 0x0022, 380, draw_quotedbl)

        self.cmap[0x2018] = 'quotesingle'
        self.cmap[0x2019] = 'quotesingle'
        self.cmap[0x201C] = 'quotedbl'
        self.cmap[0x201D] = 'quotedbl'
        self.cmap[0x00AB] = 'quotedbl'  # guillemet left
        self.cmap[0x00BB] = 'quotedbl'  # guillemet right

        # Hyphens, dashes, underscore: - – — _
        def draw_hyphen(pen):
            add_round_rect_cw(pen, 60, 290, 260, 140, 65)
        self.add_glyph('hyphen', [0x002D, 0x2010, 0x2013], 380, draw_hyphen)

        def draw_emdash(pen):
            add_round_rect_cw(pen, 40, 290, 520, 140, 65)
        self.add_glyph('emdash', 0x2014, 600, draw_emdash)

        def draw_underscore(pen):
            add_round_rect_cw(pen, 40, -120, 440, 120, 55)
        self.add_glyph('underscore', 0x005F, 520, draw_underscore)

        # Ellipsis & Bullet
        def draw_ellipsis(pen):
            add_circle_cw(pen, 120, 80, 55)
            add_circle_cw(pen, 290, 80, 55)
            add_circle_cw(pen, 460, 80, 55)
        self.add_glyph('ellipsis', 0x2026, 580, draw_ellipsis)

        def draw_bullet(pen):
            add_circle_cw(pen, 220, 360, 100)
        self.add_glyph('bullet', [0x2022, 0x00B7], 440, draw_bullet)

        # Parentheses, Brackets, Braces, Slashes
        def draw_parenleft(pen):
            add_capsule_cw(pen, 260, CAP_HEIGHT - 40, 140, 360, 65)
            add_capsule_cw(pen, 140, 360, 260, -40, 65)
        self.add_glyph('parenleft', 0x0028, 360, draw_parenleft)

        def draw_parenright(pen):
            add_capsule_cw(pen, 100, CAP_HEIGHT - 40, 220, 360, 65)
            add_capsule_cw(pen, 220, 360, 100, -40, 65)
        self.add_glyph('parenright', 0x0029, 360, draw_parenright)

        def draw_bracketleft(pen):
            add_round_rect_cw(pen, 100, -60, 150, CAP_HEIGHT + 120, 65)
            add_round_rect_cw(pen, 200, CAP_HEIGHT - 60, 120, 120, 50)
            add_round_rect_cw(pen, 200, -60, 120, 120, 50)
        self.add_glyph('bracketleft', 0x005B, 380, draw_bracketleft)

        def draw_bracketright(pen):
            add_round_rect_cw(pen, 130, -60, 150, CAP_HEIGHT + 120, 65)
            add_round_rect_cw(pen, 60, CAP_HEIGHT - 60, 120, 120, 50)
            add_round_rect_cw(pen, 60, -60, 120, 120, 50)
        self.add_glyph('bracketright', 0x005D, 380, draw_bracketright)

        self.cmap[0x007B] = 'bracketleft'   # {
        self.cmap[0x007D] = 'bracketright'  # }

        def draw_slash(pen):
            add_capsule_cw(pen, 360, CAP_HEIGHT + 40, 80, -60, 75)
        self.add_glyph('slash', 0x002F, 440, draw_slash)

        def draw_backslash(pen):
            add_capsule_cw(pen, 80, CAP_HEIGHT + 40, 360, -60, 75)
        self.add_glyph('backslash', 0x005C, 440, draw_backslash)

        def draw_bar(pen):
            add_round_rect_cw(pen, 140, -80, 160, CAP_HEIGHT + 160, 75)
        self.add_glyph('bar', 0x007C, 440, draw_bar)

        # Currencies: $, ¢, £, €, ¥, ¤
        def draw_dollar(pen):
            add_capsule_cw(pen, 360, 590, 160, 540, 75)
            add_capsule_cw(pen, 160, 540, 320, 360, 85)
            add_capsule_cw(pen, 320, 360, 130, 180, 85)
            add_capsule_cw(pen, 130, 180, 340, 110, 75)
            add_round_rect_cw(pen, 215, -40, 90, CAP_HEIGHT + 80, 45)
        self.add_glyph('dollar', 0x0024, 520, draw_dollar)

        def draw_euro(pen):
            add_ellipse_cw(pen, 300, 360, 240, 340)
            add_round_rect_ccw(pen, 260, 220, 280, 240, 80)
            add_round_rect_cw(pen, 40, 400, 240, 90, 40)
            add_round_rect_cw(pen, 40, 230, 240, 90, 40)
        self.add_glyph('euro', 0x20AC, 560, draw_euro)

        def draw_cent(pen):
            add_ellipse_cw(pen, 240, 300, 190, 260)
            add_round_rect_ccw(pen, 200, 200, 220, 180, 60)
            add_round_rect_cw(pen, 215, 20, 60, 540, 30)
        self.add_glyph('cent', 0x00A2, 480, draw_cent)

        def draw_sterling(pen):
            add_capsule_cw(pen, 340, 600, 160, 560, 75)
            add_capsule_cw(pen, 160, 560, 180, 200, 85)
            add_round_rect_cw(pen, 80, 0, 360, 150, 70)
            add_round_rect_cw(pen, 60, 310, 240, 100, 45)
        self.add_glyph('sterling', 0x00A3, 520, draw_sterling)

        def draw_yen(pen):
            add_capsule_cw(pen, 80, CAP_HEIGHT - 60, 250, 330, 75)
            add_capsule_cw(pen, 420, CAP_HEIGHT - 60, 250, 330, 75)
            add_round_rect_cw(pen, 185, 0, 130, 360, 65)
            add_round_rect_cw(pen, 70, 310, 360, 100, 45)
            add_round_rect_cw(pen, 70, 160, 360, 100, 45)
        self.add_glyph('yen', 0x00A5, 500, draw_yen)

        def draw_currency(pen):
            add_ellipse_cw(pen, 240, 360, 180, 180)
            add_circle_ccw(pen, 240, 360, 60)
            add_circle_cw(pen, 100, 500, 40)
            add_circle_cw(pen, 380, 500, 40)
            add_circle_cw(pen, 100, 220, 40)
            add_circle_cw(pen, 380, 220, 40)
        self.add_glyph('currency', 0x00A4, 480, draw_currency)

        # Math and Symbols: +, -, ×, ÷, =, ≠, <, >, ≤, ≥, ~, ^, °, @, #, &, *, %, ‰, §, ¶, ©, ®, ™
        def draw_plus(pen):
            add_round_rect_cw(pen, 60, 290, 360, 140, 65)
            add_round_rect_cw(pen, 170, 180, 140, 360, 65)
        self.add_glyph('plus', 0x002B, 480, draw_plus)

        def draw_equal(pen):
            add_round_rect_cw(pen, 60, 410, 360, 130, 60)
            add_round_rect_cw(pen, 60, 200, 360, 130, 60)
        self.add_glyph('equal', 0x003D, 480, draw_equal)

        def draw_notequal(pen):
            add_round_rect_cw(pen, 60, 410, 360, 130, 60)
            add_round_rect_cw(pen, 60, 200, 360, 130, 60)
            add_capsule_cw(pen, 340, 580, 140, 150, 50)
        self.add_glyph('notequal', 0x2260, 480, draw_notequal)

        def draw_multiply(pen):
            add_capsule_cw(pen, 100, 190, 360, 450, 75)
            add_capsule_cw(pen, 100, 450, 360, 190, 75)
        self.add_glyph('multiply', 0x00D7, 460, draw_multiply)

        def draw_divide(pen):
            add_round_rect_cw(pen, 60, 300, 360, 120, 60)
            add_circle_cw(pen, 240, 540, 60)
            add_circle_cw(pen, 240, 180, 60)
        self.add_glyph('divide', 0x00F7, 480, draw_divide)

        def draw_less(pen):
            add_capsule_cw(pen, 360, 530, 100, 360, 75)
            add_capsule_cw(pen, 100, 360, 360, 190, 75)
        self.add_glyph('less', 0x003C, 460, draw_less)

        def draw_greater(pen):
            add_capsule_cw(pen, 100, 530, 360, 360, 75)
            add_capsule_cw(pen, 360, 360, 100, 190, 75)
        self.add_glyph('greater', 0x003E, 460, draw_greater)

        self.cmap[0x2264] = 'less'     # ≤
        self.cmap[0x2265] = 'greater'  # ≥

        # At @: big bubble circle + pinpoint counter + hook
        def draw_at(pen):
            add_ellipse_cw(pen, 320, 360, 260, 320)
            add_circle_ccw(pen, 320, 420, PINPOINT_R)
            add_round_rect_cw(pen, 340, 180, 180, 120, 50)
        self.add_glyph('at', 0x0040, 640, draw_at)

        # Hash #
        def draw_numbersign(pen):
            add_round_rect_cw(pen, 140, 50, 110, CAP_HEIGHT - 100, 55)
            add_round_rect_cw(pen, 320, 50, 110, CAP_HEIGHT - 100, 55)
            add_round_rect_cw(pen, 50, 420, 470, 120, 55)
            add_round_rect_cw(pen, 50, 200, 470, 120, 55)
        self.add_glyph('numbersign', 0x0023, 570, draw_numbersign)

        # Ampersand &
        def draw_ampersand(pen):
            add_ellipse_cw(pen, 280, 500, 180, 180)
            add_circle_ccw(pen, 280, 520, PINPOINT_R)
            add_ellipse_cw(pen, 300, 200, 240, 220)
            add_circle_ccw(pen, 300, 200, PINPOINT_R)
            add_capsule_cw(pen, 380, 150, 520, 90, 75)
        self.add_glyph('ampersand', 0x0026, 600, draw_ampersand)

        # Percent %
        def draw_percent(pen):
            add_capsule_cw(pen, 420, 640, 120, 80, 65)
            add_ellipse_cw(pen, 180, 520, 110, 110)
            add_circle_ccw(pen, 180, 520, PINPOINT_R - 5)
            add_ellipse_cw(pen, 360, 200, 110, 110)
            add_circle_ccw(pen, 360, 200, PINPOINT_R - 5)
        self.add_glyph('percent', 0x0025, 540, draw_percent)
        self.cmap[0x2030] = 'percent'  # per mille

        # Asterisk *
        def draw_asterisk(pen):
            add_capsule_cw(pen, 140, 480, 360, 480, 55)
            add_capsule_cw(pen, 180, 370, 320, 590, 55)
            add_capsule_cw(pen, 180, 590, 320, 370, 55)
        self.add_glyph('asterisk', 0x002A, 500, draw_asterisk)

        # Tilde ~ and Ascii Circumflex ^
        def draw_asciitilde(pen):
            add_capsule_cw(pen, 80, 360, 220, 420, 55)
            add_capsule_cw(pen, 220, 420, 360, 360, 55)
            add_capsule_cw(pen, 360, 360, 480, 410, 55)
        self.add_glyph('asciitilde', [0x007E, 0x02DC], 560, draw_asciitilde)

        def draw_asciicircum(pen):
            add_capsule_cw(pen, 100, 380, 260, 580, 60)
            add_capsule_cw(pen, 260, 580, 420, 380, 60)
        self.add_glyph('asciicircum', [0x005E, 0x02C6], 520, draw_asciicircum)

        # Degree °
        def draw_degree(pen):
            add_ellipse_cw(pen, 180, 560, 100, 100)
            add_circle_ccw(pen, 180, 560, PINPOINT_R)
        self.add_glyph('degree', 0x00B0, 360, draw_degree)

        # Copyright © & Registered ® & Trademark ™
        def draw_copyright(pen):
            add_ellipse_cw(pen, 340, 360, 280, 280)
            add_ellipse_ccw(pen, 340, 360, 190, 190)
            add_ellipse_cw(pen, 340, 360, 140, 150)
            add_round_rect_ccw(pen, 320, 300, 180, 120, 40)
        self.add_glyph('copyright', 0x00A9, 680, draw_copyright)

        def draw_registered(pen):
            add_ellipse_cw(pen, 340, 360, 280, 280)
            add_ellipse_ccw(pen, 340, 360, 190, 190)
            add_round_rect_cw(pen, 260, 260, 90, 200, 40)
            add_round_rect_cw(pen, 310, 360, 120, 100, 45)
            add_circle_ccw(pen, 360, 410, 15)
            add_capsule_cw(pen, 330, 360, 380, 260, 35)
        self.add_glyph('registered', 0x00AE, 680, draw_registered)

        def draw_trademark(pen):
            add_round_rect_cw(pen, 80, 480, 160, 50, 25)
            add_round_rect_cw(pen, 135, 340, 50, 170, 25)
            add_round_rect_cw(pen, 280, 340, 45, 190, 22)
            add_capsule_cw(pen, 300, 520, 350, 420, 25)
            add_capsule_cw(pen, 400, 520, 350, 420, 25)
            add_round_rect_cw(pen, 400, 340, 45, 190, 22)
        self.add_glyph('trademark', 0x2122, 520, draw_trademark)

        # Section § and Pilcrow ¶
        def draw_section(pen):
            add_ellipse_cw(pen, 200, 510, 130, 130)
            add_circle_ccw(pen, 200, 510, 20)
            add_ellipse_cw(pen, 200, 330, 140, 140)
            add_circle_ccw(pen, 200, 330, 20)
            add_ellipse_cw(pen, 200, 150, 130, 130)
            add_circle_ccw(pen, 200, 150, 20)
        self.add_glyph('section', 0x00A7, 400, draw_section)

        def draw_paragraph(pen):
            add_round_rect_cw(pen, 80, 240, 240, 380, 110)
            add_circle_ccw(pen, 180, 440, PINPOINT_R)
            add_round_rect_cw(pen, 240, 40, 100, 580, 50)
            add_round_rect_cw(pen, 360, 40, 90, 580, 45)
        self.add_glyph('paragraph', 0x00B6, 500, draw_paragraph)

    def build_arrows(self):
        """Draw 14 thick, rounded, organic bubble arrows."""
        W = 600
        H = CAP_HEIGHT
        MY = H // 2

        # Left arrow ← U+2190
        def draw_left(pen):
            add_round_rect_cw(pen, 180, MY - 75, 360, 150, 70)
            add_capsule_cw(pen, 260, MY + 180, 80, MY, 85)
            add_capsule_cw(pen, 260, MY - 180, 80, MY, 85)
        self.add_glyph('arrowleft', 0x2190, W, draw_left)

        # Right arrow → U+2192
        def draw_right(pen):
            add_round_rect_cw(pen, 60, MY - 75, 360, 150, 70)
            add_capsule_cw(pen, 340, MY + 180, 520, MY, 85)
            add_capsule_cw(pen, 340, MY - 180, 520, MY, 85)
        self.add_glyph('arrowright', [0x2192, 0x2794, 0x279C, 0x27A4], W, draw_right)

        # Up arrow ↑ U+2191
        def draw_up(pen):
            MX = W // 2
            add_round_rect_cw(pen, MX - 75, 60, 150, 440, 70)
            add_capsule_cw(pen, MX - 170, 360, MX, 540, 85)
            add_capsule_cw(pen, MX + 170, 360, MX, 540, 85)
        self.add_glyph('arrowup', 0x2191, W, draw_up)

        # Down arrow ↓ U+2193
        def draw_down(pen):
            MX = W // 2
            add_round_rect_cw(pen, MX - 75, 140, 150, 440, 70)
            add_capsule_cw(pen, MX - 170, 240, MX, 60, 85)
            add_capsule_cw(pen, MX + 170, 240, MX, 60, 85)
        self.add_glyph('arrowdown', 0x2193, W, draw_down)

        # Left-right arrow ↔ U+2194
        def draw_leftright(pen):
            add_round_rect_cw(pen, 160, MY - 65, W - 320, 130, 60)
            add_capsule_cw(pen, 220, MY + 140, 80, MY, 75)
            add_capsule_cw(pen, 220, MY - 140, 80, MY, 75)
            add_capsule_cw(pen, W - 220, MY + 140, W - 80, MY, 75)
            add_capsule_cw(pen, W - 220, MY - 140, W - 80, MY, 75)
        self.add_glyph('arrowboth', 0x2194, W, draw_leftright)

        # Up-down arrow ↕ U+2195
        def draw_updown(pen):
            MX = W // 2
            add_round_rect_cw(pen, MX - 65, 160, 130, H - 320, 60)
            add_capsule_cw(pen, MX - 140, H - 220, MX, H - 80, 75)
            add_capsule_cw(pen, MX + 140, H - 220, MX, H - 80, 75)
            add_capsule_cw(pen, MX - 140, 220, MX, 80, 75)
            add_capsule_cw(pen, MX + 140, 220, MX, 80, 75)
        self.add_glyph('arrowupdown', 0x2195, W, draw_updown)

        # Diagonals: ↖ ↗ ↘ ↙
        def draw_nw(pen):
            add_capsule_cw(pen, 460, 120, 180, 480, 80)
            add_capsule_cw(pen, 340, 520, 140, 520, 80)
            add_capsule_cw(pen, 140, 320, 140, 520, 80)
        self.add_glyph('arrownw', 0x2196, W, draw_nw)

        def draw_ne(pen):
            add_capsule_cw(pen, 140, 120, 420, 480, 80)
            add_capsule_cw(pen, 260, 520, 460, 520, 80)
            add_capsule_cw(pen, 460, 320, 460, 520, 80)
        self.add_glyph('arrowne', 0x2197, W, draw_ne)

        def draw_se(pen):
            add_capsule_cw(pen, 140, 520, 420, 160, 80)
            add_capsule_cw(pen, 260, 120, 460, 120, 80)
            add_capsule_cw(pen, 460, 320, 460, 120, 80)
        self.add_glyph('arrowse', 0x2198, W, draw_se)

        def draw_sw(pen):
            add_capsule_cw(pen, 460, 520, 180, 160, 80)
            add_capsule_cw(pen, 340, 120, 140, 120, 80)
            add_capsule_cw(pen, 140, 320, 140, 120, 80)
        self.add_glyph('arrowsw', 0x2199, W, draw_sw)

        # Circular arrows: ↻ U+21BB, ↺ U+21BA
        def draw_cw_loop(pen):
            add_ellipse_cw(pen, W // 2, MY, 230, 230)
            add_circle_ccw(pen, W // 2, MY, 130)
            add_round_rect_ccw(pen, 260, MY - 160, 260, 140, 50)
            add_capsule_cw(pen, 420, MY + 150, 480, MY, 70)
        self.add_glyph('arrowcw', 0x21BB, W, draw_cw_loop)

        def draw_ccw_loop(pen):
            add_ellipse_cw(pen, W // 2, MY, 230, 230)
            add_circle_ccw(pen, W // 2, MY, 130)
            add_round_rect_ccw(pen, 80, MY - 160, 260, 140, 50)
            add_capsule_cw(pen, 180, MY + 150, 120, MY, 70)
        self.add_glyph('arrowccw', 0x21BA, W, draw_ccw_loop)

    def build_emojis_and_ornaments(self):
        """Draw emojis, shapes and artwork easter eggs (lily flower and dragon emblem)."""
        W = 680
        H = CAP_HEIGHT
        CX = W // 2
        CY = H // 2

        # 1. Smileys: ☺ 0x263A, ☻ 0x263B, ☹ 0x2639
        def draw_smile(pen):
            add_circle_cw(pen, CX, CY, 280)
            # Eyes
            add_circle_ccw(pen, CX - 90, CY + 80, 35)
            add_circle_ccw(pen, CX + 90, CY + 80, 35)
            # Smile cutout
            add_round_rect_ccw(pen, CX - 120, CY - 140, 240, 90, 45)
        self.add_glyph('smileface', [0x263A, 0x263B], W, draw_smile)

        def draw_sad(pen):
            add_circle_cw(pen, CX, CY, 280)
            add_circle_ccw(pen, CX - 90, CY + 80, 35)
            add_circle_ccw(pen, CX + 90, CY + 80, 35)
            # Frown cutout
            add_round_rect_ccw(pen, CX - 120, CY - 90, 240, 70, 35)
        self.add_glyph('sadface', 0x2639, W, draw_sad)

        # 2. Hearts: ♥ 0x2665, ♡ 0x2661
        def draw_heart(pen):
            add_circle_cw(pen, CX - 100, CY + 60, 150)
            add_circle_cw(pen, CX + 100, CY + 60, 150)
            pts = [(CX - 220, CY + 40), (CX + 220, CY + 40), (CX, 70)]
            add_polygon_cw(pen, pts)
        self.add_glyph('heart', [0x2665, 0x2661], W, draw_heart)

        # 3. Stars: ★ 0x2605, ☆ 0x2606, ✦ 0x2726, ✨ 0x2728
        def draw_star(pen):
            pts = []
            for i in range(10):
                r = 280 if i % 2 == 0 else 120
                ang = i * math.pi / 5 - math.pi / 2
                pts.append((round(CX + r * math.cos(ang), 1), round(CY + r * math.sin(ang), 1)))
            add_polygon_cw(pen, pts)
        self.add_glyph('star', [0x2605, 0x2606], W, draw_star)

        def draw_sparkle(pen):
            # 4-point organic diamond star
            pts = [
                (CX, CY + 280), (CX + 60, CY + 60), (CX + 280, CY),
                (CX + 60, CY - 60), (CX, CY - 280), (CX - 60, CY - 60),
                (CX - 280, CY), (CX - 60, CY + 60)
            ]
            add_polygon_cw(pen, pts)
        self.add_glyph('sparkle', [0x2726, 0x2728], W, draw_sparkle)

        # 4. Weather & Music: ☀ 0x2600, ☁ 0x2601, ⚡ 0x26A1, 🔥 0x1F525, ♪ 0x266A, ♫ 0x266B
        def draw_sun(pen):
            add_circle_cw(pen, CX, CY, 160)
            for i in range(8):
                ang = i * math.pi / 4
                x1 = CX + 190 * math.cos(ang)
                y1 = CY + 190 * math.sin(ang)
                x2 = CX + 280 * math.cos(ang)
                y2 = CY + 280 * math.sin(ang)
                add_capsule_cw(pen, x1, y1, x2, y2, 45)
        self.add_glyph('sun', 0x2600, W, draw_sun)

        def draw_cloud(pen):
            add_round_rect_cw(pen, 100, 160, 480, 220, 110)
            add_circle_cw(pen, 260, 360, 150)
            add_circle_cw(pen, 420, 340, 130)
        self.add_glyph('cloud', 0x2601, W, draw_cloud)

        def draw_lightning(pen):
            pts = [
                (CX + 40, CY + 270), (CX - 120, CY + 30), (CX - 20, CY + 30),
                (CX - 80, CY - 250), (CX + 140, CY - 10), (CX + 20, CY - 10)
            ]
            add_polygon_cw(pen, pts)
        self.add_glyph('lightning', [0x26A1, 0x1F525], W, draw_lightning)

        def draw_note(pen):
            add_ellipse_cw(pen, 220, 180, 110, 90)
            add_round_rect_cw(pen, 280, 180, 80, 420, 40)
            add_capsule_cw(pen, 320, 600, 460, 520, 60)
        self.add_glyph('musicalnote', [0x266A, 0x266B], W, draw_note)

        # 5. Status & Geometry: ✓ 0x2713, ✗ 0x2717, ▲ ▼ ◀ ▶ ● ○ ■ ◆
        def draw_check(pen):
            add_capsule_cw(pen, 100, CY - 20, 240, CY - 180, 75)
            add_capsule_cw(pen, 240, CY - 180, 540, CY + 220, 75)
        self.add_glyph('checkmark', 0x2713, W, draw_check)

        def draw_cross(pen):
            add_capsule_cw(pen, 140, CY - 200, 500, CY + 200, 80)
            add_capsule_cw(pen, 140, CY + 200, 500, CY - 200, 80)
        self.add_glyph('ballotx', 0x2717, W, draw_cross)

        # Geometric shapes
        self.add_glyph('triangup', 0x25B2, W, lambda pen: add_polygon_cw(pen, [(CX, CY + 240), (CX + 240, CY - 200), (CX - 240, CY - 200)]))
        self.add_glyph('triangdown', 0x25BC, W, lambda pen: add_polygon_cw(pen, [(CX, CY - 240), (CX + 240, CY + 200), (CX - 240, CY + 200)]))
        self.add_glyph('triangleft', 0x25C0, W, lambda pen: add_polygon_cw(pen, [(CX - 240, CY), (CX + 200, CY + 220), (CX + 200, CY - 220)]))
        self.add_glyph('triangright', 0x25B6, W, lambda pen: add_polygon_cw(pen, [(CX + 240, CY), (CX - 200, CY + 220), (CX - 200, CY - 220)]))
        self.add_glyph('circleblack', 0x25CF, W, lambda pen: add_circle_cw(pen, CX, CY, 240))
        self.add_glyph('circlewhite', 0x25CB, W, lambda pen: (add_circle_cw(pen, CX, CY, 240), add_circle_ccw(pen, CX, CY, 160)))
        self.add_glyph('squareblack', 0x25A0, W, lambda pen: add_round_rect_cw(pen, CX - 220, CY - 220, 440, 440, 70))
        self.add_glyph('diamondblack', 0x25C6, W, lambda pen: add_polygon_cw(pen, [(CX, CY + 260), (CX + 240, CY), (CX, CY - 260), (CX - 240, CY)]))

        # 6. Special Easter Eggs:
        # Easter Egg 1: Lily Flower ✿ U+273F (inspired by the yellow lily in the artwork)
        def draw_lily(pen):
            # 6 rounded petals around center
            for i in range(6):
                ang = i * math.pi / 3
                px = CX + 170 * math.cos(ang)
                py = CY + 170 * math.sin(ang)
                add_circle_cw(pen, px, py, 95)
            # Center pistil
            add_circle_cw(pen, CX, CY, 100)
            add_circle_ccw(pen, CX, CY, PINPOINT_R)
        self.add_glyph('lilyflower', 0x273F, W, draw_lily)

        # Easter Egg 2: Dragon Emblem 🐉 U+1F409 (inspired by the green oriental dragon)
        def draw_dragon(pen):
            # Coiled dragon silhouette
            add_ellipse_cw(pen, CX, CY + 60, 240, 240)
            add_circle_ccw(pen, CX, CY + 60, 110)
            # Dragon snout & horns
            add_capsule_cw(pen, CX + 140, CY + 120, CX + 280, CY + 180, 70)
            add_capsule_cw(pen, CX + 20, CY + 240, CX - 80, CY + 340, 50)  # horn 1
            add_capsule_cw(pen, CX + 80, CY + 240, CX + 40, CY + 350, 50)  # horn 2
            # Whiskers
            add_capsule_cw(pen, CX + 240, CY + 120, CX + 200, CY - 100, 35)
            # Claws
            add_capsule_cw(pen, CX - 180, CY - 60, CX - 140, CY - 200, 50)
        self.add_glyph('dragonemblem', 0x1F409, W, draw_dragon)

    def build_accented_variants(self):
        """Build Portuguese and Latin-1 accented letters using stylized floating diacritics."""
        print("-> Synthesizing complete accented glyphs (Á, À, Â, Ã, Ç, É, Í, Ñ, Ó, Ú, etc.)...")

        # Diacritic drawing primitives
        def add_acute(pen, cx, cy):
            add_capsule_cw(pen, cx - 40, cy, cx + 50, cy + 90, 55)

        def add_grave(pen, cx, cy):
            add_capsule_cw(pen, cx + 40, cy, cx - 50, cy + 90, 55)

        def add_circumflex(pen, cx, cy):
            add_capsule_cw(pen, cx - 70, cy, cx, cy + 90, 50)
            add_capsule_cw(pen, cx, cy + 90, cx + 70, cy, 50)

        def add_tilde(pen, cx, cy):
            add_capsule_cw(pen, cx - 90, cy + 10, cx - 20, cy + 60, 45)
            add_capsule_cw(pen, cx - 20, cy + 60, cx + 30, cy + 10, 45)
            add_capsule_cw(pen, cx + 30, cy + 10, cx + 90, cy + 50, 45)

        def add_umlaut(pen, cx, cy):
            add_circle_cw(pen, cx - 60, cy + 40, 50)
            add_circle_cw(pen, cx + 60, cy + 40, 50)

        def add_ring(pen, cx, cy):
            add_circle_cw(pen, cx, cy + 50, 60)
            add_circle_ccw(pen, cx, cy + 50, 20)

        def add_cedilla(pen, cx):
            add_capsule_cw(pen, cx, -20, cx - 40, -120, 45)
            add_capsule_cw(pen, cx - 40, -120, cx + 20, -150, 45)

        # Uppercase accents
        accent_map_uc = [
            ('Aacute', 0x00C1, 'A', add_acute),
            ('Agrave', 0x00C0, 'A', add_grave),
            ('Acircumflex', 0x00C2, 'A', add_circumflex),
            ('Atilde', 0x00C3, 'A', add_tilde),
            ('Adieresis', 0x00C4, 'A', add_umlaut),
            ('Aring', 0x00C5, 'A', add_ring),
            ('Eacute', 0x00C9, 'E', add_acute),
            ('Egrave', 0x00C8, 'E', add_grave),
            ('Ecircumflex', 0x00CA, 'E', add_circumflex),
            ('Edieresis', 0x00CB, 'E', add_umlaut),
            ('Iacute', 0x00CD, 'I', add_acute),
            ('Igrave', 0x00CC, 'I', add_grave),
            ('Icircumflex', 0x00CE, 'I', add_circumflex),
            ('Idieresis', 0x00CF, 'I', add_umlaut),
            ('Ntilde', 0x00D1, 'N', add_tilde),
            ('Oacute', 0x00D3, 'O', add_acute),
            ('Ograve', 0x00D2, 'O', add_grave),
            ('Ocircumflex', 0x00D4, 'O', add_circumflex),
            ('Otilde', 0x00D5, 'O', add_tilde),
            ('Odieresis', 0x00D6, 'O', add_umlaut),
            ('Uacute', 0x00DA, 'U', add_acute),
            ('Ugrave', 0x00D9, 'U', add_grave),
            ('Ucircumflex', 0x00DB, 'U', add_circumflex),
            ('Udieresis', 0x00DC, 'U', add_umlaut),
            ('Yacute', 0x00DD, 'Y', add_acute),
            ('Ydieresis', 0x0178, 'Y', add_umlaut),
        ]

        for name, u, base, fn in accent_map_uc:
            base_fn = self.draw_fns[base]
            adv_w = self.metrics[base][0]
            cx = adv_w // 2
            cy = CAP_HEIGHT + 30
            def make_drawer(bf=base_fn, f=fn, x=cx, y=cy):
                def draw(pen):
                    bf(pen)
                    f(pen, x, y)
                return draw
            self.add_glyph(name, u, adv_w, make_drawer())

        # Ç (Ccedilla)
        c_adv = self.metrics['C'][0]
        c_base_fn = self.draw_fns['C']
        def draw_ccedilla(pen):
            c_base_fn(pen)
            add_cedilla(pen, c_adv // 2)
        self.add_glyph('Ccedilla', 0x00C7, c_adv, draw_ccedilla)

        # Æ (AE) & Ø (Oslash) & ß (germandbls)
        a_fn = self.draw_fns['A']
        e_fn = self.draw_fns['E']
        def draw_ae(pen):
            a_fn(pen)
            e_fn(pen)
        self.add_glyph('AE', 0x00C6, self.metrics['A'][0] + 200, draw_ae)

        o_fn = self.draw_fns['O']
        def draw_oslash(pen):
            o_fn(pen)
            o_w = self.metrics['O'][0]
            add_capsule_cw(pen, 60, -30, o_w - 60, CAP_HEIGHT + 30, 45)
        self.add_glyph('Oslash', 0x00D8, self.metrics['O'][0], draw_oslash)

        b_fn = self.draw_fns['B']
        def draw_eszett(pen):
            b_fn(pen)
            add_round_rect_cw(pen, 50, DESCENDER, 160, 240, 75)
        self.add_glyph('germandbls', 0x00DF, self.metrics['B'][0], draw_eszett)

        # Lowercase accents
        accent_map_lc = [
            ('aacute', 0x00E1, 'a', add_acute),
            ('agrave', 0x00E0, 'a', add_grave),
            ('acircumflex', 0x00E2, 'a', add_circumflex),
            ('atilde', 0x00E3, 'a', add_tilde),
            ('adieresis', 0x00E4, 'a', add_umlaut),
            ('aring', 0x00E5, 'a', add_ring),
            ('eacute', 0x00E9, 'e', add_acute),
            ('egrave', 0x00E8, 'e', add_grave),
            ('ecircumflex', 0x00EA, 'e', add_circumflex),
            ('edieresis', 0x00EB, 'e', add_umlaut),
            ('iacute', 0x00ED, 'i', add_acute),
            ('igrave', 0x00EC, 'i', add_grave),
            ('icircumflex', 0x00EE, 'i', add_circumflex),
            ('idieresis', 0x00EF, 'i', add_umlaut),
            ('ntilde', 0x00F1, 'n', add_tilde),
            ('oacute', 0x00F3, 'o', add_acute),
            ('ograve', 0x00F2, 'o', add_grave),
            ('ocircumflex', 0x00F4, 'o', add_circumflex),
            ('otilde', 0x00F5, 'o', add_tilde),
            ('odieresis', 0x00F6, 'o', add_umlaut),
            ('uacute', 0x00FA, 'u', add_acute),
            ('ugrave', 0x00F9, 'u', add_grave),
            ('ucircumflex', 0x00FB, 'u', add_circumflex),
            ('udieresis', 0x00FC, 'u', add_umlaut),
            ('yacute', 0x00FD, 'y', add_acute),
            ('ydieresis', 0x00FF, 'y', add_umlaut),
        ]

        for name, u, base, fn in accent_map_lc:
            base_fn = self.draw_fns[base]
            adv_w = self.metrics[base][0]
            cx = adv_w // 2
            cy = X_HEIGHT + 25
            def make_drawer_lc(bf=base_fn, f=fn, x=cx, y=cy):
                def draw(pen):
                    bf(pen)
                    f(pen, x, y)
                return draw
            self.add_glyph(name, u, adv_w, make_drawer_lc())

        # ç (ccedilla)
        c_lc_adv = self.metrics['c'][0]
        c_lc_fn = self.draw_fns['c']
        def draw_ccedilla_lc(pen):
            c_lc_fn(pen)
            add_cedilla(pen, c_lc_adv // 2)
        self.add_glyph('ccedilla', 0x00E7, c_lc_adv, draw_ccedilla_lc)

        # æ (ae) & ø (oslash)
        a_lc_fn = self.draw_fns['a']
        e_lc_fn = self.draw_fns['e']
        def draw_ae_lc(pen):
            a_lc_fn(pen)
            e_lc_fn(pen)
        self.add_glyph('ae', 0x00E6, self.metrics['a'][0] + 160, draw_ae_lc)

        o_lc_fn = self.draw_fns['o']
        def draw_oslash_lc(pen):
            o_lc_fn(pen)
            o_w = self.metrics['o'][0]
            add_capsule_cw(pen, 40, -20, o_w - 40, X_HEIGHT + 20, 40)
        self.add_glyph('oslash', 0x00F8, self.metrics['o'][0], draw_oslash_lc)

def compile_fonts(builder, font_family="AnoDragonDisplay", style="Regular"):
    """Phase 4 & 5: Compile TTF, OTF, and WOFF2."""
    print(f"-> Phase 4 & 5: Compiling {font_family}-{style} (.ttf, .otf, .woff2)...")

    glyph_order = ['.notdef', 'space'] + [g for g in builder.glyphs.keys() if g not in ('.notdef', 'space')]

    # 1. Compile TTF
    fb_ttf = FontBuilder(unitsPerEm=UPM, isTTF=True)
    fb_ttf.setupGlyphOrder(glyph_order)
    fb_ttf.setupCharacterMap(builder.cmap)
    fb_ttf.setupGlyf(builder.glyphs)
    fb_ttf.setupHorizontalMetrics(builder.metrics)
    fb_ttf.setupHorizontalHeader(ascent=ASCENDER, descent=DESCENDER)
    fb_ttf.setupNameTable({
        'familyName': font_family,
        'styleName': style,
        'uniqueFontIdentifier': f"{font_family}-{style}:2026",
        'fullName': f"{font_family} {style}",
        'version': 'Version 1.000',
        'psName': f"{font_family}-{style}",
        'designer': 'Marcus Maglia',
        'description': 'Handcrafted display typography reverse-engineered from manual ink artwork.'
    })
    fb_ttf.setupOS2(
        sTypoAscender=ASCENDER,
        sTypoDescender=DESCENDER,
        sTypoLineGap=100,
        usWinAscent=ASCENDER,
        usWinDescent=abs(DESCENDER),
        sxHeight=X_HEIGHT,
        sCapHeight=CAP_HEIGHT
    )
    fb_ttf.setupPost()

    # Kerning table for tight signature look
    kerning_pairs = {
        ('A', 'V'): -60, ('A', 'T'): -50, ('A', 'Y'): -50,
        ('A', 'N'): -40, ('N', 'O'): -45, ('T', 'O'): -50,
        ('V', 'A'): -60, ('W', 'A'): -50, ('P', 'A'): -40
    }
    kern_table = newTable('kern')
    kern_table.version = 0
    subtable = KernTable_format_0()
    subtable.version = 0
    subtable.coverage = 1
    subtable.format = 0
    subtable.kernTable = kerning_pairs
    kern_table.kernTables = [subtable]
    fb_ttf.font['kern'] = kern_table

    os.makedirs("fonts/ttf", exist_ok=True)
    os.makedirs("fonts/otf", exist_ok=True)
    os.makedirs("fonts/web", exist_ok=True)

    ttf_path = f"fonts/ttf/{font_family}-{style}.ttf"
    woff2_path = f"fonts/web/{font_family}-{style}.woff2"
    otf_path = f"fonts/otf/{font_family}-{style}.otf"

    fb_ttf.save(ttf_path)
    print(f"  ✓ Exported: {ttf_path} ({os.path.getsize(ttf_path)} bytes)")

    # Save WOFF2
    font_woff2 = fb_ttf.font
    font_woff2.flavor = 'woff2'
    font_woff2.save(woff2_path)
    print(f"  ✓ Exported: {woff2_path} ({os.path.getsize(woff2_path)} bytes)")

    # 2. Compile OTF (CFF)
    fb_otf = FontBuilder(unitsPerEm=UPM, isTTF=False)
    fb_otf.setupGlyphOrder(glyph_order)
    fb_otf.setupCharacterMap(builder.cmap)

    # Convert glyphs to CFF charStrings
    char_strings = {}
    for name in glyph_order:
        pen = T2CharStringPen(builder.metrics[name][0], None)
        builder.draw_fns[name](pen)
        char_strings[name] = pen.getCharString()

    fb_otf.setupCFF(
        f"{font_family}-{style}",
        {'FullName': f"{font_family} {style}", 'FamilyName': font_family, 'Weight': 'Black'},
        char_strings,
        {}
    )
    fb_otf.setupHorizontalMetrics(builder.metrics)
    fb_otf.setupHorizontalHeader(ascent=ASCENDER, descent=DESCENDER)
    fb_otf.setupNameTable({
        'familyName': font_family,
        'styleName': style,
        'uniqueFontIdentifier': f"{font_family}-{style}:2026",
        'fullName': f"{font_family} {style}",
        'version': 'Version 1.000',
        'psName': f"{font_family}-{style}",
        'designer': 'Marcus Maglia'
    })
    fb_otf.setupOS2(
        sTypoAscender=ASCENDER,
        sTypoDescender=DESCENDER,
        sTypoLineGap=100,
        usWinAscent=ASCENDER,
        usWinDescent=abs(DESCENDER),
        sxHeight=X_HEIGHT,
        sCapHeight=CAP_HEIGHT
    )
    fb_otf.setupPost()
    fb_otf.save(otf_path)
    print(f"  ✓ Exported: {otf_path} ({os.path.getsize(otf_path)} bytes)")

def generate_specimen_html():
    """Phase 6: Create rich interactive specimen HTML page."""
    print("-> Phase 6: Generating interactive typographic specimen HTML...")
    specimen_content = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AnoDragonDisplay — Espécime Tipográfico Interativo</title>
  <style>
    @font-face {
      font-family: 'AnoDragonDisplay';
      src: url('../fonts/web/AnoDragonDisplay-Regular.woff2') format('woff2'),
           url('../fonts/ttf/AnoDragonDisplay-Regular.ttf') format('truetype');
      font-weight: 900;
      font-style: normal;
      font-display: swap;
    }

    :root {
      --bg: #0d0f0c;
      --card-bg: #161a14;
      --border: #2c3325;
      --olive-dark: #222912;
      --cream: #dce29f;
      --cream-glow: rgba(220, 226, 159, 0.25);
      --dragon-red: #c93b2b;
      --text: #eaeede;
      --muted: #8e9981;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, sans-serif;
      padding: 40px 24px;
      line-height: 1.5;
    }

    .container {
      max-width: 1100px;
      margin: 0 auto;
    }

    header {
      text-align: center;
      margin-bottom: 50px;
      padding-bottom: 30px;
      border-bottom: 1px solid var(--border);
    }

    .badge-pill {
      display: inline-block;
      padding: 6px 16px;
      background: var(--olive-dark);
      color: var(--cream);
      border: 1px solid var(--cream);
      border-radius: 20px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      margin-bottom: 16px;
    }

    h1 {
      font-family: 'AnoDragonDisplay', sans-serif;
      font-size: clamp(3rem, 8vw, 6.5rem);
      color: var(--cream);
      text-shadow: 0 0 25px var(--cream-glow);
      line-height: 1.05;
      margin-bottom: 12px;
      letter-spacing: 2px;
    }

    .subtitle {
      color: var(--muted);
      font-size: 1.15rem;
      max-width: 650px;
      margin: 0 auto;
    }

    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      margin-bottom: 40px;
    }

    @media (max-width: 768px) {
      .grid-2 { grid-template-columns: 1fr; }
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    }

    .card h2 {
      font-size: 1.1rem;
      color: var(--cream);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Comparison Box */
    .compare-container {
      display: flex;
      gap: 20px;
      align-items: center;
      justify-content: center;
      background: #000;
      border-radius: 12px;
      padding: 20px;
      border: 1px dashed var(--border);
    }

    .compare-item {
      text-align: center;
      flex: 1;
    }

    .compare-item img {
      max-height: 180px;
      border-radius: 8px;
      border: 1px solid var(--border);
    }

    .compare-text {
      font-family: 'AnoDragonDisplay', sans-serif;
      font-size: 5rem;
      color: var(--cream);
      line-height: 1;
    }

    .caption {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    /* Interactive Playground */
    .playground {
      margin-bottom: 40px;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
      margin-bottom: 20px;
      background: var(--olive-dark);
      padding: 14px 20px;
      border-radius: 12px;
    }

    .controls label {
      font-size: 13px;
      font-weight: 600;
      color: var(--cream);
    }

    .controls input[type="range"] {
      flex: 1;
      min-width: 150px;
      accent-color: var(--cream);
    }

    .preview-box {
      font-family: 'AnoDragonDisplay', sans-serif;
      min-height: 180px;
      padding: 24px;
      background: #050705;
      border: 1px solid var(--border);
      border-radius: 12px;
      outline: none;
      word-break: break-word;
      transition: all 0.2s;
    }

    .preview-box:focus {
      border-color: var(--cream);
      box-shadow: 0 0 15px var(--cream-glow);
    }

    /* Glyph Matrix */
    .glyph-section {
      margin-bottom: 30px;
    }

    .glyph-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
    }

    .glyph-box {
      font-family: 'AnoDragonDisplay', sans-serif;
      width: 58px;
      height: 58px;
      background: #000;
      border: 1px solid var(--border);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 26px;
      color: var(--cream);
      transition: transform 0.15s, border-color 0.15s;
    }

    .glyph-box:hover {
      transform: scale(1.18);
      border-color: var(--cream);
      background: var(--olive-dark);
      z-index: 2;
    }

    .easter-egg-banner {
      background: linear-gradient(135deg, var(--olive-dark), #10160a);
      border: 2px solid var(--cream);
      border-radius: 16px;
      padding: 24px;
      text-align: center;
      margin-top: 40px;
    }

    .easter-egg-banner h3 {
      font-size: 1.3rem;
      color: var(--cream);
      margin-bottom: 8px;
    }

    .special-glyphs {
      font-family: 'AnoDragonDisplay', sans-serif;
      font-size: 3.5rem;
      color: var(--cream);
      margin: 12px 0;
      display: flex;
      justify-content: center;
      gap: 30px;
    }

    footer {
      text-align: center;
      margin-top: 60px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 13px;
    }
  </style>
</head>
<body>

<div class="container">
  <header>
    <div class="badge-pill">Display Orgânica • Handcrafted • Ultra-Bold</div>
    <h1>AnoDragonDisplay</h1>
    <p class="subtitle">Tipografia autoral concebida a partir de ilustração manual em nanquim e pintura digital. Com micro-contragrafismos circulares (pinpoint counters) e energia bubble-graffiti.</p>
  </header>

  <div class="grid-2">
    <!-- Comparison -->
    <div class="card">
      <h2>🔍 Comparação: Arte Original vs. Glifos Vetoriais</h2>
      <div class="compare-container">
        <div class="compare-item">
          <img src="../sources/drawings/ano_extracted.png" alt="Original ANO" onerror="this.src='../sources/drawings/roi_preview.png'">
          <div class="caption">Lettering da Ilustração</div>
        </div>
        <div class="compare-item">
          <div class="compare-text">ANO</div>
          <div class="caption">Fonte Vetorial (.woff2)</div>
        </div>
      </div>
    </div>

    <!-- Font DNA Specs -->
    <div class="card">
      <h2>🧬 DNA & Métricas Tipográficas</h2>
      <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text);">
        <li>📐 <strong>Units Per Em (UPM):</strong> 1000</li>
        <li>📏 <strong>Cap Height:</strong> 720 | <strong>x-Height:</strong> 520</li>
        <li>⛰️ <strong>Ascender:</strong> 800 | <strong>Descender:</strong> -200</li>
        <li>🎯 <strong>Assinatura:</strong> Contragrafismos em micro-círculos posicionados no terço superior óptico.</li>
        <li>📦 <strong>Formatos Exportados:</strong> .otf, .ttf, .woff2 (Web)</li>
        <li>🔤 <strong>Suporte Linguístico:</strong> Português e Latin-1 completo, Diacríticos, Moedas (R$, $, €, £, ¥), Setas e Emojis.</li>
      </ul>
    </div>
  </div>

  <!-- Interactive Playground -->
  <div class="card playground">
    <h2>⚡ Playground Interativo (Digite seu texto)</h2>
    <div class="controls">
      <label for="font-size">Tamanho:</label>
      <input type="range" id="font-size" min="24" max="120" value="64">
      <span id="size-val">64px</span>

      <label for="color-picker" style="margin-left: 20px;">Cor:</label>
      <input type="color" id="color-picker" value="#dce29f">
    </div>

    <div class="preview-box" id="preview" contenteditable="true" spellcheck="false">
      1º ANO DO DRAGÃO 2026
    </div>
  </div>

  <!-- Complete Glyph Matrix -->
  <div class="card">
    <h2>📚 Catálogo Completo de Caracteres</h2>

    <div class="glyph-section">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Maiúsculas (A-Z)</h3>
      <div class="glyph-grid" id="grid-upper"></div>
    </div>

    <div class="glyph-section" style="margin-top: 20px;">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Minúsculas (a-z)</h3>
      <div class="glyph-grid" id="grid-lower"></div>
    </div>

    <div class="glyph-section" style="margin-top: 20px;">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Acentuadas & Diacríticos (Português)</h3>
      <div class="glyph-grid" id="grid-accents"></div>
    </div>

    <div class="glyph-section" style="margin-top: 20px;">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Números & Frações</h3>
      <div class="glyph-grid" id="grid-numbers"></div>
    </div>

    <div class="glyph-section" style="margin-top: 20px;">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Pontuação & Símbolos Especiais</h3>
      <div class="glyph-grid" id="grid-symbols"></div>
    </div>

    <div class="glyph-section" style="margin-top: 20px;">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Setas Direcionais (14 Direções)</h3>
      <div class="glyph-grid" id="grid-arrows"></div>
    </div>

    <div class="glyph-section" style="margin-top: 20px;">
      <h3 style="font-size: 13px; color: var(--muted); text-transform: uppercase;">Emojis & Pictogramas</h3>
      <div class="glyph-grid" id="grid-emojis"></div>
    </div>
  </div>

  <!-- Easter Egg Banner -->
  <div class="easter-egg-banner">
    <h3>🌸 Ornamentos Temáticos Especiais (Easter Eggs) 🐉</h3>
    <p style="color: var(--muted); font-size: 14px;">Incluídos nos pontos de código Unicode de flor de lírio e dragão:</p>
    <div class="special-glyphs">
      <span title="Lírio Amarelo (U+273F)">✿</span>
      <span title="Dragão Oriental (U+1F409)">🐉</span>
    </div>
    <p style="font-size: 13px; color: var(--cream);">Copie e cole ou use os caracteres <code>✿</code> e <code>🐉</code> em seus designs!</p>
  </div>

  <footer>
    <p>AnoDragonDisplay Regular • Tipografia Autoral por Marcus Maglia • 2026</p>
  </footer>
</div>

<script>
  // Playground sizing
  const slider = document.getElementById('font-size');
  const sizeVal = document.getElementById('size-val');
  const preview = document.getElementById('preview');
  const colorPicker = document.getElementById('color-picker');

  slider.addEventListener('input', (e) => {
    preview.style.fontSize = e.target.value + 'px';
    sizeVal.textContent = e.target.value + 'px';
  });

  colorPicker.addEventListener('input', (e) => {
    preview.style.color = e.target.value;
  });

  // Populate glyph sets
  const sets = {
    'grid-upper': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split(''),
    'grid-lower': 'abcdefghijklmnopqrstuvwxyz'.split(''),
    'grid-accents': 'ÁÀÂÃÄÅÆÇÉÊËÍÌÎÏÑÓÔÕÖØÙÚÛÜÝŸßáàâãäåæçéêëíìîïñóôõöøùúûüýÿ'.split(''),
    'grid-numbers': '0123456789½¼¾¹²³'.split(''),
    'grid-symbols': '.,:;!¡?¿\'"“”«»()[]{}/\\|-_…•@#&*%$¢£€¥+×÷=≠<>~°©®™'.split(''),
    'grid-arrows': ['←', '↑', '→', '↓', '↔', '↕', '↖', '↗', '↘', '↙', '➔', '➜', '↻', '↺'],
    'grid-emojis': ['☺', '☻', '☹', '♥', '♡', '★', '☆', '✦', '✨', '☀', '☁', '⚡', '🔥', '♪', '♫', '✓', '✗', '▲', '▼', '◀', '▶', '●', '○', '■', '◆', '✿', '🐉']
  };

  for (const [id, list] of Object.entries(sets)) {
    const el = document.getElementById(id);
    if (!el) continue;
    list.forEach(char => {
      const b = document.createElement('div');
      b.className = 'glyph-box';
      b.textContent = char;
      b.title = `${char} (U+${char.codePointAt(0).toString(16).toUpperCase()})`;
      b.onclick = () => {
        preview.textContent += char;
      };
      el.appendChild(b);
    });
  }
</script>

</body>
</html>
"""
    os.makedirs("specimens", exist_ok=True)
    with open("specimens/specimen.html", "w", encoding="utf-8") as f:
        f.write(specimen_content)
    print("✓ Interactive specimen generated at specimens/specimen.html")

def main():
    print("=================================================================")
    print("  ANODRAGONDISPLAY — TYPOGRAPHY EXTRACTION & COMPILER PIPELINE   ")
    print("=================================================================")

    image_path = "sources/drawings/dragon_ano.jpg"
    if not os.path.exists(image_path):
        image_path = "/home/marcus/.gemini/antigravity/brain/bb0343d1-fd91-4fbf-a363-4f9a4b9970b5/.user_uploaded/media_1795401638767_4b7bda9d.jpg"

    # Step 1: Computer Vision
    vision_data_a, vision_data_b = extract_vision_glyphs(image_path)

    # Step 2 & 3: Glyph Modeling (Regular)
    builder_reg = GlyphBuilder(vision_data_a, variant="Regular")
    builder_reg.build_all()

    # Step 4 & 5: Compile Regular
    compile_fonts(builder_reg, font_family="AnoDragonDisplay", style="Regular")

    # Step 4 & 5 (Bonus): Compile Core Variant
    builder_core = GlyphBuilder(vision_data_b, variant="Core")
    builder_core.build_all()
    compile_fonts(builder_core, font_family="AnoDragonDisplay", style="Core")

    # Step 6: Generate Specimen
    generate_specimen_html()

    print("=================================================================")
    print("  ALL PHASES COMPLETED SUCCESSFULLY! ✨                          ")
    print("=================================================================")

if __name__ == '__main__':
    main()
