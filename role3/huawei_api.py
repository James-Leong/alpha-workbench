"""Huawei model call helper for isolated Role3 development."""

from __future__ import annotations

import os
from typing import Any

import requests


def call_huawei_model(prompt: str, api_url: str | None = None, token: str | None = None) -> object:
    """Call a Huawei-compatible model endpoint.

    The endpoint shape may vary across deployments, so callers should treat the
    returned object as raw model response and parse it separately.
    """

    resolved_url = api_url or os.environ.get("HUAWEI_API_URL")
    resolved_token = token or os.environ.get("HUAWEI_TOKEN")
    if not resolved_url:
        raise ValueError("api_url must be provided via argument or HUAWEI_API_URL")
    if not resolved_token:
        raise ValueError("token must be provided via argument or HUAWEI_TOKEN")

    headers = {
        "Authorization": f"Bearer {resolved_token}",
        "Content-Type": "application/json",
    }
    payloads = [
        {"messages": [{"role": "user", "content": prompt}]},
        {"prompt": prompt},
        {"input": prompt},
        {"inputs": prompt},
        {"instances": [prompt]},
    ]

    last_error: Exception | None = None
    for payload in payloads:
        try:
            response = requests.post(resolved_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return response.text
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("No Huawei request payload was attempted.")
