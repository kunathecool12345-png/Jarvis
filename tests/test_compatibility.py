import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import main


class JarvisCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.say = patch("main.speak").start()
        self.addCleanup(patch.stopall)
        main._assistant.voice_output = True

    def test_loads_local_environment_without_overriding_existing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                '\ufeffEXISTING="file value"\nNEW_KEY="quoted value"\n'
                "INLINE=value # comment\n# ignored\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"EXISTING": "process value"}, clear=True):
                main._load_local_env(env_file)
                self.assertEqual(os.environ["EXISTING"], "process value")
                self.assertEqual(os.environ["NEW_KEY"], "quoted value")
                self.assertEqual(os.environ["INLINE"], "value")

    @patch("main.webbrowser.open")
    def test_open_command_is_case_insensitive(self, open_browser):
        self.assertFalse(main.processCommand("OPEN Google"))
        open_browser.assert_called_once_with("https://google.com")

    @patch("main.webbrowser.open")
    def test_play_looks_up_song_case_insensitively(self, open_browser):
        self.assertFalse(main.processCommand("play NAINA"))
        open_browser.assert_called_once_with(main.musiclibrary.music["naina"])

    def test_play_without_song_lists_available_music(self):
        self.assertFalse(main.processCommand("play"))
        self.assertIn("naina", self.say.call_args.args[0])

    @patch("main.webbrowser.open")
    def test_unknown_song_searches_youtube(self, open_browser):
        self.assertFalse(main.processCommand("play Bohemian Rhapsody"))
        open_browser.assert_called_once_with(
            "https://www.youtube.com/results?search_query=Bohemian+Rhapsody"
        )
        self.assertIn("Searching YouTube", self.say.call_args.args[0])

    @patch("main.webbrowser.open")
    def test_youtube_suffix_is_removed_from_song_search(self, open_browser):
        self.assertFalse(main.processCommand("play lo-fi beats on YouTube"))
        open_browser.assert_called_once_with(
            "https://www.youtube.com/results?search_query=lo-fi+beats"
        )

    def test_exit_command_stops_assistant(self):
        self.assertTrue(main.processCommand("quit"))

    @patch("main.aiProcess", return_value="AI response")
    def test_play_prefix_does_not_capture_unrelated_words(self, ai_process):
        self.assertFalse(main.processCommand("playful question"))
        ai_process.assert_called_once_with("playful question")

    def test_gemini_failure_without_key_returns_actionable_message(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            main, "_gemini_client", None
        ):
            answer = main.aiProcess("hello")
        self.assertIn("couldn't reach Gemini", answer)

    def test_gemini_response_is_trimmed(self):
        response = SimpleNamespace(text=" hello ")
        chat = SimpleNamespace(send_message=Mock(return_value=response))
        chats = SimpleNamespace(create=Mock(return_value=chat))
        client = SimpleNamespace(chats=chats)
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
            patch.object(main, "_get_gemini_client", return_value=client),
            patch.object(main, "_gemini_chat", None),
            patch.object(main, "_gemini_chat_model", None),
            patch.object(main, "_gemini_chat_config", None),
        ):
            self.assertEqual(main.aiProcess("hello"), "hello")
        chats.create.assert_called_once()
        chat.send_message.assert_called_once_with("hello")

    def test_gemini_503_reports_temporary_model_overload(self):
        from google.genai.errors import APIError

        primary_chat = SimpleNamespace(
            send_message=Mock(
                side_effect=APIError(
                    503,
                    {
                        "error": {
                            "code": 503,
                            "message": "Model is temporarily overloaded",
                            "status": "UNAVAILABLE",
                        }
                    },
                )
            ),
            get_history=Mock(return_value=["earlier conversation"]),
        )
        fallback_chat = SimpleNamespace(
            send_message=Mock(return_value=SimpleNamespace(text="Fallback answer"))
        )
        client = SimpleNamespace(
            models=SimpleNamespace(
                list=Mock(
                    return_value=[
                        SimpleNamespace(
                            name="models/gemini-fallback-flash",
                            supported_actions=["generateContent"],
                        )
                    ]
                )
            ),
            chats=SimpleNamespace(create=Mock(return_value=fallback_chat)),
        )
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
            patch.object(main, "_gemini_client", client),
            patch.object(main, "_gemini_chat", primary_chat),
            patch.object(main, "_gemini_chat_model", "gemini-primary-flash"),
            patch.object(main, "_gemini_chat_config", None),
        ):
            answer = main.aiProcess("What is the current temperature?")
            self.assertEqual(answer, "Fallback answer")
            self.assertEqual(main._gemini_chat_model, "gemini-fallback-flash")
        client.models.list.assert_called_once()
        client.chats.create.assert_called_once_with(
            model="gemini-fallback-flash",
            config=None,
            history=["earlier conversation"],
        )
        fallback_chat.send_message.assert_called_once_with(
            "What is the current temperature?"
        )

    def test_gemini_503_reports_busy_when_no_fallback_is_available(self):
        from google.genai.errors import APIError

        chat = SimpleNamespace(
            send_message=Mock(
                side_effect=APIError(
                    503,
                    {
                        "error": {
                            "code": 503,
                            "message": "Model is temporarily overloaded",
                            "status": "UNAVAILABLE",
                        }
                    },
                )
            ),
            get_history=Mock(return_value=[]),
        )
        client = SimpleNamespace(
            models=SimpleNamespace(
                list=Mock(
                    return_value=[
                        SimpleNamespace(
                            name="models/gemini-primary-flash",
                            supported_actions=["generateContent"],
                        )
                    ]
                )
            ),
            chats=SimpleNamespace(create=Mock()),
        )
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
            patch.object(main, "_gemini_client", client),
            patch.object(main, "_gemini_chat", chat),
            patch.object(main, "_gemini_chat_model", "gemini-primary-flash"),
            patch.object(main, "_gemini_chat_config", None),
        ):
            answer = main.aiProcess("What is the current temperature?")
        self.assertIn("temporarily busy", answer)
        self.assertIn("try your question again", answer)

    def test_gemini_uses_current_default_model(self):
        response = SimpleNamespace(text="hello")
        chat = SimpleNamespace(send_message=Mock(return_value=response))
        client = SimpleNamespace(chats=SimpleNamespace(create=Mock(return_value=chat)))
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
            patch.object(main, "_get_gemini_client", return_value=client),
            patch.object(main, "_gemini_chat", None),
            patch.object(main, "_gemini_chat_model", None),
            patch.object(main, "_gemini_chat_config", None),
        ):
            main.aiProcess("hello")
        self.assertEqual(
            client.chats.create.call_args.kwargs["model"], "gemini-3.8-flash"
        )

    @patch("main.requests.get")
    def test_news_articles_are_spoken(self, get):
        response = Mock()
        response.json.return_value = {
            "status": "ok",
            "articles": [{"title": "First headline"}, {"title": "Second headline"}],
        }
        get.return_value = response
        with patch.dict(os.environ, {"NEWS_API_KEY": "test-key"}):
            main._fetch_news()
        self.assertEqual(
            [call.args[0] for call in self.say.call_args_list],
            ["First headline", "Second headline"],
        )

    def test_news_without_key_reports_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            main._fetch_news()
        self.assertIn("NEWS_API_KEY", self.say.call_args.args[0])

    def test_missing_microphone_falls_back_to_text_mode(self):
        speech_module = SimpleNamespace(
            Recognizer=Mock(),
            Microphone=Mock(side_effect=AttributeError("Could not find PyAudio")),
        )
        with (
            patch.object(main, "sr", speech_module),
            patch("main._run_text_mode") as text_mode,
        ):
            main.run()
        text_mode.assert_called_once_with()
        self.assertTrue(main._assistant.voice_output)

    def test_text_mode_speaks_assistant_replies(self):
        with (
            patch("builtins.input", side_effect=["hello", "quit"]),
            patch("main.aiProcess", return_value="Hello from Jarvis"),
        ):
            main._run_text_mode()
        self.assertTrue(main._assistant.voice_output)
        self.assertIn(
            call("Hello from Jarvis"),
            self.say.call_args_list,
        )


if __name__ == "__main__":
    unittest.main()
