"""Isometric line drawings for the deck, in the style of the architecture stack (charcoal faces,
beige strokes, one red element). Writes assets/iso_ensemble.svg (model choices) and
assets/iso_sandbox.svg (privacy design).

Usage: python deck/tools/iso_draw.py
"""

from __future__ import annotations

import math
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
C30, S30 = math.cos(math.radians(30)), 0.5
TAN = "#C29B72"
FACE = {"top": "#33353A", "left": "#2E3034", "right": "#25272A"}
RED = {"top": "#D7262E", "left": "#B01F26", "right": "#8C1A20"}


class Drawing:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.xs: list[float] = []
        self.ys: list[float] = []

    def p(self, x: float, y: float, z: float = 0) -> tuple[float, float]:
        sx, sy = (x - y) * C30, (x + y) * S30 - z
        self.xs.append(sx)
        self.ys.append(sy)
        return sx, sy

    @staticmethod
    def pts(points) -> str:
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    def poly(self, points, fill="none", stroke=TAN, sw=1.6, extra="") -> None:
        self.items.append(f'<polygon points="{self.pts(points)}" fill="{fill}" stroke="{stroke}" '
                          f'stroke-width="{sw}" stroke-linejoin="round" {extra}/>')

    def box(self, x, y, z, w, d, h, red=False, cls="part") -> None:
        f, s = (RED, RED["top"]) if red else (FACE, TAN)
        self.items.append(f'<g class="{cls}">')
        self.poly([self.p(x + w, y, z), self.p(x + w, y + d, z), self.p(x + w, y + d, z + h), self.p(x + w, y, z + h)], f["right"], s)
        self.poly([self.p(x, y + d, z), self.p(x + w, y + d, z), self.p(x + w, y + d, z + h), self.p(x, y + d, z + h)], f["left"], s)
        self.poly([self.p(x, y, z + h), self.p(x + w, y, z + h), self.p(x + w, y + d, z + h), self.p(x, y + d, z + h)], f["top"], s)
        self.items.append("</g>")

    def wire(self, x, y, z, w, d, h, part="all", cls="part") -> None:
        """A dashed glass box with no faces. Draw part="back" before the objects inside it and
        part="front" after them, so the near edges pass in front of the contents."""
        back = [((x, y, z), (x + w, y, z)), ((x, y, z), (x, y + d, z)), ((x, y, z), (x, y, z + h))]
        front = [((x + w, y + d, z), (x + w, y, z)), ((x + w, y + d, z), (x, y + d, z)),
                 ((x + w, y + d, z), (x + w, y + d, z + h)), ((x + w, y, z), (x + w, y, z + h)),
                 ((x, y + d, z), (x, y + d, z + h)),
                 ((x, y, z + h), (x + w, y, z + h)), ((x + w, y, z + h), (x + w, y + d, z + h)),
                 ((x + w, y + d, z + h), (x, y + d, z + h)), ((x, y + d, z + h), (x, y, z + h))]
        edges = {"back": back, "front": front, "all": back + front}[part]
        self.items.append(f'<g class="{cls}" fill="none" stroke="{TAN}" stroke-width="1.6" stroke-dasharray="7 6">')
        for a, b in edges:
            (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
            self.items.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        self.items.append("</g>")

    def plate(self, w, d, t=14) -> None:
        self.box(0, 0, -t, w, d, t, cls="plate")
        self.items.append(f'<g class="grid" stroke="{TAN}" stroke-opacity="0.18" stroke-width="1">')
        for i in range(1, int(w // 40)):
            (x1, y1), (x2, y2) = self.p(i * 40, 0), self.p(i * 40, d)
            self.items.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        for j in range(1, int(d // 40)):
            (x1, y1), (x2, y2) = self.p(0, j * 40), self.p(w, j * 40)
            self.items.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        self.items.append("</g>")

    def flow(self, a, b, red=True, cls="flow") -> None:
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        col = RED["top"] if red else TAN
        self.items.append(f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" '
                          f'stroke-width="3" stroke-dasharray="2 9" stroke-linecap="round"/>')

    def label(self, anchor, dx, dy, text, side="end", underline=150, cls="lab") -> None:
        """Leader line from a world point to a label dx, dy away (screen units), with a rule under the text."""
        ax, ay = self.p(*anchor)
        lx, ly = ax + dx, ay + dy
        ux = lx - underline if side == "end" else lx + underline
        tx = lx - 4 if side == "end" else lx + 4
        self.xs += [ux, tx]
        self.ys += [ly - 30]
        self.items.append(
            f'<g class="{cls}"><circle cx="{ax:.1f}" cy="{ay:.1f}" r="3.5" fill="{TAN}"/>'
            f'<polyline points="{ax:.1f},{ay:.1f} {lx:.1f},{ly:.1f} {ux:.1f},{ly:.1f}" fill="none" stroke="{TAN}" stroke-width="1.4"/>'
            f'<text x="{tx:.1f}" y="{ly - 10:.1f}" text-anchor="{side}" font-family="IBM Plex Mono" font-size="22" '
            f'fill="{TAN}">{text}</text></g>')

    def save(self, name: str, pad: int = 24) -> None:
        x0, x1 = min(self.xs) - pad, max(self.xs) + pad
        y0, y1 = min(self.ys) - pad, max(self.ys) + pad
        w, h = x1 - x0, y1 - y0
        svg = (f'<svg class="iso" xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" '
               f'width="{w:.0f}" height="{h:.0f}" aria-hidden="true">' + "".join(self.items) + "</svg>")
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(name, f"{w:.0f} x {h:.0f}")


def ensemble() -> None:
    d = Drawing()
    d.plate(560, 330)
    # AdaBoost: weak learners added one after another (thin slabs)
    for i in range(5):
        d.box(30 + i * 3, 50 + i * 3, i * 30, 84 - i * 6, 84 - i * 6, 16)
    # Bagging: models on bootstrap samples (a cluster of small blocks)
    for (x, y, h) in [(160, 50, 70), (205, 50, 110), (160, 95, 120), (205, 95, 80)]:
        d.box(x, y, 0, 38, 38, h)
    # Stacking: base learners under one meta-learner
    d.box(290, 50, 0, 90, 90, 60)
    d.box(296, 56, 60, 78, 78, 46)
    d.box(312, 72, 106, 46, 46, 30)
    # Voting: three different models side by side (KNN, LR, SVM)
    for i in range(3):
        d.box(420 + i * 32, 50, 0, 24, 90, 140)
    # Flows into the mean score
    for fx in (72, 202, 335, 465):
        d.flow((fx, 140, 0), (300, 260, 60))
    d.box(270, 230, 0, 60, 60, 60, red=True, cls="part hot")
    d.label((72, 92, 136), -60, -60, "AdaBoost", "end", 140)
    d.label((179, 114, 120), -30, -130, "Bagging", "end", 130)
    d.label((335, 95, 136), 20, -110, "Stacking", "start", 150)
    d.label((496, 95, 140), 50, -50, "Voting", "start", 110)
    d.label((330, 290, 30), 90, 60, "mean score", "start", 170)
    d.save("iso_ensemble.svg")


def sandbox() -> None:
    d = Drawing()
    d.plate(600, 360)
    # Host laptop: base and screen; it shows the dashboard and never opens the page
    d.box(40, 200, 0, 190, 130, 10)
    d.box(40, 200, 10, 8, 130, 110)
    # Sandbox VM: a glass box with the suspicious page inside
    d.wire(330, 40, 0, 230, 220, 190, part="back")
    d.box(355, 70, 0, 40, 40, 26)
    d.box(410, 110, 0, 70, 70, 70, red=True, cls="part hot")
    d.wire(330, 40, 0, 230, 220, 190, part="front")
    # Only a screenshot and page facts travel back to the host
    d.flow((330, 160, 60), (200, 250, 30), red=False)
    d.label((560, 40, 190), 60, -40, "Sandbox VM", "start", 170)
    d.label((445, 180, 35), 120, 80, "suspicious page", "start", 210)
    d.label((48, 330, 120), -60, -40, "host laptop", "end", 170)
    d.label((265, 205, 45), -70, 175, "screenshot and facts only", "end", 340)
    d.save("iso_sandbox.svg")


if __name__ == "__main__":
    ensemble()
    sandbox()
