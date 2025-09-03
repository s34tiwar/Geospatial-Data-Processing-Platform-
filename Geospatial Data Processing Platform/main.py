import requests
import json
import urllib.parse
import os

# PostGIS specific imports
import psycopg2
from psycopg2 import sql
from shapely.geometry import Polygon, Point, shape
from shapely.wkt import dumps as wkt_dumps

# Import the Planet service function
from planet_service import get_and_process_planet_imagery, check_planet_api_key_validity

#-----------------MAPBOX------------------
MAPBOX_TOKEN = os.getenv('MAPBOX_TOKEN', 'YOUR_MAPBOX_TOKEN_HERE')

if MAPBOX_TOKEN == 'YOUR_MAPBOX_TOKEN_HERE':
    print("WARNING: MAPBOX_TOKEN is not set. Please set it as an environment variable or replace 'YOUR_MAPBOX_TOKEN_HERE' in main.py.")

# Check Planet API key validity
print("Checking Planet API key validity...")
if not check_planet_api_key_validity():
    print("ERROR: Planet API key is invalid. Please check your PL_API_KEY environment variable.")
    exit(1)
print("Planet API key is valid.")

# define waterloo bounding box : south, west, north, east
#bbox = (43.4200, -80.5700, 43.5000, -80.4800)
bbox = (43.4900, -80.5300, 43.5000, -80.5200)

# overpass query to get industrial zones
landuse_query = f'''
[out:json][timeout:60];
(
    way["landuse"="industrial"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out body;
>;
out skel qt;
'''

# overpass query to get buildings
building_query = f'''
[out:json][timeout:60];
(
    way["building"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out body;
>;
out skel qt;
'''

def overpass_query(query):
    """Sends a query to the overpass API and returns JSON response."""
    url = 'https://overpass-api.de/api/interpreter'
    response = requests.post(url, data={'data': query})
    response.raise_for_status()
    return response.json()

def to_feature_dict(elements):
    """
    Converts overpass API elements (nodes, ways) into GeoJSON-like features
    Modified to include 'id' and 'name' from way elements.
    """
    nodes = {e['id']: e for e in elements if e['type'] == 'node'}
    features = []
    for el in elements:
        if el['type'] == 'way' and 'nodes' in el:
            coords = [[nodes[nid]['lon'], nodes[nid]['lat']] for nid in el['nodes'] if nid in nodes]
            if not coords:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0]) # close the polygon

            properties = {
                'id': el['id'], # OSM WAY ID
                'name': el.get('tags', {}).get('name') # OSM Name tag
            }
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': [coords]},
                'properties': properties
            })
    return features

def bbox_center(coords):
    """Calculates the center of a list of coordinates."""
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [(min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2]

def reverse_geocode(lng, lat):
    """Performs reverse geocoding using Mapbox API."""
    url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{lng},{lat}.json?access_token={MAPBOX_TOKEN}&limit=1"
    )
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data["features"][0]["place_name"] if data["features"] else None
    except requests.exceptions.RequestException as e:
        print(f"Error during reverse geocoding for {lat},{lng}: {e}")
        return None

# ---- Database connection details (from the docker.yml file)
DB_HOST = os.getenv('POSTGRES_HOST', 'postgis_db')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_NAME = os.getenv('POSTGRES_DB', 'backend_database')
DB_USER = os.getenv('POSTGRES_USER', 'mapwork_user')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'mapwork.ai')

def get_db_connection():
    """Establishes and returns a database connection."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

def insert_building_data(building_data):
    """Inserts or updates a single building's data into the PostGIS 'buildings' table."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        building_polygon = Polygon(building_data['coordinates'])
        geometry_wkt = wkt_dumps(building_polygon)

        center_point = Point(building_data['center']['lng'], building_data['center']['lat'])
        center_wkt = wkt_dumps(center_point)

        # Extract Planet data (will be None if not fetched or an error occurred)
        planet_image_url = building_data.get('planet_image_url')
        planet_capture_date = building_data.get('planet_capture_date')
        planet_cloud_cover = building_data.get('planet_cloud_cover')

        insert_query = sql.SQL("""
            INSERT INTO buildings (
                osm_id, name, geometry, center_point, address, mapbox_image_url, image_capture_date,
                planet_image_url, planet_image_capture_date, planet_cloud_cover_percentage
            ) VALUES (
                %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (osm_id) DO UPDATE SET
                name = EXCLUDED.name,
                geometry = EXCLUDED.geometry,
                center_point = EXCLUDED.center_point,
                address = EXCLUDED.address,
                mapbox_image_url = EXCLUDED.mapbox_image_url,
                image_capture_date = EXCLUDED.image_capture_date,
                planet_image_url = EXCLUDED.planet_image_url,
                planet_image_capture_date = EXCLUDED.planet_image_capture_date,
                planet_cloud_cover_percentage = EXCLUDED.planet_cloud_cover_percentage,
                last_updated = CURRENT_TIMESTAMP;
        """)
        cur.execute(insert_query, (
            building_data.get('osm_id'),
            building_data.get('name'),
            geometry_wkt,
            center_wkt,
            building_data.get('address'),
            building_data.get('image_url'),
            None, # Mapbox image_capture_date is not available
            planet_image_url,
            planet_capture_date,
            planet_cloud_cover
        ))

        conn.commit()
        print(f"Successfully inserted/updated building with OSM ID: {building_data.get('osm_id')}")

    except Exception as e:
        print(f"Error inserting data for building (OSM ID: {building_data.get('osm_id')}): {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

# ----------Main Script execution ----

print("Querying industrial zones from Overpass API...")
landuse_data = overpass_query(landuse_query)
industrial_features = to_feature_dict(landuse_data['elements'])
print(f"Found {len(industrial_features)} industrial zones.")

print("Querying all buildings from Overpass API...")
building_data = overpass_query(building_query)
building_features = to_feature_dict(building_data['elements'])
print(f"Found {len(building_features)} total buildings in the area.")

# --- STAGE 1: Filter all buildings to find only those within industrial zones ---
print("Filtering for buildings located within industrial zones...")
industrial_buildings = []
industrial_shapes = [shape(f['geometry']) for f in industrial_features]

for b_feature in building_features:
    b_shape = shape(b_feature['geometry'])
    # Check if this building is within any of the industrial zone polygons
    for zone_shape in industrial_shapes:
        if b_shape.within(zone_shape):
            industrial_buildings.append(b_feature)
            break # Found a zone, no need to check others for this building

print(f"-> Found {len(industrial_buildings)} buildings within industrial zones.")
print("-" * 20)


# --- STAGE 2: Process only the filtered buildings to get imagery and save to DB ---
print("Now processing these industrial buildings to get imagery and save to the database...")
count = 0
for building_feature in industrial_buildings:
    count += 1
    osm_id = building_feature['properties'].get('id')
    name = building_feature['properties'].get('name')
    
    print(f"\nProcessing building {count}/{len(industrial_buildings)} (OSM ID: {osm_id})...")

    # --- Prepare building data ---
    coords = building_feature['geometry']['coordinates'][0]
    center_coords = bbox_center(coords)
    address = reverse_geocode(center_coords[0], center_coords[1])
    
    # Mapbox static image URL (still useful for general context)
    mapbox_image_url = f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{center_coords[0]},{center_coords[1]},16,0/300x200@2x?access_token={urllib.parse.quote(MAPBOX_TOKEN)}"

    # --- CALL PLANET SERVICE TO GET CLEARER IMAGERY ---
    # Pass the building's GeoJSON geometry for its Area of Interest (AOI).
    aoi_geojson_for_planet = building_feature['geometry']
    planet_image_info = get_and_process_planet_imagery(
        aoi_geojson_for_planet,
        days_back=30,       # Look for images in the last 30 days
        cloud_cover_limit=0.10 # Limit to 10% cloud cover
    )

    # Initialize Planet data fields
    planet_image_url = None
    planet_capture_date = None
    planet_cloud_cover = None

    if planet_image_info and planet_image_info.get('url'):
        planet_image_url = planet_image_info.get('url')
        planet_capture_date = planet_image_info.get('capture_date')
        planet_cloud_cover = planet_image_info.get('cloud_cover')
        print(f"-> Planet imagery found: URL={planet_image_url}, Date={planet_capture_date}, Cloud Cover={planet_cloud_cover:.2f}%")
    else:
        print(f"-> No suitable Planet imagery found for building {osm_id}.")

    # --- Prepare the final record for the database ---
    building_record = {
        'osm_id': osm_id,
        'name': name,
        'coordinates': coords,
        'center': {'lng': center_coords[0], 'lat': center_coords[1]},
        'address': address,
        'image_url': mapbox_image_url, # This is the Mapbox static image URL
        'capture_date': None, # Mapbox static images don't have a specific capture date
        'planet_image_url': planet_image_url,
        'planet_capture_date': planet_capture_date,
        'planet_cloud_cover': planet_cloud_cover
    }

    # --- Insert the processed building data into the database ---
    insert_building_data(building_record)

print("-" * 20)
print("Database insertion process complete.")