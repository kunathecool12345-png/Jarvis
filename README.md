# Jarvis

Jarvis is a Python voice assistant with Gemini chat, browser shortcuts, music
links, and optional NewsAPI headlines. It also supports typed-command mode.

## Windows setup

Use Python 3.13 for voice input. PyAudio 0.2.14 publishes Windows wheels for
Python 3.13, but not Python 3.14, so installing it with Python 3.14 attempts a
native build and can fail.

From the project folder in PowerShell:

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and add your own Gemini API key. Add a NewsAPI key too if you want
the `news` command. For live weather from OpenWeatherMap, set
`OPENWEATHER_API_KEY` in `.env` to your key from your OpenWeatherMap account.
Optionally set `WEATHER_CITY` to a city query such as `London,GB`; it defaults
to `New Delhi,IN`. The key stays on the Python server and is never sent to the
browser. If the OpenWeatherMap key is blank, Jarvis continues to use the
keyless Open-Meteo weather service. Do not commit or share `.env`; it is ignored
by Git.
`.env.example` contains blank placeholders only.
The default Gemini model is `gemini-3.8-flash`; you can override it with the
`GEMINI_MODEL` setting in `.env`. If that model returns a temporary 503 busy
response, Jarvis discovers other Gemini models available to your key and tries
supported models automatically. You can optionally list preferred alternatives
in `GEMINI_FALLBACK_MODELS`, separated by commas. A successful fallback stays
active for the rest of the running session, and conversation history is kept.

In VS Code, select `.venv313\Scripts\python.exe` as the Python interpreter. Check
the setup and start Jarvis:

```powershell
python main.py --check
python main.py
```

To open the animated Jarvis dashboard in your browser:

```powershell
python main.py --dashboard
```

The dashboard runs locally at `http://127.0.0.1:5000`. Allow microphone access
in a current version of Chrome or Edge, then say **“Jarvis”** to wake it. You
can include a question after the wake word, for example, “Jarvis, what is the
capital of India?” If you only say “Jarvis,” it will ask what you need. Jarvis
stays awake for follow-up questions until you say **“go to sleep.”** The
The dashboard uses Indian English recognition, shows interim voice transcription,
and automatically retries temporary speech-service network failures. For
longer voice requests it gives a brief spoken acknowledgement while Gemini
finishes. Recognition speed still depends on the browser's speech service and
your internet connection. It shows current weather and detailed top India
headlines. Ask Jarvis `weather` or `weather in <city>` for a current spoken or
typed weather report. The dashboard and Jarvis use OpenWeatherMap when
`OPENWEATHER_API_KEY` is configured, otherwise weather loads from Open-Meteo.
The report includes temperature, feels-like temperature, humidity, wind,
pressure, visibility, and cloud cover when provided by the service. Headlines use the optional NewsAPI key
in `.env` when configured and fall back to India-focused Google News RSS if
that key is missing or unavailable. Use the refresh button to update both
cards. The browser
listens for the wake word while the dashboard is open; if microphone access or
speech recognition is unavailable, use the text box instead. Jarvis speaks its
answers through the browser, and the animated globe changes while listening,
thinking, and speaking. The dashboard's Voice On/Off control mutes or enables
spoken replies without disabling voice input.

Run `python test_voice.py` to start the same listening assistant. If a
microphone/PyAudio device is unavailable, Jarvis explains the issue and
switches to typed commands. Start typed mode directly with:

```powershell
python main.py --text
```

Voice recognition uses Google's speech recognition service, so audio is sent
to that service for transcription in the command-line assistant. Dashboard
voice recognition and speech output use your browser's speech APIs. Browser
speech recognition may send microphone audio to the browser's speech service
for transcription.
Typed command-line mode does not use the microphone; Jarvis still speaks its
replies.

Say or type `quit` to exit. Use `open google`, `open youtube`, `open github`,
`play lo-fi beats`, or `news` for built-in commands; other prompts go to Gemini.
Saved names in `musiclibrary.py` open their links directly. Any other
`play <song name>` command searches YouTube, for example `play Bohemian
Rhapsody` or `play lo-fi beats on YouTube`.

## Publishing safely

Before publishing, review `git status --short --ignored`. Do not add `.env`,
virtual environments, API keys, personal paths, microphone recordings, or
other private data. Never paste API keys into source code. If a key was
previously committed or shared, revoke it with its provider and create a
replacement; deleting it from the latest file does not remove it from Git
history.
