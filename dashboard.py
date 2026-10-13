"""Local Flask server for Jarvis's animated browser dashboard."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from html import unescape
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request

import main as jarvis
import requests
from weather import OPEN_METEO_URL, configured_weather_city, fetch_weather


app = Flask(__name__, static_folder="static", template_folder="templates")
_command_lock = Lock()
WEATHER_URL = OPEN_METEO_URL
NEWS_URL = "https://newsapi.org/v2/top-headlines"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss"


@app.get("/")
def index():
    return render_template("index.html", weather_city=configured_weather_city())


def _fetch_dashboard_weather() -> dict[str, Any]:
    return fetch_weather()


def _fetch_dashboard_headlines() -> dict[str, Any]:
    api_key = os.getenv("NEWS_API_KEY", "").strip()
    if not api_key:
        return _fetch_google_news_headlines()

    try:
        response = requests.get(
            NEWS_URL,
            params={"country": "in", "pageSize": 5, "sortBy": "publishedAt"},
            headers={"X-Api-Key": api_key},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("NewsAPI returned an invalid response")
        if payload.get("status") != "ok":
            app.logger.warning("NewsAPI did not return a successful status; using Google News fallback")
            return _fetch_google_news_headlines()
        articles_data = payload.get("articles")
        if not isinstance(articles_data, list):
            raise ValueError("NewsAPI returned an invalid articles list")
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        app.logger.warning("Headline request failed; using Google News fallback: %s", exc)
        return _fetch_google_news_headlines()

    articles = []
    for item in articles_data:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            continue
        if urlsplit(url).scheme != "https":
            continue
        source = item.get("source")
        articles.append(
            {
                "title": title.strip(),
                "description": item.get("description")
                if isinstance(item.get("description"), str)
                else "",
                "source": source.get("name", "News source")
                if isinstance(source, dict)
                else "News source",
                "url": url,
                "published_at": item.get("publishedAt")
                if isinstance(item.get("publishedAt"), str)
                else "",
            }
        )
    if articles:
        return {"available": True, "source": "NewsAPI", "articles": articles}
    app.logger.info("NewsAPI returned no India headlines; using Google News fallback")
    return _fetch_google_news_headlines()


def _fetch_google_news_headlines() -> dict[str, Any]:
    try:
        response = requests.get(
            GOOGLE_NEWS_RSS_URL,
            params={"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
            timeout=8,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError, ValueError) as exc:
        app.logger.warning("Google News RSS request failed: %s", exc)
        return {
            "available": False,
            "error": "India headlines are unavailable. Check your internet connection and refresh.",
        }

    articles = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "").strip()
        url = item.findtext("link", "").strip()
        if not title or urlsplit(url).scheme != "https":
            continue
        description = item.findtext("description", "")
        description = re.sub(r"<[^>]*>", " ", unescape(description))
        description = re.sub(r"\s+", " ", description).strip()
        articles.append(
            {
                "title": title,
                "description": description[:500],
                "source": item.findtext("source", "Google News").strip(),
                "url": url,
                "published_at": item.findtext("pubDate", "").strip(),
            }
        )
        if len(articles) == 5:
            break
    return {"available": bool(articles), "source": "Google News", "articles": articles}


@app.get("/api/dashboard-info")
def dashboard_info():
    return jsonify(
        weather=_fetch_dashboard_weather(),
        headlines=_fetch_dashboard_headlines(),
    )


@app.post("/api/command")
def command():
    payload: Any = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Send a JSON object with a command."), 400

    text = payload.get("text")
    if not isinstance(text, str):
        return jsonify(error="Command text must be a string."), 400
    if len(text) > 2000:
        return jsonify(error="Command is too long (maximum 2000 characters)."), 413

    try:
        with _command_lock:
            result = jarvis._assistant.handle_dashboard_command(text)
    except Exception:
        app.logger.exception("Dashboard command failed")
        return jsonify(error="Jarvis could not complete that request. Please try again."), 500
    return jsonify(result)


def run_dashboard() -> None:
    """Start the dashboard on loopback only and open it in the default browser."""
    import webbrowser

    url = "http://127.0.0.1:5000"
    webbrowser.open(url)
    print(f"Jarvis dashboard is running at {url}. Press Ctrl+C to stop.")
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )
# real time location and latest data on 2026