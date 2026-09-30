"""Rebuilds the visor hero around one orchestrated moment: the name being decoded.

It reuses the name's own glyph outlines from the panel, so the typeface stays exactly
what was designed, and adds:
  - a scanning beam that crosses the lens; each letter it passes scrambles through the
    name's other letters, then locks solid
  - the target brackets, rangefinder and subtitle landing on the last lock
  - an idle re-scan every 11s: the beam sweeps again, letters twitch as it passes,
    and the red and cyan fringe jolts for a beat
  - depth in the city below: two skyline layers drift at different speeds, windows flicker
Everything rests in its final state, so reduced motion and still renders read cleanly.

Usage:  python visor_name_fx.py in.svg out.svg
Input is the original visor (with the plain <g class="nm"> name). live_overlays.py
adds the live "last signal" line on top afterwards."""
import random, re, sys
from pathlib import Path

RED, CYAN, WHITE = "#FF2D46", "#5CE1FF", "#EEF2FA"
NAME = "VARUNBANSAL"            # glyph order in the panel (the space draws nothing)
START = 1.95                    # intro: when the beam enters
LETTER = 0.085                  # intro: beam time per letter
FRAMES, FRAME = 4, 0.055        # scramble frames per letter and their length
PERIOD = 11.0                   # idle re-scan cycle
SWEEP = 1.1                     # idle beam crossing time
rnd = random.Random(99)


# ---------------------------------------------------------------- geometry

def bbox(d):
    """Bounds of an absolute path from the font pen (M L H V Q Z only)."""
    xs, ys, x, y = [], [], 0.0, 0.0
    for cmd, args in re.findall(r"([MLHVQZ])([^MLHVQZ]*)", d):
        n = [float(v) for v in re.findall(r"-?\d*\.?\d+", args)]
        if cmd == "H":
            for v in n:
                x = v; xs.append(x); ys.append(y)
        elif cmd == "V":
            for v in n:
                y = v; xs.append(x); ys.append(y)
        elif cmd in "MLQ":
            for k in range(0, len(n) - 1, 2):
                x, y = n[k], n[k + 1]; xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def split_name(doc):
    m = re.search(r'<g class="nm"><path d="([^"]+)"[^>]*/></g>', doc)
    if not m:
        raise SystemExit("plain name group not found: pass the original visor.svg")
    parts = m.group(1).split(" M")
    gs = [p if i == 0 else "M" + p for i, p in enumerate(parts)]
    if len(gs) != len(NAME):
        raise SystemExit(f"expected {len(NAME)} glyphs for {NAME}, found {len(gs)}; update NAME")
    return m, gs


# ---------------------------------------------------------------- skyline depth

def skyline_depth(doc):
    """Wraps the far and near skyline layers so they can drift, and flickers some windows."""
    far0 = doc.index('<rect x="-20" y="372"')
    near0 = doc.rindex("<rect", 0, doc.index('fill="#070C1A"'))
    haze = doc.index('<rect y="260" width="1200" height="240" fill="url(#haze)"')

    def flicker(block):
        def f(m):
            if rnd.random() < .22:
                return m.group(0).replace("<rect ", f'<rect class="wn" style="animation-delay:{rnd.uniform(0, 6):.2f}s" ', 1)
            return m.group(0)
        return re.sub(r'<rect x="[^"]+" y="[^"]+" width="2" height="3"[^>]*/>', f, block)

    return (doc[:far0] + f'<g class="far">{flicker(doc[far0:near0])}</g>'
            f'<g class="near">{flicker(doc[near0:haze])}</g>' + doc[haze:])


# ---------------------------------------------------------------- the name

def build(doc):
    doc = skyline_depth(doc)
    m, gs = split_name(doc)
    boxes = [bbox(g) for g in gs]
    X0, TOP = min(b[0] for b in boxes), min(b[1] for b in boxes)
    X1, BASE = max(b[2] for b in boxes), max(b[3] for b in boxes)
    cx = [(b[0] + b[2]) / 2 for b in boxes]
    src = {}                                          # one outline per distinct letter
    for ch, g, c in zip(NAME, gs, cx):
        src.setdefault(ch, (g, c))
    whole = " ".join(gs)
    n = len(gs)
    t_lock = [START + i * LETTER + FRAMES * FRAME for i in range(n)]
    lock_at = t_lock[-1] + .15
    mid = (X0 + X1) / 2

    defs = ['<defs>']
    for ch, (g, _) in src.items():
        defs.append(f'<path id="nm-{ch}" d="{g}"/>')
    defs.append(
        f'<clipPath id="nmc"><path d="{whole}"/></clipPath>'
        f'<pattern id="nml" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="4" height="1.2" fill="#05070E" opacity=".26"/></pattern>'
        f'<linearGradient id="nmf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/>'
        f'<stop offset=".62" stop-color="{WHITE}"/><stop offset="1" stop-color="#B9C6E4"/></linearGradient>'
        f'<linearGradient id="bm" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
        f'<stop offset=".82" stop-color="{CYAN}" stop-opacity=".2"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".85"/></linearGradient>'
        f'<filter id="nmb" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="9"/></filter>'
        '</defs>')

    css, out = [], ["".join(defs)]
    out.append(f'<path class="nmglow" d="{whole}" fill="{CYAN}" opacity=".22" filter="url(#nmb)"/>')
    out.append(f'<g class="ghin"><g class="gh ghr"><path d="{whole}" fill="{RED}" opacity=".6"/></g>'
               f'<g class="gh ghc"><path d="{whole}" fill="{CYAN}" opacity=".5"/></g></g>')

    idle0 = lock_at + 3.0                             # first re-scan
    pass_at = [(cx[i] - X0) / (X1 - X0) * SWEEP for i in range(n)]
    pct = lambda s: f"{s / PERIOD * 100:.3f}%"

    for i, (ch, g) in enumerate(zip(NAME, gs)):
        pool = [c for c in src if c != ch]
        # intro scramble: other letters of the name flicker in cyan at this letter's centre
        for k in range(FRAMES):
            pc = rnd.choice(pool)
            dx = cx[i] - src[pc][1]
            t = START + i * LETTER + k * FRAME
            out.append(f'<use class="sc" href="#nm-{pc}" transform="translate({dx:.1f} 0)" '
                       f'style="animation-delay:{t:.3f}s" fill="{CYAN}"/>')
        # idle twitch: two frames while the re-scan beam passes
        a, b = pass_at[i], pass_at[i] + 2 * FRAME
        for k, pc in enumerate(rnd.sample(pool, 2)):
            dx = cx[i] - src[pc][1]
            s0, s1 = a + k * FRAME, a + (k + 1) * FRAME
            css.append(f"@keyframes q{i}{k}{{0%,{pct(s0)}{{opacity:0}}{pct(s0 + .001)},{pct(s1)}{{opacity:1}}"
                       f"{pct(s1 + .001)},100%{{opacity:0}}}}")
            out.append(f'<use class="sc2" href="#nm-{pc}" transform="translate({dx:.1f} 0)" fill="{CYAN}" '
                       f'style="animation:q{i}{k} {PERIOD}s steps(1) {idle0:.2f}s infinite"/>')
        css.append(f"@keyframes h{i}{{0%,{pct(a)}{{opacity:1}}{pct(a + .001)},{pct(b)}{{opacity:0}}"
                   f"{pct(b + .001)},100%{{opacity:1}}}}")
        out.append(f'<path d="{g}" fill="url(#nmf)" style="animation:lt .24s steps(3) {t_lock[i]:.3f}s backwards,'
                   f'h{i} {PERIOD}s steps(1) {idle0:.2f}s infinite"/>')

    out.append(f'<g clip-path="url(#nmc)"><rect x="{X0}" y="{TOP}" width="{X1 - X0:.1f}" '
               f'height="{BASE - TOP:.1f}" fill="url(#nml)"/></g>')

    # the beam: crosses with the decode, then sweeps again every cycle
    t0, t1 = TOP - 34, BASE + 30
    beam = (f'<rect x="-60" y="{t0}" width="60" height="{t1 - t0}" fill="url(#bm)"/>'
            f'<rect x="-1" y="{t0}" width="2" height="{t1 - t0}" fill="{CYAN}"/>'
            f'<rect x="-6" y="{t0}" width="12" height="2" fill="{CYAN}"/>'
            f'<rect x="-6" y="{t1 - 2}" width="12" height="2" fill="{CYAN}"/>')
    span = f"--x0:{X0 - 10:.1f}px;--x1:{X1 + 14:.1f}px"
    out.append(f'<g class="bmi" style="{span}">{beam}</g><g class="bmd" style="{span}">{beam}</g>')
    intro = (n - 1) * LETTER + FRAMES * FRAME
    css.append(f".bmi{{opacity:0;animation:bmi {intro:.2f}s linear {START:.2f}s}}"
               "@keyframes bmi{0%{opacity:1;transform:translateX(var(--x0))}90%{opacity:1}100%{opacity:0;transform:translateX(var(--x1))}}"
               f".bmd{{opacity:0;animation:bmd {PERIOD}s linear {idle0:.2f}s infinite}}"
               f"@keyframes bmd{{0%{{opacity:.85;transform:translateX(var(--x0))}}{pct(SWEEP)}{{opacity:.85;transform:translateX(var(--x1))}}"
               f"{pct(SWEEP + .01)},100%{{opacity:0;transform:translateX(var(--x1))}}}}")

    # rangefinder under the name
    ry = BASE + 16
    ticks = "".join(
        f'<rect x="{X0 + j * (X1 - X0) / 40:.1f}" y="{ry - (5 if j % 5 == 0 else 2)}" width="1" '
        f'height="{5 if j % 5 == 0 else 2}" fill="{CYAN}"/>' for j in range(41))
    out.append(f'<g class="rf" style="transform-origin:{mid:.1f}px {ry}px">'
               f'<rect x="{X0}" y="{ry}" width="{X1 - X0:.1f}" height="1" fill="{CYAN}" opacity=".5"/>'
               f'<g opacity=".55">{ticks}</g>'
               f'<path d="M{X0} {ry - 7}v14M{X1} {ry - 7}v14" stroke="{RED}" stroke-width="1.5"/>'
               f'<path d="M{mid - 5:.1f} {ry + 7}l5-6 5 6z" fill="{RED}"/></g>')

    doc = doc[:m.start()] + f'<g class="nm2" aria-hidden="true">{"".join(out)}</g>' + doc[m.end():]

    css.append(
        f".sc,.sc2{{opacity:0}}.sc{{animation:sc {FRAME}s steps(1)}}@keyframes sc{{0%,100%{{opacity:1}}}}"
        "@keyframes lt{0%{opacity:0}40%{opacity:.9}70%{opacity:.35}100%{opacity:1}}"
        f".ghr{{transform:translate(-1.5px,0);animation:glr {PERIOD}s steps(1) {idle0:.2f}s infinite}}"
        f".ghc{{transform:translate(1.5px,0);animation:glc {PERIOD}s steps(1) {idle0:.2f}s infinite}}"
        "@keyframes glr{0%,3%,100%{transform:translate(-1.5px,0)}.8%{transform:translate(-7px,1px)}1.6%{transform:translate(3px,-1px)}2.3%{transform:translate(-4px,0)}}"
        "@keyframes glc{0%,3%,100%{transform:translate(1.5px,0)}.8%{transform:translate(6px,-1px)}1.6%{transform:translate(-4px,1px)}2.3%{transform:translate(3px,0)}}"
        ".gh{opacity:.55}"
        f".ghin{{animation:fade .4s ease-out {lock_at:.2f}s backwards}}"
        f".nmglow{{animation:fade .8s ease-out {lock_at - .2:.2f}s backwards,br 4s ease-in-out {lock_at + .6:.2f}s infinite}}"
        "@keyframes br{50%{opacity:.1}}"
        f".rf{{animation:rf .7s cubic-bezier(.2,.9,.2,1) {lock_at - .1:.2f}s backwards}}@keyframes rf{{from{{transform:scaleX(0);opacity:0}}}}"
        ".far{animation:dr 18s ease-in-out infinite alternate}.near{animation:dr2 18s ease-in-out infinite alternate}"
        "@keyframes dr{from{transform:translateX(-6px)}to{transform:translateX(6px)}}"
        "@keyframes dr2{from{transform:translateX(14px)}to{transform:translateX(-14px)}}"
        ".wn{animation:wn 5s steps(1) infinite}@keyframes wn{62%{visibility:hidden}70%{visibility:visible}}"
    )
    doc = doc.replace("cubic-bezier(.2,.9,.2,1) 2.6s backwards}", f"cubic-bezier(.2,.9,.2,1) {lock_at - .45:.2f}s backwards}}", 1)
    doc = doc.replace(".sub{animation:fade .6s ease-out 3.4s backwards}", f".sub{{animation:fade .6s ease-out {lock_at + .35:.2f}s backwards}}", 1)
    return doc.replace("@media (prefers-reduced-motion", "".join(css) + "@media (prefers-reduced-motion", 1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    Path(sys.argv[2]).write_text(build(Path(sys.argv[1]).read_text()))
    print(f"{Path(sys.argv[2]).name}: visor rebuilt")
