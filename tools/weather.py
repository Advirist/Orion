import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 10
MAX_LOCATION_LENGTH = 100

#Open-Meteo reports conditions as WMO weather codes; this maps them to words
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "light freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "light freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with light hail", 99: "thunderstorm with heavy hail",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather_check",
            "description": "Gets the current weather for a city using the Open-Meteo internet service: conditions, temperature, feels-like temperature, humidity, precipitation, and wind speed. The result includes the place that was actually matched, so confirm it's the right one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name only, e.g. 'Pittsburgh'. Text after a comma (like a state) is ignored by the lookup."
                    },
                    "units": {
                        "type": "string",
                        "enum": ["fahrenheit", "celsius"],
                        "description": "Temperature units. 'fahrenheit' also uses mph and inches; 'celsius' uses km/h and mm. Defaults to 'fahrenheit'."
                    }
                },
                "required": ["location"]
            }
        }
    },
]


def weather_check(location, units='fahrenheit'):
    if not isinstance(location, str) or not location.strip() or len(location) > MAX_LOCATION_LENGTH:
        return {
            "success": False,
            "error": "invalid_location",
            "message": f"location must be a city name under {MAX_LOCATION_LENGTH} characters."
        }
    units = str(units).strip().lower()
    if units not in ('fahrenheit', 'celsius'):
        return {
            "success": False,
            "error": "invalid_argument",
            "message": f"units must be 'fahrenheit' or 'celsius', but got '{units}'."
        }

    #the geocoder matches on place names, so "Pittsburgh, PA" becomes "Pittsburgh"
    city = location.split(',')[0].strip()
    imperial = units == 'fahrenheit'

    try:
        geo_response = requests.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        geo_response.raise_for_status()
        matches = geo_response.json().get("results") or []
        if not matches:
            return {
                "success": False,
                "error": "location_not_found",
                "message": f"No place called '{city}' could be found."
            }
        place = matches[0]

        forecast_response = requests.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "temperature_unit": units,
                "wind_speed_unit": "mph" if imperial else "kmh",
                "precipitation_unit": "inch" if imperial else "mm",
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        forecast_response.raise_for_status()
        current = forecast_response.json()["current"]
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "timeout_error",
            "message": "The weather service didn't respond in time. Let the user know and offer to try again."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": "network_error",
            "message": f"Couldn't reach the weather service; the internet may be down. ({e})"
        }
    except (ValueError, KeyError):
        return {
            "success": False,
            "error": "bad_response",
            "message": "The weather service returned data in an unexpected format."
        }

    #shows exactly which place matched, so a wrong match (e.g. Paris, France vs Paris, Texas) is obvious
    place_name = ", ".join(part for part in (place.get("name"), place.get("admin1"), place.get("country")) if part)
    temp_unit = "°F" if imperial else "°C"
    conditions = WEATHER_CODES.get(current.get("weather_code"), "unknown conditions")

    return {
        "success": True,
        "matched_location": place_name,
        "conditions": conditions,
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),
        "units": {
            "temperature": temp_unit,
            "wind_speed": "mph" if imperial else "km/h",
            "precipitation": "in" if imperial else "mm"
        },
        "message": f"Current weather in {place_name}: {conditions}, {current.get('temperature_2m')}{temp_unit}."
    }


TOOL_REGISTRY = {
    "weather_check": {'function': weather_check, 'mutating': False},
}
