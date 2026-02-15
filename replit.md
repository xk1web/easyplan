# Python Backend App

## Overview
A simple Python backend HTTP server using only the standard library (`http.server`). No external frameworks.

## Project Architecture
- `main.py` — The entire application. Runs an HTTP server on port 5000.

## Endpoints
- `GET /` — Returns a JSON greeting message.
- `GET /health` — Returns a health check response.
- `POST /` — Accepts JSON data and echoes it back.
- Any other path returns a 404 JSON error.

## Running
```
python main.py
```

## Recent Changes
- 2026-02-15: Initial project setup with basic HTTP server.
