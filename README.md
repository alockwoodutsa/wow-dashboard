# wow-dashboard
Simple tool for viewing World of Warcraft character information.

## Environment setup

This app expects the Blizzard API credentials to be provided via environment variables:

1. Copy `.env.example` to `.env`
2. Fill in your Blizzard client ID and client secret
3. Load the variables before running the app

Example:

```bash
copy .env.example .env
# edit .env with your values
```

On Windows PowerShell:

```powershell
$env:CLIENT_ID="your_client_id_here"
$env:CLIENT_SECRET="your_client_secret_here"
python app.py
```

Do not commit your real `.env` file or production secrets to version control.
