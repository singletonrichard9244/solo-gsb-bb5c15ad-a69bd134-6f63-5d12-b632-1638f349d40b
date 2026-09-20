"""令牌桶连续补充 + 桶链原子扣减模拟器。"""
from __future__ import annotations

from dataclasses import dataclass

from .models import BucketSnapshot, RequestResult, SimulateRequest, SimulateResponse

EPS = 1e-9  # 浮点比较容差
NDIGITS = 6  # 输出余额保留小数位


@dataclass
class _BucketState:
    capacity: float
    refill_rate: float
    balance: float
    last_update: float

    def refill(self, now: float) -> None:
        """按经过时间连续补充，余额封顶 capacity。"""
        if now > self.last_update:
            self.balance = min(
                self.capacity,
                self.balance + (now - self.last_update) * self.refill_rate,
            )
            self.last_update = now


def simulate(payload: SimulateRequest) -> SimulateResponse:
    """按时间顺序逐条试算：先补充，再原子判定扣减。"""
    states = {
        b.id: _BucketState(
            capacity=b.capacity,
            refill_rate=b.refill_rate,
            balance=b.capacity,  # 初始满桶
            last_update=0.0,
        )
        for b in payload.buckets
    }

    results: list[RequestResult] = []
    for index, req in enumerate(payload.requests):
        chain = [(bid, states[bid]) for bid in req.buckets]

        # 1) 链上各桶连续补充至请求时刻
        for _, st in chain:
            st.refill(req.timestamp)
        before = {bid: round(st.balance, NDIGITS) for bid, st in chain}

        # 2) 原子判定：仅当链上所有桶余额充足才扣减，否则全部保持不变
        limiting_id, poorest = min(chain, key=lambda item: item[1].balance)
        allowed = poorest.balance + EPS >= req.amount
        if allowed:
            for _, st in chain:
                st.balance -= req.amount

        after = {bid: round(st.balance, NDIGITS) for bid, st in chain}
        results.append(
            RequestResult(
                index=index,
                timestamp=req.timestamp,
                amount=req.amount,
                allowed=allowed,
                limiting_bucket=None if allowed else limiting_id,
                buckets={
                    bid: BucketSnapshot(before=before[bid], after=after[bid])
                    for bid, _ in chain
                },
            )
        )
    return SimulateResponse(results=results)
