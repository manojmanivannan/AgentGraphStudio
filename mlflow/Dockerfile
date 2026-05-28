FROM python:3.12-slim

RUN pip install mlflow

WORKDIR /app

CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000", "--backend-store-uri", "sqlite:///mlflow/mlflow.db"]