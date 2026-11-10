"""يبني terrain.mbtiles (ارتفاعات بصيغة terrarium) للسعودية من بيانات AWS المفتوحة."""
import math, sqlite3, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

W, S, E, N = 34.4, 15.5, 56.0, 32.4
MAXZ = 10
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

def tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)

tiles = []
for z in range(MAXZ + 1):
    x0, y0 = tile(W, N, z)
    x1, y1 = tile(E, S, z)
    tiles += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
print("tiles:", len(tiles), flush=True)

def fetch(t):
    z, x, y = t
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL.format(z=z, x=x, y=y), headers={"User-Agent": "saudi-tiles-builder"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return t, r.read()
        except Exception:
            time.sleep(1 + attempt)
    return t, None

db = sqlite3.connect("terrain.mbtiles")
db.executescript("""
CREATE TABLE metadata (name TEXT, value TEXT);
CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);
CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
""")
meta = {"name": "ksa-terrain", "format": "png", "minzoom": "0", "maxzoom": str(MAXZ),
        "bounds": f"{W},{S},{E},{N}", "type": "baselayer", "version": "1",
        "description": "Terrarium elevation tiles (AWS Terrain Tiles)"}
db.executemany("INSERT INTO metadata VALUES (?,?)", meta.items())

missing = 0
with ThreadPoolExecutor(16) as ex:
    for i, ((z, x, y), data) in enumerate(ex.map(fetch, tiles)):
        if data is None:
            missing += 1
            continue
        db.execute("INSERT INTO tiles VALUES (?,?,?,?)", (z, x, (2 ** z - 1) - y, data))
        if i % 500 == 0:
            db.commit(); print(i, "/", len(tiles), flush=True)
db.commit(); db.close()
print("missing:", missing)
if missing > len(tiles) * 0.02:
    sys.exit("too many missing tiles")
