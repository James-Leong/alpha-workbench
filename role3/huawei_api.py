"""Huawei Model Call helper for role3 development.

This is a copy of the helper placed under `role3/` to allow isolated
development before migration into `alpha_workbench/`.
"""

from __future__ import annotations

import os
from typing import Any

import requests


def call_huawei_model(api_url: str, token: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"text": resp.text}


def extract_idea_via_huawei(input_text: str, api_url: str | None = None, token: str | None = None) -> dict[str, Any]:
    api_url = api_url or os.environ.get("HUAWEI_API_URL")
    token = token or os.environ.get("HUAWEI_TOKEN")
    if not api_url:
        raise ValueError("api_url must be provided via argument or HUAWEI_API_URL")
    if not token:
        raise ValueError("token must be provided via argument or HUAWEI_TOKEN")
    # The Huawei MaaS / model-call APIs have varied request shapes across
    # deployments. Try several common payload shapes until one succeeds.
    candidate_payloads = [
        {"input": input_text},
        {"inputs": input_text},
        {"instances": [input_text]},
        {"prompt": input_text},
        {"messages": [{"role": "user", "content": input_text}]},
    ]

    last_err: Exception | None = None
    for p in candidate_payloads:
        try:
            return call_huawei_model(api_url=api_url, token=token, payload=p, timeout=30)
        except Exception as e:
            last_err = e
            # try next shape
    # If all shapes failed, raise the last exception for caller to handle
    if last_err:
        raise last_err
    return {"text": "no-payload-tried"}
