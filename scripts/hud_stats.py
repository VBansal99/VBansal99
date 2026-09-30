"""Fetches live GitHub numbers and draws two visor panels:
  assets/hud-stats.svg  - telemetry: counters, languages, 52-week signal trace
  assets/activity.svg   - mission log: latest public events, typed in like a terminal
  assets/upstream.svg   - upstream: pull requests merged into other people's projects
Run by .github/workflows/visor-sync.yml. If a fetch fails, that panel's old file is kept."""
import json, os, sys, time, urllib.error, urllib.request
from xml.dom import minidom
from datetime import date, datetime, timezone
from pathlib import Path
from visor_font import Font, svg, BASE, PANEL, EDGE, RED, CYAN, STEEL, WHITE

ASSETS = Path(__file__).resolve().parent.parent / "assets"
OUT, LOG_OUT, UP_OUT = ASSETS / "hud-stats.svg", ASSETS / "activity.svg", ASSETS / "upstream.svg"
USER = os.environ.get("GH_USER", "VBansal99")
DIM = "#3A4A70"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

QUERY = """
query($login:String!){ user(login:$login){
  followers{totalCount}
  repositories(ownerAffiliations:OWNER, isFork:false, first:100, privacy:PUBLIC){
    totalCount
    nodes{ stargazerCount languages(first:10, orderBy:{field:SIZE,direction:DESC}){ edges{ size node{name} } } }
  }
  contributionsCollection{ contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } } }
}}"""


def _get(url, body=None, tries=3):
    """GitHub call with retries: GraphQL often answers 502 or a partial error under load."""
    headers = {"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "User-Agent": "visor-sync"}
    if body:
        headers["Content-Type"] = "application/json"
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=headers)
            out = json.load(urllib.request.urlopen(req, timeout=30))
            if isinstance(out, dict) and out.get("errors") and not out.get("data"):
                raise RuntimeError("; ".join(e.get("message", "?") for e in out["errors"]))
            return out
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                raise  # bad token or user: retrying will not help
            if attempt == tries:
                raise
            print(f"  {url.split('/')[-1] or url}: {e}, retrying in {attempt * 5}s")
            time.sleep(attempt * 5)


# ---------------------------------------------------------------- run report

def report(panel, ok, detail, warn=False):
    """One line per panel in the log, a warning annotation on failure, a row in the run summary."""
    print(f"{'ok  ' if ok else 'FAIL'} {panel}: {detail}")
    if (warn or not ok) and os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title=Visor sync: {panel}::{detail}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        new = not Path(summary).exists() or not Path(summary).read_text().strip()
        with open(summary, "a") as f:
            if new:
                f.write("### Visor sync\n\n| panel | status | detail |\n|---|---|---|\n")
            f.write(f"| {panel} | {'updated' if ok else 'kept last good'} | {detail} |\n")


def write_svg(path, doc):
    """Writes only a well-formed SVG, so a bad render can never break the profile image."""
    try:
        minidom.parseString(doc)
    except Exception as e:
        raise RuntimeError(f"rendered SVG is malformed ({e})")
    path.write_text(doc)


def _synced():
    return datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


# ---------------------------------------------------------------- telemetry

def fetch():
    u = _get("https://api.github.com/graphql", {"query": QUERY, "variables": {"login": USER}})["data"]["user"]
    repos = u["repositories"]
    langs = {}
    for r in repos["nodes"]:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda x: -x[1])[:5]
    cal = u["contributionsCollection"]["contributionCalendar"]
    today = date.today().isoformat()
    weeks = [[d for d in w["contributionDays"] if d["date"] <= today] for w in cal["weeks"]]
    weeks = [w for w in weeks if w]
    days = [d for w in weeks for d in w]

    cur = longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"]:
            cur += 1
        elif i == 0:
            continue  # today may not have activity yet
        else:
            break

    by_day = [0] * 7
    for d in days:
        by_day[date.fromisoformat(d["date"]).weekday()] += d["contributionCount"]
    return {
        "contributions": cal["totalContributions"], "streak": cur, "longest": longest,
        "stars": sum(r["stargazerCount"] for r in repos["nodes"]),
        "repos": repos["totalCount"], "followers": u["followers"]["totalCount"],
        "langs": [(n, s * 100 / total) for n, s in top],
        "weeks": [(w[0]["date"], sum(d["contributionCount"] for d in w)) for w in weeks],
        "busiest": DAYS[by_day.index(max(by_day))] if any(by_day) else None,
        "synced": _synced(),
    }


def _sync_badge(b, mono, d, W):
    sync = f"last sync {d['synced']}" if d.get("synced") else "awaiting first sync"
    b.append(mono.text(sync, 13, W - 48, 60, STEEL, "end"))
    b.append(f'<circle class="bl" cx="{W - 60 - mono.width(sync, 13):.1f}" cy="56" r="4" '
             f'fill="{RED if d.get("synced") else STEEL}"/>')


def render(d):
    disp, mono, bold = Font("Tektur-Medium.ttf"), Font("GeistMono-Regular.ttf"), Font("GeistMono-Bold.ttf")
    W, H = 1200, 500
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{PANEL}" stroke="{EDGE}" stroke-width="2"/>',
         f'<rect class="sw" x="0" y="0" width="{W}" height="2" fill="{CYAN}" opacity=".35"/>',
         disp.text("Field telemetry", 24, 48, 62, WHITE)]
    _sync_badge(b, mono, d, W)

    # counters -----------------------------------------------------------
    streak, longest = d.get("streak"), d.get("longest")
    cells = [("contributions", d.get("contributions")), ("current streak", streak),
             ("longest streak", longest), ("stars earned", d.get("stars")),
             ("public repos", d.get("repos")), ("followers", d.get("followers"))]
    for i, (label, val) in enumerate(cells):
        cx, cy = 48 + (i % 3) * 205, 100 + (i // 3) * 105
        b.append(f'<rect x="{cx}" y="{cy}" width="190" height="90" rx="10" fill="{BASE}" stroke="{EDGE}"/>')
        b.append(f'<rect x="{cx}" y="{cy + 18}" width="3" height="54" fill="{RED if i == 1 else CYAN}"/>')
        v = "--" if val is None else f"{val:,}"
        b.append(disp.text(v, 34, cx + 20, cy + 50, WHITE))
        b.append(mono.text(label, 13, cx + 20, cy + 72, STEEL))
        if i == 1 and streak is not None and longest:
            # how close the current run is to the record, as a gauge in the corner
            r, gx, gy = 16, cx + 160, cy + 30
            circ = 2 * 3.14159 * r
            fill = circ * min(streak / longest, 1)
            b.append(f'<circle cx="{gx}" cy="{gy}" r="{r}" fill="none" stroke="{EDGE}" stroke-width="3"/>')
            b.append(f'<circle class="ga" cx="{gx}" cy="{gy}" r="{r}" fill="none" stroke="{RED}" stroke-width="3" '
                     f'stroke-linecap="round" stroke-dasharray="{fill:.1f} {circ:.1f}" '
                     f'transform="rotate(-90 {gx} {gy})" style="--c:{circ:.1f}"/>')
            pct = f"{min(streak / longest, 1) * 100:.0f}%"
            b.append(mono.text(pct, 9, gx, gy + 3, STEEL, "middle"))

    # languages ----------------------------------------------------------
    lx = 700
    b.append(mono.text("languages by code volume", 13, lx, 112, STEEL))
    langs = d.get("langs") or []
    colors = [RED, CYAN, WHITE, STEEL, DIM]
    if not langs:
        b.append(mono.text("syncing...", 15, lx, 150, STEEL))
    x = lx
    for (n, p), c in zip(langs, colors):
        w = max(4, 452 * p / 100)
        b.append(f'<rect class="gr" x="{x:.1f}" y="126" width="{w - 2:.1f}" height="10" fill="{c}"/>')
        x += w
    for i, ((n, p), c) in enumerate(zip(langs, colors)):
        y = 176 + i * 27
        b.append(f'<rect x="{lx}" y="{y - 10}" width="10" height="10" fill="{c}"/>')
        b.append(bold.text(n, 15, lx + 22, y, WHITE))
        b.append(mono.text(f"{p:.1f}%", 15, lx + 452, y, STEEL, "end"))

    # 52-week signal trace -------------------------------------------------
    top, base = 352, 452
    b.append(f'<rect x="48" y="{top - 44}" width="{W - 96}" height="1" fill="{EDGE}"/>')
    b.append(mono.text("52-week signal", 13, 48, top - 16, STEEL))
    weeks = d.get("weeks") or []
    if not weeks:
        b.append(mono.text("the trace draws after the first sync", 13, W / 2, (top + base) / 2 + 4, STEEL, "middle"))
        for k in range(53):  # idle noise floor so the panel still reads as a scope
            b.append(f'<rect x="{48 + k * 1104 / 53 + 3:.1f}" y="{base - 2}" width="14" height="2" fill="{DIM}"/>')
    else:
        peak = max(c for _, c in weeks) or 1
        pk = max(range(len(weeks)), key=lambda k: weeks[k][1])
        avg = sum(c for _, c in weeks) / len(weeks)
        note = f"avg {avg:.0f} a week, peak {weeks[pk][1]} in week of {date.fromisoformat(weeks[pk][0]):%d %b}"
        if d.get("busiest"):
            note += f", most active on {d['busiest']}s"
        b.append(mono.text(note, 13, W - 48, top - 16, STEEL, "end"))
        step = 1104 / len(weeks)
        bw = max(4, step - 6)
        for k, (start, c) in enumerate(weeks):
            h = max(2, (base - top) * c / peak)
            color = RED if k == pk else WHITE if k == len(weeks) - 1 else CYAN
            op = 1 if k in (pk, len(weeks) - 1) else .35 + .5 * c / peak
            b.append(f'<rect class="tr" style="animation-delay:{k * 18}ms" x="{48 + k * step + (step - bw) / 2:.1f}" '
                     f'y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="1.5" fill="{color}" opacity="{op:.2f}"/>')
            day = date.fromisoformat(start)
            if day.day <= 7 and k < len(weeks) - 2:
                b.append(mono.text(f"{day:%b}", 11, 48 + k * step, base + 22, DIM))
        ay = base - (base - top) * avg / peak
        b.append(f'<rect x="48" y="{ay:.1f}" width="{W - 96}" height="1" fill="{STEEL}" opacity=".5"/>')
    b.append(f'<rect x="48" y="{base}" width="{W - 96}" height="1" fill="{EDGE}"/>')

    style = (f".sw{{animation:sw 4s linear infinite}}@keyframes sw{{0%{{transform:translateY(0)}}100%{{transform:translateY({H - 4}px)}}}}"
             ".bl{animation:bl 1.4s infinite}@keyframes bl{50%{opacity:.2}}"
             ".gr{transform-origin:700px 0;animation:gr 1.6s ease-out both}@keyframes gr{from{transform:scaleX(0)}}"
             f".tr{{transform-origin:0 {base}px;animation:tr .7s cubic-bezier(.2,.9,.2,1) both}}@keyframes tr{{from{{transform:scaleY(0)}}}}"
             ".ga{animation:ga 1.4s ease-out both}@keyframes ga{from{stroke-dasharray:0 var(--c)}}")
    return svg(W, H, "".join(b), style, "GitHub telemetry for Varun Bansal")


# ---------------------------------------------------------------- mission log

def fetch_events(limit=6):
    raw = _get(f"https://api.github.com/users/{USER}/events/public?per_page=50")
    out = []
    for e in raw:
        p, repo = e.get("payload", {}), e["repo"]["name"]
        kind, text = None, None
        t = e["type"]
        if t == "PushEvent":
            n = p.get("size") or len(p.get("commits") or [])
            branch = (p.get("ref") or "").rsplit("/", 1)[-1]
            what = f"{n} commit{'s' if n != 1 else ''}" if n else "commits"
            kind, text = "push", f"pushed {what} to {repo}" + (f" on {branch}" if branch else "")
        elif t == "PullRequestEvent":
            pr = p.get("pull_request", {})
            act = "merged" if pr.get("merged") else p.get("action", "updated")
            kind, text = "pr", f"{act} PR #{pr.get('number', '?')} in {repo}"
        elif t == "CreateEvent":
            ref = p.get("ref_type")
            kind, text = "new", (f"created repository {repo}" if ref == "repository"
                                 else f"created {ref} {p.get('ref')} in {repo}")
        elif t == "ReleaseEvent":
            kind, text = "new", f"released {p.get('release', {}).get('tag_name', '')} of {repo}"
        elif t == "IssuesEvent":
            kind, text = "issue", f"{p.get('action')} issue #{p.get('issue', {}).get('number', '?')} in {repo}"
        elif t == "WatchEvent":
            kind, text = "star", f"starred {repo}"
        elif t == "ForkEvent":
            kind, text = "fork", f"forked {repo}"
        if kind:
            when = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
            out.append({"kind": kind, "text": text, "when": f"{when:%d %b %H:%M}"})
        if len(out) == limit:
            break
    return {"events": out, "synced": _synced()}


def render_log(d):
    disp, mono, bold = Font("Tektur-Medium.ttf"), Font("GeistMono-Regular.ttf"), Font("GeistMono-Bold.ttf")
    events = d.get("events")
    W = 1200
    H = 150 + 32 * max(len(events or []), 2)
    tags = {"push": CYAN, "pr": RED, "new": WHITE, "issue": RED, "star": STEEL, "fork": STEEL}
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{BASE}" stroke="{EDGE}" stroke-width="2"/>',
         disp.text("Mission log", 24, 48, 62, WHITE)]
    _sync_badge(b, mono, d, W)
    b.append(f'<rect x="48" y="84" width="{W - 96}" height="1" fill="{EDGE}"/>')

    if not events:
        msg = ("no public activity in the last 90 days" if events is not None
               else "the log fills in after the first sync")
        b.append(mono.text(f"> {msg}", 15, 48, 124, STEEL))
        y = 124
    else:
        for i, ev in enumerate(events):
            y = 124 + i * 32
            delay = f'style="animation-delay:{300 + i * 260}ms"'
            c = tags[ev["kind"]]
            g = [mono.text(ev["when"], 14, 48, y, STEEL),
                 f'<rect x="196" y="{y - 15}" width="62" height="20" rx="4" fill="none" stroke="{c}" opacity=".8"/>',
                 bold.text(ev["kind"], 12, 227, y - 1, c, "middle")]
            text = _fit(mono, ev["text"], 15, W - 96 - 230)
            g.append(mono.text(text, 15, 278, y, WHITE if i == 0 else "#C9D1E3"))
            b.append(f'<g class="ln" {delay}>{"".join(g)}</g>')
    cy = y + 32
    delay = 300 + len(events or []) * 260
    b.append(f'<g class="ln" style="animation-delay:{delay}ms">{mono.text(">", 15, 48, cy, RED)}'
             f'<rect class="cur" x="66" y="{cy - 13}" width="9" height="16" fill="{RED}"/></g>')
    style = (".bl{animation:bl 1.4s infinite}@keyframes bl{50%{opacity:.2}}"
             ".ln{animation:ln .35s ease-out backwards}@keyframes ln{from{opacity:0;transform:translateX(-10px)}}"
             ".cur{animation:bl 1s steps(1) infinite}")
    return svg(W, H, "".join(b), style, "Latest public GitHub activity for Varun Bansal")


# ---------------------------------------------------------------- upstream

UP_QUERY = """
query($merged:String!, $open:String!){
  merged: search(query:$merged, type:ISSUE, first:50){
    issueCount
    nodes{ ... on PullRequest { title number mergedAt repository{ nameWithOwner } } }
  }
  open: search(query:$open, type:ISSUE, first:1){ issueCount }
}"""


def fetch_upstream(limit=5):
    base = f"author:{USER} is:pr -user:{USER}"
    r = _get("https://api.github.com/graphql", {"query": UP_QUERY, "variables": {
        "merged": f"{base} is:merged sort:updated-desc", "open": f"{base} is:open"}})["data"]
    prs = [n for n in r["merged"]["nodes"] if n]
    prs.sort(key=lambda n: n["mergedAt"] or "", reverse=True)
    return {
        "merged": r["merged"]["issueCount"], "open": r["open"]["issueCount"],
        "projects": len({n["repository"]["nameWithOwner"] for n in prs}),
        "prs": [{"repo": n["repository"]["nameWithOwner"], "num": n["number"], "title": n["title"],
                 "when": f"{datetime.fromisoformat(n['mergedAt'].replace('Z', '+00:00')):%d %b %Y}"}
                for n in prs[:limit]],
        "synced": _synced(),
    }


def _fit(font, text, size, room):
    if font.width(text, size) <= room:
        return text
    while font.width(text + "...", size) > room and len(text) > 4:
        text = text[:-1]
    return text.rstrip() + "..."


def render_upstream(d):
    disp, mono, bold = Font("Tektur-Medium.ttf"), Font("GeistMono-Regular.ttf"), Font("GeistMono-Bold.ttf")
    prs = d.get("prs") or []
    W = 1200
    H = max(330, 130 + 58 * len(prs) + 30)
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{PANEL}" stroke="{EDGE}" stroke-width="2"/>',
         disp.text("Upstream", 24, 48, 62, WHITE)]
    _sync_badge(b, mono, d, W)
    b.append(mono.text("code merged into other people's projects", 13, 48 + disp.width("Upstream", 24) + 18,
                       60, STEEL))

    # counters: a single column, the headline number first
    cells = [("merged pull requests", d.get("merged"), RED), ("projects", d.get("projects"), CYAN),
             ("in review", d.get("open"), STEEL)]
    for i, (label, val, c) in enumerate(cells):
        cy = 100 + i * 70
        b.append(f'<rect x="48" y="{cy + 8}" width="3" height="44" fill="{c}"/>')
        b.append(disp.text("--" if val is None else f"{val:,}", 34 if i == 0 else 26, 66, cy + 38, WHITE))
        b.append(mono.text(label, 13, 66, cy + 58, STEEL))
    b.append(f'<rect x="330" y="100" width="1" height="{H - 140}" fill="{EDGE}"/>')

    lx, rx = 362, W - 48
    if not prs:
        msg = ("no merged pull requests outside your own repos yet" if d.get("synced")
               else "the list fills in after the first sync")
        b.append(mono.text(msg, 15, lx, 132, STEEL))
    for i, pr in enumerate(prs):
        y = 124 + i * 58
        g = [f'<rect x="{lx}" y="{y - 22}" width="{rx - lx}" height="48" rx="8" fill="{BASE}" stroke="{EDGE}"/>',
             f'<path d="M{lx + 18} {y - 8}l6 6 10-11" fill="none" stroke="{RED}" stroke-width="2" '
             f'stroke-linecap="round" stroke-linejoin="round"/>']
        tag = f"{pr['repo']} #{pr['num']}"
        g.append(bold.text(tag, 13, lx + 48, y - 6, CYAN))
        g.append(mono.text(pr["when"], 13, rx - 16, y - 6, STEEL, "end"))
        g.append(mono.text(_fit(mono, pr["title"], 14, rx - lx - 64), 14, lx + 48, y + 14, WHITE))
        b.append(f'<g class="ln" style="animation-delay:{200 + i * 180}ms">{"".join(g)}</g>')

    style = (".bl{animation:bl 1.4s infinite}@keyframes bl{50%{opacity:.2}}"
             ".ln{animation:ln .4s ease-out backwards}@keyframes ln{from{opacity:0;transform:translateX(-10px)}}")
    return svg(W, H, "".join(b), style, "Pull requests Varun Bansal has merged into other projects")


# ---------------------------------------------------------------- entry

def _try(label, fn, draw, path, detail):
    try:
        data = fn()
        write_svg(path, draw(data))
    except Exception as e:  # keep the last good panel
        report(label, False, f"{type(e).__name__}: {e}")
        return
    report(label, True, detail(data))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--placeholder":
        OUT.write_text(render({"repos": 36, "followers": 12}))
        LOG_OUT.write_text(render_log({}))
        UP_OUT.write_text(render_upstream({}))
        sys.exit()
    _try("telemetry", fetch, render, OUT,
         lambda d: f"{d['contributions']:,} contributions, streak {d['streak']}, {len(d['weeks'])} weeks traced")
    _try("mission log", fetch_events, render_log, LOG_OUT, lambda d: f"{len(d['events'])} event{'s' if len(d['events']) != 1 else ''}")
    _try("upstream", fetch_upstream, render_upstream, UP_OUT,
         lambda d: f"{d['merged']} merged PRs across {d['projects']} project{'s' if d['projects'] != 1 else ''}, {d['open']} in review")
