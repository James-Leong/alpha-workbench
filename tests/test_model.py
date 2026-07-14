#!/usr/bin/env python3
"""测试模型连通性 — 验证 model.py 能正确加载配置并调用 LLM。"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from alpha_workbench.agents.core.model import AlphaModel
from alpha_workbench.core.config import settings
from agno.models.message import Message

print("=" * 60)
print("模型连通性测试")
print("=" * 60)

# 打印配置（隐藏 key 前缀）
key_preview = settings.llm_api_key[:8] + "..." if settings.llm_api_key else "(empty)"
print("\n配置信息:")
print(f"  provider : {settings.llm_provider}")
print(f"  model_id : {settings.llm_model_id}")
print(f"  base_url : {settings.llm_base_url}")
print(f"  api_key  : {key_preview}")

# 创建模型实例
print("\n初始化 TgModel...")
model = AlphaModel()
print(f"  model.id = {model.id}")
print(f"  model.base_url = {model.base_url}")

# 发起测试请求
print("\n发送测试请求...")
try:
    response = model.response(
        messages=[
            Message(role="system", content="You are a helpful assistant. Reply in 1 sentence."),
            Message(role="user", content="你好，请回复一句话表示连接正常。"),
        ]
    )
    content = response.content if hasattr(response, "content") else str(response)
    print(f"\n✅ 连接成功！模型回复: {content}")
except Exception as e:
    print(f"\n❌ 连接失败: {type(e).__name__}: {e}")
    sys.exit(1)
