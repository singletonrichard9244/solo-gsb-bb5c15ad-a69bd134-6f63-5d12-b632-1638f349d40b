"""FastAPI 应用入口。"""
from fastapi import FastAPI

from .models import SimulateRequest, SimulateResponse
from .simulator import simulate

app = FastAPI(
    title="多层配额原子试算 API",
    version="1.0.0",
    description=(
        "按时间顺序模拟令牌桶连续补充；仅当桶链上所有桶余额充足时原子扣减，"
        "否则全部保持不变。交互式文档见 /docs。"
    ),
)


@app.get("/health", summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/simulate", response_model=SimulateResponse, summary="多层配额原子试算")
def simulate_endpoint(payload: SimulateRequest) -> SimulateResponse:
    return simulate(payload)
