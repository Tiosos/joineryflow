# JoineryFlow 可扩展架构设计与长期演进规划

> **状态：提案（Draft / 未批准）。** 本文是外部架构评审产出，**不是规则**。在团队接受之前，它不改变 `CLAUDE.md`（rulebook）和 Plan V1 的任何约束力。被接受的条目应分别落到 ADR、`CLAUDE.md` 与 Plan V1，而不是留在本文件里长期生效。
>
> **对象**：`Tiosos/joineryflow`（Python/FastAPI + Next.js 16，替换 FileMaker 的细木工生产系统）
> **依据**：对 `apps/api`、`apps/web`、`db/alembic`、`tests/` 的实地代码勘查（2026-10-27，HEAD = `main`，迁移 head `0089_variation_fields`）+ `CLAUDE.md`、`docs/REVIEW-2026-10.md`、Plan V1
> **定位**：给"下一步怎么走"的架构判断与可执行路线，不是通用最佳实践清单
>
> **与既有文档的关系**
> - 与 `CLAUDE.md`：本文只描述现状与建议，不新增硬规则。若本文与 `CLAUDE.md` 冲突，**以 `CLAUDE.md` 为准**，并把冲突上报（RULE ZERO）。
> - 与 Plan V1（`docs/plan-v1/`）：Plan V1 是**客户目标规格与路线图**，本文是**代码树的可演进性评估**。两者视角不同，不构成替代关系；建任何东西前仍须读 `ALIGNMENT.md` §3。
> - 与 `docs/REVIEW-2026-10.md`：那份是缺陷清单（已逐项处理），本文是结构性/长期议题。二者不重复。

---

## 0. 结论先行：六个要点

| # | 要点 | 一句话 |
| --- | --- | --- |
| **1** | **不要拆微服务，做"可拆而暂不拆"的模块化单体** | 107 张表高度内聚、`items` 是事实上的上帝表，拆服务会立刻撞上跨服务 join 与分布式事务；而 1690 个真库集成测试是单体最贵的资产，拆分会让它贬值一半 |
| **2** | **真正的风险不是性能，是"生产化缺失"** | 实测 1000 items 列表 137 ms、5000 items 715 ms，性能远未到瓶颈；但两个 Dockerfile 都是 dev 镜像（装 dev 依赖、非 multi-stage、root 运行），且**没有部署流水线、没有监控、没有备份** |
| **3** | **最脆的耦合是"用 SQL 字符串当接口"** | `row_types` 被 47 处调用点依赖，`open_orders_sql`、`FROM_VISIBLE` 被跨模块 import 后字符串拼接。类型检查、编译器都管不了它，只有测试能管——这是拆任何东西之前必须先消除的东西 |
| **4** | **缺 Application 层，业务规则粘在 HTTP 层** | `routes.py` 合计 9580 行且 `commit()` 全在 route 里。这导致规则无法被 worker / CLI / 后台任务复用，也意味着每多一个非 HTTP 入口就要重写一遍业务判断 |
| **5** | **把 outbox 从"搜索专用"升级为"系统级集成模式"** | 搜索已经用对了（DB 触发器写 outbox + 独立 worker + `FOR UPDATE SKIP LOCKED`），这是全项目唯一的真解耦范例，应推广到 PDF 生成、CV 导入、E3 数据迁移 |
| **6** | **把规矩从"文档"变成"CI 门禁"** | `CLAUDE.md` 323 条规则靠自律执行，而 AI 结对贡献了 43% 的提交（226 提交 / 25 天）。速度还会涨，护栏必须自动化才有意义 |

> **补充（目标为多客户 SaaS，已确认）**：多租户**不改变**上面第 1 条——租户数量多不等于要拆服务。但它新增一项**上线前必须完成**的 P0 工作：Meilisearch master key、单根文件存储、未鉴权的 `/public/stats` 这三处在单客户时可接受，多客户后即跨租户数据泄露（详见 §决策 5.2）。

---

## 1. 现状体检

### 1.1 客观规模

| 维度 | 实测值 |
| --- | --- |
| 后端 | `apps/api/app` 44 个模块目录、40,056 行 Python；`routes.py` 9,580 行、`queries.py` 13,829 行、`schemas.py` 4,486 行 |
| 数据库 | 89 个 Alembic 迁移（`0001`→`0089`）、约 **107 张表 + 5 个视图**，全部裸 DDL |
| 前端 | `apps/web` 300 个 TS/TSX、38,590 行、28 个 `page.tsx`；`useState` 896 处、`useEffect` 262 处 |
| 测试 | 157 个 `test_*.py`、**1690 个测试函数**，全部跑真 Postgres + 真迁移；`tests/e2e/` 有 **76 个 `*.spec.ts`**（实测 `ls`，⚠️ `CLAUDE.md:125` 记为 66，见 §7） |
| 交付 | 2 个 Dockerfile（均 dev 级）、1 个 `docker-compose.yml`（dev 级）、2 个 GitHub workflow（**0 个 deploy**） |
| 团队 | 3 位贡献者（117 / 97 / 12），其中 Claude 占 43% |

### 1.2 当前分层：两层半

```
HTTP routes.py  ──►  queries.py  ──►  Postgres (text() 裸 SQL)
     │                    │
     │ 业务规则 + commit   │ 跨模块 SQL 字符串片段共享
     └────────────────────┴──── 没有中间的 Application / Domain 层
```

- **0 个** `service.py` / `repo.py` / `models.py` / `router.py`；约定是 `routes.py + queries.py + schemas.py`
- **无 ORM 实体层**：`relationship` / `joinedload` / `declarative_base` 零命中，`app/db.py` 只有 `create_engine` + `sessionmaker`
- 事务边界在 route：`estimating/routes.py` 29 处 `commit()`、`items/routes.py` 14 处；辅助层只 flush 不 commit（`auth/audit.py:6-8` 有明确注释）

### 1.3 已经做对、不要动的事

这几项是真正的资产，重构时最容易误伤：

1. **搜索 outbox**（`0033_search_outbox`）：PL/pgSQL 触发器写 `search_outbox`，业务代码零侵入（app 内 `INSERT INTO search_outbox` 零命中）；worker 用 `FOR UPDATE SKIP LOCKED` 批量取，等 Meili 任务真成功才删行。**这是全项目唯一的真解耦范例。**
2. **Workspace 隔离 + 自动探针**：`workspace_scope.py` 集中提供 `project_in_workspace` / `user_in_workspace` / `vendor_in_workspace`；`test_workspace_isolation_probe.py` 遍历 `app.openapi()` 的 paths，**新增路由自动被覆盖，5xx 也算失败**。这是做多客户 SaaS 的真实基础。
3. **RBAC 真集中式**：`require_permission()` 工厂 + DB 驱动引擎，且用独立短事务避免被业务 rollback 波及（`rbac.py:20-28`）。
4. **文件存储有 Protocol 抽象**：`files/store.py:16-21`，注释已写明"S3 实现可平替，routes 不用改"。
5. **测试密度**：1690 个测试、真库真迁移、xdist 每 worker 独立库、downgrade 也有测试。远超同类项目，是所有重构的安全网。
6. **性能没有 N+1**：语句数在 14 items 和 1000 items 下完全一致。

### 1.4 五个结构性风险（按优先级）

| 级别 | 风险 | 证据 | 后果 |
| --- | --- | --- | --- |
| **P0** | 生产化缺口 | Dockerfile 装 dev 依赖、无 multi-stage、root 运行；`docker-compose.yml` 是 dev（`--reload`/源码挂载），且 `db` 带 `fsync=off`（虽有注释警告，但复用同一份 compose 就会踩中）；0 个 deploy workflow；grep `sentry\|prometheus\|grafana\|/metrics` 零命中；grep `pg_dump\|wal-g` 零命中 | 上线即事故；出事无据可查；数据无退路 |
| **P1** | SQL 字符串当接口 | `row_types.py` 被 24 个模块 import、47 处调用点；`notifications/queries.py:12` import 了 `tasks.queries.FROM_VISIBLE` 再 f-string 拼接；`home/queries.py:24-27` 一个文件拼 6 个模块的 SQL 片段 | 改一个列名会静默破坏别处；**拆服务时第一个断的就是它** |
| **P1** | 已存在循环依赖 | `orders/queries.py:31` ←→ `catalog/routes.py:26`，图上确认 `catalog ↔ orders` 成环，`orders/queries.py:212` 用函数内延迟 import 绕开 | 边界已破，无法按模块物理隔离 |
| **P2** | 缺 Application 层 | 业务规则 + `commit()` 在 route；`get_db` 只 `close()` 不显式 `rollback()`，靠连接关闭隐式回滚 | 规则无法被 worker/CLI 复用；异常路径的事务语义不显式 |
| **P2** | 前端无数据层、契约靠手写 | 21 个手写 `*-types.ts`（3,084 行）、无 OpenAPI 生成；`lib/api.ts` 的 `apiCall` 硬编码 `cache:"no-store"`，另有 3 份重复 fetch 封装；契约正确性靠 tsc + 76 个 e2e 兜底 | 后端改字段 → 前端静默错；重复取数无去重 |

---

## 2. 目标架构：有界上下文 + 可拆而暂不拆

### 2.1 分层目标

```
┌─ Interface 层 ─────────────────────────────────────────┐
│  routes.py  — 只做：鉴权、参数校验、调用用例、映射响应  │
└───────────────────────┬────────────────────────────────┘
┌─ Application 层（新增，本项目最大缺口）────────────────┐
│  use cases：业务规则、事务边界、编排、发领域事件        │
└───────────────────────┬────────────────────────────────┘
┌─ Domain / 数据访问 ────────────────────────────────────┐
│  queries.py（现有资产保留） + 显式的数据服务接口        │
└───────────────────────┬────────────────────────────────┘
┌─ Infrastructure ───────────────────────────────────────┐
│  Postgres / Meili / FileStore / outbox worker           │
└────────────────────────────────────────────────────────┘
```

**关键取舍**：不引入 ORM。现有 `text()` 裸 SQL 是团队已验证的性能优势（无 N+1、DB 时间 ≤37 ms）。补的是**结构**，不是**抽象**。

### 2.2 上下文地图（建议的边界划分）

| 上下文 | 现有模块 | 类型 | 演进策略 |
| --- | --- | --- | --- |
| **Item & Production**（核心域） | `items` `parts` `cutlists` `related_parts` `hardware_lines` | 核心 | 留在主库，绝不外迁 |
| **Project & Tracking**（核心域） | `projects` `areas` `order_tabs` `project_*` | 核心 | 同上 |
| **Estimating / Tender** | `estimating` `catalog`(部分) | 核心 | 先抽 Application 层，暂不拆 |
| **Procurement** | `orders` `purchase_orders` `procurement_v1` `suppliers` | 支撑 | 与 `catalog` 的环必须打破 |
| **Shop Floor / Cut Floor** | `shop_floor` `cut_floor` `qc` | 支撑 | 现场 kiosk，未来最可能需要离线/独立部署 |
| **Catalog** | `catalog` `cv` `importers` | 支撑 | 九张表不做统一（现有不变量，遵守） |
| **Search** | `search` + worker | 通用 | **已独立进程**，是拆分模板 |
| **Files / Printing** | `files` `printing` `shop_drawings` | 通用 | CPU 密集（PDF 3.3 s / 300 行），**最适合第一个拆出去** |

### 2.3 依赖规则（要能被 CI 检查，不能只写在文档里）

1. 上下文之间**只能**通过显式接口通信，禁止 import 对方的 `queries.py` 内部符号
2. 禁止 import 任何模块的 `_q_*` 私有文件
3. 通用层（`db` `auth` `files` `search`）不得反向依赖业务上下文
4. **先冻结、再收敛**：用 import-linter 把"当前状态"固化为基线契约，禁止新增违规，存量违规登记后逐个消灭

---

## 3. 扩展性设计的六个关键决策

### 决策 1：保持单体进程，但让它"随时可拆"

**理由**：峰值负载远低于实测的 5000 items / 715 ms（单 workspace 基线）。分布式系统的全部成本（网络失败、幂等、最终一致、链路追踪）现在换不来任何收益。

**注意**：目标是多客户 SaaS（已确认），但**租户数量多 ≠ 要拆服务**。多租户是数据与隔离问题，靠 §决策 5 解决；拆不拆服务是部署与团队问题。**不要因为要做 SaaS 就去拆微服务**——一家细木工公司的用量下，共享进程 + 强租户隔离是最优解。

**可拆的条件先备齐**（这些本身就有价值）：
- 所有跨上下文调用走显式接口，而非 SQL 字符串
- 所有写操作的事务边界收敛到 Application 层
- 所有跨上下文的副作用走 outbox，而非同步调用

### 决策 2：抽 Application 层，把业务规则从 HTTP 里救出来

按**变更频率**而非代码量排序试点：`estimating`（4591 行、已拆 facade）→ `orders` → `items`。

每步的验收标准：
- route 里不再出现 `db.commit()`
- 新增的用例函数可以在**不启动 HTTP** 的情况下被测试调用
- 1690 个测试全绿（这是硬性门槛）

### 决策 3：用"数据服务接口"消灭 SQL 字符串耦合

把 `row_types.joinery_items_only()`、`orders.queries.open_orders_sql`、`tasks.queries.FROM_VISIBLE` 这类被跨模块 import 的 SQL 片段，改成**归属方提供的显式函数**（如 `items.read.visible_items(...)`、`orders.read.open_orders(...)`），调用方拿到的是**数据**，不是**可拼接的 SQL 文本**。

- 收益：列名变更从"静默破坏 47 处"变成"编译期/导入期报错"
- 成本：中等。建议先在 `orders ↔ catalog` 这个已确认成环的一对上试点

### 决策 4：把 outbox 升级为系统级集成模式

`search_outbox` 的模式（触发器 → outbox 表 → 独立 worker → `SKIP LOCKED`）已经验证可用。推广到：

| 场景 | 现状 | 改后 |
| --- | --- | --- |
| 报价 PDF | 300 行 3.3 s、800 行 12 s，同步阻塞（已有 `0062` 缓存） | 异步生成 + 通知，缓存兜底 |
| CV 导入 | 3 阶段向导，同步 | 后台任务 + 进度查询 |
| E3 数据迁移 | CLI，dry run 靠回滚 | 复用同一任务表 |
| 通知 | 唯一写入点在 `comments/queries.py:328` 硬编码 INSERT | 领域事件 → outbox → 通知服务 |

注意：搜索 outbox 是**身份型**（只记 id，worker 反查）。通用任务 outbox 需要**载荷型**（记完整 payload），两者不要混用一张表。

### 决策 5：多租户——目标是 SaaS，先修三个真实的跨租户泄露点

**已确认目标是多客户 SaaS。** 好消息是 `workspace` 已经是事实上的租户，而且数据面基础比多数项目扎实：`workspace_scope.py` 集中提供 `project_in_workspace` / `user_in_workspace` / `vendor_in_workspace`（跨租户一律 404），`test_workspace_isolation_probe.py` 遍历 `app.openapi()` 的 paths——**新增路由自动被覆盖，5xx 也算失败**。这是全项目最成熟的工程资产，不要另起炉灶。

#### 5.1 隔离模型：保持 shared schema + `workspace_id`

| 方案 | 评价 |
| --- | --- |
| **shared schema + `workspace_id`**（现状） | ✅ 采纳。89 个迁移对所有租户原子生效；单客户数据量小；已有集中 helper + 自动 probe |
| schema-per-tenant | ❌ 现在上成本极高：107 张表只有 DDL、**无 ORM 元数据**，且每次迁移要遍历所有 schema |
| database-per-tenant | ❌ 同上，且连接管理复杂化 |

**只在出现明确信号时才迁移到独立库**：大客户合同要求物理隔离、单租户数据量让维护窗口不可接受、或需要租户级 PITR。为将来留门只需两件事：SQL 里不写死 schema 名、租户表上的 `workspace_id` 保持齐全（现状已满足）。

#### 5.2 三个必须修的跨租户泄露点（P0，与 Phase 0 生产化同期）

| # | 风险 | 证据 | 为什么单客户时能忍、多客户时不能 |
| --- | --- | --- | --- |
| **1** | **Meilisearch 用 master key** | `.env.example` 注释原话："The master key is also used as the api's key in dev; **scoped keys are out of scope for v1**"；隔离目前只靠应用层的 `build_filter`（`app/search/index.py:20-35`） | 应用层过滤是**唯一**防线，一处遗漏即全量泄露。多客户必须改用 Meilisearch **tenant token**，把 `workspace_id` 过滤下沉到搜索引擎侧，让"忘加过滤"变成"拿不到数据" |
| **2** | **文件存储是单根目录** | `FILE_STORE_ROOT=/uploads`（`docker-compose.yml`）；`files/store.py` 的 `LocalDiskStore` 无租户分层的强制约束 | 下载路由若校验不严即跨租户读文件。改为按 `workspace` 分片存储，且下载路由**强制**校验归属（不能只靠路径不可猜测） |
| **3** | **`GET /public/stats?workspace_slug=` 未鉴权** | `docs/REVIEW-2026-10.md` A4 已接受此风险（"知道或猜到 slug 就能读三个计数"） | 单客户时只是三个数字；多客户时意味着**任何人可枚举其他客户的项目数/供应商数**。要么让 slug 不可猜测 + 限流，要么在多客户上线前直接下线 |

#### 5.3 深度防御（Phase 2 评估，不要现在就上）

Postgres **RLS** 可作为应用层过滤之外的第二道防线：连接时 `SET LOCAL app.workspace_id`，策略为 `workspace_id = current_setting('app.workspace_id')`。

- 收益：把"忘记加 workspace 过滤"从数据泄露降级为查询报错
- 成本：需在每张租户表建策略；当前是单连接池单角色，需改造
- **建议**：先做一个模块的可行性验证再决定是否全量铺开。主防线仍是 `workspace_scope` + 自动 probe

#### 5.4 缺口清单

- [ ] workspace 自助开通与 onboarding（现在靠 `make seed`；`CLAUDE.md:137`、`seed_system_groups()` 需在开通流程里自动化，见 `CLAUDE.md:171`）
- [ ] 订阅 / 配额 / 计费模型
- [ ] **租户级备份与恢复**（当前全仓无 `pg_dump` / 无 PITR，shared schema 下至少要做到"按 workspace 导出 + 按 workspace 恢复"）
- [ ] 租户级数据导出（客户要带走数据）与删除（合同终止 / 合规）
- [ ] 租户级配置隔离（`workspace.at_risk_days` 已由 `0085` 建立，可沿此模式推广）

> **现成骨架**：E3 importer 已经在做"把一个 workspace 的数据灌进去"（`python -m app.importers.tracking_grid FILE.xlsx … --workspace-slug`，含 dry-run 回滚语义）。租户 onboarding 的导入可以直接复用它，不用从零写。

### 决策 6：前端补两件高回报的事

1. **OpenAPI → TS 类型生成**：21 个手写 `*-types.ts`（3,084 行）可直接生成，契约漂移从"靠 tsc 撞运气"变成"CI 报错"。后端已有 `app.openapi()`（probe 测试在用），基础现成。
2. **统一取数层**：262 处裸 `useEffect` + 3 份重复 fetch 封装 → 一个带去重/失效/错误规范的 hook 层。不必引入 TanStack Query（现有约束明确不用），自建薄层即可，但要**先统一到 `lib/api.ts`**。

---

## 4. 长期演进路线

### Phase 0 — 生产化（2–4 周，最高优先级）

| 项 | 动作 | 验收 |
| --- | --- | --- |
| 生产镜像 | Dockerfile 改 multi-stage、非 root、装 prod 依赖、`next build` + `next start` / gunicorn+uvicorn workers | 镜像不含 dev 依赖，进程非 root |
| 配置分离 | `docker-compose.yml`（dev）与 `docker-compose.prod.yml` 彻底分开，**移除 `fsync=off` 等** | dev 危险参数不出现在任何 prod 配置里 |
| 部署流水线 | 新增 deploy workflow（构建 → 推镜像 → 迁移 → 健康检查 → 回滚） | 一键可回滚 |
| 备份 | PITR（WAL 归档）+ 定期 `pg_dump`，**并演练恢复** | 恢复演练成功一次（没演练过的备份不算备份） |
| 可观测性 | 结构化日志 + 错误上报 + `/metrics` + 关键告警 | 出事故能在 5 分钟内定位 |
| **多租户安全三件事** | Meili 换 tenant token；文件存储按 workspace 分片 + 下载路由强制校验；`/public/stats` 加固或下线 | 拿 A 租户的凭据取不到 B 租户的任何数据（写成自动化测试，不是人工验证） |

**这一步不做完，后面所有架构工作都没有承载体。**（多租户三件事属于"上线前必须完成"，不是"可以后补"——见 §决策 5.2。）

### Phase 1 — 边界与契约（1–2 个月）

- OpenAPI → TS 类型生成上线，删掉手写 types
- import-linter 落地，冻结当前依赖图为基线契约
- **打破 `catalog ↔ orders` 环**（唯一确认的循环依赖）
- 消灭 SQL 字符串跨模块共享：先在 `orders↔catalog` 试点，再推 `row_types` / `FROM_VISIBLE` / `open_orders_sql`
- 前端 fetch 封装统一到 `lib/api.ts`
- **workspace 自助开通 + onboarding**（替换 `make seed` 的手工流程，`seed_system_groups()` 自动化）+ 订阅 / 配额表与迁移

### Phase 2 — 抽出 Application 层（2–4 个月）

- 按 `estimating` → `orders` → `items` 顺序抽用例层
- `commit()` 全部移出 route，引入显式 unit-of-work
- `get_db` 显式 `rollback()`，去掉"靠连接关闭隐式回滚"
- PDF / CV 导入 / E3 迁移后台化（通用任务 outbox）
- 通知改为领域事件驱动
- **租户级数据导出 / 删除**（合同终止与合规），复用 E3 importer 的导入骨架做反向能力
- RLS 可行性验证（一个模块试点，验证后再决定是否全量铺开，见 §决策 5.3）

### Phase 3 — 选择性拆分（条件触发，6–12 个月）

**只在出现明确信号时才拆**，不要按时间表拆：

| 触发信号 | 拆什么 | 为什么它最安全 |
| --- | --- | --- |
| PDF / 优化计算成为 CPU 瓶颈 | `printing` `cut_floor` 的 `/optimise` | 天然无状态、纯函数、无共享写 |
| 搜索吞吐成为瓶颈，或需要搜索独立扩缩容 | `search` + worker | 已经是独立进程，模式现成（**注意**：第二家客户本身**不是**拆分的触发条件，见 §决策 5.1） |
| Shop Floor kiosk 需要现场离线能力 | `shop_floor` `qc` | 读写集与主流程交集小 |
| 团队规模增长到需要独立发布 | 见 §2.2 上下文边界 | 边界已在 Phase 1 收敛 |

**拆分前必须先完成的前置**：补上 SQLAlchemy Core 的 `Table` 元数据定义（现在 107 张表只有 DDL、无模型元数据）。没有元数据，"按模块拆库"无从做起。

---

## 5. 工程治理：让护栏自动生效

项目速度极高（226 提交 / 25 天，AI 结对占 43%）。`CLAUDE.md` 的 323 条规则目前靠自律执行——这在高速 + AI 参与下不可持续。建议把规则逐条转成 CI 门禁：

| 现有规则（文档） | 转成（CI） |
| --- | --- |
| "workspace 隔离 everywhere" | 已有 ✅ 自动 probe（标杆做法，保持） |
| "动态 SQL 列名必须走 allow-list" | 已有 ✅ `test_sql_set_columns.py` |
| "PATCH 必须 `no_null`" | 可补：扫描所有 PATCH schema 字段 vs 列 NOT NULL |
| "读 items 必须带 `not_deleted`" | 已有 ✅ `test_items_deleted_filter.py` |
| **模块依赖规则** | **缺失 ❌** — 引入 import-linter |
| **契约漂移** | **缺失 ❌** — OpenAPI → TS 生成 + diff 检查 |
| **迁移安全** | 部分：有 downgrade 测试，可补"禁止破坏性 DDL"检查（Q435 要求数据保全） |

**ADR 建议**：`docs/adr/` 记录关键决策（为什么不拆微服务、为什么不上 ORM、outbox 选型），避免每季度重新辩论一遍。

---

## 6. 风险登记

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 89 迁移 / 107 表无 ORM 元数据 | 阻断未来一切拆库动作 | Phase 2 内补 Core `Table` 定义（只读用途即可） |
| `items` 被 10 个模块硬依赖，锁语义被 7 个模块复制 | 改动 blast radius 大 | 锁检查收敛为单一入口，其余通过接口调用 |
| AI 结对 43% 提交 + 规则靠自律 | 架构腐化速度快于人工 review | 护栏 CI 化（§5）是第一优先级治理项 |
| 单 Postgres + 单 Meili 无高可用 | 单点故障，且多客户后影响所有租户 | Phase 0 至少要有 PITR 与演练过的恢复 |
| **Meili master key + 单根文件存储 + 未鉴权 `/public/stats`** | **多客户上线后即跨租户数据泄露** | §决策 5.2，与 Phase 0 同期修完 |
| shared schema 下租户级恢复粒度粗 | 一个租户误删数据要全库回滚 | 先做"按 workspace 导出/恢复"（可复用 E3 importer），不要为此提前拆库 |
| e2e 分 2 shards 且 `main` 上为 required check | 一个 spec 依赖另一个 spec 留下的数据时会在分片下失败 | `CLAUDE.md:152-153` 已规定"自造数据、不放回"，遵守即可；本文不再把它列为风险 |

---

## 附：本次判断所依据的关键证据

| 结论 | 证据位置 |
| --- | --- |
| 两层半、无 service 层 | `apps/api/app/**/routes.py` 9,580 行含 `commit()`；`find -name "service*.py"` → 0 |
| 无 ORM | `app/db.py:5-6`；`relationship\|joinedload\|declarative_base` 零命中 |
| 循环依赖 | `apps/api/app/orders/queries.py:31` ↔ `apps/api/app/catalog/routes.py:26` |
| SQL 字符串接口 | `app/row_types.py`（24 个模块 import / 47 调用点）；`app/notifications/queries.py:12`；`app/home/queries.py:24-27` |
| outbox 范例 | `db/alembic/versions/0033_search_outbox.py:86-127`；`app/search/worker.py:44-49` |
| 事务边界在 route | `app/auth/audit.py:6-8` 注释；`estimating/routes.py` 29 处 `commit()` |
| dev 级 Dockerfile | `apps/web/Dockerfile`（`pnpm install \|\| true`、无 build）、`apps/api/Dockerfile`（`pip install -e ".[dev]"`） |
| 无运维资产 | `sentry\|prometheus\|grafana\|/metrics\|pg_dump\|wal-g` 全仓零命中；`.github/workflows` 仅 2 个且无 deploy |
| 性能基线 | `docs/REVIEW-2026-10.md` §C（1000 items → 137 ms / 1.5 MB；5000 items → 715 ms；PDF 300 行 → 3.3 s） |

---

## 7. 待澄清（RULE ZERO：不自行取舍）

1. **`tests/e2e/` 的 spec 数量**：实测 `ls tests/e2e/*.spec.ts` = **76**，而 `CLAUDE.md:125` 写 **66**。二者必有一错，需确认后统一。（`CLAUDE.md` §1 对 pytest 文件数注明"counts drift, so none are recorded here"——e2e 这一行是否也应去掉具体数字，请定。）
2. **生产部署的目标形态未定**：本文 Phase 0 假设"容器 + 一条流水线"，但项目没有说明是自托管（客户机房）还是云托管。这直接决定备份（PITR vs 托管快照）与可观测性选型，**需先确认**。
3. ~~是否要走向多客户 SaaS~~ — **已确认：目标是 SaaS。** §决策 5 已按此展开（隔离模型、三个泄露点、缺口清单）。由此产生的新问题：
   - 首个非 Hartwood 客户预计何时上线？这决定 Phase 0 的"多租户安全三件事"是现在做还是可以排到后面——**如果 3 个月内会有第二家客户，它就是 P0 里的第一件事**。
   - 计费模型：按席位、按项目数，还是按 workspace 一口价？这决定配额表怎么设计。
   - 数据驻留：客户数据是否要求留在特定地区（如只在澳大利亚境内）？这决定托管选型，且与 §7 第 2 条（生产部署目标形态）叠加。
