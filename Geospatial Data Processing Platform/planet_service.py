import os
import json
import requests
from datetime import datetime, timedelta

# Import boto3 for S3 interaction
import boto3

# --- Planet API Configuration ---
PLANET_API_KEY = os.getenv('PL_API_KEY')
if not PLANET_API_KEY:
    print("INFO: PL_API_KEY is not configured. Planet imagery integration is disabled.")

PLANET_SEARCH_URL = "https://api.planet.com/data/v1/quick-search"
PLANET_ASSETS_URL_TEMPLATE = "https://api.planet.com/data/v1/item-types/{item_type}/items/{item_id}/assets/"

# --- Cloud Storage Configuration (Example for S3) ---
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'your-default-s3-bucket-name-if-not-set-in-env')

if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
    print("WARNING: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not set. S3 upload will be skipped.")
    s3_client = None
else:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )


def planet_search_imagery(aoi_geojson, days_back=1000, cloud_cover_limit=0.90):
    if not PLANET_API_KEY:
        return []
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"api-key {PLANET_API_KEY}"
    }

    #  Set the date range
    # end_date = datetime.utcnow()
    # start_date = end_date - timedelta(days=days_back)

    # Fixed date range
    start = "2016-01-01T00:00:00Z"
    end = "2020-12-31T23:59:59Z"

    # Create filters
    geometry_filter = {
        "type": "GeometryFilter",
        "field_name": "geometry",
        "config": aoi_geojson
    }

    date_range_filter = {
        "type": "DateRangeFilter",
        "field_name": "acquired",
        "config": {
            "gte": start,
            "lte": end
        }
    }

    cloud_cover_filter = {
        "type": "RangeFilter",
        "field_name": "cloud_cover",
        "config": {
            "lte": cloud_cover_limit
        }
    }


    permission_filter = {
        "type": "PermissionFilter",
        "config": ["assets:download"]
    }


    # Combine filters
    combined_filter = {
    "type": "AndFilter",
    "config": [geometry_filter, date_range_filter, cloud_cover_filter, permission_filter]
    }

    # Build final request body
    search_request = {
        "item_types": ["PSScene"],
        "filter": combined_filter
    }

    # Print request for debugging
    print("Search request being sent to Planet API:")
    # Remove the detailed JSON printing to keep output clean
    print(f"  Item types: {search_request['item_types']}")
    print(f"  Filter types: {[f['type'] for f in search_request['filter']['config']]}")

    response = requests.post(PLANET_SEARCH_URL, json=search_request, headers=headers, timeout=30)
    response.raise_for_status()
    search_results = response.json()

    items = search_results.get('features', [])
    return items


def activate_asset(item_type, item_id, asset_key):
    """
    Activate the asset for the given item.
    """
    url = PLANET_ASSETS_URL_TEMPLATE.format(item_type=item_type, item_id=item_id) + asset_key + "/activate"
    headers = {
        "Authorization": f"api-key {PLANET_API_KEY}"
        
    }
    response = requests.post(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def get_assets(item_type, item_id):
    """
    Get all assets for a given item.
    """
    url = PLANET_ASSETS_URL_TEMPLATE.format(item_type=item_type, item_id=item_id)
    headers = {
        "Authorization": f"api-key {PLANET_API_KEY}"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


from datetime import datetime, timedelta

def planet_search_with_filter(combined_filter):
    """
    Search Planet API using a provided filter dictionary.
    Returns a list of items matching the filter.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"api-key {PLANET_API_KEY}"
    }

    search_request = {
        "item_types": ["PSScene"],
        "filter": combined_filter
    }

    print("Search request being sent to Planet API:")
    # Remove the detailed JSON printing to keep output clean
    print(f"  Item types: {search_request['item_types']}")
    print(f"  Filter types: {[f['type'] for f in search_request['filter']['config']]}")

    if not PLANET_API_KEY:
        return []

    response = requests.post(PLANET_SEARCH_URL, json=search_request, headers=headers, timeout=30)
    
    if response.status_code != 200:
        print(f"Planet API Error {response.status_code}: {response.text}")
        response.raise_for_status()
        
    search_results = response.json()

    return search_results.get('features', [])


def get_and_process_planet_imagery(aoi_geojson, days_back=30, cloud_cover_limit=0.10):
    """
    Searches for, activates, downloads, and uploads (to S3) Planet imagery
    for a given GeoJSON AOI. Returns image URL, date, and cloud cover.
    """
    if not aoi_geojson:
        print("No AOI GeoJSON provided.")
        return None

    if not PLANET_API_KEY:
        print("Planet imagery skipped because PL_API_KEY is not configured.")
        return None

    if days_back < 1:
        raise ValueError("days_back must be at least 1")
    if not 0 <= cloud_cover_limit <= 1:
        raise ValueError("cloud_cover_limit must be between 0 and 1")

    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)

        print(f"Searching date range: {start_date} to {end_date}")

        date_range_filter = {
            "type": "DateRangeFilter",
            "field_name": "acquired",
            "config": {
                "gte": start_date.isoformat() + "Z",
                "lte": end_date.isoformat() + "Z"
            }
        }

        cloud_cover_filter = {
            "type": "RangeFilter",
            "field_name": "cloud_cover",
            "config": {
                "lte": cloud_cover_limit
            }
        }

        # Geometry filter for AOI
        geometry_filter = {
            "type": "GeometryFilter",
            "field_name": "geometry",
            "config": aoi_geojson
        }

        # Permission filter - required for accessing assets
        permission_filter = {
            "type": "PermissionFilter",
            "config": ["assets:download"]
        }

        # Combine filters using AndFilter - remove permission filter since it's too restrictive
        combined_filter = {
            "type": "AndFilter",
            "config": [geometry_filter, date_range_filter, cloud_cover_filter]
        }

        print(f"Searching Planet API for imagery in AOI with cloud limit {cloud_cover_limit} and date range {start_date.isoformat()}Z to {end_date.isoformat()}Z")

        # You need a function here that does the actual API call with combined_filter,
        # e.g. planet_search_with_filter(combined_filter)
        # Assuming you have this function, replace planet_search_imagery with it:
        items = planet_search_with_filter(combined_filter)

        print(f"Found {len(items)} items from Planet API")

        if not items:
            print("No suitable Planet imagery found for the specified criteria.")
            return None

        # Debug: Show first few items and their properties
        print(f"First 3 items found:")
        for i, item in enumerate(items[:3]):
            props = item.get('properties', {})
            print(f"  Item {i+1}: ID={item.get('id')}, Acquired={props.get('acquired')}, Cloud Cover={props.get('cloud_cover')}")

        # Sort and filter as before
        valid_items = [
            item for item in items
            if 'cloud_cover' in item['properties'] and 'acquired' in item['properties']
        ]

        print(f"Valid items after filtering: {len(valid_items)}")

        if not valid_items:
            print("No valid items found after filtering for properties.")
            return None

        best_item = sorted(
            valid_items,
            key=lambda x: (x['properties']['cloud_cover'], x['properties']['acquired'])
        )[0]

        item_id = best_item['id']
        item_type = "PSScene"  # Fixed: Use the actual Planet item type, not the GeoJSON feature type
        acquired_date = best_item['properties']['acquired'].split('T')[0]  # YYYY-MM-DD
        cloud_cover_pct = best_item['properties']['cloud_cover']

        print(f"Selected Planet item: {item_id}, Acquired: {acquired_date}, Cloud Cover: {cloud_cover_pct:.2f}%")

        # Rest of your function unchanged from here...
        assets = get_assets(item_type, item_id)
        
        print(f"Assets response for {item_id}: {list(assets.keys())}")

        # Try different asset types in order of preference
        asset_key = None
        preferred_assets = ['analytic_udm2', 'visual', 'analytic', 'basic_udm2', 'basic_analytics']
        
        for asset_type in preferred_assets:
            if asset_type in assets and 'status' in assets[asset_type]:
                asset_key = asset_type
                break
        
        if asset_key is None:
            print(f"No desired assets found for item {item_id}. Available assets: {list(assets.keys())}")
            
            # Try the next best item if this one has no assets
            if len(valid_items) > 1:
                print("Trying next best item...")
                best_item = sorted(
                    valid_items,
                    key=lambda x: (x['properties']['cloud_cover'], x['properties']['acquired'])
                )[1]  # Get the second best item
                
                item_id = best_item['id']
                item_type = "PSScene"
                acquired_date = best_item['properties']['acquired'].split('T')[0]
                cloud_cover_pct = best_item['properties']['cloud_cover']
                
                print(f"Trying Planet item: {item_id}, Acquired: {acquired_date}, Cloud Cover: {cloud_cover_pct:.2f}%")
                
                assets = get_assets(item_type, item_id)
                print(f"Assets response for {item_id}: {list(assets.keys())}")
                
                for asset_type in preferred_assets:
                    if asset_type in assets and 'status' in assets[asset_type]:
                        asset_key = asset_type
                        break
                
                if asset_key is None:
                    print(f"Still no desired assets found for item {item_id}. Available assets: {list(assets.keys())}")
                    # Return metadata even without downloadable assets
                    return {
                        'url': None,
                        'capture_date': acquired_date,
                        'cloud_cover': cloud_cover_pct,
                        'planet_item_id': item_id,
                        'planet_item_type': item_type,
                        'available_assets': list(assets.keys())
                    }
            else:
                # Return metadata even without downloadable assets
                return {
                    'url': None,
                    'capture_date': acquired_date,
                    'cloud_cover': cloud_cover_pct,
                    'planet_item_id': item_id,
                    'planet_item_type': item_type,
                    'available_assets': list(assets.keys())
                }

        asset = assets[asset_key]

        print(f"Selected asset '{asset_key}' for item {item_id}")
        print(f"Asset status: {asset.get('status')}")

        # Check if we have a direct URL (some assets might have this)
        download_url = asset.get('location')
        
        if not download_url:
            print(f"No download URL found for asset '{asset_key}' on item {item_id}.")
            print("This might be due to download permissions not being available in your Planet plan.")
            # Return metadata even without download URL
            return {
                'url': None,
                'capture_date': acquired_date,
                'cloud_cover': cloud_cover_pct,
                'planet_item_id': item_id,
                'planet_item_type': item_type,
                'available_assets': list(assets.keys()),
                'selected_asset': asset_key,
                'asset_status': asset.get('status')
            }

        # If we have a download URL, try to download (but this might fail due to permissions)
        local_filename = f"/tmp/planet_image_{item_id}_{asset_key}.tif"
        print(f"Attempting to download {item_id} asset '{asset_key}' to {local_filename}...")
        
        try:
            response = requests.get(download_url, stream=True, timeout=120)
            response.raise_for_status()

            with open(local_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Downloaded {local_filename}")

            final_hosted_url = None
            if s3_client:
                s3_key = f"planet_images/{item_id}_{asset_key}.tif"
                try:
                    print(f"Uploading {local_filename} to s3://{S3_BUCKET_NAME}/{s3_key}...")
                    s3_client.upload_file(local_filename, S3_BUCKET_NAME, s3_key)
                    final_hosted_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
                    print(f"Successfully uploaded to S3: {final_hosted_url}")
                except Exception as e:
                    print(f"Error uploading to S3: {e}")
            else:
                print("S3 client not initialized due to missing AWS credentials. Skipping upload to S3.")

            # Clean up local file
            if os.path.exists(local_filename):
                os.remove(local_filename)
                print(f"Cleaned up local file: {local_filename}")

            return {
                'url': final_hosted_url,
                'capture_date': acquired_date,
                'cloud_cover': cloud_cover_pct,
                'planet_item_id': item_id,
                'planet_item_type': item_type
            }
            
        except requests.exceptions.RequestException as e:
            print(f"Download failed (likely due to permissions): {e}")
            # Return metadata even if download fails
            return {
                'url': None,
                'capture_date': acquired_date,
                'cloud_cover': cloud_cover_pct,
                'planet_item_id': item_id,
                'planet_item_type': item_type,
                'available_assets': list(assets.keys()),
                'selected_asset': asset_key,
                'asset_status': asset.get('status'),
                'download_error': str(e)
            }

    except requests.exceptions.RequestException as e:
        print(f"Network or download error with Planet API: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred in Planet service: {e}")
        return None


def check_planet_api_key_validity():
    """
    Checks if the Planet API key is valid by making a simple authenticated request.
    """
    if not PLANET_API_KEY:
        print("Planet API key is not configured.")
        return False

    url = "https://api.planet.com/data/v1"
    try:
        response = requests.get(url, auth=(PLANET_API_KEY, ""), timeout=10)
    except requests.RequestException as error:
        print(f"Planet API key validation failed: {error}")
        return False
    
    print(f"Planet API Key Validation Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ Planet API key is valid.")
        return True
    elif response.status_code == 401:
        print("❌ Unauthorized: Invalid API key.")
        return False
    else:
        print(f"⚠️ Unexpected response: {response.status_code}")
        print(response.text)
        return False
