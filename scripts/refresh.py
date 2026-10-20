#!/usr/bin/env python3
"""Hackathon Afterlife refresh script.

Reads data/seed.json, checks public signals for every project and writes
data/projects.json. Python 3.9+ standard library only (plus the `git` CLI).
No paid APIs, no secrets required:
  * GITHUB_TOKEN  (optional) - raises GitHub API limits; only used as a fallback.
  * X_BEARER_TOKEN (optional) - if set, last X post is checked live; otherwise
    data/x_snapshot.json is used if present, else the signal is 'unknown'.
Signals that cannot be checked are recorded as 'unknown', never guessed.
"""
import json, os, re, subprocess, sys, tempfile, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "HackathonAfterlifeBot/1.0 (+https://github.com/suhasdasari/hackathon-afterlife)"
NOW = datetime.now(timezone.utc)
CHECKPOINTS = [30, 90, 180]
ACTIVE_WINDOW = 30      # days: "active" = public activity within this many days
RECENT_WINDOW = 90
PARKED = ["domain is for sale", "buy this domain", "this domain is parked", "domain parking",
          "deployment_not_found", "this deployment cannot be found", "site not found",
          "there isn't a github pages site here", "no such app", "application not found"]
IGNORE_GH_OWNERS = {"ethglobal", "colosseum", "colosseumorg", "solana-labs", "solana-foundation",
                    "features", "sponsors", "orgs", "topics", "about", "pricing", "login", "settings"}
IGNORE_X = {"ethglobal", "colosseum", "colosseumorg", "solana", "share", "intent", "home", "i",
            "search", "hashtag", "x", "twitter"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def http(url, accept=None, token=None, timeout=20, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    if accept:
        req.add_header("Accept", accept)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace"), dict(r.headers), r.geturl()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(50_000).decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, body, dict(e.headers or {}), url
    except Exception as e:
        return None, str(e), {}, url


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------------------------------------------------------------- discovery
def discover(listing_url):
    """Pull repo / X handle / website links from a public listing page."""
    out = {}
    if not listing_url:
        return out
    st, body, _, _ = http(listing_url)
    if st != 200:
        return {"listing_status": st}
    body = body.replace("\\/", "/")
    repos = []
    for o, r in re.findall(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", body):
        r = re.sub(r"\.git$", "", r).rstrip(".\\")
        if o.lower() in IGNORE_GH_OWNERS or not r:
            continue
        if (o, r) not in repos:
            repos.append((o, r))
    if repos:
        out["repo"] = "https://github.com/%s/%s" % repos[0]
    xs = []
    for h in re.findall(r"https?://(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})(?:[/\"'?\\]|$)", body):
        if h.lower() not in IGNORE_X and h not in xs:
            xs.append(h)
    if "arena.colosseum.org" in listing_url:
        m = re.search(r'twitterUrl\\?"?:\\?"https?://(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})', body)
        if m:
            out["x_handle"] = m.group(1)   # the project's listed X account
        m = re.search(r'website\\?"?:\\?"(https?://[^"\\]+)', body)
        if m:
            out["website"] = m.group(1)
        m = re.search(r'repoLink\\?"?:\\?"(https://github\.com/[^"\\]+)', body)
        if m:
            out["repo"] = m.group(1).rstrip("/")
    if "ethglobal.com/showcase" in listing_url:
        m = re.search(r'href="(https?://[^"]+)"[^>]*>\s*Live Demo', body)
        if m:
            out["website"] = m.group(1)
        m = re.search(r'href="(https://github\.com/[^"]+)"[^>]*>\s*Source Code', body)
        if m:
            out["repo"] = m.group(1).rstrip("/")
    return out


# ---------------------------------------------------------------- GitHub
def repo_slug(url):
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url or "")
    return (m.group(1), re.sub(r"\.git$", "", m.group(2))) if m else None


def commits_via_git(url):
    """Commit timestamps on the default branch via a treeless bare clone (no API quota)."""
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        p = subprocess.run(["git", "clone", "--bare", "--filter=tree:0", "--quiet", url, d + "/r"],
                           capture_output=True, text=True, timeout=180, env=env)
        if p.returncode != 0:
            return None, p.stderr.strip()[-200:]
        p = subprocess.run(["git", "-C", d + "/r", "log", "--format=%cI", "HEAD"],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return [], "empty repository"
        return [parse_dt(x) for x in p.stdout.split()], None


def commits_via_api(owner, repo):
    tok = os.environ.get("GITHUB_TOKEN") or None
    dates, page = [], 1
    while page <= 5:
        st, body, hdr, _ = http("https://api.github.com/repos/%s/%s/commits?per_page=100&page=%d" % (owner, repo, page),
                                "application/vnd.github+json", tok)
        if st in (403, 429) and hdr.get("X-RateLimit-Remaining", hdr.get("x-ratelimit-remaining")) == "0":
            reset = int(hdr.get("X-RateLimit-Reset", hdr.get("x-ratelimit-reset", "0")) or 0)
            wait = max(0, reset - time.time()) + 2
            if wait > 900:
                return None, "rate limited"
            log("  rate limited, sleeping %ds" % wait)
            time.sleep(wait)
            continue
        if st == 409:
            return [], "empty repository"
        if st != 200:
            return None, "HTTP %s" % st
        items = json.loads(body)
        dates += [parse_dt(c["commit"]["committer"]["date"]) for c in items]
        if len(items) < 100:
            break
        page += 1
    return dates, None


def github_signal(url, demo):
    sl = repo_slug(url)
    if not sl:
        return {"status": "unknown", "note": "no public repo linked"}
    dates, err = commits_via_git("https://github.com/%s/%s.git" % sl)
    if dates is None:
        dates, err2 = commits_via_api(*sl)
        if dates is None:
            return {"status": "unknown", "repo": url, "note": "repo not reachable (private, renamed or deleted?): %s" % (err2 or err)}
    if not dates:
        return {"status": "checked", "repo": url, "last_commit": None, "commits_total": 0, "windows": {}}
    dates.sort()
    w = {}
    for n in CHECKPOINTS:
        end = demo + timedelta(days=n)
        start = end - timedelta(days=30)
        if NOW < end:
            w[str(n)] = {"reached": False, "commits": sum(1 for d in dates if start <= d <= NOW)}
        else:
            w[str(n)] = {"reached": True, "commits": sum(1 for d in dates if start <= d <= end)}
    after = [d for d in dates if d >= demo]
    return {"status": "checked", "repo": url, "last_commit": dates[-1].isoformat(),
            "first_commit": dates[0].isoformat(), "commits_total": len(dates),
            "commits_after_demo": len(after),
            "commits_last_30d": sum(1 for d in dates if d >= NOW - timedelta(days=30)),
            "windows": w}


# ---------------------------------------------------------------- website
def site_signal(url):
    if not url:
        return {"status": "unknown", "note": "no website linked"}
    st, body, _, final = http(url, timeout=20)
    if st is None:
        return {"status": "down", "url": url, "http": None, "note": body[:120]}
    low = body.lower()
    parked = next((k for k in PARKED if k in low), None)
    if st == 200 and parked:
        return {"status": "parked", "url": url, "http": st, "note": "matched '%s'" % parked}
    if 200 <= st < 400:
        return {"status": "up", "url": url, "http": st, "final_url": final}
    if st in (401, 403, 429, 503):   # bot walls (Cloudflare etc.) – reachable but not verifiable
        return {"status": "unknown", "url": url, "http": st, "note": "blocked automated check"}
    return {"status": "down", "url": url, "http": st}


# ---------------------------------------------------------------- X
def x_signal(handle, snapshot):
    if not handle:
        return {"status": "unknown", "note": "no project X account linked"}
    tok = os.environ.get("X_BEARER_TOKEN")
    if tok:
        st, body, _, _ = http("https://api.x.com/2/users/by/username/%s?user.fields=most_recent_tweet_id" % handle, token=tok)
        if st == 200:
            u = json.loads(body).get("data") or {}
            tid = u.get("most_recent_tweet_id")
            if not tid:
                return {"status": "checked", "handle": handle, "last_post": None}
            st, body, _, _ = http("https://api.x.com/2/tweets/%s?tweet.fields=created_at" % tid, token=tok)
            if st == 200:
                return {"status": "checked", "handle": handle, "source": "live",
                        "last_post": json.loads(body)["data"]["created_at"]}
    if handle.lower() in [h.lower() for h in snapshot.get("not_found", [])]:
        return {"status": "unknown", "handle": handle, "note": "account not found at snapshot time"}
    s = (snapshot.get("accounts") or {}).get(handle.lower())
    if s is not None:
        return {"status": "checked", "handle": handle, "source": "snapshot " + snapshot.get("as_of", "?"),
                "last_post": s.get("last_post"), "post_url": s.get("post_url")}
    return {"status": "unknown", "handle": handle, "note": "X not checked (no API token)"}


# ---------------------------------------------------------------- token
def token_signal(addr):
    if not addr:
        return {"status": "unknown", "note": "no token address listed"}
    st, body, _, _ = http("https://api.dexscreener.com/latest/dex/tokens/" + addr)
    if st != 200:
        return {"status": "unknown", "note": "DexScreener HTTP %s" % st}
    pairs = json.loads(body).get("pairs") or []
    if not pairs:
        return {"status": "checked", "exists": False}
    fdv = max((p.get("fdv") or 0) for p in pairs)
    return {"status": "checked", "exists": True, "fdv_usd": fdv, "pairs": len(pairs)}


# ---------------------------------------------------------------- rules
def days_ago(iso):
    return None if not iso else (NOW - parse_dt(iso)).days


def classify(p):
    g, s, x, t, raise_ = p["signals"]["github"], p["signals"]["site"], p["signals"]["x"], p["signals"]["token"], p.get("raise")
    if raise_ and raise_.get("source"):
        return "graduated", "Raise announced (sourced)"
    if t.get("exists") and (t.get("fdv_usd") or 0) >= 1_000_000:
        return "graduated", "Token FDV >= $1M"
    acts = [d for d in (days_ago(g.get("last_commit")), days_ago(x.get("last_post"))) if d is not None]
    last = min(acts) if acts else None
    if last is not None and last <= ACTIVE_WINDOW:
        return "active", "Public activity in last 30 days"
    if last is not None and last <= RECENT_WINDOW:
        return "recent", "Last public activity 31-90 days ago"
    if s.get("status") == "up":
        return "site_only", "Site responds; no commit/post activity in 90 days" if acts else "Site responds; commit/post activity not verifiable"
    if g["status"] == "unknown" and x["status"] == "unknown" and s["status"] == "unknown":
        return "unknown", "No checkable public signal"
    if last is None and g["status"] == "unknown" and x["status"] == "unknown":
        return "unknown", "Site not responding; no repo or X to check"
    if last is None and p["days_since_demo"] < RECENT_WINDOW:
        return "quiet", "No public commit/post found since demo day"
    return "quiet", "No public activity in 90 days"


def checkpoint(p, n):
    g = p["signals"]["github"]
    if g["status"] != "checked":
        return "unknown"
    w = g["windows"].get(str(n))
    if not w:
        return "no_activity"
    if not w["reached"]:
        return "pending"
    return "active" if w["commits"] > 0 else "no_activity"


def survival(p):
    """Time-to-quiet for Kaplan-Meier: event = >30 days with no commit after last commit."""
    g = p["signals"]["github"]
    if g["status"] != "checked":
        return None
    demo = parse_dt(p["demo_day"] + "T00:00:00+00:00")
    age = (NOW - demo).days
    last = parse_dt(g["last_commit"]) if g.get("last_commit") else None
    last_day = max(0, (last - demo).days) if last else 0
    if last and (NOW - last).days <= ACTIVE_WINDOW:
        return {"t": age, "event": 0}
    return {"t": min(age, last_day + ACTIVE_WINDOW), "event": 1}


def main():
    seed = json.load(open(os.path.join(DATA, "seed.json")))
    prev = {}
    try:
        prev = {p["name"]: p for p in json.load(open(os.path.join(DATA, "projects.json")))["projects"]}
    except Exception:
        pass
    snap = {}
    try:
        snap = json.load(open(os.path.join(DATA, "x_snapshot.json")))
    except Exception:
        pass
    out = []
    for i, s in enumerate(seed):
        p = dict(s)
        log("[%d/%d] %s" % (i + 1, len(seed), p["name"]))
        disc = (prev.get(p["name"]) or {}).get("discovered")
        if disc is None or os.environ.get("REDISCOVER"):
            disc = discover(p.get("listing_url"))
        p["discovered"] = disc
        for k in ("repo", "x_handle", "website"):
            if not p.get(k) and disc.get(k) and k not in (p.get("ignore_discovered") or []):
                p[k] = disc[k]
                p.setdefault("link_sources", {})[k] = "listing page"
        demo = parse_dt(p["demo_day"] + "T00:00:00+00:00")
        p["days_since_demo"] = (NOW - demo).days
        p["signals"] = {
            "github": github_signal(p.get("repo"), demo),
            "site": site_signal(p.get("website")),
            "x": x_signal(p.get("x_handle"), snap),
            "token": token_signal(p.get("token_address")),
            "contract": {"status": "unknown", "note": "contract activity is v2"},
            "raise": {"status": "checked", "source": p["raise"]["source"]} if p.get("raise") else {"status": "none recorded"},
        }
        p["status"], p["status_reason"] = classify(p)
        p["checkpoints"] = {str(n): checkpoint(p, n) for n in CHECKPOINTS}
        p["survival"] = survival(p)
        out.append(p)
    res = {"generated_at": NOW.replace(microsecond=0).isoformat(), "rules_version": 1,
           "x_snapshot_as_of": snap.get("as_of"), "projects": out}
    with open(os.path.join(DATA, "projects.json"), "w") as f:
        json.dump(res, f, indent=1)
    log("wrote %d projects" % len(out))


if __name__ == "__main__":
    main()
