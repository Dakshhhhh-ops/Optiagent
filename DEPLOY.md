# Deploying OptiAgent

The free-tier setup: **website on Vercel**, **API on Render**, **Postgres on Neon**, **AI on Groq**
(or OpenRouter), **sign-in with Clerk**. Each has a free plan. Follow the steps in order: later
steps need values from earlier ones.

You will collect these values along the way:

| Value | From | Used by |
|---|---|---|
| Database URL | Neon | Render |
| Groq API key | Groq | Render |
| Clerk publishable key, secret key, Frontend API URL | Clerk | Vercel, Render |
| API URL (`https://optiagent-api.onrender.com`) | Render | Vercel |
| Website URL (`https://<name>.vercel.app`) | Vercel | Render, Clerk |

Never commit any of these to Git. They go into each provider's dashboard.

## 1. Database: Neon

1. Sign up at https://neon.tech and create a project (pick the region closest to your users).
2. Copy the **connection string**. It looks like
   `postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require`.

The API creates its tables automatically on first start.

## 2. AI model: Groq

1. Sign up at https://console.groq.com and create an **API key**.
2. Check the model list at https://console.groq.com/docs/models. The blueprint uses `qwen/qwen3-32b`;
   if Groq has renamed or retired it, pick another model that supports JSON output and set
   `OPTIAGENT_LLM_MODEL` accordingly.

For OpenRouter instead: base URL `https://openrouter.ai/api/v1`, key from https://openrouter.ai/keys.

## 3. Sign-in: Clerk

1. Sign up at https://dashboard.clerk.com and create an application (enable Email and, if you like,
   Google/GitHub).
2. From **API keys**, copy the **publishable key** (`pk_...`), the **secret key** (`sk_...`) and the
   **Frontend API URL** (`https://...clerk.accounts.dev` for development instances).
3. After step 5, add your Vercel URL under **Domains / Allowed origins**. For a real launch, create
   a **production instance**, which needs your own domain.

## 4. API: Render

1. Sign up at https://render.com and connect your GitHub account.
2. **New → Blueprint**, choose this repository. Render reads `render.yaml` and creates
   `optiagent-api`.
3. Fill in the secret values it asks for:
   - `OPTIAGENT_DATABASE_URL`: the Neon connection string
   - `OPTIAGENT_LLM_API_KEY`: the Groq key
   - `OPTIAGENT_AUTH_ISSUER`: the Clerk Frontend API URL
   - `OPTIAGENT_CORS_ORIGINS`: `["https://<your-site>.vercel.app"]` (set after step 5; redeploy)
   - `OPTIAGENT_SENTRY_DSN`: optional
4. Wait for the deploy, then open `https://<api>.onrender.com/health`; it should say `{"status":"ok"}`.
   `https://<api>.onrender.com/docs` shows the API.

Free Render services sleep after ~15 minutes without traffic; the first request afterwards takes
up to a minute. The free instance has 512 MB of memory, which is enough for normal use but not for
very large problems.

## 5. Website: Vercel

1. Sign up at https://vercel.com, **Add New → Project**, import this repository.
2. Set **Root Directory** to `web`. Vercel detects Next.js.
3. Environment variables:
   - `NEXT_PUBLIC_API_URL`: `https://<api>.onrender.com`
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`: Clerk publishable key
   - `CLERK_SECRET_KEY`: Clerk secret key
4. Deploy. Then put the Vercel URL into Render's `OPTIAGENT_CORS_ORIGINS` and Clerk's allowed origins.

## 6. Check it works

1. Open the site: Overview and Benchmarks load without signing in.
2. **New problem** asks you to sign in. Sign up, then solve the SunRay sample.
3. **Status** (sidebar) shows the AI model as reachable and available.
4. Sign in as a second user in a private window: the first user's projects are not visible.

## Limits you can tune (Render environment)

| Variable | Default | Meaning |
|---|---|---|
| `OPTIAGENT_LLM_REQUESTS_PER_HOUR` | 30 | AI requests per user per hour |
| `OPTIAGENT_LLM_REQUESTS_PER_DAY` | 2000 | AI requests per day for the whole site (caps the bill) |
| `OPTIAGENT_REQUESTS_PER_MINUTE` | 240 | All requests per IP per minute |
| `OPTIAGENT_MAX_UPLOAD_BYTES` | 10000000 | Largest uploaded file |

Rate limits are kept in memory, which is correct for one instance. If you ever run several API
instances, move them to Redis first.
