# RazorBuy Backend

## Start the backend

From any directory, run one of these commands from the repository root:

```powershell
.\backend\scripts\start_backend.ps1
```

Or double-click `backend\scripts\start_backend.cmd`.

The launcher selects the backend directory automatically, so `uvicorn` can always import `app.main`. Start PostgreSQL first with:

```powershell
docker compose up -d
```

The API is available at http://127.0.0.1:8000 and its health check is http://127.0.0.1:8000/health.
