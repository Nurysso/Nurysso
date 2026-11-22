#!/usr/bin/python3
"""README banner: my projects drawn as a call graph rooted at my name.

Static: no API calls, so run it by hand after editing TREE.
    python3 generate_banner.py
"""

import os
from html import escape

from theme import MONO, SANS, SERIF, theme_vars

# Each project is a call out of the root; its parts are calls out of it.
# The hot project gets the ember path, like a profiler's hottest call chain.
TREE = [
    ("eulix()", True, [
        ("prism()", "call graphs from syntax"),
        ("ehnas()", "retrieval with no model"),
        ("mcp()", "context for coding agents"),
    ]),
    ("vanish()", False, [("undo()", "rm with an undo button")]),
    ("tyr()", False, [("classify()", "sorts files with local ML")]),
    ("hecate()", False, [("theme()", "Hyprland that themes itself")]),
]

NAME = "Nurysso"
ROLE = ["Systems engineer.", "Compilers, code analysis,", "developer tooling."]

# ── Layout ────────────────────────────────────────────────────────────────────
W = 860                      # same width as the stats card
ROW = 28                     # one leaf per row
GROUP_GAP = 10               # extra space after the hot project's group
PAD_Y = 46

ROOT_X = 232                 # the name is right-aligned just left of this
PROJ_X = 330
LEAF_X = 490
NOTE_X = 610

PROJ_PX, LEAF_PX, NOTE_PX = 14, 13, 11
MONO_EM = 0.6                # advance width of one monospace glyph, in em

# ── Motion: one reveal, root outward ─────────────────────────────────────────
DRAW_MS = 520
STAGGER_MS = 70
DEPTH_MS = 420               # leaf edges start once project edges have landed


def label_end(x: float, text: str, px: int) -> float:
    return x + len(text) * px * MONO_EM


def curve(x1: float, y1: float, x2: float, y2: float) -> str:
    mx = (x1 + x2) / 2
    return f"M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"


def layout():
    """Rows top to bottom; each project sits level with the middle of its leaves."""
    y = PAD_Y
    projects = []
    for name, hot, leaves in TREE:
        leaf_rows = []
        for leaf, note in leaves:
            leaf_rows.append((leaf, note, y))
            y += ROW
        mid = (leaf_rows[0][2] + leaf_rows[-1][2]) / 2
        projects.append((name, hot, mid, leaf_rows))
        if hot:
            y += GROUP_GAP
    height = y - ROW + PAD_Y
    return projects, height


STYLE_BODY = """
text{font-family:SANS;fill:var(--ink)}
.panel{fill:var(--panel);stroke:var(--line);stroke-width:1}
.name{font-family:SERIF;font-size:42px;font-weight:700}
.role{font-size:12.5px;fill:var(--mute)}
.fn{font-family:MONO}
.proj{font-size:PROJ_PXpx;font-weight:600}
.leaf{font-size:LEAF_PXpx}
.note{font-family:MONO;font-size:NOTE_PXpx;fill:var(--dim)}
.edge{fill:none;stroke:var(--dim);stroke-width:1.4}
.edge.hot{stroke:var(--ember);stroke-width:2}
.node{fill:var(--panel);stroke:var(--dim);stroke-width:1.4}
.node.hot{fill:var(--ember);stroke:var(--ember)}
.root{fill:var(--ember)}
@media (prefers-reduced-motion: no-preference){
  .edge{stroke-dasharray:1;animation:draw DRAW_MSms cubic-bezier(.3,.7,.2,1) backwards}
  .in{animation:show 260ms ease-out backwards}
  @keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
  @keyframes show{from{opacity:0}to{opacity:1}}
}
"""
for key, val in dict(SANS=SANS, SERIF=SERIF, MONO=MONO, PROJ_PX=PROJ_PX, LEAF_PX=LEAF_PX,
                     NOTE_PX=NOTE_PX, DRAW_MS=DRAW_MS).items():
    STYLE_BODY = STYLE_BODY.replace(key, str(val))


def delay(ms: float) -> str:
    return f'style="animation-delay:{ms:.0f}ms"'


def render_svg(theme: str) -> str:
    projects, H = layout()
    # the root dot doubles as the name's full stop; lift it so name + role sit centred
    root_y = H / 2 - 22
    out = [
        f'<svg width="{W}" height="{H:.0f}" viewBox="0 0 {W} {H:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{NAME}: {", ".join(p[0].rstrip("()") for p in projects)}">',
        f"<title>{NAME}</title>",
        f"<style>{theme_vars(theme)}{STYLE_BODY}</style>",
        f'<rect class="panel" x="1" y="1" width="{W - 2}" height="{H - 2:.0f}" rx="16"/>',
    ]

    # name block, right-aligned against the root so it lines up whatever the font
    base = root_y + 5
    out.append(f'<text class="name" x="{ROOT_X - 12}" y="{base:.1f}" text-anchor="end">{NAME}</text>')
    for i, line in enumerate(ROLE):
        out.append(f'<text class="role" x="{ROOT_X - 12}" y="{base + 28 + i * 18:.1f}" '
                   f'text-anchor="end">{escape(line)}</text>')

    edges, marks = [], []
    for i, (name, hot, py, leaves) in enumerate(projects):
        hot_cls = " hot" if hot else ""
        t0 = i * STAGGER_MS
        landed = t0 + DRAW_MS * 0.8
        edges.append(f'<path class="edge{hot_cls}" pathLength="1" {delay(t0)} '
                     f'd="{curve(ROOT_X, root_y, PROJ_X - 6, py)}"/>')
        marks += [
            f'<circle class="node{hot_cls} in" {delay(landed)} cx="{PROJ_X}" cy="{py:.1f}" r="4.5"/>',
            f'<text class="fn proj in" {delay(landed)} x="{PROJ_X + 12}" y="{py + 5:.1f}">{escape(name)}</text>',
        ]

        start_x = label_end(PROJ_X + 12, name, PROJ_PX) + 10
        for j, (leaf, note, ly) in enumerate(leaves):
            t1 = DEPTH_MS + t0 + j * STAGGER_MS
            leaf_landed = t1 + DRAW_MS * 0.8
            edges.append(f'<path class="edge{hot_cls}" pathLength="1" {delay(t1)} '
                         f'd="{curve(start_x, py, LEAF_X - 5, ly)}"/>')
            marks += [
                f'<circle class="node{hot_cls} in" {delay(leaf_landed)} cx="{LEAF_X}" cy="{ly:.1f}" r="3.5"/>',
                f'<text class="fn leaf in" {delay(leaf_landed)} x="{LEAF_X + 11}" y="{ly + 4.5:.1f}">{escape(leaf)}</text>',
                f'<text class="note in" {delay(leaf_landed + 120)} x="{NOTE_X}" y="{ly + 4:.1f}">// {escape(note)}</text>',
            ]

    out += edges + marks
    out.append(f'<circle class="root" cx="{ROOT_X}" cy="{root_y:.1f}" r="6"/>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    os.makedirs("generated", exist_ok=True)
    # fixed-colour files for the README's <picture>
    for theme in ("dark", "light"):
        path = f"generated/banner-{theme}.svg"
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_svg(theme))
        print(f"✓ {path}")


if __name__ == "__main__":
    main()
