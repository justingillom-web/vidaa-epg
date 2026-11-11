#!/usr/bin/env python3
"""
m3u2xmltv.py - build an XMLTV guide from an M3U playlist.

Vidaa (and most FAST lists) ship no program data, so this generates:
  * a <channel> entry for every stream (id, display-name, icon, group)
  * filler <programme> blocks (default 1 h, 3 days) titled with the
    channel name + group, so players show a populated grid and logos.

It also rewrites the playlist so every channel has a unique tvg-id
and the header points at the guide (x-tvg-url), which keeps players
from collapsing the duplicate names in vidaa.m3u.

Usage:
  python3 m3u2xmltv.py https://www.apsattv.com/vidaa.m3u
  python3 m3u2xmltv.py vidaa.m3u --days 7 --block 30 \
      --guide-url http://homelab.lan/vidaa.xml
Outputs: vidaa.xml  vidaa_epg.m3u  (names follow the input)
"""
import argparse, re, sys, urllib.request, datetime as dt
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def load(src):
    if re.match(r'https?://', src):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    return Path(src).read_text(encoding="utf-8", errors="replace")


def parse(text):
    chans, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF"):
            head, _, name = line.partition(",")
            cur = dict(ATTR.findall(head))
            cur["name"] = name.strip() or cur.get("tvg-name", "Unknown")
            cur["extra"] = []
        elif cur is not None and line.startswith("#"):
            cur["extra"].append(line)          # #EXTVLCOPT etc.
        elif cur is not None and line:
            cur["url"] = line
            chans.append(cur)
            cur = None
    return chans


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "ch"


def assign_ids(chans):
    seen = {}
    for c in chans:
        base = c.get("tvg-id") or slug(c["name"])
        n = seen.get(base, 0)
        seen[base] = n + 1
        c["id"] = base if n == 0 else f"{base}.{n + 1}"


def xmltv(chans, days, block):
    fmt = "%Y%m%d%H%M%S +0000"
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now + dt.timedelta(days=days)
    step = dt.timedelta(minutes=block)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<tv generator-info-name="m3u2xmltv">']
    for c in chans:
        out.append(f'  <channel id={quoteattr(c["id"])}>')
        out.append(f'    <display-name>{escape(c["name"])}</display-name>')
        if c.get("tvg-logo"):
            out.append(f'    <icon src={quoteattr(c["tvg-logo"])}/>')
        out.append('  </channel>')
    for c in chans:
        title, grp = escape(c["name"]), escape(c.get("group-title", ""))
        t = now
        while t < end:
            out.append(f'  <programme start="{t.strftime(fmt)}" '
                       f'stop="{(t + step).strftime(fmt)}" channel={quoteattr(c["id"])}>')
            out.append(f'    <title lang="en">{title}</title>')
            if grp:
                out.append(f'    <desc lang="en">{grp}</desc>')
                out.append(f'    <category lang="en">{grp}</category>')
            out.append('  </programme>')
            t += step
    out.append('</tv>')
    return "\n".join(out) + "\n"


def m3u(chans, guide_url):
    hdr = f'#EXTM3U x-tvg-url="{guide_url}"' if guide_url else "#EXTM3U"
    lines = [hdr]
    for c in chans:
        attrs = {k: v for k, v in c.items()
                 if k not in ("name", "url", "extra", "id", "tvg-id")}
        a = " ".join(f'{k}="{v}"' for k, v in attrs.items())
        lines.append(f'#EXTINF:-1 tvg-id="{c["id"]}" {a},{c["name"]}'.replace("  ", " "))
        lines += c["extra"]
        lines.append(c["url"])
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="M3U URL or local file")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--block", type=int, default=60, help="minutes per filler block")
    p.add_argument("--guide-url", default="", help="URL the XML will be served at")
    p.add_argument("--out", default=None, help="output basename (default: input name)")
    a = p.parse_args()

    chans = parse(load(a.source))
    if not chans:
        sys.exit("No channels found - is that an M3U?")
    assign_ids(chans)
    base = a.out or Path(a.source.split("?")[0]).stem or "guide"
    Path(f"{base}.xml").write_text(xmltv(chans, a.days, a.block), encoding="utf-8")
    Path(f"{base}_epg.m3u").write_text(m3u(chans, a.guide_url), encoding="utf-8")
    print(f"{len(chans)} channels -> {base}.xml, {base}_epg.m3u")


if __name__ == "__main__":
    main()
