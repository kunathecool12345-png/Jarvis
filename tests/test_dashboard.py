import os
import unittest
from unittest.mock import Mock, call, patch

import dashboard


class DashboardTests(unittest.TestCase):
    def setUp(self):
        dashboard.app.config["TESTING"] = True
        self.client = dashboard.app.test_client()

    def test_dashboard_page_renders_controls(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Command console", response.data)
        self.assertIn(b"SAY \xe2\x80\x9cJARVIS\xe2\x80\x9d", response.data)
        self.assertIn(b"Latest headlines", response.data)
        self.assertIn(b"New Delhi,IN", response.data)
        self.assertIn(b'data-command="weather"', response.data)
        self.assertNotIn(b"mic-button", response.data)
        self.assertIn(b"orb-stage", response.data)

    def test_dashboard_automatically_listens_for_wake_phrase(self):
        response = self.client.get("/static/dashboard.js")
        self.assertEqual(response.status_code, 200)
        script = response.get_data()
        response.close()
        self.assertIn(b"recognition.continuous = true", script)
        self.assertIn(b"/\\bjarvis\\b/i", script)
        self.assertIn(b'recognition.lang = "en-IN"', script)
        self.assertIn(b"recognition.interimResults = true", script)
        self.assertIn(b"One moment. I'm working on that.", script)
        self.assertIn(b"startListening();", script)
        self.assertEqual(script.count(b"recognitionRetryDelay = 400;"), 2)

    def test_dashboard_info_returns_current_delhi_weather_and_india_headlines(self):
        weather = Mock()
        weather.json.return_value = {
            "current": {
                "temperature_2m": 31.2,
                "relative_humidity_2m": 42,
                "apparent_temperature": 33.1,
                "weather_code": 2,
                "wind_speed_10m": 8.4,
                "time": "2026-10-06T22:00",
            }
        }
        headlines = Mock()
        headlines.json.return_value = {
            "status": "ok",
            "articles": [
                {
                    "title": "India announces a new initiative",
                    "description": "A detailed summary of today's announcement.",
                    "source": {"name": "Example News"},
                    "url": "https://example.com/story",
                    "publishedAt": "2026-10-06T15:30:00Z",
                }
            ]
        }
        weather.raise_for_status.return_value = None
        headlines.raise_for_status.return_value = None
        with patch.dict(os.environ, {"NEWS_API_KEY": "test-news-key"}), patch(
            "dashboard.requests.get", side_effect=[weather, headlines]
        ) as get:
            response = self.client.get("/api/dashboard-info")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["weather"]["temperature"], 31.2)
        self.assertEqual(data["weather"]["condition"], "Partly cloudy")
        self.assertEqual(data["headlines"]["articles"][0]["title"], "India announces a new initiative")
        self.assertEqual(
            get.call_args_list,
            [
                call(
                    dashboard.WEATHER_URL,
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
                ),
                call(
                    dashboard.NEWS_URL,
                    params={"country": "in", "pageSize": 5, "sortBy": "publishedAt"},
                    headers={"X-Api-Key": "test-news-key"},
                    timeout=8,
                ),
            ],
        )

    def test_dashboard_info_uses_google_news_when_no_newsapi_key_is_configured(self):
        weather = Mock()
        weather.raise_for_status.return_value = None
        weather.json.return_value = {
            "current": {
                "temperature_2m": 25,
                "relative_humidity_2m": 50,
                "apparent_temperature": 26,
                "weather_code": 0,
                "wind_speed_10m": 4,
                "time": "2026-10-06T22:00",
            }
        }
        news = Mock()
        news.raise_for_status.return_value = None
        news.content = (
            b"<rss><channel><item><title>India live headline</title>"
            b"<link>https://news.google.com/articles/example</link>"
            b"<description>A detailed story summary.</description>"
            b"<source>Example News</source><pubDate>Tue, 06 Oct 2026 16:00:00 GMT</pubDate>"
            b"</item></channel></rss>"
        )
        with patch.dict(os.environ, {}, clear=True), patch(
            "dashboard.requests.get", side_effect=[weather, news]
        ) as get:
            response = self.client.get("/api/dashboard-info")

        self.assertTrue(response.get_json()["weather"]["available"])
        self.assertTrue(response.get_json()["headlines"]["available"])
        self.assertEqual(response.get_json()["headlines"]["source"], "Google News")
        self.assertEqual(
            response.get_json()["headlines"]["articles"][0]["title"],
            "India live headline",
        )
        get.assert_has_calls(
            [
                call(
                    dashboard.WEATHER_URL,
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
                ),
                call(
                    dashboard.GOOGLE_NEWS_RSS_URL,
                    params={"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                    timeout=8,
                ),
            ]
        )

    def test_dashboard_info_reports_newsapi_key_rejection(self):
        weather = Mock()
        weather.raise_for_status.return_value = None
        weather.json.return_value = {
            "current": {
                "temperature_2m": 25,
                "relative_humidity_2m": 50,
                "apparent_temperature": 26,
                "weather_code": 0,
                "wind_speed_10m": 4,
                "time": "2026-10-06T22:00",
            }
        }
        rejected_news = Mock()
        rejected_news.raise_for_status.return_value = None
        rejected_news.json.return_value = {"status": "error", "articles": []}
        with patch.dict(os.environ, {"NEWS_API_KEY": "test-news-key"}), patch(
            "dashboard.requests.get",
            side_effect=[
                weather,
                rejected_news,
                dashboard.requests.ConnectionError("offline"),
            ],
        ):
            response = self.client.get("/api/dashboard-info")

        self.assertFalse(response.get_json()["headlines"]["available"])
        self.assertIn("internet connection", response.get_json()["headlines"]["error"])

    def test_command_endpoint_returns_assistant_reply(self):
        with patch.object(
            dashboard.jarvis._assistant,
            "handle_dashboard_command",
            return_value={"reply": "The capital is New Delhi.", "continue": True},
        ) as handle:
            response = self.client.post(
                "/api/command", json={"text": "What is the capital of India?"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"reply": "The capital is New Delhi.", "continue": True},
        )
        handle.assert_called_once_with("What is the capital of India?")

    def test_command_endpoint_rejects_non_string_text(self):
        response = self.client.post("/api/command", json={"text": ["not", "text"]})
        self.assertEqual(response.status_code, 400)

    def test_command_endpoint_rejects_oversized_text(self):
        response = self.client.post("/api/command", json={"text": "a" * 2001})
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
