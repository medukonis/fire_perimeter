# Wildfire Perimeter Address Check API

## Overview
This Flask-based API checks whether a given address falls within a wildfire perimeter. The script utilizes KML data from wildfire agencies and integrates with the Google Geocoding API to determine the geographical location of the input address.

## Features
- Parses KML files to extract wildfire perimeter polygons.
- Uses the Google Geocoding API to obtain latitude and longitude for a given address.
- Checks if the geocoded point falls within a wildfire perimeter.
- Calculates the distance to the nearest fire perimeter if the address is outside.
- Logs all API requests and responses to a CSV file.
- Supports CORS for cross-origin requests.

## Requirements
### Software
- Python 3.x
- Flask
- Flask-CORS
- Shapely
- Requests
- xml.etree.ElementTree (built-in)
- Werkzeug (for proxy handling)

### API Key
- Google Maps Geocoding API key is required to convert addresses to latitude/longitude.
  - Obtain a key from: [Google Cloud Console](https://console.cloud.google.com/)

## Installation
1. Clone the repository or copy the script.
2. Install dependencies:
   ```sh
   pip install flask flask-cors shapely requests
   ```
3. Update the script with your Google API key.
   ```python
   api_key = 'YOUR_GOOGLE_API_KEY'
   ```
4. Ensure your KML file is accessible at the configured path.

## Usage
### Running the API
```sh
python flask_fires.py
```

### API Endpoints
#### 1. Check if an address is inside a wildfire perimeter
- **Endpoint:** `/check-address`
- **Method:** `POST`
- **Request Body:**
  ```json
  {
    "address": "123 Main St, Los Angeles, CA",
    "placemark_name": "PALISADES"  # Optional, defaults to 'PALISADES'
  }
  ```
- **Response Example:**
  ```json
  {
    "address": "123 Main St, Los Angeles, CA",
    "coordinates": [34.0522, -118.2437],
    "inside_polygon": false,
    "distance_to_perimeter": 2.5,
    "placemark_name": "PALISADES",
    "message": "Outside PALISADES fire perimeter, 2.5 miles away"
  }
  ```

#### 2. Get available wildfire perimeter names
- **Endpoint:** `/get-polygons`
- **Method:** `GET`
- **Response Example:**
  ```json
  {
    "polygons": ["PALISADES", "DIXIE", "CALDOR"]
  }
  ```

## Logs
The system logs all requests to `address_checks.csv` with details such as:
- Date, Time, IP Address, User Agent
- Address Checked, Latitude, Longitude
- KML File Used, Placemark Name
- Inside Fire Perimeter, Distance to Perimeter
- HTTP Status, Success Flag, Error Message

## Deployment
- The script is configured to run with SSL:
  ```python
  app.run(host="0.0.0.0", port=5000, ssl_context=('/etc/apache2/ssl/your_ssh_pemfile.pem', '/etc/apache2/ssl/your_ssh_keyfile.key'))
  ```
- Ensure valid SSL certificates are available at the specified paths.
- Use a process manager like `gunicorn` or `supervisor` for production deployment.

## Notes
- Make sure the Google API key has permissions for Geocoding API.
- Fire perimeters are sourced from [WFIGS Current Interagency Fire Perimeters](https://data-nifc.opendata.arcgis.com/).
- Address verification depends on accurate KML data and API responses.

## Author
Mike Edukonis
Updated: March 2, 2025

