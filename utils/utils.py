"""
Utility functions for the Manitoba Incidents Streamlit app.

This module centralizes helper logic for:
  • Geometry handling (bounds, centroid, coordinate iteration)
  • Incident parsing & filtering
  • Styling and icons (including loading SVGs for markers)
  • Municipality property normalization and filters
"""
from __future__ import annotations
import json
import os
from typing import Dict, Any, Iterable, Iterator, List, Tuple, Optional

import folium

# -------------------------- Geometry helpers --------------------------

def iter_coords(geom: Dict[str, Any]) -> Iterator[Tuple[float, float]]:
    """
    Yield (lon, lat) coordinate pairs from a GeoJSON Polygon or MultiPolygon geometry.

    Parameters
    ----------
    geom : dict
        A GeoJSON-like geometry dictionary.

    Yields
    ------
    (float, float)
        Longitude, latitude pairs.
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        for ring in coords:
            for x, y in ring:
                yield (x, y)
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for x, y in ring:
                    yield (x, y)


def get_bounds(features: Iterable[Dict[str, Any]]) -> List[List[float]]:
    """
    Compute south-west and north-east bounds for a collection of features.

    Parameters
    ----------
    features : iterable of dict
        An iterable of GeoJSON Feature dictionaries.

    Returns
    -------
    list
        [[south, west], [north, east]] suitable for folium.fit_bounds.
    """
    xs, ys = [], []
    for feat in features:
        geom = feat.get("geometry", {})
        if not geom:
            continue
        for x, y in iter_coords(geom):
            xs.append(x); ys.append(y)
    if not xs:
        # Fallback: approximate bounds for Manitoba
        return [[48.0, -102.0], [60.5, -88.0]]
    return [[min(ys), min(xs)], [max(ys), max(xs)]]


def centroid_of_feature(feature: Dict[str, Any]) -> Tuple[float, float]:
    """
    Approximate centroid (lat, lon) for a polygon feature by averaging coordinates.
    For large or complex polygons, consider using shapely for accuracy.

    Parameters
    ----------
    feature : dict
        GeoJSON Feature with Polygon/MultiPolygon geometry.

    Returns
    -------
    (lat, lon) : tuple of float
    """
    xs, ys = [], []
    geom = feature.get("geometry", {})
    for x, y in iter_coords(geom):
        xs.append(x); ys.append(y)
    if xs:
        return (sum(ys)/len(ys), sum(xs)/len(xs))
    return (50.0, -97.0)


# -------------------------- Incident helpers --------------------------

def split_incidents(incidents_data: Dict[str, Any], status_filter: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Split input incidents into wildfire and flood feature lists, honoring a status filter.
    Accepts either GeoJSON FeatureCollection (features[].properties.type) or a custom
    structure: {'wildfires': [...], 'floods': [...]} with polygon coordinates.

    Parameters
    ----------
    incidents_data : dict
        Input incidents data.
    status_filter : list of str
        Allowed statuses (e.g., ['confirmed', 'suspected']).

    Returns
    -------
    (wildfires, floods) : tuple of lists of GeoJSON Features
    """
    wf_features: List[Dict[str, Any]] = []
    fl_features: List[Dict[str, Any]] = []

    if isinstance(incidents_data, dict) and incidents_data.get("type") == "FeatureCollection":
        for feat in incidents_data.get("features", []):
            props = feat.get("properties", {})
            t = props.get("type")
            stat = props.get("status")
            if stat not in status_filter:
                continue
            if t == "wildfire":
                wf_features.append(feat)
            elif t == "flood":
                fl_features.append(feat)
    else:
        # fallback for custom structure
        for inc in incidents_data.get("wildfires", []):
            if inc.get("status") in status_filter:
                wf_features.append({
                    "type": "Feature",
                    "properties": {k: v for k, v in inc.items() if k != "coordinates"} | {"type": "wildfire"},
                    "geometry": {"type": "Polygon", "coordinates": [inc["coordinates"]]}
                })
        for inc in incidents_data.get("floods", []):
            if inc.get("status") in status_filter:
                fl_features.append({
                    "type": "Feature",
                    "properties": {k: v for k, v in inc.items() if k != "coordinates"} | {"type": "flood"},
                    "geometry": {"type": "Polygon", "coordinates": [inc["coordinates"]]}
                })
    return wf_features, fl_features


def style_for_feature(props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a folium style dict for an incident polygon based on type and status.

    Colors follow:
      - Wildfire: red shades (#d73027 confirmed, #fc8d59 suspected)
      - Flood: blue/teal (#2c7fb8 confirmed, #7fcdbb suspected)
    """
    kind = props.get('type')
    conf = props.get('status') or props.get('confidence')
    if kind == 'wildfire':
        color = '#d73027' if conf == 'confirmed' else '#fc8d59'
    else:
        color = '#2c7fb8' if conf == 'confirmed' else '#7fcdbb'
    return {'color': color, 'weight': 2, 'fillColor': color, 'fillOpacity': 0.25}


def make_muni_style(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    Style function for municipality polygons based on status (city/town).
    """
    status = (feature.get("properties", {}).get("status", "") or "").lower()
    color = "#3b82f6" if status == "city" else "#10b981" if status == "town" else "#64748b"
    return {"fillOpacity": 0.35, "weight": 2, "color": color}


# -------------------------- Icon helpers --------------------------

def load_svg_icon(path: str, size: Tuple[int, int] = (30, 30)) -> Optional[folium.CustomIcon]:
    """
    Load an SVG file and return a folium.CustomIcon. If the file is missing,
    return None so the caller can fall back to a standard folium.Icon.

    Parameters
    ----------
    path : str
        Path to the local SVG file.
    size : (int, int)
        Icon size in pixels.

    Returns
    -------
    folium.CustomIcon | None
    """
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            svg = f.read()
        import base64
        uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return folium.CustomIcon(icon_image=uri, icon_size=size)
    except Exception:
        return None


def icon_for_feature(props: Dict[str, Any], fire_icon: Optional[folium.CustomIcon] = None, flood_icon: Optional[folium.CustomIcon] = None) -> folium.map.Icon:
    """
    Return an icon for an incident. Prefer provided CustomIcons (SVG),
    otherwise fall back to Folium's AwesomeMarkers (Font Awesome).

    Parameters
    ----------
    props : dict
        Feature properties dict.
    fire_icon : folium.CustomIcon | None
        Preloaded fire SVG icon.
    flood_icon : folium.CustomIcon | None
        Preloaded droplet SVG icon.

    Returns
    -------
    folium.Icon | folium.CustomIcon
    """
    kind = props.get('type')
    conf = props.get('status') or props.get('confidence')
    if kind == 'wildfire':
        if fire_icon is not None:
            return fire_icon
        color = 'red' if conf == 'confirmed' else 'orange'
        return folium.Icon(color=color, icon='fire', prefix='fa')
    elif kind == 'flood':
        if flood_icon is not None:
            return flood_icon
        color = 'blue' if conf == 'confirmed' else 'lightblue'
        return folium.Icon(color=color, icon='tint', prefix='fa')
    return folium.Icon(color='gray', icon='info-sign')


# -------------------------- Municipality helpers --------------------------

def normalize_muni_properties(muni_feats: List[Dict[str, Any]]) -> None:
    """
    Normalize common property names for municipality features in-place.
    Adds 'name' and 'status' if only 'MUNI_NAME'/'MUNI_STATU' exist.
    """
    for f in muni_feats:
        p = f.setdefault("properties", {})
        if "name" not in p and "MUNI_NAME" in p:
            p["name"] = p["MUNI_NAME"]
        if "status" not in p and "MUNI_STATU" in p:
            p["status"] = p["MUNI_STATU"]


def muni_passes(f: Dict[str, Any], sel_status: List[str], sel_pop: Tuple[int, int]) -> bool:
    """
    Return True if a municipality feature passes the sidebar filters.

    Parameters
    ----------
    f : dict
        Municipality feature.
    sel_status : list of str
        Accepted statuses (e.g., ['City', 'Town']).
    sel_pop : (int, int)
        Inclusive population range.
    """
    p = f.get("properties", {})
    if p.get("status", "Unknown") not in sel_status:
        return False
    pv = p.get("population_2021")
    return isinstance(pv, (int, float)) and sel_pop[0] <= pv <= sel_pop[1]
