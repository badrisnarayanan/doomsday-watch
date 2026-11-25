#!/usr/bin/env python3
"""Avengers: Doomsday seat watcher for Chennai (District).
Alerts via ntfy push (and optional email) when a show at your cinemas
has free seats in centre, middle-to-back rows (front third of rows and
side corners skipped, read row by row from District's seat map)."""
import json, os, re, sys, urllib.request, smtplib
from email.message import EmailMessage

MOVIE_URL = "https://www.district.in/movies/avengers-doomsday-movie-tickets-in-chennai-MV176735?fromdate={date}"
DATES = os.environ.get("DATES", "2026-12-17,2026-12-18,2026-12-19,2026-12-20").split(",")
# District name substring -> short label used in output.
CINEMAS = {"phoenix": "phoenix", "grand mall": "grand mall", "bsr": "bsr", "aerohub": "aerohub",
           "citi centre": "citi centre", "vr mall": "vr", "palazzo": "palazzo",
           "escape": "escape", "sathyam": "sathyam"}
# Row-level rules (District seat map: higher GridRowId = closer to screen).
# Skip the front third of rows, and never fewer than FRONT_ROWS rows from the screen.
FRONT_ROWS = int(os.environ.get("FRONT_ROWS", "3"))
FRONT_FRACTION = float(os.environ.get("FRONT_FRACTION", "0.34"))
# Trim this share of seat columns off each side (no extreme corners).
SIDE_TRIM = float(os.environ.get("SIDE_TRIM", "0.15"))
SEAT_API = "https://www.district.in/gw/consumer/movies/v1/select-seat"
GUEST_API = "https://www.district.in/gw/auth/skip_login"
CONTENT_ID = "176735"
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

def post_json(url, body, headers):
    h = {"User-Agent": UA, "Content-Type": "application/json", "Origin": "https://www.district.in",
         "Referer": "https://www.district.in/", "x-device-id": "doomsdaywatch01", **headers}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=h)
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())

_TOKEN = None
def guest_token():
    global _TOKEN
    if not _TOKEN:
        _TOKEN = post_json(GUEST_API, {}, {})["token"]["guest_token"]
    return _TOKEN

def good_seats(s):
    """Count free seats in centre, middle-to-back rows of one show."""
    body = {"cinemaId": s["cid"], "sessionId": s["sid"], "providerId": s["pid"], "screenOnTop": True,
            "freeSeating": False, "screenFormat": s.get("scrnFmt", ""), "moviecode": s["mid"],
            "config": {"socialDistancing": 1}, "contentId": CONTENT_ID}
    d = post_json(SEAT_API, body, {"x-guest-token": guest_token(), "paytmCinemaId": str(s["cid"])})
    areas = [a for a in d["seatLayout"]["colAreas"]["objArea"] if "couple" not in a["AreaDesc"].lower()]
    rows = [r for a in areas for r in a["objRow"] if r["objSeat"]]
    if not rows:
        return 0, []
    order = sorted({int(r["GridRowId"]) for r in rows}, reverse=True)  # screen first
    skip = max(FRONT_ROWS, round(len(order) * FRONT_FRACTION))
    front = set(order[:skip])
    cols = [x["GridSeatNum"] for r in rows for x in r["objSeat"]]
    lo, hi = min(cols), max(cols)
    pad = (hi - lo) * SIDE_TRIM
    seats = []
    for r in rows:
        if int(r["GridRowId"]) in front:
            continue
        for x in r["objSeat"]:
            if str(x["SeatStatus"]) == "0" and lo + pad <= x["GridSeatNum"] <= hi - pad:
                seats.append(f'{r["PhyRowId"].strip("-")}{x.get("displaySeatNumber", x["seatNumber"])}')
    return len(seats), seats

def fetch(date):
    html = get_html(MOVIE_URL.format(date=date))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    ms = json.loads(m.group(1))["props"]["pageProps"]["data"]["serverState"]["movieSessions"]
    out = []
    for v in ms.values():
        pd = v.get("pageData") or {}
        for c in pd.get("nearbyCinemas", []) + pd.get("farCinemas", []):
            name = c["cinemaInfo"]["name"]
            short = next((v for k, v in CINEMAS.items() if k in name.lower()), None)
            if not short:
                continue
            for s in c.get("sessions", []):
                if not ok_time(s["showTimeText"]):
                    continue
                good, seats = 0, []
                if s.get("avail", 0) > 0:
                    try:
                        good, seats = good_seats(s)
                    except Exception as e:
                        print("seat map failed", name, s["showTimeText"], e, file=sys.stderr)
                out.append({"key": s["sid"], "cinema": short, "date": date,
                            "time": s["showTimeText"], "fmt": s.get("scrnFmt", ""),
                            "lang": s.get("lang", ""), "good": good, "seats": seats[:6]})
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
    from datetime import datetime, timedelta, timezone
    t = datetime.now(timezone(timedelta(hours=5, minutes=30)))  # IST
    now = t.strftime("%H:%M:%S")
    print(f"--- checked {t:%d %b %H:%M:%S} IST ---")
    for s in shows: print(f'[{now}] {s["date"][5:]} {s["time"]:>8} {s["good"]:>4} good  {s["cinema"]} {s["fmt"]}')
    if new:
        notify([f'{s["cinema"]} {s["date"][5:]} {s["time"]} {s["fmt"]} {s["lang"]}: {s["good"]} seats ({", ".join(s["seats"])})' for s in new])
        print("ALERTED", len(new))
    json.dump({s["key"]: s["good"] for s in shows}, open(STATE, "w"))

if __name__ == "__main__":
    main()
