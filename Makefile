.PHONY: doctor doctor-strict bootstrap bootstrap-playwright bootstrap-blender frontend-install frontend-dev backend-install backend-dev backend-test frontend-test frontend-e2e

doctor:
	python3 scripts/setup_doctor.py

doctor-strict:
	python3 scripts/setup_doctor.py --strict

bootstrap:
	python3 scripts/bootstrap.py

bootstrap-playwright:
	python3 scripts/bootstrap.py --with-playwright

bootstrap-blender:
	python3 scripts/bootstrap.py --install-blender

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

backend-install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

backend-dev:
	cd backend && . .venv/bin/activate && python -m app.main

backend-test:
	cd backend && python3 -m unittest discover tests

frontend-test:
	cd frontend && npm run test:unit

frontend-e2e:
	cd frontend && npx playwright install chromium && npm run test:e2e
