#!/usr/bin/env python3
"""Avengers: Doomsday seat watcher for Chennai (District).
Alerts via ntfy push (and optional email) when a show at your cinemas
has seats free in the better (non-front) sections."""
import json, os, re, sys, urllib.request, smtplib
from email.message import EmailMessage

MOVIE_URL = "https://www.district.in/movies/avengers-doomsday-movie-tickets-in-chennai-MV176735?fromdate={date}"
DATES = os.environ.get("DATES", "2026-12-17,2026-12-18,2026-12-19,2026-12-20").split(",")
CINEMAS = ["phoenix", "grand mall", "bsr", "aerohub", "citi centre", "vr mall",
           "palazzo", "escape", "sathyam"]
# Front/cheap sections to ignore. Everything else counts as middle/back.
FRONT = {"budget", "classic", "normal", "economy", "silver", "first class"}
MIN_SEATS = int(os.environ.get("MIN_SEATS", "1"))
STATE = "state.json"
# Only shows starting between 5:00 AM and LATEST_START (24h, default 18:00).
LATEST_START = os.environ.get("LATEST_START", "18:00")

def mins(t):
    from datetime import datetime
    d = datetime.strptime(t.strip().upper(), "%I:%M %p")
    return d.hour * 60 + d.minute

def ok_time(t):
    h, m = map(int, LATEST_START.split(":"))
    try: x = mins(t)
    except ValueError: return True
    return 5 * 60 <= x <= h * 60 + m
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"

def get_html(url):
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, impersonate="chrome", timeout=30,
                   headers={"Accept-Language": "en-IN,en;q=0.9"})
        r.raise_for_status()
        return r.text
    except ImportError:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        return urllib.request.urlopen(req, timeout=30).read().decode()

def fetch(date):
    html = get_html(MOVIE_URL.format(date=date))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    ms = json.loads(m.group(1))["props"]["pageProps"]["data"]["serverState"]["movieSessions"]
    out = []
    for v in ms.values():
        pd = v.get("pageData") or {}
        for c in pd.get("nearbyCinemas", []) + pd.get("farCinemas", []):
            name = c["cinemaInfo"]["name"]
            if not any(k in name.lower() for k in CINEMAS):
                continue
            for s in c.get("sessions", []):
                if not ok_time(s["showTimeText"]):
                    continue
                good = sum(a["sAvail"] for a in s.get("areas", [])
                           if a["label"].lower().split(" (")[0] not in FRONT
                           and "couple" not in a["label"].lower())
                out.append({"key": s["sid"], "cinema": name.split(",")[0], "date": date,
                            "time": s["showTimeText"], "fmt": s.get("scrnFmt", ""),
                            "lang": s.get("lang", ""), "good": good})
    return out

def notify(lines):
    body = "\n".join(lines)
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers={
            "Title": "Doomsday seats open!", "Priority": "urgent", "Tags": "rotating_light",
            "Click": MOVIE_URL.format(date=DATES[0])})
        urllib.request.urlopen(req, timeout=20)
    user, pw, to = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD"), os.environ.get("MAIL_TO")
    if user and pw:
        msg = EmailMessage(); msg["Subject"] = "Doomsday seats open in Chennai"
        msg["From"] = user; msg["To"] = to or user; msg.set_content(body + "\n\n" + MOVIE_URL.format(date=DATES[0]))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw); s.send_message(msg)

def main():
    prev = json.load(open(STATE)) if os.path.exists(STATE) else {}
    shows = []
    for d in DATES:
        try: shows += fetch(d)
        except Exception as e: print("fetch failed", d, e, file=sys.stderr)
    if not shows:
        sys.exit("no data fetched (blocked or page changed)")
    new = [s for s in shows if s["good"] >= MIN_SEATS and prev.get(s["key"], 0) < MIN_SEATS]
    for s in shows: print(f'{s["date"]} {s["time"]:>8} {s["good"]:>4} good  {s["cinema"]} {s["fmt"]}')
    if new:
        notify([f'{s["cinema"]} {s["date"][5:]} {s["time"]} {s["fmt"]} {s["lang"]}: {s["good"]} seats' for s in new])
        print("ALERTED", len(new))
    json.dump({s["key"]: s["good"] for s in shows}, open(STATE, "w"))

if __name__ == "__main__":
    main()
