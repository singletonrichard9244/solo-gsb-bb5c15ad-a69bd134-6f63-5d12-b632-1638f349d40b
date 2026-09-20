"""Pydantic 数据模型与请求校验。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class BucketSpec(BaseModel):
    """令牌桶定义：容量 + 连续补充速率（令牌/秒），初始为满桶。"""

    id: str = Field(min_length=1, description="桶标识，需全局唯一")
    capacity: float = Field(gt=0, description="桶容量（最大令牌数），必须为正数")
    refill_rate: float = Field(gt=0, description="补充速率（令牌/秒），必须为正数")


class ConsumeRequest(BaseModel):
    """一次消耗请求：在 timestamp 时刻尝试从桶链中每个桶各扣 amount 个令牌。"""

    timestamp: float = Field(ge=0, description="请求时间戳（秒），请求序列须按时间非递减排列")
    amount: float = Field(gt=0, description="消耗量，必须为正数")
    buckets: list[str] = Field(min_length=1, description="桶链：需同时满足的桶 id 列表")

    @field_validator("buckets")
    @classmethod
    def _chain_no_duplicates(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("桶链中存在重复桶 id")
        return v


class SimulateRequest(BaseModel):
    """试算请求体：若干令牌桶 + 带时间戳的请求序列。"""

    buckets: list[BucketSpec] = Field(default_factory=list, description="令牌桶定义列表")
    requests: list[ConsumeRequest] = Field(default_factory=list, description="按时间非递减排列的消耗请求序列")

    @model_validator(mode="after")
    def _check_consistency(self) -> "SimulateRequest":
        # 校验重复桶定义
        ids = [b.id for b in self.buckets]
        if len(set(ids)) != len(ids):
            dups = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"桶定义存在重复 id: {dups}")
        # 校验未知引用
        known = set(ids)
        for idx, req in enumerate(self.requests):
            unknown = [b for b in req.buckets if b not in known]
            if unknown:
                raise ValueError(f"requests[{idx}] 引用了未定义的桶: {unknown}")
        # 校验时间顺序
        for prev, cur in zip(self.requests, self.requests[1:]):
            if cur.timestamp < prev.timestamp:
                raise ValueError("requests 必须按时间戳非递减排列")
        return self


class BucketSnapshot(BaseModel):
    """单个桶在扣减前后的余额。"""

    before: float = Field(description="扣减前余额（已补充至请求时刻）")
    after: float = Field(description="扣减后余额（拒绝时与 before 相同）")


class RequestResult(BaseModel):
    """单个请求的试算结果。"""

    index: int = Field(description="请求在输入序列中的下标")
    timestamp: float
    amount: float
    allowed: bool = Field(description="是否放行（链上所有桶余额均充足）")
    limiting_bucket: str | None = Field(
        default=None,
        description="限制桶：拒绝时为链上余额最少、导致拒绝的桶；放行时为 null",
    )
    buckets: dict[str, BucketSnapshot] = Field(description="桶链中各桶扣减前后余额")


class SimulateResponse(BaseModel):
    results: list[RequestResult]
