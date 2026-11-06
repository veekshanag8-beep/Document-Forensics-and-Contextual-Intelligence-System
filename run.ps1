# Start the investigation console at http://localhost:8000
# Optional: $env:ANTHROPIC_API_KEY = "sk-ant-..." before running, for an LLM-written summary.
.\.venv\Scripts\python.exe -X utf8 -m uvicorn app.main:app --port 8000
