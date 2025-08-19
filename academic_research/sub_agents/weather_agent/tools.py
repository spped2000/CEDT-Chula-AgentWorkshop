# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Weather tools for geocoding and weather data retrieval."""

import os
import asyncio
from typing import Any, Dict
import httpx

from google.adk.tools import FunctionTool


async def retry_api_call(func, max_retries: int = 3, base_delay: float = 1.0):
    """
    Retry an async function call with exponential backoff and immediate feedback.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
    
    Returns:
        Result of the function call
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                print(f"Retrying API call (attempt {attempt + 1}/{max_retries + 1})...")
            return await func()
        except Exception as e:
            last_exception = e
            
            if attempt == max_retries:
                print(f"All {max_retries + 1} attempts failed. Using fallback data.")
                raise e
            
            # Calculate exponential backoff delay (increased for stability)
            delay = min(base_delay * (2.0 ** attempt), 15.0)  # Cap at 15 seconds max
            
            # Add jitter to prevent thundering herd
            import random
            jitter = random.uniform(0.2, 0.5) * delay
            total_delay = delay + jitter
            
            error_type = "rate limit" if "429" in str(e) or "rate" in str(e).lower() else "API error"
            print(f"API {error_type} detected. Retrying in {total_delay:.1f}s...")
            
            # Use shorter sleep intervals to prevent chatbot timeout
            await asyncio.sleep(total_delay)
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


async def get_lat_lng(location_description: str) -> Dict[str, float]:
    """Get the latitude and longitude of a location.
    
    Args:
        location_description: A description of a location (e.g., 'Bangkok', 'New York City')
        
    Returns:
        Dictionary containing 'lat' and 'lng' coordinates
    """
    geo_api_key = os.getenv('GEO_API_KEY')
    
    # Fallback to dummy coordinates if no API key
    if not geo_api_key:
        print(f"No GEO_API_KEY provided, using Bangkok coordinates as fallback")
        # Bangkok coordinates as fallback
        return {'lat': 13.7563, 'lng': 100.5018}
    
    async def _make_geocode_request():
        async with httpx.AsyncClient() as client:
            params = {
                'q': location_description,
                'api_key': geo_api_key,
            }
            
            response = await client.get(
                'https://geocode.maps.co/search', 
                params=params,
                timeout=30.0  # Increased timeout for better reliability
            )
            response.raise_for_status()
            data = response.json()
            
            if data and len(data) > 0:
                return {
                    'lat': float(data[0]['lat']), 
                    'lng': float(data[0]['lon'])
                }
            else:
                raise ValueError(f"No coordinates found for location: {location_description}")
    
    try:
        print(f"Looking up coordinates for: {location_description}")
        # Try with retry logic (increased delays for stability)
        return await retry_api_call(_make_geocode_request, max_retries=3, base_delay=2.0)
    except Exception as e:
        print(f"Geocoding unavailable for '{location_description}'. Using Bangkok coordinates as fallback.")
        # Return Bangkok coordinates as fallback
        return {'lat': 13.7563, 'lng': 100.5018}


async def get_weather(lat: float, lng: float) -> Dict[str, Any]:
    """Get current weather information for specific coordinates.
    
    Args:
        lat: Latitude coordinate
        lng: Longitude coordinate
        
    Returns:
        Dictionary containing weather information
    """
    weather_api_key = os.getenv('WEATHER_API_KEY')
    
    # Fallback to dummy weather if no API key
    if not weather_api_key:
        print(f"No WEATHER_API_KEY provided, using dummy weather data")
        return {
            'temperature': '28C',
            'description': 'Partly Cloudy',
            'location': f'Location ({lat:.2f}, {lng:.2f})'
        }
    
    # Weather code mapping from tomorrow.io API
    code_lookup = {
        1000: 'Clear, Sunny',
        1100: 'Mostly Clear', 
        1101: 'Partly Cloudy',
        1102: 'Mostly Cloudy',
        1001: 'Cloudy',
        2000: 'Fog',
        2100: 'Light Fog',
        4000: 'Drizzle',
        4001: 'Rain',
        4200: 'Light Rain',
        4201: 'Heavy Rain',
        5000: 'Snow',
        5001: 'Flurries',
        5100: 'Light Snow',
        5101: 'Heavy Snow',
        6000: 'Freezing Drizzle',
        6001: 'Freezing Rain',
        6200: 'Light Freezing Rain',
        6201: 'Heavy Freezing Rain',
        7000: 'Ice Pellets',
        7101: 'Heavy Ice Pellets',
        7102: 'Light Ice Pellets',
        8000: 'Thunderstorm',
    }
    
    async def _make_weather_request():
        async with httpx.AsyncClient() as client:
            params = {
                'apikey': weather_api_key,
                'location': f'{lat},{lng}',
                'units': 'metric',
            }
            
            response = await client.get(
                'https://api.tomorrow.io/v4/weather/realtime',
                params=params,
                timeout=30.0  # Increased timeout for better reliability
            )
            response.raise_for_status()
            data = response.json()
            
            if 'data' not in data or 'values' not in data['data']:
                raise ValueError("Invalid weather API response format")
            
            values = data['data']['values']
            
            return {
                'temperature': f'{values["temperatureApparent"]:.0f}C',
                'description': code_lookup.get(values.get('weatherCode'), 'Unknown'),
                'humidity': f'{values.get("humidity", "N/A")}%',
                'wind_speed': f'{values.get("windSpeed", "N/A")} m/s',
                'location': f'Location ({lat:.2f}, {lng:.2f})',
                'timestamp': data.get('data', {}).get('time', 'Unknown time')
            }
    
    try:
        print(f"Fetching weather data for coordinates ({lat:.2f}, {lng:.2f})")
        # Try with retry logic (increased delays for stability)
        return await retry_api_call(_make_weather_request, max_retries=3, base_delay=3.0)
    except Exception as e:
        print(f"Weather data temporarily unavailable. Using sample data as fallback.")
        # Return dummy weather data as fallback
        return {
            'temperature': '28C',
            'description': 'Partly Cloudy',
            'location': f'Location ({lat:.2f}, {lng:.2f})',
            'note': 'Weather data temporarily unavailable due to API limits'
        }


# Create tool instances using FunctionTool
get_lat_lng_tool = FunctionTool(get_lat_lng)
get_weather_tool = FunctionTool(get_weather)