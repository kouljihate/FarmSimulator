"""Generate a realistic test KML (Google-Maps-style export) in the samples folder.

The parcel is ~3 ha around Algiers with a fake terrain so the basin logic
can be exercised (max elevation ~ 178 m).
"""
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))

LAT0, LON0 = 36.75, 3.05


def m_to_deg(dx, dy, lat):
    return dx / (111320.0 * math.cos(math.radians(lat))), dy / 111320.0


# parcel shape: irregular polygon, vertices in metres relative to (LON0, LAT0)
VERTICES_M = [
    (0, 0), (70, 10), (150, -35), (210, -10), (265, 45), (250, 120),
    (190, 175), (120, 215), (60, 190), (15, 130), (-8, 70), (0, 0),
]

# a smooth-ish elevation field: z = 120 + slope*hill
def elev(x, y):
    return 120.0 + 30.0 * math.exp(-(((x - 130) / 60.0) ** 2 + ((y - 60) / 45.0) ** 2)) \
        + 0.04 * y + 0.02 * x


ring = []
for x, y in VERTICES_M:
    dlon, dlat = m_to_deg(x, y, LAT0)
    ring.append((LON0 + dlon, LAT0 + dlat, elev(x, y)))

# water point ~45 m south of the parcel
w_dlon, w_dlat = m_to_deg(120, -45, LAT0)
wlon, wlat = LON0 + w_dlon, LAT0 + w_dlat

coords = " ".join("{0:.7f},{1:.7f},{2:.2f}".format(lon, lat, z) for lon, lat, z in ring)
kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Test parcel - Algiers 3 ha</name>
    <Style id="b">
      <LineStyle><color>ff2f6fa1</color><width>3</width></LineStyle>
      <PolyStyle><color>2e2f6fa1</color></PolyStyle>
    </Style>
    <Placemark>
      <name>Parcel boundary</name>
      <styleUrl>#b</styleUrl>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>{coords}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Water point</name>
      <Point><coordinates>{wlon:.7f},{wlat:.7f},0</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""

out = os.path.join(BASE, "test_parcel.kml")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(kml.format(coords=coords, wlon=wlon, wlat=wlat))
print("wrote", out)