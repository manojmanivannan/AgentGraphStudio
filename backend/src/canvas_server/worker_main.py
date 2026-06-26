from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from canvas_server.background_run_worker import get_background_run_worker, shutdown_background_run_worker
from canvas_server.config import settings

logger = logging.getLogger("canvas_server.worker_main")


async def _run_worker_process() -> None:
    if settings.execution_mode == "api":
        raise RuntimeError("EXECUTION_MODE=api cannot run canvas-worker")

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # add_signal_handler is not available on some platforms.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    worker = get_background_run_worker()
    await worker.ensure_started()
    worker.kick()

    logger.info("Execution worker ready (worker_id=%s)", worker.worker_id)
    await stop_event.wait()


async def _main_async() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
    )

    # Initialize MLflow tracing for DSPy — skip gracefully when unavailable
    if settings.mlflow_enabled:
        try:
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            mlflow.set_experiment(settings.mlflow_experiment_name)
            mlflow.dspy.autolog()
            logger.info(
                "MLflow tracing enabled: tracking_uri=%s experiment=%s",
                settings.mlflow_tracking_uri,
                settings.mlflow_experiment_name,
            )
        except Exception as exc:
            logger.warning(
                "MLflow tracing disabled — could not connect to %s: %s",
                settings.mlflow_tracking_uri,
                exc,
            )
    else:
        logger.info("MLflow tracing disabled via configuration")

    logger.info("Starting execution worker process")
    try:
        await _run_worker_process()
    finally:
        await shutdown_background_run_worker()
        logger.info("Execution worker process stopped")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
