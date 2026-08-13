import statistics
import time

import httpx

from app.config import settings


headers = {
    "Authorization": f"Bearer {settings.gateway_api_key}",
    "Content-Type": "application/json",
}
models_response = httpx.get(
    f"{settings.gateway_base_url}/models",
    headers=headers,
    timeout=30.0,
)
models_response.raise_for_status()
model_ids = sorted(
    str(row.get("id", ""))
    for row in models_response.json().get("data", [])
    if "embed" in str(row.get("id", "")).lower()
)

for model_id in model_ids:
    durations = []
    dimensions = 0
    status = 0
    for index in range(3):
        started = time.perf_counter()
        response = httpx.post(
            f"{settings.gateway_base_url}/embeddings",
            headers=headers,
            json={
                "model": model_id,
                "input": [f"京奥电竞历史项目与培训方案检索 {index}"],
            },
            timeout=30.0,
        )
        durations.append((time.perf_counter() - started) * 1000)
        status = response.status_code
        if status < 400:
            dimensions = len(response.json()["data"][0]["embedding"])
    print(
        f"model={model_id} status={status} dimensions={dimensions} "
        f"mean_ms={statistics.fmean(durations):.2f} "
        f"max_ms={max(durations):.2f}"
    )
