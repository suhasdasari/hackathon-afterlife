# Hackathon Afterlife

A live tracker of crypto hackathon winners: does each project still show **public** activity 30, 90 and 180 days after demo day? Static site (GitHub Pages), data refreshed nightly by a GitHub Action. No backend, no paid APIs, no secrets required.

Live: https://suhasdasari.github.io/hackathon-afterlife/

## Layout
```
index.html               page (relative paths only; works from /hackathon-afterlife/)
assets/style.css
assets/app.js            table, filters, checkpoint table, Kaplan-Meier chart (inline SVG, no CDN)
data/seed.json           hand-curated project list (name, hackathon, demo day, tier, sources, links)
data/x_snapshot.json     optional dated snapshot of last X post per project account
data/projects.json       generated output (do not edit by hand)
scripts/refresh.py       refresh script (Python 3.9+ stdlib + git CLI)
.github/workflows/refresh.yml   nightly cron + manual run; commits data/projects.json
```

## Run locally
```
python3 scripts/refresh.py            # ~1-2 min for 58 projects
REDISCOVER=1 python3 scripts/refresh.py   # re-scrape repo/site links from listing pages
python3 -m http.server 8000           # open http://localhost:8000/
```
Optional env: `GITHUB_TOKEN` (higher API limits for the fallback path), `X_BEARER_TOKEN` (live X checks). Without them the script still runs; anything it cannot check is recorded as `unknown`.

## Deploy
Push to `suhasdasari/hackathon-afterlife`, then Settings → Pages → Deploy from branch `main` / root. The workflow needs no configuration (`permissions: contents: write`, uses the built-in `GITHUB_TOKEN`).

## Rules (v1) <a id="rules"></a>
All rules are mechanical; there are no subjective calls. Labels describe public signals only.

**Demo day**: date the winners/finalists were publicly announced (source linked per project).

**Signals**
| Signal | How it is checked | When it is `unknown` |
|---|---|---|
| GitHub | Treeless `git clone` of the linked public repo; committer dates on the default branch. Falls back to the GitHub REST API (unauthenticated allowed; waits on rate-limit reset up to 15 min). | No repo linked, or repo private/renamed/deleted |
| Website | HTTP GET (20 s timeout, redirects followed). 2xx/3xx = `up` unless the body matches a parked / "deployment not found" pattern (`parked`). Other 4xx/5xx or no response = `down`. | No site linked, or 401/403/429/503 bot wall |
| X | Project account's most recent post (any type, incl. replies/reposts). Live if `X_BEARER_TOKEN` is set, else from `data/x_snapshot.json` (dated). | No project account linked, account not found, or no token and no snapshot |
| Token | DexScreener `/latest/dex/tokens/{address}` — only when a token address is listed in the seed. No fuzzy name search. | No address listed |
| Raise | Manual seed entry with a source link | Shown as "none recorded" |
| Contract activity | Planned for v2 | Always `unknown` in v1 |

Repo/site/X links come from the seed or are scraped from the project's official listing page (ETHGlobal showcase "Source Code"/"Live Demo", Colosseum Arena repo/website/X fields). Personal accounts are excluded.

**Checkpoints (30 / 90 / 180 days)**: `active` if ≥1 public commit in the 30 days ending N days after demo day; `no public commits` if none; `pending` if that day hasn't arrived; `unknown` if no public repo. (Only GitHub has history, so checkpoints use commits only.)

**Current status** (first match wins)
1. **Graduated** — sourced raise, or listed token with FDV ≥ $1M
2. **Active (≤30d)** — a public commit or X post in the last 30 days
3. **Recent (31–90d)** — last public commit/post 31–90 days ago
4. **Site up only** — website responds, but no commit/post in 90 days (or none checkable)
5. **Quiet** — no public commit/post in 90 days (or none found since demo day, for projects < 90 days old)
6. **Insufficient data** — nothing checkable

**Survival curves**: Kaplan-Meier over public-repo projects. A project "goes quiet" at (last commit after demo day + 30 days); projects with a commit in the last 30 days are censored at today.

**Wording**: neutral only ("no public activity in 90 days"). Private repos, pivots and renames are common; a quiet label is not a judgement on the team.

## Claim & correct
Every row has a prefilled issue link (`/issues/new?title=Claim/correct: …`). Teams can add a repo, site, X account, contract, token or raise with evidence; corrections land in `data/seed.json`. Paid listings, if ever offered, never change a status label.

## Not financial advice
Automated checks of public signals; may be wrong or stale. See `generated_at` in `data/projects.json`.

Built by Satoshi Drops 🪂 [@SatoshiDropsHQ](https://x.com/SatoshiDropsHQ)
