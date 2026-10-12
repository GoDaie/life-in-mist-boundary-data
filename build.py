"""Builds the simplified boundary regions used by Life in Mist.

Inputs are OpenStreetMap boundary relations exported as GeoJSON by
polygons.openstreetmap.fr (see README). Outputs:

  out/<region>.geojson          simplified region geometry (ODbL 1.0)
  out/BoundaryRegionData.swift  the same geometry plus a lookup grid

Each region is stored as a set of rings tested with the even-odd rule, plus a
0.25 degree grid. A grid cell is "boundary" when the bounding box of any ring
edge overlaps it; every other cell is uniformly inside or outside. Boundary
cells also record whether their centre is inside, so a point in such a cell is
resolved by counting edge crossings between the point and the cell centre.
The Swift side uses exactly the same rules and the same rounded coordinates.
"""

import json
import math
import os

from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

SIMPLIFY_TOLERANCE_DEGREES = 0.001
COORDINATE_SCALE = 100_000  # 1e-5 degree, the polyline precision
CELL_SIZE_DEGREES = 0.25
# Record the export date whenever src/ is refreshed.
SOURCE_NOTE = "polygons.openstreetmap.fr export of the OSM relations, downloaded 2026-10-12"

RELATIONS = {
    "china": [270056],  # People's Republic of China, includes Hong Kong and Macau
    "hong-kong-macau-taiwan": [913110, 1867188, 449220],
}

# Open water of the Taiwan Strait between the mainland and Taiwan territorial
# seas. Corners sit on Fujian/Guangdong coastal waters and on Taiwan, so the
# polygon only adds the strait itself. (longitude, latitude)
TAIWAN_STRAIT_WATERS = [
    (117.20, 23.50),
    (119.60, 26.00),
    (121.60, 25.35),
    (120.85, 21.90),
    (117.20, 23.50),
]


def load_relation(relation_id):
    with open(os.path.join("src", f"rel_{relation_id}.geojson")) as f:
        return make_valid(shape(json.load(f)))


def polygons_of(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) for g in polygons_of(g)]


def rounded_rings(geometry):
    """Returns rings as lists of (lat_e5, lon_e5) integer pairs, closed."""
    rings = []
    for polygon in polygons_of(geometry):
        for ring in [polygon.exterior, *polygon.interiors]:
            points = []
            for lon, lat in ring.coords:
                p = (round(lat * COORDINATE_SCALE), round(lon * COORDINATE_SCALE))
                if not points or points[-1] != p:
                    points.append(p)
            if points[0] != points[-1]:
                points.append(points[0])
            if len(points) >= 4:
                rings.append(points)
    return rings


def encode_polyline(points):
    """Google encoded polyline algorithm, points already scaled by 1e5."""
    out = []
    prev_lat = prev_lon = 0
    for lat, lon in points:
        for delta in (lat - prev_lat, lon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = lat, lon
    return "".join(out)


class Region:
    def __init__(self, name, rings):
        self.name = name
        self.rings = rings
        self.edges = [
            (ring[i][0] / COORDINATE_SCALE, ring[i][1] / COORDINATE_SCALE,
             ring[i + 1][0] / COORDINATE_SCALE, ring[i + 1][1] / COORDINATE_SCALE)
            for ring in rings for i in range(len(ring) - 1)
        ]
        lats = [p[0] for r in rings for p in r]
        lons = [p[1] for r in rings for p in r]
        self.min_lat = math.floor(min(lats) / COORDINATE_SCALE / CELL_SIZE_DEGREES) * CELL_SIZE_DEGREES
        self.min_lon = math.floor(min(lons) / COORDINATE_SCALE / CELL_SIZE_DEGREES) * CELL_SIZE_DEGREES
        self.rows = math.floor((max(lats) / COORDINATE_SCALE - self.min_lat) / CELL_SIZE_DEGREES) + 1
        self.columns = math.floor((max(lons) / COORDINATE_SCALE - self.min_lon) / CELL_SIZE_DEGREES) + 1
        self._build_grid()

    def cell_range(self, low, high, origin, count):
        first = max(0, math.floor((low - origin) / CELL_SIZE_DEGREES))
        last = min(count - 1, math.floor((high - origin) / CELL_SIZE_DEGREES))
        return first, last

    def _build_grid(self):
        boundary = [[False] * self.columns for _ in range(self.rows)]
        self.cell_edges = {}
        for index, (alat, alon, blat, blon) in enumerate(self.edges):
            r0, r1 = self.cell_range(min(alat, blat), max(alat, blat), self.min_lat, self.rows)
            c0, c1 = self.cell_range(min(alon, blon), max(alon, blon), self.min_lon, self.columns)
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    boundary[r][c] = True
                    self.cell_edges.setdefault((r, c), []).append(index)
        self.cells = []
        for r in range(self.rows):
            y = self.min_lat + (r + 0.5) * CELL_SIZE_DEGREES
            crossings = sorted(
                alon + (y - alat) * (blon - alon) / (blat - alat)
                for alat, alon, blat, blon in self.edges
                if (alat > y) != (blat > y)
            )
            row = []
            k = 0
            for c in range(self.columns):
                x = self.min_lon + (c + 0.5) * CELL_SIZE_DEGREES
                while k < len(crossings) and crossings[k] < x:
                    k += 1
                inside = k % 2 == 1
                row.append(("3" if inside else "2") if boundary[r][c] else ("1" if inside else "0"))
            self.cells.append("".join(row))

    def contains(self, lat, lon):
        r = math.floor((lat - self.min_lat) / CELL_SIZE_DEGREES)
        c = math.floor((lon - self.min_lon) / CELL_SIZE_DEGREES)
        if not (0 <= r < self.rows and 0 <= c < self.columns):
            return False
        state = self.cells[r][c]
        if state in "01":
            return state == "1"
        clat = self.min_lat + (r + 0.5) * CELL_SIZE_DEGREES
        clon = self.min_lon + (c + 0.5) * CELL_SIZE_DEGREES
        inside = state == "3"
        for index in self.cell_edges[(r, c)]:
            if segments_cross(lat, lon, clat, clon, *self.edges[index]):
                inside = not inside
        return inside

    def geometry(self):
        """The rings combined with the even-odd rule, as the lookup sees them."""
        result = Polygon()
        for ring in self.rings:
            polygon = make_valid(Polygon([(lon / COORDINATE_SCALE, lat / COORDINATE_SCALE) for lat, lon in ring]))
            result = result.symmetric_difference(polygon)
        return result


def orientation(alat, alon, blat, blon, plat, plon):
    value = (blon - alon) * (plat - alat) - (blat - alat) * (plon - alon)
    return (value > 0) - (value < 0)


def segments_cross(qlat, qlon, clat, clon, alat, alon, blat, blon):
    """Whether edge a-b crosses segment q-c. Vertices exactly on the line q-c
    count as lying on its non-positive side, so shared vertices count once."""
    side_a = orientation(qlat, qlon, clat, clon, alat, alon) > 0
    side_b = orientation(qlat, qlon, clat, clon, blat, blon) > 0
    if side_a == side_b:
        return False
    return orientation(alat, alon, blat, blon, qlat, qlon) * orientation(alat, alon, blat, blon, clat, clon) < 0


def swift_region(name, region):
    rows = "\n".join(f"        {row}" for row in reversed(region.cells))
    def wrapped(ring):
        encoded = encode_polyline(ring)
        lines = "\n".join(f"            {encoded[i:i + 100]}" for i in range(0, len(encoded), 100))
        return f'            #"""\n{lines}\n            """#'
    rings = ",\n".join(wrapped(ring) for ring in region.rings)
    return f"""    static let {name} = EncodedBoundaryRegion(
        minLatitude: {region.min_lat},
        minLongitude: {region.min_lon},
        cellSize: {CELL_SIZE_DEGREES},
        rows: {region.rows},
        columns: {region.columns},
        // One line per grid row, north to south. 0 outside, 1 inside,
        // 2 crossed by the boundary with the cell centre outside, 3 with it inside.
        cells: \"\"\"
{rows}
        \"\"\",
        rings: [
{rings}
        ]
    )"""


def main():
    source_note = SOURCE_NOTE
    os.makedirs("out", exist_ok=True)
    regions = {}
    for name, relation_ids in RELATIONS.items():
        merged = unary_union([load_relation(i) for i in relation_ids])
        simplified = make_valid(merged.simplify(SIMPLIFY_TOLERANCE_DEGREES, preserve_topology=True))
        regions[name] = Region(name, rounded_rings(simplified))
    regions["taiwan-strait-waters"] = Region(
        "taiwan-strait-waters",
        rounded_rings(Polygon(TAIWAN_STRAIT_WATERS)),
    )

    swift_names = {
        "china": "china",
        "hong-kong-macau-taiwan": "hongKongMacauTaiwan",
        "taiwan-strait-waters": "taiwanStraitWaters",
    }
    for name, region in regions.items():
        feature = {
            "type": "Feature",
            "properties": {
                "region": name,
                "osm_relations": RELATIONS.get(name, []),
                "simplify_tolerance_degrees": SIMPLIFY_TOLERANCE_DEGREES if name in RELATIONS else None,
                "source": source_note if name in RELATIONS else "hand-drawn strait polygon, see build.py",
            },
            "geometry": mapping(region.geometry()),
        }
        with open(os.path.join("out", f"{name}.geojson"), "w") as f:
            json.dump({"type": "FeatureCollection", "features": [feature]}, f)
        vertices = sum(len(r) for r in region.rings)
        boundary = sum(row.count("2") + row.count("3") for row in region.cells)
        print(f"{name}: rings={len(region.rings)} vertices={vertices} grid={region.rows}x{region.columns} boundary_cells={boundary}")

    body = "\n\n".join(swift_region(swift_names[n], r) for n, r in regions.items())
    swift = f"""// Generated by build.py in GoDaie/life-in-mist-boundary-data. Do not edit.
// Boundary data © OpenStreetMap contributors, available under the
// Open Database License 1.0 (https://www.openstreetmap.org/copyright).
// Source: {source_note}

enum BoundaryRegionData {{
{body}
}}
"""
    with open(os.path.join("out", "BoundaryRegionData.swift"), "w") as f:
        f.write(swift)
    return regions


if __name__ == "__main__":
    main()
