"""Jarvis voice and text assistant."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import quote_plus

import webbrowser

import musiclibrary
import requests
from weather import fetch_weather

try:
    import speech_recognition as sr
except ImportError:
    sr = None


class _GoogleSpeechRecognizer(Protocol):
    def recognize_google(self, audio: object) -> str: ...


MUSIC_LIBRARY = musiclibrary.MUSIC_LIBRARY


DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"
SHORTCUTS = {
    "google": "https://google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
}

from datetime import datetime
from zoneinfo import ZoneInfo

def get_current_datetime():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    return (
        f"Today's date is {now.strftime('%d %B %Y')}. "
        f"The current time is {now.strftime('%I:%M %p')}. "
        f"The timezone is India Standard Time (IST)."
    )


def _load_local_env(path: str | Path = ".env") -> None:
    """Load simple KEY=value entries without overriding the process environment."""
    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.lstrip("\ufeff").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "a").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = value.split("#", 1)[0].rstrip()
        if key not in os.environ:
            os.environ[key] = value


def load_environment() -> None:
    _load_local_env(Path(__file__).resolve().with_name(".env"))


_speech_engine = None
_speech_engine_checked = False


def speak(message: str) -> None:
    """Speak a message when the optional text-to-speech package is available."""
    global _speech_engine, _speech_engine_checked
    print(f"Jarvis: {message}")
    if _speech_engine_checked and _speech_engine is None:
        return
    try:
        import pyttsx3
    except ImportError:
        _speech_engine_checked = True
        return
    try:
        if _speech_engine is None:
            _speech_engine = (
                pyttsx3.init(driverName="sapi5")
                if os.name == "nt"
                else pyttsx3.init()
            )
            _speech_engine.setProperty("volume", 1.0)
        _speech_engine.say(message)
        _speech_engine.runAndWait()
    except (RuntimeError, OSError) as exc:
        print(f"Voice output failed: {exc}", file=sys.stderr)
        _speech_engine = None
        _speech_engine_checked = True


_gemini_client = None
_gemini_chat = None
_gemini_chat_model = None
_gemini_chat_config = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured")
        from google import genai

        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _available_fallback_models(client, current_model: str) -> list[str]:
    from google.genai.errors import APIError

    configured = [
        item.strip()
        for item in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",")
        if item.strip()
    ]
    available: set[str] = set()
    try:
        for model_info in client.models.list():
            name = getattr(model_info, "name", None)
            actions = getattr(model_info, "supported_actions", None) or []
            if not isinstance(name, str) or "generateContent" not in actions:
                continue
            model_name = name.rsplit("/", 1)[-1]
            if model_name.startswith("gemini-") and model_name != current_model:
                available.add(model_name)
    except (APIError, OSError, RuntimeError, ValueError) as exc:
        print(f"Could not discover Gemini fallback models: {exc}", file=sys.stderr)

    candidates = []
    for model in configured:
        normalized = model.rsplit("/", 1)[-1]
        if normalized != current_model and normalized not in candidates:
            candidates.append(normalized)

    def priority(model: str) -> tuple[int, int, str]:
        is_preview = int("preview" in model.casefold() or "exp" in model.casefold())
        if "flash-lite" in model.casefold():
            family = 0
        elif "flash" in model.casefold():
            family = 1
        else:
            family = 2
        return is_preview, family, model

    candidates.extend(sorted(available.difference(candidates), key=priority))
    return candidates


def _try_gemini_fallback(
    client, current_chat, current_model: str, prompt: str, config
):
    from google.genai.errors import APIError

    previous_history = current_chat.get_history(curated=True)
    for fallback_model in _available_fallback_models(client, current_model):
        fallback_chat = client.chats.create(
            model=fallback_model,
            config=config,
            history=previous_history,
        )
        try:
            response = fallback_chat.send_message(prompt)
        except APIError as exc:
            if exc.code in {404, 503}:
                print(
                    f"Gemini fallback {fallback_model} is unavailable; trying another model.",
                    file=sys.stderr,
                )
                continue
            raise
        print(f"Gemini switched from {current_model} to {fallback_model}.")
        return fallback_chat, fallback_model, response
    return None


def aiProcess(prompt: str) -> str:
    global _gemini_chat, _gemini_chat_model, _gemini_chat_config
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "I couldn't reach Gemini: please configure GEMINI_API_KEY in your .env file."
    try:
        from google.genai import types
        from google.genai.errors import APIError
    except ImportError as exc:
        print(f"Gemini SDK is unavailable: {exc}", file=sys.stderr)
        return "I couldn't reach Gemini. Install the project requirements and check GEMINI_API_KEY."
    try:
        if _gemini_chat is None:
            model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
            if not model:
                model = DEFAULT_GEMINI_MODEL
            _gemini_chat_config = types.GenerateContentConfig(
                system_instruction=(
                    "You are Jarvis, a helpful personal AI assistant. "
                    "Be accurate, friendly, concise, and clear."
                )
            )
            _gemini_chat = _get_gemini_client().chats.create(
                model=model,
                config=_gemini_chat_config,
            )
            _gemini_chat_model = model
        else:
            model = _gemini_chat_model or DEFAULT_GEMINI_MODEL
        try:
            response = _gemini_chat.send_message(prompt)
        except APIError as exc:
            if exc.code != 503:
                raise
            client = _get_gemini_client()
            fallback = _try_gemini_fallback(
                client, _gemini_chat, model, prompt, _gemini_chat_config
            )
            if fallback is None:
                print(f"Gemini request failed: {exc}", file=sys.stderr)
                return (
                    "Gemini is temporarily busy, and no available fallback model "
                    "could answer. "
                    "Please try your question again in a moment."
                )
            _gemini_chat, _gemini_chat_model, response = fallback
    except ValueError as exc:
        print(f"Gemini setup failed: {exc}", file=sys.stderr)
        return "I couldn't reach Gemini. Check the GEMINI_API_KEY configuration."
    except APIError as exc:
        print(f"Gemini request failed: {exc}", file=sys.stderr)
        if exc.code == 503:
            return "Gemini is temporarily busy. Please try your question again in a moment."
        return "Gemini couldn't complete that request. Please check your API key and try again."
    except OSError as exc:
        print(f"Gemini connection failed: {exc}", file=sys.stderr)
        return "I couldn't reach Gemini just now. Please check your connection and API key."
    return (response.text or "").strip() or "Gemini returned an empty response."


def _fetch_news() -> list[str]:
    api_key = os.getenv("NEWS_API_KEY", "").strip()
    if not api_key:
        speak("News is not configured. Add a NewsAPI key to NEWS_API_KEY in .env.")
        return []
    country = os.getenv("NEWS_COUNTRY", "us").strip().lower() or "us"
    try:
        response = requests.get(
            NEWS_API_URL,
            params={"country": country, "apiKey": api_key, "pageSize": 5},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"News request failed: {exc}", file=sys.stderr)
        speak("I couldn't retrieve the headlines. Please try again later.")
        return []

    articles = payload.get("articles", [])
    titles: list[str] = []
    for article in articles:
        if isinstance(article, dict):
            title = article.get("title")
            if isinstance(title, str) and title:
                titles.append(title)
    if not titles:
        speak("No headlines were returned.")
        return []
    for title in titles:
        speak(title)
    return titles


def _run_text_mode() -> None:
    _assistant.voice_output = True
    while True:
        try:
            command = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print()
            _assistant.say("Goodbye!")
            return
        if processCommand(command):
            return


def run() -> None:
    _assistant.voice_output = True
    _assistant.say("Hello! I'm Jarvis. Say or type 'quit' to exit.")
    while True:
        try:
            command = _assistant.listen()
        except RuntimeError as exc:
            print(f"{exc} Switching to typed commands.", file=sys.stderr)
            _run_text_mode()
            return
        if command is not None and processCommand(command):
            return


class Jarvis:
    """Routes built-in commands and sends other prompts to Gemini."""

    def __init__(self) -> None:
        self._chat = None
        self._speech_engine = None
        self._speech_engine_checked = False
        self.voice_output = True

    def say(self, message: str) -> None:
        if not self.voice_output:
            print(f"Jarvis: {message}")
            return
        speak(message)

    def listen(self) -> str | None:
        """Listen for one phrase. Return None when the phrase was not understood."""
        if sr is None:
            raise RuntimeError(
                "Speech recognition is not installed. Install requirements.txt or use --text."
            )

        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                print("Listening...")
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=12)
        except (OSError, AttributeError) as exc:
            raise RuntimeError(
                "No microphone is available. Connect one or start Jarvis with --text."
            ) from exc
        except sr.WaitTimeoutError:
            return None

        try:
            google_recognizer = cast(_GoogleSpeechRecognizer, recognizer)
            phrase = google_recognizer.recognize_google(audio)
            print(f"You: {phrase}")
            return phrase
        except sr.UnknownValueError:
            self.say("Sorry, I didn't catch that.")
            return None
        except sr.RequestError as exc:
            print(f"Speech recognition service failed: {exc}", file=sys.stderr)
            return None

    def _gemini_reply(self, prompt: str) -> str:
        return aiProcess(prompt)

    @staticmethod
    def _open_url(url: str) -> str:
        if not webbrowser.open(url):
            return "I couldn't open a browser. Please check your default browser settings."
        return "Opening it now."

    def _play(self, song: str) -> str:
        normalized_song = song.strip().casefold()
        saved_url = MUSIC_LIBRARY.get(normalized_song)
        if saved_url:
            return self._open_url(saved_url)
        search_term = re.sub(r"\s+on\s+youtube$", "", song.strip(), flags=re.IGNORECASE)
        if not search_term:
            return "Tell me which song to play."
        query = quote_plus(search_term)
        if not webbrowser.open(f"https://www.youtube.com/results?search_query={query}"):
            return "I couldn't open a browser. Please check your default browser settings."
        return f"Searching YouTube for {search_term}."

    def _news(self) -> str:
        titles = _fetch_news()
        return "Here are the top headlines: " + " ".join(titles) if titles else ""

    @staticmethod
    def _weather(city: str | None = None) -> str:
        weather = fetch_weather(city)
        if not weather.get("available"):
            return str(weather.get("error", "Weather is temporarily unavailable."))

        location = weather.get("location", "your configured location")
        details = [
            f"{weather['condition']} in {location}",
            f"{weather['temperature']:.1f} degrees Celsius",
            f"feels like {weather['feels_like']:.1f} degrees",
            f"humidity {weather['humidity']} percent",
            f"wind {weather['wind_speed']:.1f} kilometers per hour",
        ]
        if weather.get("pressure") is not None:
            details.append(f"pressure {weather['pressure']} hectopascals")
        if weather.get("visibility") is not None:
            details.append(f"visibility {weather['visibility']:.1f} kilometers")
        if weather.get("cloud_cover") is not None:
            details.append(f"cloud cover {weather['cloud_cover']} percent")
        return "Current weather: " + ", ".join(details) + "."

    @staticmethod
    def _weather_city_from_command(command: str) -> tuple[bool, str | None]:
        match = re.fullmatch(
            r"(?:what(?:'s| is)\s+)?(?:the\s+)?weather"
            r"(?:\s+(?:in|for)\s+(.+))?",
            command.strip().rstrip(" .!?"),
            flags=re.IGNORECASE,
        )
        if not match:
            return False, None
        city = match.group(1)
        return True, city.strip() if city else None

    def handle_command(self, command: str) -> bool:
        """Handle one command. Return False to stop the assistant."""
        prompt = command.strip()
        if not prompt:
            return True
        normalized = prompt.casefold().strip(" .!?")
        if normalized in {"quit", "exit", "stop", "goodbye"}:
            self.say("Goodbye!")
            return False

        if normalized.startswith("open "):
            destination = normalized[5:].strip()
            if destination in SHORTCUTS:
                self.say(self._open_url(SHORTCUTS[destination]))
                return True
            self.say("I know these shortcuts: Google, YouTube, and GitHub.")
            return True

        if normalized == "play" or normalized.startswith("play "):
            song = prompt[4:].strip()
            if not song:
                available = ", ".join(MUSIC_LIBRARY)
                self.say(f"Available music: {available}")
            else:
                self.say(self._play(song))
            return True

        if normalized in {"news", "headlines", "latest news"}:
            _fetch_news()
            return True

        is_weather_command, weather_city = self._weather_city_from_command(prompt)
        if is_weather_command:
            self.say(self._weather(weather_city))
            return True

        self.say(self._gemini_reply(prompt))
        return True

    def handle_dashboard_command(self, command: str) -> dict[str, object]:
        """Handle a dashboard request without speaking from the Python process."""
        prompt = command.strip()
        if not prompt:
            return {"reply": "Type or say something for Jarvis.", "continue": True}
        normalized = prompt.casefold().strip(" .!?")
        if normalized in {"quit", "exit", "stop", "goodbye"}:
            return {"reply": "Goodbye!", "continue": False}

        if normalized.startswith("open "):
            destination = normalized[5:].strip()
            url = SHORTCUTS.get(destination)
            if url:
                return {
                    "reply": f"Opening {destination}.",
                    "continue": True,
                    "action_url": url,
                }
            return {
                "reply": "I know these shortcuts: Google, YouTube, and GitHub.",
                "continue": True,
            }

        if normalized == "play" or normalized.startswith("play "):
            song = prompt[4:].strip()
            if not song:
                return {
                    "reply": "Available music: " + ", ".join(MUSIC_LIBRARY),
                    "continue": True,
                }
            saved_url = MUSIC_LIBRARY.get(song.casefold())
            if saved_url:
                return {
                    "reply": f"Opening {song}.",
                    "continue": True,
                    "action_url": saved_url,
                }
            search_term = re.sub(
                r"\s+on\s+youtube$", "", song, flags=re.IGNORECASE
            )
            if not search_term:
                return {
                    "reply": "Tell me which song to play.",
                    "continue": True,
                }
            return {
                "reply": f"Searching YouTube for {search_term}.",
                "continue": True,
                "action_url": (
                    "https://www.youtube.com/results?search_query="
                    + quote_plus(search_term)
                ),
            }

        if normalized in {"news", "headlines", "latest news"}:
            if not os.getenv("NEWS_API_KEY", "").strip():
                return {
                    "reply": "News is not configured. Add a NewsAPI key to NEWS_API_KEY in .env.",
                    "continue": True,
                }
            headlines = _fetch_news()
            reply = (
                "Here are the top headlines: " + " ".join(headlines)
                if headlines
                else "I couldn't retrieve the headlines right now."
            )
            return {"reply": reply, "continue": True}

        is_weather_command, weather_city = self._weather_city_from_command(prompt)
        if is_weather_command:
            return {"reply": self._weather(weather_city), "continue": True}

        return {"reply": self._gemini_reply(prompt), "continue": True}

    def run(self, text_mode: bool = False) -> None:
        self.voice_output = True
        self.say("Hello! I'm Jarvis. Say or type 'quit' to exit.")
        voice_mode = not text_mode
        while True:
            if voice_mode:
                try:
                    command = self.listen()
                except RuntimeError as exc:
                    print(f"{exc} Switching to typed commands.", file=sys.stderr)
                    voice_mode = False
                    self.voice_output = True
                    continue
                if command is None:
                    continue
            else:
                try:
                    command = input("You: ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    self.say("Goodbye!")
                    return
            if not self.handle_command(command):
                return


_assistant = Jarvis()


def processCommand(command: str) -> bool:
    """Handle one command; return True only when the assistant should stop."""
    return not _assistant.handle_command(command)


def check_setup() -> int:
    """Report configuration and dependencies without exposing secret values."""
    load_environment()

    try:
        gemini_installed = importlib.util.find_spec("google.genai") is not None
    except ModuleNotFoundError:
        gemini_installed = False
    checks = {
        "Gemini SDK (google-genai)": gemini_installed,
        "Dashboard server (Flask)": importlib.util.find_spec("flask") is not None,
        "Speech recognition": importlib.util.find_spec("speech_recognition") is not None,
        "Text to speech (pyttsx3)": importlib.util.find_spec("pyttsx3") is not None,
        "HTTP client (requests)": importlib.util.find_spec("requests") is not None,
        "Gemini API key configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "NewsAPI key configured (optional)": bool(os.getenv("NEWS_API_KEY", "").strip()),
        "OpenWeatherMap key configured (optional)": bool(
            os.getenv("OPENWEATHER_API_KEY", "").strip()
        ),
    }
    for name, available in checks.items():
        status = "OK" if available else ("OPTIONAL" if "optional" in name else "MISSING")
        print(f"{status}: {name}")
    required_failures = [
        name for name, available in checks.items()
        if not available and "optional" not in name
    ]
    if required_failures:
        print("Setup check failed. Install dependencies and configure the Gemini API key.")
        return 1
    print("Setup check passed. Microphone access is checked when voice mode starts.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis voice and text assistant")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--text", action="store_true", help="use typed commands without a microphone")
    modes.add_argument("--check", action="store_true", help="check dependencies and API-key configuration")
    modes.add_argument("--dashboard", action="store_true", help="open the local Jarvis visual dashboard")
    args = parser.parse_args(argv)

    load_environment()
    if args.check:
        return check_setup()
    if args.dashboard:
        from dashboard import run_dashboard

        run_dashboard()
        return 0
    if args.text:
        _run_text_mode()
    else:
        run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())