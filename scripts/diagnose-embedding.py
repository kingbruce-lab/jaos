import httpx

from app.config import settings
from app.embeddings import EmbeddingServiceError, request_embeddings


try:
    vector = request_embeddings(["京奥电竞召回测试"])[0]
except EmbeddingServiceError as exc:
    print(f"embedding_error={exc}")
    response = httpx.get(
        f"{settings.gateway_base_url}/models",
        headers={"Authorization": f"Bearer {settings.gateway_api_key}"},
        timeout=30.0,
    )
    print(f"models_status={response.status_code}")
    if response.status_code < 400:
        model_ids = sorted(
            str(row.get("id", ""))
            for row in response.json().get("data", [])
            if "embed" in str(row.get("id", "")).lower()
        )
        print("embedding_models=" + ",".join(model_ids))
        for model_id in model_ids:
            probe = httpx.post(
                f"{settings.gateway_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.gateway_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model_id, "input": ["京奥电竞召回测试"]},
                timeout=30.0,
            )
            print(f"probe_model={model_id} status={probe.status_code}")
    raise SystemExit(1)

print(f"embedding_model={settings.embedding_model}")
print(f"embedding_dimensions={len(vector)}")
