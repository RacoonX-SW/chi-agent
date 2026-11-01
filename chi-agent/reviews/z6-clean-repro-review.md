# Z6 干净依赖安装与独立包预检：实际证据

更新：2026-11-01。基于合并后 main `dac6080`，在 Docker/Python 3.12 中从空依赖卷安装固定锁，再对 release 包执行无 Key、无网络的 preflight。**未启动 world、模型或 Trial。**

## 1. 身份

| 项目 | 值 |
| --- | --- |
| 源码 commit | `dac60805a1b6beac85a1e38b1652cf46a78bd351` |
| release 包 | `runs/z6-clean-repro/release`（忽略目录，不入库） |
| bundle manifest SHA | `95302f2252b838b6bd272f1ba205272c47e208eb86ea80cfedfc2d2387c6f664` |
| release manifest SHA | `eb88a9c325a673e22431e782dc483101ec3af28b2c91f13e0297a229ebc4bf8b` |
| 新 model 卷 | `chi-z6-clean-model-20261101-v1` |
| 新 PDF 卷 | `chi-z6-clean-pdf-20261101-v1` |
| 环境 | `chi-agent-dev:latest`，Linux aarch64，Python 3.12.15 |

## 2. 实际命令

构建 release（禁网、只读源码）：

```bash
docker run --rm --network none -v "$PWD:/source:ro" \
  -v "$PWD/runs/z6-clean-repro:/out:rw" -w /tmp chi-agent-dev:latest \
  /opt/venv/bin/python /source/scripts/go_chi_release.py build \
  --target /out/release --source-root /source \
  --source-commit "$(git -C .. rev-parse HEAD)"
```

空卷安装固定锁（安装需要网络；锁带 hash）：

```bash
docker volume create chi-z6-clean-model-20261101-v1
docker volume create chi-z6-clean-pdf-20261101-v1
docker run --rm \
  -v "$PWD/runs/z6-clean-repro/release/package/requirements-model.lock:/lock:ro" \
  -v chi-z6-clean-model-20261101-v1:/deps \
  -e UV_CACHE_DIR=/tmp/uv-cache -e UV_LINK_MODE=copy chi-agent-dev:latest \
  uv pip install --target /deps --require-hashes -r /lock
docker run --rm \
  -v "$PWD/runs/z6-clean-repro/release/package/requirements-pdf.lock:/lock:ro" \
  -v chi-z6-clean-pdf-20261101-v1:/deps \
  -e UV_CACHE_DIR=/tmp/uv-cache -e UV_LINK_MODE=copy chi-agent-dev:latest \
  uv pip install --target /deps --require-hashes -r /lock
```

无 Key、禁网 preflight（包 + 固定 vendor + 新依赖卷）：

```bash
docker run --rm --network none --read-only --tmpfs /tmp \
  -v "$PWD/runs/z6-clean-repro/release/package:/package:ro" \
  -v "$PWD/vendor/chi-bench:/package/vendor/chi-bench:ro" \
  -v chi-z6-clean-model-20261101-v1:/model-deps:ro \
  -v chi-z6-clean-pdf-20261101-v1:/pdf-deps:ro \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/package/vendor/chi-bench/src \
  -w /tmp chi-agent-dev:latest /usr/local/bin/python -S \
  /package/scripts/go_chi_entry.py preflight \
  --bundle-sha256 95302f2252b838b6bd272f1ba205272c47e208eb86ea80cfedfc2d2387c6f664
```

## 3. 结果

preflight 返回 `status=identity_verified`，关键字段：

- `identity_sha256 = d4651acbd5c987fd6c1098359cb8259d4f423dd8cb93bab5f413c97d65f32633`
- bundle manifest SHA 与 release 一致 `95302f…`
- SDK：`openai-agents 0.13.6`、`openai 2.36.0`、`httpx 0.28.1`、`httpcore 1.0.9`、`mcp 1.30.0`、`jsonschema 4.26.0`、`pydantic 2.14.1`、`pydantic-core 2.50.1`
- PDF：`pypdf 6.20.1`，lock/wheel/package hash 均通过
- upstream：`clean=true`，commit `4444a07fa68a4f1623f841a292a54e284fc8e7f7`
- `official_reward=null`

## 4. 证明与不证明

**证明**：

- 从空 model/PDF 卷、固定带 hash 的锁可以安装出 preflight 认可的依赖；
- release 包在独立容器中能完成 bundle/config/依赖/upstream/PDF 身份校验；
- 预检不需要 Key、不需要网络、不启动 world/模型。

**不证明**：

- 官方 world/MCP 可连接、真实 Harbor Trial 生命周期、模型调用、日志/trajectory/context；
- 状态目录持久化、owned 资源清理、超时/取消后的残留；
- 官方判分、临床正确性或业务效果；
- 其他架构/不同 Docker 主机的可复现性。

## 5. 下一步

真实 Z4/Z6 前，需要用户一次性确认：任务/角色、候选与 release SHA、资源/镜像 hash、B/C 次数、用途、停止条件、费用/账目边界。本文只是干净依赖安装与 preflight 证据，不是运行授权。
