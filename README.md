# Life in Mist boundary data

Simplified OpenStreetMap boundaries used by the Life in Mist iOS app to decide
how a GPS point is stored and drawn:

- **GCJ zone**: mainland China, Hong Kong, Macau and Taiwan (including Kinmen,
  Matsu and Penghu), their territorial seas, and the open water of the Taiwan
  Strait. Inside this zone China-mode maps draw coordinates in GCJ-02.
- **Mainland administrative area**: the China boundary minus Hong Kong, Macau
  and Taiwan.

The app composes both from three regions in `out/`:

| File | Content |
| --- | --- |
| `china.geojson` | OSM relation 270056 (People's Republic of China, includes Hong Kong, Macau and the waters around Kinmen and Matsu) |
| `hong-kong-macau-taiwan.geojson` | OSM relations 913110 (Hong Kong), 1867188 (Macau), 449220 (Taiwan) |
| `taiwan-strait-waters.geojson` | Hand-drawn polygon closing the strait between the two territorial seas (see `build.py`) |
| `BoundaryRegionData.swift` | The same regions as encoded polylines plus a 0.25° lookup grid, compiled into the app |

GCJ zone = china ∪ hong-kong-macau-taiwan ∪ taiwan-strait-waters;
mainland area = china − hong-kong-macau-taiwan. Disputed areas follow the
OpenStreetMap boundaries as exported.

## Source

`src/rel_<id>.geojson` are the unmodified exports of the four relations from
[polygons.openstreetmap.fr](https://polygons.openstreetmap.fr/) (`params=0`),
downloaded on 2026-10-12.

## Processing

`build.py` repairs the geometry (`make_valid`), simplifies it with a tolerance of
0.001° (about 110 m; the largest deviation from the unsimplified boundary
measured by `validate.py` was 99 m), rounds coordinates to 1e-5°, and builds the
grid. Each grid cell is either uniformly inside, uniformly outside, or crossed by
the boundary; a point in a crossed cell is resolved by counting the edges between
it and the cell centre. The app's lookup (`BoundaryRegion.swift`) uses the same
rules and must change together with `build.py`.

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python build.py       # writes out/
venv/bin/python validate.py    # grid vs brute force, simplified vs original, named test points
```

## Licenses

- Data (`src/`, `out/`): © OpenStreetMap contributors, available under the
  [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
  (`LICENSE-DATA.md`). See <https://www.openstreetmap.org/copyright>.
  The derived regions are a Derivative Database under the ODbL and are shared
  here under the same license.
- Scripts (`build.py`, `validate.py`): MIT (`LICENSE-CODE`).
