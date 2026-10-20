# Smart Spend Tracker API

## Запуск (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Відкривати:
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- OpenAPI JSON від FastAPI: http://127.0.0.1:8000/openapi.json

`openapi.yaml` можна імпортувати у https://editor.swagger.io/.


