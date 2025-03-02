'''
Author: Mike Edukonis
Date: January 20, 2025
Description: This script provides a Flask-based API to check if a given address is within a wildfire perimeter
by parsing KML data and using the Google Geocoding API. to get an updated perimeter map
WFIGS Current Interagency Fire Perimeters https://data-nifc.opendata.arcgis.com/maps/d1c32af3212341869b3c810f1a215824
'''
from flask import Flask, request, jsonify
from flask_cors import CORS
from shapely.geometry import Point, Polygon
import xml.etree.ElementTree as ET
import requests
from werkzeug.middleware.proxy_fix import ProxyFix
import csv
from datetime import datetime
import os
import time
from math import radians, sin, cos, sqrt, atan2

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
                    'Placemark Name',  # Added placemark name
                    'Inside Fire Perimeter',
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
            kwargs.get('response_time_ms', ''),          # Response Time
            kwargs.get('http_status', ''),               # HTTP Status
            kwargs.get('success', False),                # Success
            kwargs.get('error_message', '')              # Error Message
        ]

        with open(self.log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

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
def parse_kml(kml_file, placemark_name='PALISADES'):
    tree = ET.parse(kml_file)
    root = tree.getroot()
    namespace = {'kml': 'http://www.opengis.net/kml/2.2'}

    polygons = []
    for placemark in root.findall(".//kml:Placemark", namespace):
        # Check for specific placemark name
        name_elem = placemark.find('kml:name', namespace)
        if name_elem is not None and name_elem.text == placemark_name:
            for polygon in placemark.findall(".//kml:Polygon", namespace):
                # Parse outer boundary
                outer_coords_text = polygon.find(".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", namespace).text.strip()
                outer_coords = [
                    (float(lon), float(lat))
                    for lon, lat, _ in (coord.split(",") for coord in outer_coords_text.split())
                ]

                # Parse inner boundaries (holes)
                inner_coords_list = []
                for inner_boundary in polygon.findall(".//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", namespace):
                    inner_coords_text = inner_boundary.text.strip()
                    inner_coords = [
                        (float(lon), float(lat))
                        for lon, lat, _ in (coord.split(",") for coord in inner_coords_text.split())
                    ]
                    inner_coords_list.append(inner_coords)

                # Create a polygon with holes
                polygons.append(Polygon(shell=outer_coords, holes=inner_coords_list))

    return polygons

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
def geocode_address(address, api_key):
    url = f"https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
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

# Step 3: Check if the point is inside any polygon
'''
Function: is_point_in_polygon
Description: Checks if a point is inside any of the given polygons.
Inputs:
    address_coords (tuple): Coordinates (longitude, latitude) of the address.
    polygons (list): List of Shapely Polygon objects.
Outputs:
    bool: True if inside a polygon, otherwise False.
'''
def is_point_in_polygon(address_coords, polygons):
    point = Point(address_coords)
    for polygon in polygons:
        if polygon.contains(point):
            return True
    return False

"""
Function: distance_to_nearest_polygon
Description:
    Calculates the shortest distance from a given point to the nearest polygon
    in a list of polygons. The distance is computed using the Haversine formula.

Inputs:
    - point (shapely.geometry.Point): The geographical point to check.
    - polygons (list of shapely.geometry.Polygon): A list of polygons representing
      different geographic areas.

Outputs:
    - (float): The minimum distance from the point to the nearest polygon in miles.
"""
def distance_to_nearest_polygon(point, polygons):
    distances = [haversine_distance(point, polygon) for polygon in polygons]
    return min(distances)

# API Route to check if an address is inside a polygon
@app.route('/check-address', methods=['POST', 'OPTIONS'])
def check_address():
    if request.method == 'OPTIONS':
        response = app.response_class(status=200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    # Initialize logger and start timer
    logger = RequestLogger()
    start_time = time.time()

    # Get input data
    data = request.json
    address = data.get('address')
    placemark_name = data.get('placemark_name', 'PALISADES')  # Get the placemark name from request or use default
    kml_path = '/home/medukonis/Downloads/doc.kml'
    api_key = 'AIzaSyAh2CHG6fNAVkpD8mdomsMF9nl95WzjVL4'

    # Prepare base logging data
    log_data = {
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', ''),
        'address': address,
        'kml_file': kml_path,
        'placemark_name': placemark_name,  # Add placemark name to the log data
        'success': False
    }

    if not address:
        log_data.update({
            'http_status': 400,
            'error_message': 'Missing required parameter: address',
            'response_time_ms': int((time.time() - start_time) * 1000)
        })
        logger.log_request(**log_data)
        response = jsonify({"error": "Missing required parameter: address"})
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, 400

    try:
        # Parse KML and geocode address
        polygons = parse_kml(kml_path, placemark_name=placemark_name)  # Use the provided placemark name
        address_coords = geocode_address(address, api_key)
        reversed_coords = (address_coords[1], address_coords[0])
        point = Point(address_coords)  # Create Shapely Point object
        is_inside = is_point_in_polygon(address_coords, polygons)

        # Calculate distance if the point is not inside any polygon
        distance = 0 if is_inside else round(distance_to_nearest_polygon(point, polygons), 1)

        # Update log data with successful results
        log_data.update({
            'latitude': reversed_coords[0],
            'longitude': reversed_coords[1],
            'inside_perimeter': is_inside,
            'http_status': 200,
            'success': True,
            'response_time_ms': int((time.time() - start_time) * 1000)
        })

        logger.log_request(**log_data)

        return jsonify({
            "address": address,
            "coordinates": reversed_coords,
            "inside_polygon": is_inside,
            "distance_to_perimeter": round(distance, 1),  # Round to one decimal point
            "placemark_name": placemark_name,  # Include the placemark name in the response
            "message": f"{'Inside' if is_inside else 'Outside'} {placemark_name} fire perimeter" + (f", {distance} miles away" if not is_inside else "")
        })

    except Exception as e:
        error_message = str(e)
        log_data.update({
            'http_status': 500,
            'error_message': error_message,
            'response_time_ms': int((time.time() - start_time) * 1000)
        })
        logger.log_request(**log_data)
        return jsonify({"error": error_message}), 500

@app.route('/get-polygons', methods=['GET'])
def get_polygons():
    kml_path = '/home/medukonis/Downloads/doc.kml'
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
