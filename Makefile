.PHONY: help up up-gpu down down-v clean-sandbox

help:
	@echo "Available commands:"
	@echo "  make up             - Start docker containers (excluding ollama by default)"
	@echo "  make up-gpu         - Start docker containers (including ollama via gpu profile)"
	@echo "  make down           - Stop docker containers (including ollama) without removing volumes"
	@echo "  make down-v         - Stop docker containers (including ollama) and remove volumes"
	@echo "  make clean-sandbox  - Clean up sandbox containers running python3"

up:
	docker compose up --build -d

up-gpu:
	docker compose --profile gpu up --build -d

down:
	docker compose --profile gpu down --remove-orphans

down-v:
	docker compose --profile gpu down --remove-orphans --volumes

clean-sandbox:
	docker ps --format '{{.ID}} {{.Command}}' | grep 'python3' | awk '{print $$1}' | xargs -r docker stop
