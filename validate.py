"""Checks the generated regions against brute force and the unsimplified OSM data.

Run from the repository root after build.py: python validate.py
"""

import json
import math
import random

import build
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely.prepared import prep
from shapely import STRtree
regions = build.main()
china, sar, strait = regions["china"], regions["hong-kong-macau-taiwan"], regions["taiwan-strait-waters"]
def gcj(lat, lon): return china.contains(lat, lon) or sar.contains(lat, lon) or strait.contains(lat, lon)
def mainland(lat, lon): return china.contains(lat, lon) and not sar.contains(lat, lon)

def brute(region, lat, lon):
    inside = False
    for alat, alon, blat, blon in region.edges:
        if (alat > lat) != (blat > lat):
            x = alon + (lat - alat) * (blon - alon) / (blat - alat)
            if x < lon: inside = not inside
    return inside

random.seed(7)
# 1. grid lookup equals brute-force even-odd on the same rings
for region in (china, sar, strait):
    bad = 0; n = 3000 if region is china else 6000
    for _ in range(n):
        lat = random.uniform(region.min_lat, region.min_lat + region.rows * 0.25)
        lon = random.uniform(region.min_lon, region.min_lon + region.columns * 0.25)
        if region.contains(lat, lon) != brute(region, lat, lon): bad += 1
    print(f"grid-vs-bruteforce {region.name}: {bad}/{n} mismatches")

# 2. against the unsimplified OSM geometry
orig_china = make_valid(shape(json.load(open("src/rel_270056.geojson"))))
orig_sar = unary_union([make_valid(shape(json.load(open(f"src/rel_{i}.geojson")))) for i in (913110, 1867188, 449220)])
pc, ps = prep(orig_china), prep(orig_sar)
boundary = orig_china.boundary
def near_boundary_points(n, max_offset_m):
    pts = []
    L = boundary.length
    for _ in range(n):
        p = boundary.interpolate(random.uniform(0, L))
        d = random.uniform(-max_offset_m, max_offset_m) / 111320
        ang = random.uniform(0, 2 * math.pi)
        pts.append((p.y + d * math.sin(ang), p.x + d * math.cos(ang) / math.cos(math.radians(p.y))))
    return pts
pts = near_boundary_points(20000, 1500)
mism = []
for lat, lon in pts:
    if china.contains(lat, lon) != pc.contains(Point(lon, lat)):
        mism.append(boundary.distance(Point(lon, lat)) * 111320)
mism.sort()
print(f"china near-boundary (<=1.5 km) mismatches: {len(mism)}/{len(pts)}; distance to true boundary p50={mism[len(mism)//2] if mism else 0:.0f} m p99={mism[int(len(mism)*0.99)] if mism else 0:.0f} m max={max(mism) if mism else 0:.0f} m")

# 3. named points
P = {
 "Shenzhen Futian": (22.541, 114.055, True, True), "Xiamen": (24.480, 118.090, True, True),
 "Macau": (22.193, 113.543, True, False), "Gongbei (Zhuhai side)": (22.222, 113.553, True, True),
 "Hong Kong TST": (22.2988, 114.1722, True, False), "Taipei": (25.05, 121.55, True, False),
 "Kinmen": (24.43, 118.36, True, False), "Matsu Nangan": (26.16, 119.95, True, False), "Penghu Magong": (23.57, 119.58, True, False),
 "Seoul": (37.57, 126.98, False, False), "Osaka": (34.70, 135.50, False, False), "Bangkok": (13.75, 100.50, False, False),
 "Singapore": (1.29, 103.85, False, False), "Yonaguni": (24.46, 122.99, False, False), "Batanes Basco": (20.45, 121.97, False, False),
 "Hekou town": (22.525, 103.950, True, True), "Lao Cai city": (22.48, 103.97, False, False),
 "Dandong": (40.125, 124.385, True, True), "Sinuiju": (40.10, 124.40, False, False),
 "Ruili": (24.013, 97.85, True, True), "Muse": (23.98, 97.90, False, False),
 "Dongxing": (21.548, 107.972, True, True), "Mong Cai": (21.525, 107.955, False, False),
 "Heihe": (50.245, 127.49, True, True), "Blagoveshchensk": (50.27, 127.53, False, False),
 "Taiwan Strait mid": (24.5, 119.5, True, False), "Taiwan Strait south": (22.8, 119.0, True, False),
 "Pearl River estuary": (22.30, 113.75, True, True), "Qiongzhou Strait": (20.20, 110.20, True, True),
 "East China Sea 200km off Shanghai": (31.0, 123.8, False, False),
}
fail = 0
for k, (lat, lon, eg, em) in P.items():
    g, m = gcj(lat, lon), mainland(lat, lon)
    og = pc.contains(Point(lon, lat)) or ps.contains(Point(lon, lat))
    d = boundary.distance(Point(lon, lat)) * 111320
    ok = (g == eg and m == em)
    fail += not ok
    print(f"{'OK ' if ok else 'BAD'} {k:34s} gcj={int(g)} mainland={int(m)} (expected {int(eg)}/{int(em)}) dist_to_china_boundary={d:7.0f} m")
print("named failures:", fail)
