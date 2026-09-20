# 多层配额原子试算 API

基于 Python + FastAPI + Pydantic 的令牌桶配额试算服务。`POST /simulate` 接收若干令牌桶定义与一组带时间戳、消耗量和桶链的请求，按时间顺序模拟连续补充；**仅当桶链上所有桶余额充足时才原子扣减，否则链上所有桶保持不变**。响应逐项给出放行结果、限制桶及各桶扣减前后余额。

## 快速启动（单条命令）

```bash
docker compose up --build
```

- 访问地址：**http://localhost:8000**
- 端口：**8000**（宿主机 8000 → 容器 8000）
- 交互式 API 文档（Swagger UI）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

依赖安装与启动初始化均已纳入容器（`Dockerfile` 中 `pip install -r requirements.txt`，`CMD` 启动 uvicorn），无需在宿主机安装任何 Python 依赖。

也可以使用 Compose v1：`docker-compose up --build`。

## 接口说明

### POST /simulate

**请求体**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `buckets[].id` | string | 桶标识，全局唯一 |
| `buckets[].capacity` | number > 0 | 桶容量（初始为满桶） |
| `buckets[].refill_rate` | number > 0 | 补充速率（令牌/秒），按经过时间连续补充，封顶容量 |
| `requests[].timestamp` | number ≥ 0 | 请求时间戳（秒），序列须按时间非递减排列 |
| `requests[].amount` | number > 0 | 本次消耗量 |
| `requests[].buckets` | string[] | 桶链：需同时满足的桶 id，链内不可重复 |

**响应**（`results` 与输入请求一一对应）

| 字段 | 说明 |
| --- | --- |
| `allowed` | 是否放行：链上所有桶余额均 ≥ 消耗量 |
| `limiting_bucket` | 限制桶：拒绝时为链上余额最少、导致拒绝的桶；放行时为 `null` |
| `buckets` | 桶链中各桶扣减前（`before`，已补充至请求时刻）与扣减后（`after`）余额；拒绝时两者相等 |

**校验规则**（违反即返回 HTTP 422，并附具体错误信息）

- 重复桶：桶定义 id 重复，或单个请求的桶链内 id 重复
- 非法参数：`capacity`、`refill_rate`、`amount` 非正数，`timestamp` 为负
- 未知引用：请求桶链引用了未定义的桶 id
- 请求序列时间戳未按非递减排列

### 示例

```bash
curl -s -X POST http://localhost:8000/simulate \
  -H 'Content-Type: application/json' \
  -d '{
    "buckets": [
      {"id": "api",  "capacity": 100, "refill_rate": 10},
      {"id": "user", "capacity": 50,  "refill_rate": 5}
    ],
    "requests": [
      {"timestamp": 0, "amount": 10, "buckets": ["api", "user"]},
      {"timestamp": 1, "amount": 95, "buckets": ["api"]},
      {"timestamp": 2, "amount": 30, "buckets": ["api", "user"]},
      {"timestamp": 3, "amount": 20, "buckets": ["user"]}
    ]
  }'
```

响应（节选，t=2 时 `api` 仅补充至 15，不足 30，整条链拒绝且所有桶保持不变）：

```json
{
  "results": [
    {"index": 0, "timestamp": 0, "amount": 10, "allowed": true,  "limiting_bucket": null,
     "buckets": {"api": {"before": 100, "after": 90}, "user": {"before": 50, "after": 40}}},
    {"index": 1, "timestamp": 1, "amount": 95, "allowed": true,  "limiting_bucket": null,
     "buckets": {"api": {"before": 100, "after": 5}}},
    {"index": 2, "timestamp": 2, "amount": 30, "allowed": false, "limiting_bucket": "api",
     "buckets": {"api": {"before": 15, "after": 15}, "user": {"before": 50, "after": 50}}},
    {"index": 3, "timestamp": 3, "amount": 20, "allowed": true,  "limiting_bucket": null,
     "buckets": {"user": {"before": 50, "after": 30}}}
  ]
}
```

## 项目结构

```
app/
  main.py        # FastAPI 入口：POST /simulate、GET /health
  models.py      # Pydantic 请求/响应模型与校验（重复桶、非法速率、未知引用等）
  simulator.py   # 令牌桶连续补充 + 桶链原子扣减模拟器
tests/
  test_simulate.py
Dockerfile          # 依赖安装与启动初始化纳入镜像
docker-compose.yml  # 单条命令启动，映射 8000 端口
requirements.txt
```

## 本地开发（可选，不依赖 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # 启动服务
pip install pytest httpx && pytest          # 运行测试
```
