"""
Append Winnipeg (boundary + 2021 population) to mb_10_munis_with_pop.geojson.

Requirements (install if needed):
  pip install geopandas shapely osmnx

Usage:
  python append_winnipeg.py --in mb_10_munis_with_pop.geojson \
                            --out mb_10_munis_with_pop_plus_winnipeg.geojson
"""

import argparse
import json
import os
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry import mapping
from shapely.ops import unary_union

WINNIPEG_NAME = "Winnipeg"
WINNIPEG_STATUS = "City"
WINNIPEG_POP_2021 = 749_607  # Statistics Canada, 2021 Census, Winnipeg CSD (CY)
OSM_QUERY = "Winnipeg, Manitoba, Canada"

def get_winnipeg_boundary():
    # Pull admin boundary for Winnipeg from OSM (as a GeoDataFrame in WGS84)
    gdf = ox.geocode_to_gdf(OSM_QUERY, which_result=None, by_osmid=False)
    # Keep polygonal geometry only and dissolve to a single (multi)polygon
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    if gdf.empty:
        raise RuntimeError("No polygonal geometry returned for Winnipeg from OSM.")
    geom = unary_union(gdf.geometry.values)
    return geom  # WGS84 already

def load_geojson(path):
    # Load without geopandas first to keep property schema intact if needed
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("type") != "FeatureCollection":
        raise ValueError("Input is not a valid GeoJSON FeatureCollection.")
    return data

def detect_property_schema(features):
    # Expect keys like: MUNI_NAME, MUNI_STATU, population_2021, name, status
    # We'll mirror what the file already uses; fall back if missing.
    keys = set()
    for f in features:
        keys.update(f.get("properties", {}).keys())
    # Required (from your example file)
    prop_keys = {
        "MUNI_NAME": "MUNI_NAME" if "MUNI_NAME" in keys else None,
        "MUNI_STATU": "MUNI_STATU" if "MUNI_STATU" in keys else None,
        "population_2021": "population_2021" if "population_2021" in keys else None,
        "name": "name" if "name" in keys else None,
        "status": "status" if "status" in keys else None,
    }
    return prop_keys

def already_has_winnipeg(features):
    for f in features:
        props = f.get("properties", {})
        n1 = str(props.get("MUNI_NAME", "")).strip().lower()
        n2 = str(props.get("name", "")).strip().lower()
        if n1 == WINNIPEG_NAME.lower() or n2 == WINNIPEG_NAME.lower():
            return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Input GeoJSON path")
    ap.add_argument("--out", dest="out_path", required=True, help="Output GeoJSON path")
    ap.add_argument("--simplify", type=float, default=0.0,
                    help="Optional simplification tolerance in degrees (e.g., 0.0005). Default=0 (no simplify).")
    args = ap.parse_args()

    data = load_geojson(args.in_path)
    features = data.get("features", [])

    if already_has_winnipeg(features):
        print("Winnipeg already present; writing a copy to the --out path without changes.")
        with open(args.out_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return

    print("Fetching Winnipeg boundary from OpenStreetMap…")
    geom = get_winnipeg_boundary()
    if args.simplify and args.simplify > 0:
        try:
            geom = geom.simplify(args.simplify, preserve_topology=True)
        except Exception as e:
            print(f"Warning: simplify failed ({e}); using original geometry.")

    # Mirror the existing property schema
    schema = detect_property_schema(features)
    props = {}
    # Fill properties that exist in your file
    if schema["MUNI_NAME"]:        props[schema["MUNI_NAME"]] = WINNIPEG_NAME
    if schema["MUNI_STATU"]:       props[schema["MUNI_STATU"]] = WINNIPEG_STATUS
    if schema["population_2021"]:  props[schema["population_2021"]] = WINNIPEG_POP_2021
    if schema["name"]:             props[schema["name"]] = WINNIPEG_NAME
    if schema["status"]:           props[schema["status"]] = WINNIPEG_STATUS

    # Build the new feature
    new_feature = {
        "type": "Feature",
        "properties": props,
        "geometry": mapping(geom)  # GeoJSON-ready dict
    }

    # Append and write
    data["features"].append(new_feature)

    # Optional: ensure CRS metadata if present originally
    # (Most simple FeatureCollections omit "crs", which is fine for WGS84)
    out_dir = Path(args.out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    print(f"Done. Appended Winnipeg to GeoJSON -> {args.out_path}")

if __name__ == "__main__":
    in_path = "data/mb_10_munis_with_pop.geojson"
    out_path = "data/mb_with_winnipeg.geojson"

    data = load_geojson(in_path)
    features = data.get("features", [])

    if already_has_winnipeg(features):
        print("Winnipeg already present; writing copy without changes.")
    else:
        geom = get_winnipeg_boundary()
        schema = detect_property_schema(features)
        props = {
            schema["MUNI_NAME"]: "Winnipeg",
            schema["MUNI_STATU"]: "City",
            schema["population_2021"]: 749_607,
            schema["name"]: "Winnipeg",
            schema["status"]: "City",
        }
        new_feature = {"type": "Feature", "properties": props, "geometry": mapping(geom)}
        data["features"].append(new_feature)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"✅ Done. File saved to {out_path}")
