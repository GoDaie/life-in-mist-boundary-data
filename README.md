# Life in Mist boundary data

Simplified geometry and lookup data used by the Life in Mist iOS app for point
classification and coordinate rendering.

## Data inputs

The app combines three geometry inputs from `out/`:

| Technical role | File | Input |
| --- | --- | --- |
| Base geometry | `china.geojson` | OSM relation 270056 |
| Auxiliary geometry | `hong-kong-macau-taiwan.geojson` | Union of OSM relations 913110, 1867188 and 449220 |
| Supplemental coverage geometry | `taiwan-strait-waters.geojson` | Manually defined polygon in `build.py` |
| Encoded lookup data | `BoundaryRegionData.swift` | The same regions as encoded polylines plus a 0.25° lookup grid |

The existing file names and region identifiers are stable technical keys used
by the app and the build scripts.

## Point classification

The app uses the geometry inputs for two lookups:

```text
rendering coverage = base geometry ∪ auxiliary geometry ∪ supplemental geometry
primary processing region = base geometry − auxiliary geometry
```

The rendering coverage lookup determines where the app draws coordinates in
GCJ-02 when using its GCJ-02 map mode. The primary processing lookup tests
whether a point is inside the base geometry and outside the auxiliary geometry.

## Source

`src/rel_<id>.geojson` are the unmodified exports of the four relations from
[polygons.openstreetmap.fr](https://polygons.openstreetmap.fr/) (`params=0`),
downloaded on 2026-10-12.

## Generation and validation

`build.py` repairs the geometry (`make_valid`), simplifies it with a tolerance of
0.001°, rounds coordinates to 1e-5°, and builds the grid. Each grid cell is either
uniformly inside, uniformly outside, or crossed by the geometry boundary. A
point in a crossed cell is resolved by counting the edges between it and the
cell centre. The app's lookup (`BoundaryRegion.swift`) uses the same rules and
must change together with `build.py`.

`validate.py` compares grid lookup results with direct ring checks, samples
points near the source geometry, and checks predefined coordinates. Reported
sample distances describe the sampled results, not a guaranteed maximum error
bound for the complete geometry.

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python build.py       # writes out/
venv/bin/python validate.py    # grid vs direct rings, source comparison, predefined points
```

## Licenses

- Data (`src/`, `out/`): © OpenStreetMap contributors, available under the
  [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
  (`LICENSE-DATA.md`). See <https://www.openstreetmap.org/copyright>.
  The derived regions are a Derivative Database under the ODbL and are shared
  here under the same license.
- Scripts (`build.py`, `validate.py`): MIT (`LICENSE-CODE`).
