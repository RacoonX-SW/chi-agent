# Import error 清理与可重复验证（2026-11-09）

范围：清理全量离线测试的 3 个既有 import error，并增加一条可重复的 Docker 验证命令。**只做测试/工具/文档；未跑真实 C、judge/Trial/发布；`official_reward=null`。**

## 1. 3 个 import error

| 测试 | 原因 | 处理 |
| --- | --- | --- |
| `test_dev_patient_adapter` | `chi_bench.conversation` 顶层导入 `anthropic`，dev 镜像未安装 | `HAVE_ANTHROPIC` 检查；缺失时 4 个测试明确 skip |
| `test_dev_patient_network` | 同上 | 缺失时 3 个测试明确 skip |
| `test_role_payer_projection` | `role_operator` 导入 `docker.types`；该测试按设计应在 controller 镜像运行 | `HAVE_DOCKER` 检查 `docker.types`；dev 镜像 skip，controller 镜像运行 |

没有安装新依赖，也没有改 vendor 或官方环境；skip 原因写入测试输出。

## 2. 可重复验证命令

新增 `scripts/dev_verify.sh`：

```bash
cd chi-agent
./scripts/dev_verify.sh
```

步骤：

1. 全量 `unittest discover`（dev 镜像，离线）；
2. `test_role_payer_projection`（controller 镜像，14 tests）；
3. bundle build 到临时目录；
4. `validate_bundle`；
5. `preflight --bundle-sha256` 并校验 `identity_verified`。

脚本默认要求工作树干净，`--allow-dirty` 可跳过检查；bundle 只写临时目录并在结束时删除。可用 `CHI_MODEL_DEPS_VOLUME`、`CHI_PDF_DEPS_VOLUME`、`CHI_DEV_IMAGE`、`CHI_CONTROLLER_IMAGE` 覆盖默认卷/镜像。

## 3. 结果

- 全量 dev：**781 tests / 37 skipped / 0 errors / 0 failures**；
- controller：`test_role_payer_projection` **14 passed**；
- `dev_verify.sh --allow-dirty` 通过：bundle `9fbc329c…`、identity `dbe143ec…`、preflight `identity_verified`；
- 测试/文档/dev 脚本不在 bundle 文件列表中，bundle 身份与 t023 通过时一致。

## 4. 边界

- `anthropic` 相关 7 个测试在 dev 镜像仍 skip；没有为此新增依赖或重建镜像。
- `test_role_payer_projection` 在 dev 镜像 skip，必须由脚本在 controller 镜像运行；单独跑 dev 全量不会覆盖它。
- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 旧 pending 保留，不重试、不清。
