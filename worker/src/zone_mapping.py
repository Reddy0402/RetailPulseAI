import json
from shapely.geometry import Point, Polygon
from typing import Dict, List, Optional, Tuple

class PolygonZoneMapper:
    """
    Ray-Casting Polygon Spatial Mapper.
    Uses Shapely to verify whether a customer's track coordinates fall inside
    physical retail zones defined dynamically inside store_001.json.
    """
    def __init__(self, layout_path: str):
        with open(layout_path) as f:
            self.layout_data = json.load(f)

        self.store_id = self.layout_data["store_id"]
        
        # Build Shapely Polygons for each camera's zones
        self.camera_polygons: Dict[str, Dict[str, Polygon]] = {}
        
        for camera_id, cam_data in self.layout_data["cameras"].items():
            self.camera_polygons[camera_id] = {}
            for zone_id, coords in cam_data["zones"].items():
                # coords is a list of [x, y] coordinates forming the polygon
                poly = Polygon(coords)
                self.camera_polygons[camera_id][zone_id] = poly

    def get_zone(self, camera_id: str, point: Tuple[float, float]) -> Optional[str]:
        """
        Calculates which physical zone contains the given 2D screen coordinate.
        """
        if camera_id not in self.camera_polygons:
            return None

        # Point representing shopper feet coordinates
        pt = Point(point)
        
        for zone_id, poly in self.camera_polygons[camera_id].items():
            if poly.contains(pt):
                return zone_id
                
        return None
