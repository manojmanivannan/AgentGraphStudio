.PHONY: help up up-gpu down down-v clean-sandbox sandbox-image test test-backend test-frontend

help:
	@echo "Available commands:"
	@echo "  make up             - Start docker containers (excluding ollama by default)"
	@echo "  make up-gpu         - Start docker containers (including ollama via gpu profile)"
	@echo "  make down           - Stop docker containers (including ollama) without removing volumes"
	@echo "  make down-v         - Stop docker containers (including ollama) and remove volumes"
	@echo "  make clean-sandbox  - Clean up sandbox containers running python3"
	@echo "  make sandbox-image  - Build the baked-floor sandbox image (matplotlib/plotly/numpy)"
	@echo "  make test            - Run backend and frontend tests"
	@echo "  make test-backend   - Run backend tests (uv run pytest)"
	@echo "  make test-frontend  - Run frontend tests (npx vitest run)"

# Baked-floor image shared by the locked (network_mode="none") default pool and
# the networked pool. Must exist on the host docker daemon before the backend
# starts, since sandbox containers are created via the host docker.sock.
sandbox-image:
	docker build -t agentgraphstudio-sandbox-floor:latest ./sandbox

up: sandbox-image
	docker compose up --build

up-gpu: sandbox-image
	docker compose --profile gpu up --build -d

down:
	docker compose --profile gpu down --remove-orphans

down-v:
	docker compose --profile gpu down --remove-orphans --volumes

clean-sandbox:
	-docker ps -a --filter "name=^sandbox-" --format '{{.ID}}' | xargs -r docker stop
	-docker ps -a --filter "name=^sandbox-" --format '{{.ID}}' | xargs -r docker rm

test-backend:
	cd backend && uv run pytest tests/ -v

test-frontend:
	cd frontend && npx vitest run

test: test-backend test-frontend clean-sandbox
