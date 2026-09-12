FROM python:3.14-slim

RUN pip install --no-cache-dir --only-binary=:all: mlflow \
	&& pip uninstall -y scipy scikit-learn matplotlib fonttools pillow pyarrow \
	&& addgroup --system --gid 10001 mlflow \
	&& adduser --system --uid 10001 --ingroup mlflow --home /app --no-create-home mlflow \
	&& mkdir -p /app/mlflow \
	&& chown -R mlflow:mlflow /app

WORKDIR /app

USER mlflow

CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000", "--backend-store-uri", "sqlite:///mlflow/mlflow.db"]