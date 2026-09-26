"""Fetches live GitHub numbers and draws assets/hud-stats.svg in the visor style.
Run by .github/workflows/visor-sync.yml. If the API call fails, the old file is kept."""
import json, os, sys, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from visor_font import Font, svg, BASE, PANEL, EDGE, RED, CYAN, STEEL, WHITE

OUT = Path(__file__).resolve().parent.parent / "assets" / "hud-stats.svg"
USER = os.environ.get("GH_USER", "VBansal99")

QUERY = """
query($login:String!){ user(login:$login){
  followers{totalCount}
  repositories(ownerAffiliations:OWNER, isFork:false, first:100, privacy:PUBLIC){
    totalCount
    nodes{ stargazerCount languages(first:10, orderBy:{field:SIZE,direction:DESC}){ edges{ size node{name} } } }
  }
  contributionsCollection{ contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } } }
}}"""


def fetch():
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    u = json.load(urllib.request.urlopen(req, timeout=30))["data"]["user"]
    repos = u["repositories"]
    langs = {}
    for r in repos["nodes"]:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda x: -x[1])[:5]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    days = [d for d in days if d["date"] <= date.today().isoformat()]
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
    return {
        "contributions": cal["totalContributions"], "streak": cur, "longest": longest,
        "stars": sum(r["stargazerCount"] for r in repos["nodes"]),
        "repos": repos["totalCount"], "followers": u["followers"]["totalCount"],
        "langs": [(n, s * 100 / total) for n, s in top],
        "synced": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
    }


def render(d):
    disp, mono, bold = Font("Tektur-Medium.ttf"), Font("GeistMono-Regular.ttf"), Font("GeistMono-Bold.ttf")
    W, H = 1200, 330
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{PANEL}" stroke="{EDGE}" stroke-width="2"/>']
    b.append(f'<rect class="sw" x="0" y="0" width="{W}" height="2" fill="{CYAN}" opacity=".35"/>')
    b.append(disp.text("Field telemetry", 24, 48, 62, WHITE))
    sync = f"last sync {d['synced']}" if d.get("synced") else "awaiting first sync"
    b.append(mono.text(sync, 13, W - 48, 60, STEEL, "end"))
    b.append(f'<circle class="bl" cx="{W - 60 - mono.width(sync, 13)}" cy="56" r="4" fill="{RED if d.get("synced") else STEEL}"/>')

    cells = [("contributions", "this year", d.get("contributions")), ("current streak", "days", d.get("streak")),
             ("longest streak", "days", d.get("longest")), ("stars earned", "all repos", d.get("stars")),
             ("public repos", "original work", d.get("repos")), ("followers", "and counting", d.get("followers"))]
    for i, (label, sub, val) in enumerate(cells):
        cx, cy = 48 + (i % 3) * 205, 110 + (i // 3) * 105
        b.append(f'<rect x="{cx}" y="{cy}" width="190" height="90" rx="10" fill="{BASE}" stroke="{EDGE}"/>')
        b.append(f'<rect x="{cx}" y="{cy + 18}" width="3" height="54" fill="{RED if i == 1 else CYAN}"/>')
        v = "--" if val is None else f"{val:,}"
        b.append(disp.text(v, 34, cx + 20, cy + 50, WHITE))
        b.append(mono.text(label, 13, cx + 20, cy + 72, STEEL))

    lx = 700
    b.append(mono.text("languages by code volume", 13, lx, 118, STEEL))
    langs = d.get("langs") or []
    colors = [RED, CYAN, WHITE, STEEL, "#3A4A70"]
    if not langs:
        b.append(mono.text("syncing...", 15, lx, 160, STEEL))
    x = lx
    for (n, p), c in zip(langs, colors):
        w = max(4, 452 * p / 100)
        b.append(f'<rect class="gr" x="{x:.1f}" y="134" width="{w:.1f}" height="10" fill="{c}"/>')
        x += w
    for i, ((n, p), c) in enumerate(zip(langs, colors)):
        y = 185 + i * 27
        b.append(f'<rect x="{lx}" y="{y - 10}" width="10" height="10" fill="{c}"/>')
        b.append(bold.text(n, 15, lx + 22, y, WHITE))
        b.append(mono.text(f"{p:.1f}%", 15, lx + 452, y, STEEL, "end"))
    style = (".sw{animation:sw 4s linear infinite}@keyframes sw{0%{transform:translateY(0)}100%{transform:translateY(326px)}}"
             ".bl{animation:bl 1.4s infinite}@keyframes bl{50%{opacity:.2}}"
             ".gr{transform-origin:700px 0;animation:gr 1.6s ease-out both}@keyframes gr{from{transform:scaleX(0)}}")
    return svg(W, H, "".join(b), style, "GitHub telemetry for Varun Bansal")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--placeholder":
        OUT.write_text(render({"repos": 36, "followers": 12}))
        sys.exit()
    try:
        data = fetch()
    except Exception as e:  # keep the last good panel
        print("telemetry fetch failed:", e)
        sys.exit(0)
    OUT.write_text(render(data))
    print("hud-stats.svg updated")
