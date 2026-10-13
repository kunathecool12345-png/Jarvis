import os
import unittest
from unittest.mock import Mock, patch

import weather


class WeatherTests(unittest.TestCase):
    def test_openweathermap_uses_key_and_normalizes_current_conditions(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "name": "London",
            "dt": 1791480600,
            "timezone": 3600,
            "weather": [{"description": "light rain"}],
            "main": {
                "temp": 18.4,
                "feels_like": 17.8,
                "humidity": 72,
                "pressure": 1012,
            },
            "wind": {"speed": 3.5},
            "visibility": 10000,
            "clouds": {"all": 90},
            "sys": {"country": "GB"},
        }
        with patch.dict(
            os.environ,
            {"OPENWEATHER_API_KEY": "test-openweather-key", "WEATHER_CITY": "London,GB"},
            clear=True,
        ), patch("weather.requests.get", return_value=response) as get:
            result = weather.fetch_weather()

        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "OpenWeatherMap")
        self.assertEqual(result["location"], "London, GB")
        self.assertEqual(result["condition"], "Light rain")
        self.assertEqual(result["wind_speed"], 12.6)
        self.assertEqual(result["visibility"], 10.0)
        self.assertEqual(result["pressure"], 1012)
        get.assert_called_once_with(
            weather.OPENWEATHER_URL,
            params={"q": "London,GB", "appid": "test-openweather-key", "units": "metric"},
            timeout=8,
        )

    def test_missing_openweathermap_key_uses_keyless_open_meteo_provider(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "current": {
                "temperature_2m": 31.2,
                "relative_humidity_2m": 42,
                "apparent_temperature": 33.1,
                "weather_code": 2,
                "wind_speed_10m": 8.4,
                "surface_pressure": 1008.2,
                "visibility": 9000,
                "cloud_cover": 45,
                "time": "2026-10-06T22:00",
            }
        }
        with patch.dict(os.environ, {}, clear=True), patch(
            "weather.requests.get", return_value=response
        ) as get:
            result = weather.fetch_weather()

        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "Open-Meteo")
        self.assertEqual(result["condition"], "Partly cloudy")
        self.assertEqual(result["visibility"], 9.0)
        self.assertEqual(result["pressure"], 1008.2)
        get.assert_called_once_with(
            weather.OPEN_METEO_URL,
            params={
                "latitude": 28.6139,
                "longitude": 77.209,
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m,surface_pressure,visibility,cloud_cover"
                ),
                "timezone": "Asia/Kolkata",
            },
            timeout=8,
        )

    def test_openweathermap_failure_does_not_log_the_api_key(self):
        with (
            patch.dict(os.environ, {"OPENWEATHER_API_KEY": "secret-key"}, clear=True),
            patch(
                "weather.requests.get",
                side_effect=weather.requests.ConnectionError("request failed"),
            ),
            self.assertLogs("weather", level="WARNING") as logs,
        ):
            result = weather.fetch_weather("London")

        self.assertFalse(result["available"])
        self.assertNotIn("secret-key", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
