# sentinel_service.py
import os
import requests
from datetime import datetime, timedelta
import urllib.parse
from typing import Union

# Import boto3 for S3 interaction
import boto3

# --- Sentinel Hub Configuration ---
# IMPORTANT: Replace 'YOUR_SENTINEL_HUB_INSTANCE_ID' with the actual ID from your JSON config.
# e.g., "id": "XXXXXXXXXd91-a324-835945af2772"
SENTINEL_HUB_INSTANCE_ID = os.getenv('SENTINEL_HUB_INSTANCE_ID', 'YOUR_SENTINEL_HUB_INSTANCE_ID')

if SENTINEL_HUB_INSTANCE_ID == 'YOUR_SENTINEL_HUB_INSTANCE_ID':
    print("WARNING: SENTINEL_HUB_INSTANCE_ID is not set. Please set it as an environment variable or replace 'YOUR_SENTINEL_HUB_INSTANCE_ID' in sentinel_service.py.")

# Base URL for Sentinel Hub OGC WMS service
SENTINEL_HUB_WMS_BASE_URL = f"https://services.sentinel-hub.com/ogc/wms/{SENTINEL_HUB_INSTANCE_ID}"

# --- Cloud Storage Configuration (Example for S3) ---
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'your-default-s3-bucket-name-if-not-set-in-env') # Replace with your actual bucket name or ensure env var is set

if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
    print("WARNING: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not set. S3 upload will be skipped.")
    s3_client = None # Set client to None if credentials are missing
else:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )

def get_sentinel_imagery_for_bbox(
    bbox: tuple, # (min_lat, min_lon, max_lat, max_lon) - e.g., (43.4200, -80.5700, 43.5000, -80.4800)
    width: int = 512,
    height: int = 512,
    layer: str = 'ALL_BANDS', # or 'NDVI', 'RGB', etc. - depends on your Sentinel Hub instance configuration
    max_cloud_cover: float = 20.0, # Percentage (0-100)
    time_period_days: int = 30, # Look for images in the last N days
    output_format: str = 'image/tiff', # 'image/png', 'image/jpeg', 'image/tiff'
    custom_evalscript: str = None # For advanced custom band combinations or processing
) -> Union[dict, None]:
    """
    Fetches Sentinel-2 imagery from Sentinel Hub WMS service for a given bounding box.

    Args:
        bbox (tuple): Bounding box in (min_lat, min_lon, max_lat, max_lon) format (EPSG:4326).
        width (int): Desired width of the output image in pixels.
        height (int): Desired height of the output image in pixels.
        layer (str): The layer configured in your Sentinel Hub instance to request.
                     Common built-in options are 'ALL_BANDS', 'RGB', 'NDVI'.
                     You can also create custom layers in Sentinel Hub.
        max_cloud_cover (float): Maximum cloud cover percentage (0-100).
        time_period_days (int): How many days back to search for imagery.
        output_format (str): The format of the output image ('image/png', 'image/jpeg', 'image/tiff').
        custom_evalscript (str): An optional custom evalscript string for advanced processing.

    Returns:
        dict or None: A dictionary containing 'url', 'capture_date', 'cloud_cover' if successful,
                      otherwise None.
    """
    if not SENTINEL_HUB_INSTANCE_ID or SENTINEL_HUB_INSTANCE_ID == 'YOUR_SENTINEL_HUB_INSTANCE_ID':
        print("Error: Sentinel Hub Instance ID is not configured.")
        return None

    # Calculate time period for the request
    end_date = datetime.now()
    start_date = end_date - timedelta(days=time_period_days)
    time_range = f"{start_date.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_date.strftime('%Y-%m-%dT%H:%M:%SZ')}"

    # Construct the BBOX string
    # WMS BBOX is typically `minx,miny,maxx,maxy` (lon, lat) for CRS:4326
    # Your `bbox` tuple is `(min_lat, min_lon, max_lat, max_lon)`
    bbox_str = f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}" # Correct order: min_lon,min_lat,max_lon,max_lat

    params = {
        'SERVICE': 'WMS',
        'REQUEST': 'GetMap',
        'VERSION': '1.3.0',
        'LAYERS': layer,
        'MAXCC': f"{max_cloud_cover:.2f}",
        'WIDTH': str(width),
        'HEIGHT': str(height),
        'CRS': 'EPSG:4326',
        'BBOX': bbox_str,
        'FORMAT': output_format,
        'TIME': time_range,
        'SHOWLOGO': 'false' # As per your config
    }

    if custom_evalscript:
        params['EVALSCRIPT'] = custom_evalscript
        # For Evalscripts, often 'LAYERS' needs to be a generic placeholder or implicitly defined in script
        # Check Sentinel Hub documentation for exact usage with EVALSCRIPT and LAYERS
        # For simplicity, we'll assume a basic evalscript scenario for now.
        # If using EVALSCRIPT, the 'layer' parameter might become less relevant.
        pass # Placeholder for more complex evalscript handling

    wms_url = f"{SENTINEL_HUB_WMS_BASE_URL}?{urllib.parse.urlencode(params)}"

    print(f"Attempting to fetch Sentinel imagery from: {wms_url}")

    try:
        response = requests.get(wms_url, stream=True)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        # Determine file extension based on format
        file_extension = "tif" if "tiff" in output_format else ("png" if "png" in output_format else "jpg")
        
        # Use a temporary file path in /tmp for Docker containers
        temp_filename = f"/tmp/sentinel_image_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_extension}"

        with open(temp_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded Sentinel image to {temp_filename}")

        # --- Upload to S3 ---
        final_hosted_url = None
        if s3_client:
            s3_key = f"sentinel_images/{os.path.basename(temp_filename)}"
            try:
                print(f"Uploading {temp_filename} to s3://{S3_BUCKET_NAME}/{s3_key}...")
                s3_client.upload_file(temp_filename, S3_BUCKET_NAME, s3_key)
                final_hosted_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
                print(f"Successfully uploaded to S3: {final_hosted_url}")
            except Exception as s3_e:
                print(f"Error uploading to S3: {s3_e}")
        else:
            print("S3 client not initialized due to missing AWS credentials. Skipping upload to S3.")

        # Clean up local temp file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            print(f"Cleaned up local file: {temp_filename}")

        # Sentinel Hub WMS/WCS doesn't directly return cloud cover or capture date in the image metadata.
        # For this, you would typically use the Sentinel Hub Catalog API or a separate search.
        # For now, we'll return None for these, but note this limitation.
        # If you use sentinelhub-py library, it simplifies this by integrating search/download.
        return {
            'url': final_hosted_url,
            'capture_date': None, # Sentinel Hub WMS GetMap doesn't provide this directly
            'cloud_cover': None  # Sentinel Hub WMS GetMap doesn't provide this directly for individual image
        }

    except requests.exceptions.RequestException as e:
        print(f"Network or download error with Sentinel Hub WMS: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred in Sentinel service: {e}")
        return None

# --- Example Usage (for testing purposes, not part of the main integration) ---
if __name__ == "__main__":
    # Ensure your Sentinel Hub instance ID is set in environment variables
    # or replace the placeholder at the top of this file.
    # Also ensure your AWS S3 credentials are set if you want to test S3 upload.

    # Example Waterloo BBOX
    # (min_lat, min_lon, max_lat, max_lon)
    waterloo_bbox = (43.4200, -80.5700, 43.5000, -80.4800)

    print("\n--- Testing Sentinel Hub WMS Integration ---")
    sentinel_info = get_sentinel_imagery_for_bbox(
        bbox=waterloo_bbox,
        width=1024, # Request a larger image for better detail
        height=1024,
        layer='RGB', # Or 'ALL_BANDS', 'NDVI' depending on your instance config
        max_cloud_cover=10.0, # Max 10% cloud cover
        time_period_days=60, # Look back 60 days
        output_format='image/tiff'
    )

    if sentinel_info:
        print("\nSuccessfully fetched Sentinel imagery info:")
        print(f"  URL: {sentinel_info['url']}")
        print(f"  Capture Date (approx): {sentinel_info['capture_date']}") # Still None, see notes above
        print(f"  Cloud Cover (max filter): {sentinel_info['cloud_cover']}") # Still None, see notes above
    else:
        print("\nFailed to fetch Sentinel imagery.")