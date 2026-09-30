"""Adds live GitHub readings to the hand-made panels without touching their design.

Each panel's clean design lives in assets/base/. Every run starts from that copy and
writes assets/<name>.svg with one live strip added. If you commit a redesigned panel,
it has no live strip yet, so the next run spots that and adopts it as the new base.
  visor.svg     - a fifth boot line (when and where you last pushed) and HUD readouts:
                  link strength from this week's activity, followers "in range" under
                  the radar, account uptime, and New Delhi weather and time by the coordinates
  m-*.svg       - a footer on each mission card: last push, commits in 30 days, stars
  briefing.svg  - a closing line: which repo has your attention this month
  loadout.svg   - a code-volume meter under each language chip
  signoff.svg   - when the next sync lands and how many followers are synced
Cards are linked to repos by the rules in CARDS. Set "repo" to pin one exactly.
If the API call fails, every panel keeps its last good version."""
import json, re, shutil, sys, urllib.request
from datetime import datetime, timedelta, timezone
from visor_font import Font, RED, CYAN, STEEL, WHITE, EDGE
from hud_stats import ASSETS, USER, _get, report, write_svg

BASE_DIR = ASSETS / "base"

# Which repos feed which card. "match" looks for any of the words in a repo's
# name or description; "language" rolls up every repo in that language.
CARDS = {
    "m-primeos": {"match": ["primeos", "qa-bench", "qabench", "qa bench"], "color": RED},
    "m-computer": {"match": ["computer", "voice assistant", "desktop assistant"], "color": CYAN},
    "m-lineage": {"match": ["lineage", "mido", "msm8953", "redmi"], "color": WHITE},
    "m-cpp": {"language": "C++", "color": STEEL},
}

QUERY = """
query($login:String!, $since:GitTimestamp!){ user(login:$login){
  createdAt followers{totalCount}
  contributionsCollection{ contributionCalendar{ weeks{ contributionDays{ date contributionCount } } } }
  repositories(ownerAffiliations:OWNER, first:100, orderBy:{field:PUSHED_AT, direction:DESC}){
    nodes{
      name description isFork pushedAt stargazerCount primaryLanguage{name}
      languages(first:10, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{name} } }
      defaultBranchRef{ target{ ... on Commit { history(since:$since){ totalCount } } } }
    }
  }
}}"""


def fetch_repos():
    return fetch_all()["repos"]


def fetch_all():
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    u = _get("https://api.github.com/graphql", {"query": QUERY, "variables": {"login": USER, "since": since}})["data"]["user"]
    repos = []
    for n in u["repositories"]["nodes"]:
        t = (n.get("defaultBranchRef") or {}).get("target") or {}
        repos.append({
            "name": n["name"], "desc": (n["description"] or ""), "fork": n["isFork"],
            "pushed": datetime.fromisoformat(n["pushedAt"].replace("Z", "+00:00")) if n["pushedAt"] else None,
            "stars": n["stargazerCount"], "lang": (n["primaryLanguage"] or {}).get("name"),
            "commits": (t.get("history") or {}).get("totalCount", 0),
            "langs": {e["node"]["name"]: e["size"] for e in ((n.get("languages") or {}).get("edges") or [])},
        })
    days = [d for w in u["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    return {
        "repos": repos,
        "followers": u["followers"]["totalCount"],
        "created": datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00")),
        "week": sum(d["contributionCount"] for d in days if d["date"] > week_ago),
        "weather": fetch_weather(),
    }


# WMO weather codes from Open-Meteo, in the few words a HUD would use
SKY = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
       51: "drizzle", 53: "drizzle", 55: "drizzle", 61: "rain", 63: "rain", 65: "heavy rain",
       80: "showers", 81: "showers", 82: "heavy showers", 95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm"}


def fetch_weather(lat=28.61, lon=77.21):
    """Current New Delhi weather from Open-Meteo (free, no key). None if it is unreachable."""
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               "&current=temperature_2m,weather_code")
        req = urllib.request.Request(url, headers={"User-Agent": "visor-sync"})
        c = json.load(urllib.request.urlopen(req, timeout=15))["current"]
        return {"temp": round(c["temperature_2m"]), "sky": SKY.get(c["weather_code"], "")}
    except Exception as e:
        print("  weather unavailable:", e)
        return None


def ago(when, now=None):
    s = ((now or datetime.now(timezone.utc)) - when).total_seconds()
    for unit, size in (("year", 31536000), ("month", 2592000), ("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= size:
            n = int(s // size)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def reading(rule, repos):
    """Returns what a card should show, or None when no repo backs it."""
    if rule.get("repo"):
        hits = [r for r in repos if r["name"].lower() == rule["repo"].lower()]
    elif rule.get("language"):
        hits = [r for r in repos if r["lang"] == rule["language"] and not r["fork"]]
    else:
        words = rule.get("match", [])
        hits = [r for r in repos if not r["fork"]
                and any(w in f"{r['name']} {r['desc']}".lower() for w in words)]
    hits = [r for r in hits if r["pushed"]]
    if not hits:
        return None
    latest = max(hits, key=lambda r: r["pushed"])
    return {
        "source": f"{len(hits)} repos" if len(hits) > 1 else latest["name"],
        "pushed": latest["pushed"], "commits": sum(r["commits"] for r in hits),
        "stars": sum(r["stars"] for r in hits),
    }


MARK = 'id="live-strip"'
# strips written before the marker existed, so an upgrade does not adopt them as base
LEGACY = ('aria-label="live repo reading"', '<g class="boot" style="animation-delay:2.15s">')


def _has_strip(doc):
    return MARK in doc or any(m in doc for m in LEGACY)


def _base(name):
    """The clean panel, so live strips never stack. A panel without a strip is a
    fresh design (first run, or you redesigned it) and becomes the new base."""
    src, base = ASSETS / f"{name}.svg", BASE_DIR / f"{name}.svg"
    if not base.exists() or not _has_strip(src.read_text()):
        BASE_DIR.mkdir(exist_ok=True)
        shutil.copy(src, base)
    return base.read_text()


def _inject(doc, strip):
    return re.sub(r"</svg>\s*$", strip + "</svg>", doc)


def card_strip(r, color, now=None):
    mono = Font("GeistMono-Regular.ttf")
    parts = [f"last push {ago(r['pushed'], now)}", f"{r['commits']} commit{'s' if r['commits'] != 1 else ''} in 30 days"]
    if r["stars"]:
        parts.append(f"{r['stars']} star{'s' if r['stars'] != 1 else ''}")
    parts.append(r["source"])
    size, sep, room = 11.5, 20, 520
    while len(parts) > 1 and sum(mono.width(p, size) for p in parts) + sep * (len(parts) - 1) > room - 46:
        parts.pop()  # drop the least important reading rather than run into the corner mark
    x, y = 46, 188
    out = [f'<circle class="bl" cx="36" cy="{y - 4}" r="3" fill="{color}"/>']
    for i, p in enumerate(parts):
        out.append(mono.text(p, size, x, y, WHITE if i == 0 else STEEL))
        x += mono.width(p, size) + sep
        if i < len(parts) - 1:
            out.append(f'<rect x="{x - sep / 2:.1f}" y="{y - 9}" width="1" height="11" fill="#1B2540"/>')
    return f'<g {MARK} aria-label="live repo reading">{"".join(out)}</g>'


def link(week):
    """Signal strength from contributions in the last 7 days: (lit bars of 5, label)."""
    if week == 0:
        return 0, "signal lost"
    if week < 5:
        return 2, "link weak"
    if week < 15:
        return 4, "link stable"
    return 5, "link strong"


def uptime(created, now):
    months = (now.year - created.year) * 12 + now.month - created.month - (now.day < created.day)
    y, m = divmod(max(months, 0), 12)
    return f"uptime {y}y {m}m" if y else f"uptime {m}m"


def visor_strip(repos, now=None, extra=None):
    mono = Font("GeistMono-Regular.ttf")
    now = now or datetime.now(timezone.utc)
    out = []
    pushed = [r for r in repos if r["pushed"]]
    if pushed:
        last = max(pushed, key=lambda r: r["pushed"])
        line = f"last signal: {ago(last['pushed'], now)}, {last['name']}"
        out.append(f'<g class="boot" style="animation-delay:2.15s">'
                   f'{mono.text(">", 12.75, 118.9, 196, CYAN)}{mono.text(line, 12.75, 134.2, 196, CYAN)}</g>')
    if extra:
        # under the radar: followers are the contacts in range, then account age
        f = extra["followers"]
        contacts = f"{f} contact{'s' if f != 1 else ''} in range"
        out.append(f'<g class="boot" style="animation-delay:3.5s">'
                   f'{mono.text(contacts, 11, 1050, 240, CYAN, "middle")}'
                   f'{mono.text(uptime(extra["created"], now), 11, 1050, 256, STEEL, "middle")}</g>')
        # by the coordinates: local weather and the time of this reading
        ist = now + timedelta(hours=5, minutes=30)
        w = extra.get("weather")
        right = (f"{w['temp']}\u00b0C {w['sky']}".strip() + "   " if w else "") + f"read {ist:%H:%M} IST"
        out.append(f'<g class="boot" style="animation-delay:3.7s">{mono.text(right, 12, 1029, 376, STEEL, "end")}</g>')
        # next to the signal bars: the live label and what it is based on
        _, label = link(extra["week"])
        basis = f"{extra['week']} contributions this week"
        out.append(mono.text(label, 12, 210.7, 396, STEEL))
        out.append(f'<g class="boot" style="animation-delay:3.7s">'
                   f'{mono.text(basis, 12, 210.7 + mono.width(label, 12) + 18, 396, "#56627F")}</g>')
    return f'<g {MARK}>{"".join(out)}</g>' if out else ""


def _visor_base(doc, extra):
    """Swaps the fixed "link stable" label for the live one and lights bars to match."""
    if not extra:
        return doc
    last = doc.rindex('class="sig"')
    i = doc.index("<path ", last)
    j = doc.index("/>", i) + 2
    doc = doc[:i] + doc[j:]                           # the designed label; the live one replaces it
    lit, k = link(extra["week"])[0], [0]

    def bar(m):
        k[0] += 1
        if k[0] <= lit:
            return m.group(0)
        return m.group(0).replace('class="sig"', 'class="sigoff"').replace('fill="#5CE1FF"', f'fill="{EDGE}"')
    return re.sub(r'<rect class="sig"[^>]*/>', bar, doc)


def apply(repos, now=None, extra=None):
    strip = visor_strip(repos, now, extra)
    write_svg(ASSETS / "visor.svg", _inject(_visor_base(_base("visor"), extra), strip))
    if extra:
        w = extra.get("weather")
        report("visor", True, f"{link(extra['week'])[1]}, {extra['followers']} in range, "
               + (f"{w['temp']}\u00b0C {w['sky']}" if w else "weather unavailable"), warn=not w)
    else:
        report("visor", True, "last signal line added" if strip else "no pushes found, left as designed")
    for name, rule in CARDS.items():
        try:
            r = reading(rule, repos)
            write_svg(ASSETS / f"{name}.svg", _inject(_base(name), card_strip(r, rule["color"], now) if r else ""))
        except Exception as e:
            report(name, False, f"{type(e).__name__}: {e}")
            continue
        report(name, True, f"reading from {r['source']}" if r
               else "no matching public repo; pin one with \"repo\" in CARDS", warn=r is None)
    apply_panels(repos, now or datetime.now(timezone.utc), extra)


# ---------------------------------------------------------------- the other panels

LOADOUT_CHIPS = [("C", 48, 36.4), ("C++", 92.4, 53.2), ("Kotlin", 153.6, 78.4), ("Java", 240, 61.6)]
SYNC_HOURS_UTC, SYNC_MINUTE = (0, 6, 12, 18), 17      # keep in step with the cron in visor-sync.yml


def briefing_strip(repos, now):
    mono = Font("GeistMono-Regular.ttf")
    own = [r for r in repos if not r["fork"] and r["commits"]]
    if own:
        top = max(own, key=lambda r: r["commits"])
        line = f"Current focus: {top['name']}, {top['commits']} commit{'s' if top['commits'] != 1 else ''} in the last 30 days."
    else:
        pushed = [r for r in repos if r["pushed"]]
        if not pushed:
            return ""
        last = max(pushed, key=lambda r: r["pushed"])
        line = f"Quiet month. Last push {ago(last['pushed'], now)} to {last['name']}."
    return (f'<g {MARK} class="ln" style="animation-delay:4.25s">'
            f'<circle class="bl" cx="352" cy="469" r="3.5" fill="{CYAN}"/>'
            f'{mono.text(line, 14, 364, 474, CYAN)}</g>')


def loadout_strip(repos):
    mono = Font("GeistMono-Regular.ttf")
    total = {}
    for r in repos:
        if not r["fork"]:
            for n, size in r["langs"].items():
                total[n] = total.get(n, 0) + size
    whole = sum(total.values())
    if not whole:
        return ""
    share = {n: total.get(n, 0) / whole for n, _, _ in LOADOUT_CHIPS}
    top = max(share.values()) or 1
    out = []
    for i, (n, x, w) in enumerate(LOADOUT_CHIPS):
        p = share[n]
        out.append(f'<rect x="{x}" y="168" width="{w}" height="2" rx="1" fill="{EDGE}"/>')
        if p:
            out.append(f'<rect class="mg" style="animation-delay:{.2 + i * .12:.2f}s;transform-origin:{x}px 0" x="{x}" y="168" '
                       f'width="{max(2, w * p / top):.1f}" height="2" rx="1" fill="{CYAN}"/>')
        out.append(mono.text(f"{p * 100:.0f}%" if p >= .005 else "<1%" if p else "0%", 10.5, x + w / 2, 186, STEEL, "middle"))
    style = "<style>.mg{animation:mg 1.2s cubic-bezier(.2,.9,.2,1) backwards}@keyframes mg{from{transform:scaleX(0)}}</style>"
    return f'<g {MARK} aria-label="code volume by language">{style}{"".join(out)}</g>'


def next_sync(now):
    for day in (0, 1):
        for h in SYNC_HOURS_UTC:
            t = (now + timedelta(days=day)).replace(hour=h, minute=SYNC_MINUTE, second=0, microsecond=0)
            if t > now + timedelta(minutes=5):
                return t
    return now + timedelta(hours=6)


def signoff_strip(now, extra):
    mono = Font("GeistMono-Regular.ttf")
    ist = next_sync(now) + timedelta(hours=5, minutes=30)
    line = f"Next sync around {ist:%H:%M} IST."
    if extra:
        f = extra["followers"]
        line += f" {f} follower{'s' if f != 1 else ''} already synced."
    return (f'<g {MARK} class="ln" style="animation-delay:1.9s">'
            f'{mono.text(line, 12, 201, 200, STEEL)}</g>')


def apply_panels(repos, now, extra):
    for name, strip, ok in (
            ("briefing", briefing_strip(repos, now), "current focus line added"),
            ("loadout", loadout_strip(repos), "language meters added"),
            ("signoff", signoff_strip(now, extra), "next sync line added")):
        try:
            write_svg(ASSETS / f"{name}.svg", _inject(_base(name), strip))
            report(name, True, ok if strip else "no data, left as designed", warn=not strip)
        except Exception as e:
            report(name, False, f"{type(e).__name__}: {e}")



if __name__ == "__main__":
    try:
        data = fetch_all()
    except Exception as e:
        report("overlays", False, f"{type(e).__name__}: {e}")
        sys.exit(0)
    apply(data["repos"], extra=data)
