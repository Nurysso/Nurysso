#!/usr/bin/python3

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from html import escape

import aiohttp

from github_stats import Stats

# ── Layout ────────────────────────────────────────────────────────────────────
# One panel, three bands separated by hairlines. Everything aligns to PX.
W = 860
PX = 30                      # left/right content padding
CW = W - 2 * PX              # content width

HEAD_H = 58
HERO_H = 156                 # streak + headline numbers
LANG_H = 140                 # languages
ACT_H = 200                  # 30-day activity

Y_HERO = HEAD_H
Y_LANG = Y_HERO + HERO_H
Y_ACT = Y_LANG + LANG_H
TOTAL_H = Y_ACT + ACT_H

WINDOW = 30                  # days shown in the activity chart

# ── Type & colour ─────────────────────────────────────────────────────────────
# GitHub renders README images as <img>, which blocks web fonts, so these are
# system stacks. Numbers get a serif for character; everything else is sans.
SANS = '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif'
SERIF = '"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif'

DARK = dict(panel="#151b27", line="#27314a", ink="#e8ecf5", mute="#8a95ad",
            ember="#ffb454", dim="#53617f", track="#222b3f")
LIGHT = dict(panel="#ffffff", line="#dfe4ee", ink="#1a2130", mute="#677189",
             ember="#d97706", dim="#aab4c9", track="#e9edf4")


def _vars(p: dict) -> str:
    return ";".join(f"--{k}:{v}" for k, v in p.items())


STYLE_BODY = """
text{font-family:SANS;fill:var(--ink)}
.panel{fill:var(--panel);stroke:var(--line);stroke-width:1}
.rule{stroke:var(--line);stroke-width:1}
.name{font-size:19px;font-weight:650}
.h{font-size:13px;font-weight:600}
.sm{font-size:12px}
.xs{font-size:10.5px}
.mute{fill:var(--mute)}
.num{font-family:SERIF;font-weight:700;font-variant-numeric:lining-nums tabular-nums}
.hero{font-size:62px;fill:var(--ember)}
.val{font-size:34px}
.unit{font-family:SANS;font-size:15px;font-weight:500;fill:var(--mute)}
.track{fill:var(--track)}
.seg{stroke:var(--panel);stroke-width:2}
.b-streak{fill:var(--ember)}
.b-dim{fill:var(--dim)}
.tick{fill:var(--track)}
.ring{fill:none;stroke:var(--ember);stroke-width:1.6}
.span{stroke:var(--ember);stroke-width:3;stroke-linecap:round}
.grid{stroke:var(--line);stroke-width:1;stroke-dasharray:3 4}
.axis{stroke:var(--line);stroke-width:1}
@media (prefers-reduced-motion: no-preference){
  .bar{transform-box:fill-box;transform-origin:50% 100%;
       animation:rise 700ms cubic-bezier(.2,.8,.2,1) both}
  @keyframes rise{from{transform:scaleY(0)}to{transform:scaleY(1)}}
}
""".replace("SANS", SANS).replace("SERIF", SERIF)


def build_style(theme: str) -> str:
    """theme: 'dark' or 'light' (fixed colours) or 'auto' (follows OS setting)."""
    if theme == "dark":
        head = f":root{{{_vars(DARK)}}}"
    elif theme == "light":
        head = f":root{{{_vars(LIGHT)}}}"
    else:
        head = (f":root{{{_vars(DARK)}}}"
                f"@media (prefers-color-scheme: light){{:root{{{_vars(LIGHT)}}}}}")
    return head + STYLE_BODY

LANG_COLORS = {
    "Python": "#3572A5", "Rust": "#dea584", "Go": "#00ADD8",
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "C": "#6e7681",
    "C++": "#f34b7d", "Shell": "#89e051", "HTML": "#e34c26",
    "CSS": "#8957e5", "Nix": "#7e7eff", "Lua": "#3b5bdb",
    "Makefile": "#427819", "TOML": "#9c4221",
}


def lang_color(name: str) -> str:
    return LANG_COLORS.get(name, "#8b949e")


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def generate_output_folder() -> None:
    os.makedirs("generated", exist_ok=True)


def rule(y: float) -> str:
    return f'<line class="rule" x1="{PX}" y1="{y}" x2="{W - PX}" y2="{y}"/>'


# ── Header ────────────────────────────────────────────────────────────────────
def build_header(name: str, updated: str) -> str:
    return (
        f'<text class="name" x="{PX}" y="40">{escape(name)} on GitHub</text>'
        f'<text class="mute sm" x="{W - PX}" y="40" text-anchor="end">Updated {updated}</text>'
    )


# ── Band 1: streak (hero) + headline numbers ──────────────────────────────────
def build_hero(streak: dict, stars: int, contribs: int, repos: int) -> str:
    y0 = Y_HERO
    cur = streak["current_streak"]

    if streak["last_active"]:
        status = f'Last active {short_date(streak["last_active"])}'
    else:
        status = "No contributions in the past year"

    out = [
        rule(y0),
        f'<text class="mute sm" x="{PX}" y="{y0 + 34}">Current streak</text>',
        f'<text class="num hero" x="{PX}" y="{y0 + 92}">{cur}'
        f'<tspan class="unit" dx="8">{"day" if cur == 1 else "days"}</tspan></text>',
        f'<text class="sm" x="{PX}" y="{y0 + 118}">{status}</text>',
        f'<text class="mute xs" x="{PX}" y="{y0 + 135}">'
        f'One day off keeps it going. Two in a row ends it.</text>',
        f'<line class="rule" x1="350" y1="{y0 + 26}" x2="350" y2="{y0 + HERO_H - 26}"/>',
    ]

    longest = streak["longest_streak"]
    if streak["longest_start"]:
        longest_sub = f'{short_date(streak["longest_start"])} to {short_date(streak["longest_end"])}'
    else:
        longest_sub = "No streak yet"

    metrics = [
        (380, "Longest streak", f"{longest}", "day" if longest == 1 else "days", longest_sub),
        (540, "Stars earned", f"{stars:,}", "", f"across {repos} repositories"),
        (700, "Contributions", f"{contribs:,}", "", "all time"),
    ]
    for x, label, value, unit, sub in metrics:
        unit_el = f'<tspan class="unit" dx="6">{unit}</tspan>' if unit else ""
        out += [
            f'<text class="mute sm" x="{x}" y="{y0 + 34}">{label}</text>',
            f'<text class="num val" x="{x}" y="{y0 + 80}">{value}{unit_el}</text>',
            f'<text class="mute xs" x="{x}" y="{y0 + 104}">{sub}</text>',
        ]
    return "\n".join(out)


# ── Band 2: languages ─────────────────────────────────────────────────────────
def build_languages(scores: dict) -> str:
    y0 = Y_LANG
    MAX, COLS, ROW_H, BAR_H = 8, 4, 24, 8
    col_w = CW / COLS
    bar_y = y0 + 52

    total = sum(scores.values()) or 1
    top = sorted(scores.items(), key=lambda t: t[1], reverse=True)[:MAX]

    out = [
        rule(y0),
        f'<text class="h" x="{PX}" y="{y0 + 32}">Languages by commits</text>',
        f'<clipPath id="lang-clip"><rect x="{PX}" y="{bar_y}" width="{CW}" '
        f'height="{BAR_H}" rx="{BAR_H / 2}"/></clipPath>',
        f'<rect class="track" x="{PX}" y="{bar_y}" width="{CW}" height="{BAR_H}" rx="{BAR_H / 2}"/>',
        '<g clip-path="url(#lang-clip)">',
    ]

    cur = float(PX)
    for name, val in top:
        w = val / total * CW
        out.append(
            f'<rect class="seg" x="{cur:.1f}" y="{bar_y}" width="{w:.1f}" '
            f'height="{BAR_H}" fill="{lang_color(name)}"/>'
        )
        cur += w
    out.append("</g>")

    for i, (name, val) in enumerate(top):
        x = PX + (i % COLS) * col_w
        y = y0 + 96 + (i // COLS) * ROW_H
        out += [
            f'<circle cx="{x + 4.5:.1f}" cy="{y - 4}" r="4.5" fill="{lang_color(name)}"/>',
            f'<text class="sm" x="{x + 16:.1f}" y="{y}">{escape(name)}</text>',
            f'<text class="mute sm" x="{x + col_w - 20:.1f}" y="{y}" '
            f'text-anchor="end">{val / total * 100:.1f}%</text>',
        ]
    return "\n".join(out)


# ── Band 3: 30-day activity, coloured by streak membership ────────────────────
def build_activity(daily: list, streak: dict, today: date) -> str:
    y0 = Y_ACT
    plot_l, plot_r = PX + 28, W - PX
    pw = plot_r - plot_l
    baseline = y0 + 150
    ph = 84
    top = baseline - ph
    col = pw / WINDOW
    bw = min(14.0, col * 0.58)

    first = today - timedelta(days=WINDOW - 1)
    counts = {d["date"]: d["count"] for d in daily}
    days = [first + timedelta(days=i) for i in range(WINDOW)]
    values = [counts.get(d.isoformat(), 0) for d in days]
    peak = max(values) or 1

    s_start = date.fromisoformat(streak["current_start"]) if streak["current_start"] else None
    s_end = date.fromisoformat(streak["current_end"]) if streak["current_end"] else None
    grace = set(streak["grace_dates"])

    def cx(i: int) -> float:
        return plot_l + i * col + col / 2

    out = [rule(y0), f'<text class="h" x="{PX}" y="{y0 + 32}">Last {WINDOW} days</text>']

    # legend, right-aligned on the title baseline
    legend = [("streak", "In streak"), ("dim", "Other days"), ("ring", "Day off, streak kept")]
    x = float(W - PX)
    ly = y0 + 32
    for kind, label in reversed(legend):
        text_w = len(label) * 6.2
        x -= text_w
        out.append(f'<text class="mute sm" x="{x:.1f}" y="{ly}">{label}</text>')
        x -= 14
        if kind == "ring":
            out.append(f'<circle class="ring" cx="{x + 4.5:.1f}" cy="{ly - 4}" r="4"/>')
        else:
            out.append(f'<rect class="b-{kind}" x="{x:.1f}" y="{ly - 9}" width="9" height="9" rx="2"/>')
        x -= 20

    # scale
    out += [
        f'<line class="grid" x1="{plot_l}" y1="{top}" x2="{plot_r}" y2="{top}"/>',
        f'<text class="mute xs" x="{plot_l - 8}" y="{top + 4}" text-anchor="end">{peak}</text>',
        f'<line class="axis" x1="{plot_l}" y1="{baseline}" x2="{plot_r}" y2="{baseline}"/>',
    ]

    # bars / ticks / grace rings
    for i, (d, v) in enumerate(zip(days, values)):
        x0 = cx(i) - bw / 2
        iso = d.isoformat()
        if v > 0:
            h = max(3.0, v / peak * ph)
            in_streak = s_start is not None and s_start <= d <= s_end
            cls = "b-streak" if in_streak else "b-dim"
            out.append(
                f'<rect class="bar {cls}" style="animation-delay:{i * 22}ms" '
                f'x="{x0:.1f}" y="{baseline - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3">'
                f'<title>{short_date(iso)}: {v} contribution{"s" if v != 1 else ""}</title></rect>'
            )
        elif iso in grace:
            out.append(f'<circle class="ring" cx="{cx(i):.1f}" cy="{baseline - 7}" r="4.5">'
                       f'<title>{short_date(iso)}: day off, streak kept</title></circle>')
        else:
            out.append(f'<rect class="tick" x="{x0:.1f}" y="{baseline - 2}" '
                       f'width="{bw:.1f}" height="2" rx="1"/>')

    # bracket under the axis showing where the current streak sits in this window
    if s_start is not None:
        i0 = max(0, (s_start - first).days)
        i1 = min(WINDOW - 1, (s_end - first).days)
        if i1 >= 0:
            out.append(f'<line class="span" x1="{cx(i0) - bw / 2:.1f}" y1="{baseline + 10}" '
                       f'x2="{cx(i1) + bw / 2:.1f}" y2="{baseline + 10}"/>')

    # date labels
    for i, d in enumerate(days):
        if i % 5 == 0 or i == WINDOW - 1:
            out.append(f'<text class="mute xs" x="{cx(i):.1f}" y="{baseline + 30}" '
                       f'text-anchor="middle">{short_date(d.isoformat())}</text>')
    return "\n".join(out)


# ── Assemble ──────────────────────────────────────────────────────────────────
def render_svg(name, stars, contribs, repos, commit_langs, daily, streak, now=None, theme="auto") -> str:
    now = now or datetime.now(timezone.utc)
    parts = [
        f'<svg width="{W}" height="{TOTAL_H}" viewBox="0 0 {W} {TOTAL_H}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="GitHub stats: {streak["current_streak"]} day current streak, '
        f'{stars:,} stars, {contribs:,} contributions">',
        f'<title>{escape(name)} on GitHub</title>',
        f'<style>{build_style(theme)}</style>',
        f'<rect class="panel" x="1" y="1" width="{W - 2}" height="{TOTAL_H - 2}" rx="16"/>',
        build_header(name, short_date(now.date().isoformat()) + f", {now.year}"),
        build_hero(streak, stars, contribs, repos),
        build_languages(commit_langs),
        build_activity(daily, streak, now.date()),
        "</svg>",
    ]
    return "\n".join(parts)


async def generate_combined_svg(s: Stats) -> None:
    data = dict(
        name=await s.name,
        stars=await s.stargazers,
        contribs=await s.total_contributions,
        repos=len(await s.repos),
        commit_langs=await s.languages_by_commits,
        daily=await s.daily_contributions,
        streak=await s.streak_stats,
    )
    generate_output_folder()
    # fixed-colour files for the README's <picture>
    for theme, filename in (("dark", "github-stats-dark.svg"),
                            ("light", "github-stats-light.svg")):
        path = f"generated/{filename}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_svg(theme=theme, **data))
        print(f"✓ {path}  ({W}×{TOTAL_H})")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main() -> None:
    token = os.getenv("ACCESS_TOKEN")
    if not token:
        raise RuntimeError("ACCESS_TOKEN required")
    user = os.getenv("GITHUB_USERNAME") or os.getenv("GITHUB_ACTOR")
    if not user:
        raise RuntimeError("GITHUB_USERNAME or GITHUB_ACTOR required")

    ex_repos = os.getenv("EXCLUDED")
    ex_langs = os.getenv("EXCLUDED_LANGS")
    raw_fork = os.getenv("EXCLUDE_FORKED_REPOS", "")

    async with aiohttp.ClientSession() as session:
        s = Stats(
            user, token, session,
            exclude_repos={x.strip() for x in ex_repos.split(",")} if ex_repos else None,
            exclude_langs={x.strip() for x in ex_langs.split(",")} if ex_langs else None,
            ignore_forked_repos=bool(raw_fork) and raw_fork.strip().lower() != "false",
        )
        await generate_combined_svg(s)


if __name__ == "__main__":
    asyncio.run(main())
