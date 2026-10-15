# Civic Issue Reporting and Resolution System

Flask-based civic complaint portal with citizen reporting, department dashboards, community voting, and optional Gemini-powered complaint assistance.

## Requirements
- Python 3.11 or newer (use a version supported by the pinned dependencies)
- MySQL Server
- A Gemini API key only if AI features are needed

## Run on Windows / VS Code
1. Extract the ZIP and open the project folder in VS Code.
2. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env`, then set a long random `SECRET_KEY`, your local MySQL credentials, and (optionally) `GEMINI_API_KEY`. Do not share or commit `.env`.
4. Elevated-role self-registration is disabled by default. To enable it, set strong private `ADMIN_REGISTRATION_CODE` and `DEPARTMENT_REGISTRATION_CODE` values in `.env`; share them only with authorized staff. Prefixes such as `AD` or `DP` are not security checks.
5. Create the database in MySQL if needed:
   ```sql
   CREATE DATABASE civic_issue_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
   Ensure the existing tables match the SQLAlchemy models before running against a database with real data. This project does not automatically migrate existing schemas.
6. Start the app:
   ```powershell
   python app.py
   ```
   Then open `http://127.0.0.1:5000`. Debug mode is off unless `FLASK_DEBUG=true` is explicitly set.

## Security notes
- `.env`, virtual environments, Python caches, and uploaded user files are excluded from the source package.
- Admin-only operations require the admin role. Department users are restricted to their assigned department for complaint status updates and dashboard filtering.
- The app uses a random signing key if `SECRET_KEY` is missing, but sessions will be invalidated on restart. Configure a stable secret for local use.
- If credentials from a previously shared `.env` were real, rotate the database password and Gemini API key immediately.
- Before public deployment, add CSRF protection for HTML forms and state-changing endpoints, rate limiting, HTTPS, production-grade secret management, and formal database migrations.

## Testing
Run syntax checks with `python -m compileall -q app.py config.py models routes services`. Database-backed integration tests require a configured MySQL database and should be run only against a disposable test database.
