import importlib.util
from pathlib import Path


async def test_get_current_weather_formats_hourly_data(monkeypatch):
    app_path = Path(__file__).resolve().parents[2] / "mcp-weather" / "app.py"
    spec = importlib.util.spec_from_file_location("mcp_weather_app", app_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    async def fake_get(self, url, params=None, timeout=None):
        return FakeResponse(
            {
                "current_weather": {"time": "2026-10-17T10:00"},
                "hourly": {
                    "time": [
                        "2026-10-17T00:00",
                        "2026-10-17T01:00",
                        "2026-10-17T02:00",
                        "2026-10-17T03:00",
                        "2026-10-17T04:00",
                        "2026-10-17T05:00",
                        "2026-10-17T06:00",
                        "2026-10-17T07:00",
                        "2026-10-17T08:00",
                        "2026-10-17T09:00",
                        "2026-10-17T10:00",
                        "2026-10-17T11:00",
                    ],
                    "temperature_2m": [
                        12.3,
                        11.4,
                        10.7,
                        10.3,
                        10.0,
                        9.6,
                        9.5,
                        9.4,
                        10.1,
                        11.6,
                        12.8,
                        13.5,
                    ],
                },
            }
        )

    monkeypatch.setattr(module.httpx.AsyncClient, "get", fake_get)

    result = await module.get_current_weather(40.7128, -74.006)

    assert result["current_time"] == ["2026-10-17T10:00"]
    assert result["hours"] == ["10:00", "11:00"]
    assert result["temps"] == [12.8, 13.5]
    assert list(result.keys()) == ["current_time", "hours", "temps"]
