import os
import unittest
from unittest.mock import patch

from main import Jarvis


class JarvisCommandTests(unittest.TestCase):
    def setUp(self):
        self.jarvis = Jarvis()

    def test_quit_stops_assistant(self):
        with patch.object(self.jarvis, "say") as say:
            self.assertFalse(self.jarvis.handle_command("quit"))
        say.assert_called_once_with("Goodbye!")

    def test_open_shortcut_uses_browser(self):
        with patch("main.webbrowser.open", return_value=True) as open_browser:
            with patch.object(self.jarvis, "say") as say:
                self.assertTrue(self.jarvis.handle_command("open google"))
        open_browser.assert_called_once_with("https://google.com")
        say.assert_called_once_with("Opening it now.")

    def test_unknown_song_searches_youtube(self):
        with patch("main.webbrowser.open", return_value=True) as open_browser:
            with patch.object(self.jarvis, "say"):
                self.jarvis.handle_command("play Bohemian Rhapsody")
        open_browser.assert_called_once_with(
            "https://www.youtube.com/results?search_query=Bohemian+Rhapsody"
        )

    def test_saved_song_opens_saved_url(self):
        with patch("main.webbrowser.open", return_value=True) as open_browser:
            with patch.object(self.jarvis, "say"):
                self.jarvis.handle_command("play LO-FI BEATS")
        open_browser.assert_called_once_with(
            "https://www.youtube.com/watch?v=jfKfPfyJRdk"
        )

    def test_missing_gemini_key_prompts_configuration(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = self.jarvis._gemini_reply("Hello")
        self.assertIn("GEMINI_API_KEY", response)

    def test_empty_input_does_not_stop_assistant(self):
        with patch.object(self.jarvis, "say") as say:
            self.assertTrue(self.jarvis.handle_command("  "))
        say.assert_not_called()

    def test_text_input_mode_keeps_spoken_responses_enabled(self):
        with (
            patch.object(self.jarvis, "say") as say,
            patch.object(self.jarvis, "listen", return_value=None),
            patch("builtins.input", side_effect=["hello", "quit"]),
        ):
            self.jarvis.run(text_mode=True)
        self.assertTrue(self.jarvis.voice_output)
        self.assertIn("Goodbye!", [call.args[0] for call in say.call_args_list])

    def test_gemini_answer_is_sent_to_speech_in_voice_mode(self):
        with (
            patch("main.speak") as speak,
            patch("main.aiProcess", return_value="The capital of India is New Delhi."),
        ):
            self.jarvis.voice_output = True
            self.jarvis.handle_command("What is the capital of India?")
        speak.assert_called_once_with("The capital of India is New Delhi.")

    def test_weather_command_reports_current_conditions(self):
        report = {
            "available": True,
            "location": "London, GB",
            "condition": "Light rain",
            "temperature": 18.4,
            "feels_like": 17.8,
            "humidity": 72,
            "wind_speed": 12.6,
            "pressure": 1012,
            "visibility": 10.0,
            "cloud_cover": 90,
        }
        with patch("main.fetch_weather", return_value=report) as fetch_weather, patch.object(
            self.jarvis, "say"
        ) as say:
            self.assertTrue(self.jarvis.handle_command("What's the weather in London?"))
        say.assert_called_once_with(
            "Current weather: Light rain in London, GB, 18.4 degrees Celsius, "
            "feels like 17.8 degrees, humidity 72 percent, wind 12.6 kilometers "
            "per hour, pressure 1012 hectopascals, visibility 10.0 kilometers, "
            "cloud cover 90 percent."
        )
        fetch_weather.assert_called_once_with("London")

    def test_dashboard_weather_command_returns_report_without_calling_gemini(self):
        report = {
            "available": True,
            "location": "New Delhi, IN",
            "condition": "Clear sky",
            "temperature": 29.0,
            "feels_like": 31.0,
            "humidity": 40,
            "wind_speed": 7.2,
        }
        with patch("main.fetch_weather", return_value=report) as fetch_weather, patch.object(
            self.jarvis, "_gemini_reply"
        ) as gemini:
            result = self.jarvis.handle_dashboard_command("weather")
        self.assertTrue(result["continue"])
        reply = result["reply"]
        if not isinstance(reply, str):
            self.fail("Jarvis weather command returned a non-string reply")
        self.assertIn("29.0 degrees Celsius", reply)
        fetch_weather.assert_called_once_with(None)
        gemini.assert_not_called()

    def test_microphone_fallback_keeps_speech_enabled(self):
        with (
            patch.object(self.jarvis, "say"),
            patch.object(
                self.jarvis,
                "listen",
                side_effect=[RuntimeError("microphone unavailable"), None],
            ),
            patch("builtins.input", side_effect=["quit"]),
        ):
            self.jarvis.run()
        self.assertTrue(self.jarvis.voice_output)


if __name__ == "__main__":
    unittest.main()
