"""Current weather data providers used by Jarvis."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
DEFAULT_WEATHER_CITY = "New Delhi"
DEFAULT_WEATHER_QUERY = "New Delhi,IN"
DEFAULT_WEATHER_LATITUDE = 28.6139
DEFAULT_WEATHER_LONGITUDE = 77.2090
_logger = logging.getLogger(__name__)

_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def configured_weather_city() -> str:
    """Return the configured city query, defaulting to New Delhi, India."""
    return (
        os.getenv("WEATHER_CITY", DEFAULT_WEATHER_QUERY).strip()
        or DEFAULT_WEATHER_QUERY
    )


def _unavailable(message: str) -> dict[str, Any]:
    return {"available": False, "error": message}


def _openweather_weather(city: str, api_key: str) -> dict[str, Any]:
    try:
        response = requests.get(
            OPENWEATHER_URL,
            params={"q": city, "appid": api_key, "units": "metric"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OpenWeatherMap returned an invalid response")
        main = payload["main"]
        wind = payload["wind"]
        weather_items = payload["weather"]
        system = payload["sys"]
        if not all(isinstance(value, dict) for value in (main, wind, system)):
            raise ValueError("OpenWeatherMap returned incomplete weather data")
        if not isinstance(weather_items, list) or not weather_items:
            raise ValueError("OpenWeatherMap returned no weather conditions")
        current_conditions = weather_items[0]
        if not isinstance(current_conditions, dict):
            raise ValueError("OpenWeatherMap returned invalid weather conditions")
        condition = current_conditions.get("description")
        if not isinstance(condition, str) or not condition.strip():
            raise ValueError("OpenWeatherMap returned no weather description")
        observed_at = datetime.fromtimestamp(
            payload["dt"],
            tz=timezone(timedelta(seconds=system.get("timezone", 0))),
        ).isoformat(timespec="minutes")
        return {
            "available": True,
            "location": ", ".join(
                part
                for part in (
                    str(payload.get("name", "")).strip(),
                    str(system.get("country", "")).strip(),
                )
                if part
            ),
            "temperature": main["temp"],
            "feels_like": main["feels_like"],
            "humidity": main["humidity"],
            "wind_speed": round(float(wind["speed"]) * 3.6, 1),
            "condition": condition.strip().capitalize(),
            "pressure": main.get("pressure"),
            "visibility": round(float(payload["visibility"]) / 1000, 1)
            if payload.get("visibility") is not None
            else None,
            "cloud_cover": payload.get("clouds", {}).get("all")
            if isinstance(payload.get("clouds"), dict)
            else None,
            "observed_at": observed_at,
            "timezone_offset": system.get("timezone", 0),
            "source": "OpenWeatherMap",
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
        _logger.warning("OpenWeatherMap weather request failed (%s)", type(exc).__name__)
        return _unavailable(
            "Weather is temporarily unavailable. Check your OpenWeatherMap key, city, "
            "internet connection, and try again."
        )


def _open_meteo_weather(city: str) -> dict[str, Any]:
    latitude = DEFAULT_WEATHER_LATITUDE
    longitude = DEFAULT_WEATHER_LONGITUDE
    location = "New Delhi, India"
    timezone_name = "Asia/Kolkata"

    if city.casefold().replace(" ", "") not in {
        DEFAULT_WEATHER_CITY.casefold().replace(" ", ""),
        DEFAULT_WEATHER_QUERY.casefold().replace(" ", ""),
    }:
        try:
            city_name, separator, country_code = city.rpartition(",")
            geocoding_params = {
                "name": city_name.strip() if separator else city,
                "count": 1,
                "language": "en",
                "format": "json",
            }
            if separator and len(country_code.strip()) == 2:
                geocoding_params["countryCode"] = country_code.strip().upper()
            geocoding_response = requests.get(
                OPEN_METEO_GEOCODING_URL,
                params=geocoding_params,
                timeout=8,
            )
            geocoding_response.raise_for_status()
            geocoding_payload = geocoding_response.json()
            if not isinstance(geocoding_payload, dict):
                raise ValueError("Open-Meteo geocoding returned an invalid response")
            results = geocoding_payload.get("results", [])
            if not isinstance(results, list) or not results:
                return _unavailable(
                    f"I couldn't find weather for {city}. Check the city name and try again."
                )
            result = results[0]
            if not isinstance(result, dict):
                raise ValueError("Open-Meteo geocoding returned an invalid location")
            latitude = result["latitude"]
            longitude = result["longitude"]
            location = ", ".join(
                part
                for part in (
                    str(result.get("name", "")).strip(),
                    str(result.get("country", "")).strip(),
                )
                if part
            )
            timezone_name = "auto"
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            _logger.warning("Weather city lookup failed (%s)", type(exc).__name__)
            return _unavailable(
                "Weather is temporarily unavailable. Check your connection and try again."
            )

    try:
        response = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m,surface_pressure,visibility,cloud_cover"
                ),
                "timezone": timezone_name,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
            raise ValueError("Open-Meteo returned an invalid response")
        current = payload["current"]
        code = current["weather_code"]
        return {
            "available": True,
            "location": location,
            "temperature": current["temperature_2m"],
            "feels_like": current["apparent_temperature"],
            "humidity": current["relative_humidity_2m"],
            "wind_speed": current["wind_speed_10m"],
            "condition": _WEATHER_CODES.get(code, "Current conditions"),
            "pressure": current.get("surface_pressure"),
            "visibility": round(float(current["visibility"]) / 1000, 1)
            if current.get("visibility") is not None
            else None,
            "cloud_cover": current.get("cloud_cover"),
            "observed_at": current["time"],
            "timezone_offset": payload.get("utc_offset_seconds", 19800),
            "source": "Open-Meteo",
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
        _logger.warning("Open-Meteo weather request failed (%s)", type(exc).__name__)
        return _unavailable(
            "Weather is temporarily unavailable. Check your internet connection and try again."
        )


def fetch_weather(city: str | None = None) -> dict[str, Any]:
    """Fetch current conditions from OpenWeatherMap, or Open-Meteo without a key."""
    requested_city = (city or configured_weather_city()).strip() or DEFAULT_WEATHER_QUERY
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if api_key:
        return _openweather_weather(requested_city, api_key)
    return _open_meteo_weather(requested_city)
