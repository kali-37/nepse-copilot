# How to proceed

Clone the code, create your own private configuration, and open your local
dashboard. Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/), and Node 24 are
recommended. No MeroShare account or AI key is needed for public market analysis.
The source code uses the [MIT license](LICENSE).

## Install and open the dashboard

```bash
git clone https://github.com/kali-37/nepse-copilot.git
cd nepse-copilot
uv sync --frozen --python 3.12
cp .env.example .env
chmod 600 .env
npm --prefix web ci
npm --prefix web run build
uv run --frozen python -m uvicorn nepse_trader.web.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ and press **Refresh today**. The first refresh downloads
prices and repairs insufficient history in bounded batches. Daily and monthly
ideas appear only when there is sufficient evidence and cash. Source failures
and unavailable symbols are shown in the refresh details. Further historical
downloads are available under **Research & tools → Operations**.

Edit **Cash for new purchases** to your own budget. **I bought this** and
**I sold** record trades you already executed through your broker. **Set exit
plan** attaches fixed stops/targets to an existing holding without buying more.
No button places a broker order.

For frontend development, run `npm --prefix web run dev` in a second terminal;
Vite proxies API requests to the local backend. The built production dashboard
is served by FastAPI when `web/dist` exists.

## Keep your credentials private

The `.env.example` template has no real credentials. Edit only your local `.env`:

```dotenv
NEPSE_MEROSHARE_ENABLED=false
NEPSE_MEROSHARE_DP_ID=
NEPSE_MEROSHARE_USERNAME=
NEPSE_MEROSHARE_PASSWORD=
NEPSE_OPENROUTER_API_KEY=
NEPSE_ANTHROPIC_API_KEY=
```

Fill your own values and explicitly enable MeroShare if you choose to use its
read-only mirror. The OS keyring is another password option. CSV imports work
without a portal login. Never paste credentials into source files, issues,
commits, screenshots or frontend `VITE_*` environment variables.

Git and Docker ignore `.env` variants, private databases and exports, logs,
backups, HAR captures, cloud credentials, generated analysis caches and local
screenshots. Keep all account
exports under `data/` or `exports/`; arbitrary files outside ignored directories
can still be tracked. Each user keeps a separate `.env` and database. Sharing
this repository does not share your running account dashboard.

Docker Compose optionally reads your local `.env` into the running container;
Docker's build context excludes it, so credentials are not baked into images.

Keep the server bound to `127.0.0.1`. Authentication and per-user database
isolation are required before offering a shared account dashboard online.

## Test before pushing

```bash
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen pytest -q
uv run --frozen python scripts/check_public_files.py
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run test:run
npm --prefix web run build
git status --short
git diff --cached --stat
```

Development tools live in uv's default `dev` dependency group. Both `uv sync`
and plain `uv run ruff check .` include Ruff, so the CI environment does not drop
it between install and lint. The optional `.[dev]` extra remains available for
pip users. CI explicitly selects Python 3.11 and 3.12 and checks both versions.

Stage source changes deliberately, inspect them, and run the public-file check
again after staging. It reads the Git index and reports locations without
printing suspected secret values. Local pre-commit hooks are optional:

```bash
uv run pre-commit install
```

If a real credential has ever been committed, ignoring the file later does not
remove it from history. Rotate that credential and remove the historical copy
before making the repository public. GitHub repository visibility is managed
under **Settings → General → Danger Zone → Change repository visibility**; the
GitHub CLI equivalent requires an authenticated account with repository access.

Read [how_to_use.md](how_to_use.md) for commands and
[docs/COMPLETION_STATUS.md](docs/COMPLETION_STATUS.md) for the delivered dashboard
features and current limitations.
