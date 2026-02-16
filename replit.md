# Python Backend App

## Overview
A simple Python backend HTTP server using only the standard library (`http.server`). No external frameworks.

## Project Architecture
- `src/` — Source code directory.
- `src/app.py` — The HTTP server for schedule generation.
- `src/scheduler.py` — The scheduling engine using Google OR-Tools.
- `src/ai_runner.py` — Script to demonstrate AI parsing and scheduling.
- `src/ai_client.py` — OpenAI client configuration.

## Running
```bash
python src/ai_runner.py
```

## Recent Changes
- 2026-02-15: Initial project setup with basic HTTP server.
