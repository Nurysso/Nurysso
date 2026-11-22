# Palette and type shared by every generated README image, so they read as one set.

# GitHub renders README images as <img>, which blocks web fonts, so these are
# system stacks. Numbers get a serif for character; everything else is sans.
SANS = '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif'
SERIF = '"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif'
MONO = 'ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace'

DARK = dict(panel="#151b27", line="#27314a", ink="#e8ecf5", mute="#8a95ad",
            ember="#ffb454", dim="#53617f", track="#222b3f")
LIGHT = dict(panel="#ffffff", line="#dfe4ee", ink="#1a2130", mute="#677189",
             ember="#d97706", dim="#aab4c9", track="#e9edf4")


def _vars(p: dict) -> str:
    return ";".join(f"--{k}:{v}" for k, v in p.items())


def theme_vars(theme: str) -> str:
    """theme: 'dark' or 'light' (fixed colours) or 'auto' (follows OS setting)."""
    if theme == "dark":
        return f":root{{{_vars(DARK)}}}"
    if theme == "light":
        return f":root{{{_vars(LIGHT)}}}"
    return (f":root{{{_vars(DARK)}}}"
            f"@media (prefers-color-scheme: light){{:root{{{_vars(LIGHT)}}}}}")
