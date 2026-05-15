.PHONY: frontend-install frontend-dev backend-install backend-dev backend-dev-live backend-test frontend-test frontend-e2e

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

backend-install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

backend-dev:
	cd backend && . .venv/bin/activate && BLENDER_PORT=$${BLENDER_PORT:-9876} python -m app.main

# Dev-only: render jobs route to the OPEN Blender session via MCP (port 9876)
# instead of spawning a headless subprocess. Lets you see changes in the
# viewport as the wizard renders. See docs/BlenderFixes/README.md.
backend-dev-live:
	cd backend && . .venv/bin/activate && BLENDER_PORT=$${BLENDER_PORT:-9876} BLENDER_LIVE_RENDER=1 BLENDER_LIVE_TIMEOUT_SECONDS=$${BLENDER_LIVE_TIMEOUT_SECONDS:-900} python -m app.main

backend-test:
	cd backend && python3 -m unittest discover tests

frontend-test:
	cd frontend && npm run test:unit

frontend-e2e:
	cd frontend && npx playwright install chromium && npm run test:e2e
