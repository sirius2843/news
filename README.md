# Global Finance Intelligence

Free-first public-source financial intelligence collector and Chinese daily briefing. No paywall bypass; stores metadata and short excerpts only.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m gfi
pytest
```

Outputs: `reports/YYYY-MM-DD.md`, `data/history.sqlite3`, and `data/latest.json`. Set `GFI_REPORT_DATE` to override the report date. RSS and GDELT are unauthenticated; SEC submissions are publicly accessible with a descriptive User-Agent. Respect each publisher's terms and rate limits.

GitHub Actions runs daily at 00:30 UTC (08:30 Asia/Shanghai), commits report and history, and uploads a run artifact. Actions must be enabled in repository settings.
