# Deploying ClientPulse

Goal: two live HTTPS URLs that share one database.

| Piece | Where | Example URL |
| :--- | :--- | :--- |
| Database | Supabase (free) | `https://xxxx.supabase.co` |
| Dashboard | Render web service `clientpulse-app` (free) | `https://clientpulse-app.onrender.com` |
| MCP server | Render web service `clientpulse-mcp` (free) | `https://clientpulse-mcp.onrender.com/mcp` |

Time needed: about 30 minutes.

---

## Step 1: Create the Supabase database

1. Sign up at https://supabase.com and click **New project**. Pick any name and region, and save the database password somewhere (you won't need it for this app).
2. When the project is ready, open **SQL Editor → New query**, paste the whole of [`schema.sql`](schema.sql), and click **Run**. You should see "Success. No rows returned".
3. Open **Project Settings → API Keys** and copy:
   - the **Project URL** (`https://xxxx.supabase.co`), shown under Project Settings → Data API
   - the **secret key** (`sb_secret_...`). On older projects this is the legacy **`service_role`** key. Do **not** use the anon/publishable key, because it can only read published reports.

## Step 2: Test Supabase locally (5 minutes, catches mistakes early)

Put the two values into your local `.env`:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=sb_secret_...
```

Then run:

```bash
python run.py seed --force
python run.py app
```

- The seed command must print `Target Database Engine: Supabase PostgreSQL`.
- The dashboard sidebar must say **DB: Supabase PostgreSQL**. If it shows a red "Supabase is configured but unreachable" box, the URL or key is wrong.
- In Supabase's **Table Editor** you should now see the demo clients and reports.

## Step 3: Put the code on GitHub

1. On https://github.com/new create a repository named `clientpulse`. Private is fine.
2. In this folder run:

```bash
git init
git add .
git commit -m "ClientPulse: initial version"
git branch -M main
git remote add origin https://github.com/<your-username>/clientpulse.git
git push -u origin main
```

`.gitignore` keeps `.env` and `clientpulse.db` out of the repository, so your secret key is never uploaded. Check that `.env` is **not** listed by `git status` before you push.

## Step 4: Deploy both services on Render

1. Sign up at https://render.com using your GitHub account.
2. Click **New → Blueprint**, pick the `clientpulse` repository, and confirm. Render reads [`render.yaml`](render.yaml) and creates `clientpulse-app` and `clientpulse-mcp`.
3. Render asks for the secret values. Fill them in for **both** services:

| Variable | Value |
| :--- | :--- |
| `SUPABASE_URL` | your Supabase Project URL |
| `SUPABASE_KEY` | your Supabase secret / service_role key |
| `PUBLIC_APP_URL` | `https://clientpulse-app.onrender.com` (the dashboard URL; if Render gives it a different name, use that) |
| `APP_PASSWORD` (dashboard only) | a password for reviewers, or leave empty for no login |

4. Click **Apply** and wait for both deploys to turn green (3–5 minutes).
5. If the dashboard URL Render assigned differs from what you entered in `PUBLIC_APP_URL`, update that variable on **both** services (Environment tab → Save, which redeploys).

## Step 5: Check it works

1. Open the dashboard URL. The sidebar should say **DB: Supabase PostgreSQL**.
2. Open `https://clientpulse-mcp.onrender.com/mcp` in a browser. An error such as "Not Acceptable" or "Missing session ID" is **expected**: it means the server is up (browsers don't speak MCP).
3. In the `clientpulse-mcp` service's **Logs**, look for `Database: Supabase PostgreSQL (Live)`.

## Step 6: Connect Claude

1. In Claude (claude.ai or the desktop app): **Settings → Connectors → Add custom connector**.
2. Name: `ClientPulse`. URL: `https://clientpulse-mcp.onrender.com/mcp`. Click **Add**.
3. In a new chat, enable the ClientPulse connector from the tools menu, then try:

> Create a client called "Synthetix Dynamics" in AI robotics with email alex@synthetix.io. Then create a published Q3 2026 report for them: $18,200 spend, 520,000 impressions, 16,800 clicks, 840 leads, with an executive summary and 3 recommendations. Give me the public link.

4. Refresh the dashboard: the client and report appear. Edit the report in **Create & Edit Report**, then open the public link in a private window.

---

## Things to know

- **Free Render services sleep after 15 minutes without traffic.** The first request then takes about a minute, and Claude may time out on that first call. Before a demo or before sending the links, open both URLs once. To keep them awake while reviewers are testing, either upgrade both services to the Starter plan, or set up a free monitor (for example UptimeRobot) that requests both URLs every 10 minutes.
- **MCP auth:** the MCP server has no login so reviewers can add it in one step. Claude's custom connector screen does not send a fixed bearer token, so leave `MCP_AUTH_TOKEN` unset on Render.
- **Re-seeding:** the Overview page's "Seed / Reset Demo Data" button wipes the shared Supabase database for everyone.
