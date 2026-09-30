"""Makes sure assets/fonts/ has the three fonts every panel is drawn with.

Fonts already in the repo are left alone. Missing ones are downloaded (both are
open source, OFL): first as ready-made static files, and if that source is down,
from the Google Fonts repository as variable fonts cut to the right weight."""
import io, sys, urllib.request
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl"
FS = "https://cdn.jsdelivr.net/fontsource/fonts"

# file we need: (static source, variable source, axis settings for the variable one)
WANTED = {
    "Tektur-Medium.ttf": (f"{FS}/tektur@latest/latin-500-normal.ttf",
                          f"{GF}/tektur/Tektur%5Bwdth,wght%5D.ttf", {"wght": 500, "wdth": 100}),
    "GeistMono-Regular.ttf": (f"{FS}/geist-mono@latest/latin-400-normal.ttf",
                              f"{GF}/geistmono/GeistMono%5Bwght%5D.ttf", {"wght": 400}),
    "GeistMono-Bold.ttf": (f"{FS}/geist-mono@latest/latin-700-normal.ttf",
                           f"{GF}/geistmono/GeistMono%5Bwght%5D.ttf", {"wght": 700}),
}


def _download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "visor-sync"})
    return urllib.request.urlopen(req, timeout=30).read()


def _usable(data):
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(data))
    cmap = f.getBestCmap()
    return all(ord(c) in cmap for c in "AZaz09%:/.°")    # what the panels actually print


def fetch(name, static_url, var_url, axes):
    try:
        data = _download(static_url)
        if _usable(data):
            (FONTS / name).write_bytes(data)
            return "static download"
    except Exception as e:
        print(f"  {name}: static source failed ({e}), trying Google Fonts")
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    var = TTFont(io.BytesIO(_download(var_url)))
    inst = instancer.instantiateVariableFont(var, {k: v for k, v in axes.items() if k in [a.axisTag for a in var["fvar"].axes]})
    inst.save(str(FONTS / name))
    return "cut from the variable font"


if __name__ == "__main__":
    FONTS.mkdir(parents=True, exist_ok=True)
    failed = []
    for name, (static_url, var_url, axes) in WANTED.items():
        if (FONTS / name).exists():
            print(f"ok   {name}: already in the repo")
            continue
        try:
            print(f"ok   {name}: {fetch(name, static_url, var_url, axes)}")
        except Exception as e:
            failed.append(name)
            print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
