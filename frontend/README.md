# Fabric Generator Frontend

React + Vite app for the guided fabric workflow:

- `Step 1` upload yarn reference images and track processing
- `Step 2` build or import the weaving draft
- `Step 3` map draft colors to processed yarn assets and launch the Blender preview

## Local Commands

```bash
cd frontend
npm install
npm run dev
```

Build:

```bash
npm run build
```

Unit tests:

```bash
npm run test:unit
```

E2E tests:

```bash
npx playwright install chromium
npm run test:e2e
```

## Dev Server Notes

- Local dev server: `http://127.0.0.1:5180`
- Playwright e2e server: `http://127.0.0.1:5190`
- API proxy targets:
  - `/api/parser`
  - `/api/blender`
  - `/api/yarn`

All API traffic is proxied to the backend service on `http://127.0.0.1:8000`.
