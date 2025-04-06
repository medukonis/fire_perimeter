'''
Author: Mike Edukonis
Updated April 5, 2025
Refactored.
Updated to use with all disasters.  Enter an address and script will tell you if address is within a polygon...and which one.  If it is not
inside a polygon, which one is closet and how far.

Update March 2, 2025
Palisades fire is 100% contained and there will be no more updates to the fire perimeters file
There are several fires in CA and each polygon has it's own name.  User can now select which fire polygon to check against an address'

Date: January 20, 2025
Description: This script provides a Flask-based API to check if a given address is within a wildfire perimeter
by parsing KML data and using the Google Geocoding API. to get an updated perimeter map
WFIGS Current Interagency Fire Perimeters https://data-nifc.opendata.arcgis.com/maps/d1c32af3212341869b3c810f1a215824

'Test Data:
'1369 El Hito Cir, Pacific Palisades, CA 90272
'15007 Bestor Blvd, Pacific Palisades, CA 90272
'''

from flask import Flask, request, jsonify
from flask_cors import CORS
from shapely.geometry import Point, Polygon
import xml.etree.ElementTree as ET
import requests
import csv
from datetime import datetime
import os
import time
from math import radians, sin, cos, sqrt, atan2
from shapely.ops import nearest_points
from geopy.distance import geodesic

GOOGLE_MAPS_API_KEY = "YOUR API KEY HERE"

# Absolute path or relative to script
kml_path = os.path.join(os.path.dirname(__file__), '/home/medukonis/Downloads/doc2.kml')


'''
Class: RequestLogger
Description: Handles logging of requests to a CSV file.
Attributes: log_file (str): The path to the log file.
'''
class RequestLogger:
    def __init__(self, log_file='address_checks.csv'):
        self.log_file = log_file
        self._ensure_file_exists()

    '''
    Method: _ensure_file_exists
    Description: Creates a CSV file with headers if it doesn't exist.
    Inputs: None
    Outputs: None
    '''
    def _ensure_file_exists(self):
        """Create the CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Date',
                    'Time',
                    'IP Address',
                    'User Agent',
                    'Checked Address',
                    'Latitude',
                    'Longitude',
                    'KML File',
                    'Polygon Name',
                    'Inside Fire Perimeter',
                    'Distance',
                    'Response Time (ms)',
                    'HTTP Status',
                    'Success',
                    'Error Message'
                ])

    '''
    Method: log_request
    Description: Logs a single request to the CSV file with relevant details.
    Inputs: kwargs (dict): Dictionary containing request data.
    Outputs: None
    '''
    def log_request(self, **kwargs):
        """Log a single request to the CSV file with all available information"""
        now = datetime.now()

        row = [
            now.strftime('%Y-%m-%d'),                    # Date
            now.strftime('%H:%M:%S'),                    # Time
            kwargs.get('ip_address', ''),                # IP Address
            kwargs.get('user_agent', ''),                # User Agent
            kwargs.get('address', ''),                   # Checked Address
            kwargs.get('latitude', ''),                  # Latitude
            kwargs.get('longitude', ''),                 # Longitude
            kwargs.get('kml_file', ''),                  # KML File Path
            kwargs.get('placemark_name', ''),            # Placemark Name
            kwargs.get('inside_perimeter', ''),          # Inside Fire Perimeter
            kwargs.get('distance', ''),
            kwargs.get('response_time_ms', ''),          # Response Time
            kwargs.get('http_status', ''),               # HTTP Status
            kwargs.get('success', False),                # Success
            kwargs.get('error_message', '')              # Error Message
        ]

        with open(self.log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

logger = RequestLogger()
app = Flask(__name__)
CORS(app)
'''
    Function: haversine_distance
    Description: Calculates the Haversine distance from a point to the nearest point on a polygon.
    Inputs:
        point1 (Point): A Shapely Point object representing the location.
        polygon (Polygon): A Shapely Polygon object representing the fire perimeter.
    Outputs:
        float: Distance in miles.
'''
def haversine_distance(point1, polygon):
    # Earth's radius in miles
    R = 3958.8

    # Convert coordinates to radians
    lon1, lat1 = point1.x, point1.y
    lon1, lat1 = radians(lon1), radians(lat1)

    # Find the nearest point on the polygon's exterior
    nearest_point = polygon.exterior.interpolate(polygon.exterior.project(point1))
    lon2, lat2 = nearest_point.x, nearest_point.y
    lon2, lat2 = radians(lon2), radians(lat2)

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c

    return distance


# Step 1: Parse the KML file to extract polygons
'''
Function: parse_kml
Description: Parses a KML file to extract polygons for a given placemark.
Inputs:
    kml_file (str): Path to the KML file.
    placemark_name (str): The name of the placemark to extract polygons for.
Outputs:
    list: List of Shapely Polygon objects.
'''
def parse_kml(kml_file):
    tree = ET.parse(kml_file)
    root = tree.getroot()
    namespace = {'kml': 'http://www.opengis.net/kml/2.2'}

    polygons = []
    for placemark in root.findall(".//kml:Placemark", namespace):
        name_elem = placemark.find('kml:name', namespace)
        name = name_elem.text if name_elem is not None else "Unnamed"

        for polygon in placemark.findall(".//kml:Polygon", namespace):
            # Outer boundary
            outer_coords_text = polygon.find(".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", namespace).text.strip()
            outer_coords = [
                (float(lon), float(lat))
                for lon, lat, _ in (coord.split(",") for coord in outer_coords_text.split())
            ]

            # Inner boundaries (holes)
            inner_coords_list = []
            for inner_boundary in polygon.findall(".//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", namespace):
                inner_coords_text = inner_boundary.text.strip()
                inner_coords = [
                    (float(lon), float(lat))
                    for lon, lat, _ in (coord.split(",") for coord in inner_coords_text.split())
                ]
                inner_coords_list.append(inner_coords)

            # Append full polygon with name
            polygons.append((Polygon(shell=outer_coords, holes=inner_coords_list), name))

    return polygons

# Parse the KML and store the polygon data for later use
polygons = parse_kml(kml_path)

print(f"Loaded {len(polygons)} polygons from {kml_path}")

# Step 2: Use Google Geocoding API to get latitude and longitude for an address
'''
Function: geocode_address
Description: Uses the Google Geocoding API to get latitude and longitude for an address.
Inputs:
    address (str): Address string to be geocoded.
    api_key (str): Google API key.
Outputs:
    tuple: Longitude and latitude of the address.
'''
def geocode_address(address):
    url = f"https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return location["lng"], location["lat"]  # Return longitude, latitude
        else:
            raise ValueError(f"Geocoding failed: {data['status']}")
    else:
        raise ConnectionError(f"Error connecting to Geocoding API: {response.status_code}")


#API Route to check if an address is inside a polygon
#Contains Step 3: Check if the point is inside any polygon
@app.route('/check-address', methods=['POST'])
def check_address():
    start_time = time.time()

    data = request.json
    address = data.get('address')

    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')

    if not address:
        logger.log_request(
            ip_address=ip_address,
            user_agent=user_agent,
            address='',
            kml_file=kml_path,
            http_status=400,
            success=False,
            error_message="No address provided",
            response_time_ms=round((time.time() - start_time) * 1000, 2)
        )
        return jsonify({"error": "No address provided."}), 400

    try:
        lon, lat = geocode_address(address)
        if lat is None or lon is None:
            raise ValueError("Failed to geocode address.")
    except Exception as e:
        logger.log_request(
            ip_address=ip_address,
            user_agent=user_agent,
            address=address,
            kml_file=kml_path,
            http_status=500,
            success=False,
            error_message=str(e),
            response_time_ms=round((time.time() - start_time) * 1000, 2)
        )
        return jsonify({"error": str(e)}), 500

    point = Point(lon, lat)
    inside_polygon_name = None
    closest_polygon_name = None
    closest_distance_miles = float("inf")

    for polygon, name in polygons:
        if polygon.contains(point):
            inside_polygon_name = name
            break
        else:
            nearest_geom = nearest_points(polygon.boundary, point)[0]
            distance_miles = geodesic((lat, lon), (nearest_geom.y, nearest_geom.x)).miles
            if distance_miles < closest_distance_miles:
                closest_distance_miles = distance_miles
                closest_polygon_name = name

    response_time = round((time.time() - start_time) * 1000, 2)

    if inside_polygon_name:
        logger.log_request(
            ip_address=ip_address,
            user_agent=user_agent,
            address=address,
            latitude=lat,
            longitude=lon,
            kml_file=kml_path,
            placemark_name=inside_polygon_name,
            inside_perimeter=True,
            distance=0,
            http_status=200,
            success=True,
            response_time_ms=response_time
        )
        return jsonify({
            "address": address,
            "inside": True,
            "polygon": inside_polygon_name,
            "lat": lat,
            "lon": lon
        })
    else:
        logger.log_request(
            ip_address=ip_address,
            user_agent=user_agent,
            address=address,
            latitude=lat,
            longitude=lon,
            kml_file=kml_path,
            placemark_name=closest_polygon_name,
            inside_perimeter=False,
            distance=round(closest_distance_miles, 1),
            http_status=200,
            success=True,
            response_time_ms=response_time
        )
        return jsonify({
            "address": address,
            "inside": False,
            "closest_polygon": closest_polygon_name,
            "distance_miles": round(closest_distance_miles, 1),
            "lat": lat,
            "lon": lon
        })

@app.route('/get-polygons', methods=['GET'])
def get_polygons():
    kml_path = '/home/medukonis/Downloads/doc2.kml'
    try:
        polygon_names = extract_polygon_names(kml_path)
        return jsonify({"polygons": polygon_names})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def extract_polygon_names(kml_file):
    """Extract all polygon names from the KML file."""
    tree = ET.parse(kml_file)
    root = tree.getroot()
    namespace = {'kml': 'http://www.opengis.net/kml/2.2'}

    polygon_names = []
    for placemark in root.findall(".//kml:Placemark", namespace):
        name_elem = placemark.find('kml:name', namespace)
        if name_elem is not None:
            polygon_names.append(name_elem.text)

    return polygon_names


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, ssl_context=('/etc/apache2/ssl/edukonis_com.pem', '/etc/apache2/ssl/edukonis_com.key'))
