# Developer setup

The product is the hosted app ([README](../README.md)). This page is only for working on the code.

Needs Docker and `make` (Windows: `winget install ezwinports.make`). No `.env` is needed (DEMO defaults, password
sign-in handled by the app); copy `.env.example` to `.env` to change passwords.

```
make up          # the stack in Docker: database, backend, frontend
make migrate     # the schema and its guards
make seed-demo   # the DEMO factory: six logins, master data, opening stock, a short history
make benchmark   # NIT's nine steps on a fresh benchmark factory: the 26-row scoreboard
```

Checks: `make test` (backend), `make web-test`, `make e2e` (Playwright), `make integrity` (the four conservation
laws), `make sim` / `make ml-eval` (synthetic analytics), `make backup` / `make restore-check`.

The production image is the root `Dockerfile`: the web app is built and served by the backend on one port, the way
it runs on Render ([deploy.md](deploy.md)). Sign-in mode: `AAHAR_AUTH_MODE=local` (default) or `supabase`
([ADR-0023](adr/0023-supabase-auth-token-exchange.md)).
