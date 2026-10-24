# ToolAsset / ToolGroup / ToolAccess field dictionary (issue #27, reopened)

Single field source for the three records. Every field below is the issue's
field table entry verbatim; each maps to exactly one record field and one
SQLite column, and the frozen DDL (`data/record_schema.sql`) plus the parity
check refuse any drift. Later tasks consume these records — they do not
restate, rename or shadow them.

## Physical layout: three logical entities, six tables

| 表 | 主键/约束 | 职责 |
| --- | --- | --- |
| `tool_asset` | `tool_id` PK | 工具身份、名称、来源、安装入口 |
| `tool_release` | `(tool_id, version, platform)` 唯一 | 版本、平台、制品、摘要 |
| `tool_group` | `group_id` PK | 组身份与整体摘要 |
| `tool_group_member` | `(group_id, tool_id)` PK | 组内工具及专属 summary |
| `tool_group_member_alias` | `(group_id, tool_id, alias)` PK | 成员专属别名 |
| `tool_access` | `access_id` PK | 每个入口独立的 method、target、contract、summary |

`PRAGMA foreign_keys = ON` 强制:没有 `ToolAsset` 不能登记关联的
`ToolAccess`/成员/发行物;一个工具可以关联多个不同入口;每个入口必须
拥有独立的 `method`、`target`、`contract`;缺失必填字段直接失败。

## ToolAsset — 工具注册与资产来源

| 字段(issue 原文) | 记录字段 | 列 | 规则 |
| --- | --- | --- | --- |
| tool_id · 必填;全局工具主键,按登记值使用 | `ToolAsset.tool_id` | `tool_asset.tool_id` PK | 裸名或点式均按登记值;更名、版本、平台、分组及访问入口变化均不另生成工具身份 |
| name · 必填;工具标准名称 | `.name` | `name` NOT NULL | 非空 |
| provider · 必填;资产来源或准备方式 | `.provider` | `provider` CHECK | 公共定义列明:`uv`、`github-release`、`oci` |
| package · 可缺省;Python 工具包名 | `.package` | `package` NULL | uv 场景缺省时可采用 name;存登记值,不隐式改写 |
| versions · 必填;版本及对应资产子记录 | `.versions` | `tool_release` 行 | 子记录见下;同工具多版本多平台不分配新 tool_id |
| entrypoint · 必填;安装后可执行程序名称 | `.entrypoint` | `entrypoint` NOT NULL | 非空 |

### tool_release 子记录(versions 的每条资产)

| 字段(issue 原文) | 记录字段 | 列 | 规则 |
| --- | --- | --- | --- |
| version · 必填;实际工具版本 | `ToolAssetVersion.version` | `version` NOT NULL | 非空 |
| platform · 平台相关资产必填;明确的 OS/架构表示 | `.platform` | `platform_os`,`platform_arch` | 成对出现、成对非空;平台无关资产为 NULL;复用已有目标平台信息时按 os/arch 精确映射 |
| source · 必填;下载 URL、包标识或 OCI 地址 | `.source` | `source` NOT NULL | 非空 |
| digest_type · 必填;明确使用的摘要类型 | `.digest_type` | `digest_type` CHECK | 公共定义列明:`sha256` |
| digest · 必填;对应制品的摘要 | `.digest` | `digest` CHECK | sha256 时 64 位十六进制 |

本地安装记录通过 tool_id、版本、平台及摘要关联实际制品;本地路径不成为工具主键。

## ToolGroup — Agent 的发现入口

| 字段(issue 原文) | 记录字段 | 列 | 规则 |
| --- | --- | --- | --- |
| group_id · 必填;分组主键,支持原文示例 ci-security、ci-release | `ToolGroup.group_id` | `tool_group.group_id` PK | 按登记值 |
| summary · 必填;整组能力摘要 | `.summary` | `summary` NOT NULL | 非空 |
| members · 必填;该组的工具索引 | `.members` | `tool_group_member` 行 | 子记录见下 |

### 成员子记录

| 字段(issue 原文) | 记录字段 | 列 | 规则 |
| --- | --- | --- | --- |
| tool_id · 必填;关联 ToolAsset | `GroupMember.tool_id` | `tool_group_member.tool_id` FK | 外键强制存在 |
| summary · 必填;该工具在本组中的用途 | `.summary` | `summary` NOT NULL | 组内专属;同一工具在不同组各持其文 |
| aliases · 可为空;匹配别名、近义名称 | `.aliases` | `tool_group_member_alias.alias` | 成员专属表;**组级无别名列** |

成员 summary、aliases 保留在成员记录中:同一个 trivy 在 ci-security 描述漏洞及配置扫描,在 ci-release 描述 SBOM 生成。

## ToolAccess — 调用入口

| 字段(issue 原文) | 记录字段 | 列 | 规则 |
| --- | --- | --- | --- |
| access_id · 必填;唯一入口标识,支持 trivy.scan、trivy.sbom、trivy.cli | `ToolAccess.access_id` | `tool_access.access_id` PK | **按登记值使用**,不强制拼接 catalog_ref、entry_key、本机路径或参数 |
| tool_id · 必填;关联 ToolAsset | `.tool_id` | `tool_id` FK NOT NULL | 同一工具的多个入口使用同一 tool_id |
| method · 必填;dagger、uv、native、api | `.method` | `method` CHECK | 公共定义列明四值 |
| target · 必填;实际 Dagger Function、CLI 命令或 API 地址 | `.target` | `target` NOT NULL | 非空 |
| contract · 必填;调用参数、输入输出契约 | `.contract` | `contract` JSON 对象 NOT NULL | 复用已有 ToolSpec 或 Dagger 原生接口描述;每入口独立,单一 ToolSpec 契约不替代多个入口 |
| summary · 必填;入口执行什么操作 | `.summary` | `summary` NOT NULL | 非空 |

provider 描述资产来源,method 描述调用入口:由 uv 准备的 CLI 可以通过
Dagger 入口执行。工具身份、入口身份与契约内部身份之间只建立引用,
不强制新 tool_id 等于旧 ToolSpec 能力 ID。**全库无 `asset_id` 列**:
旧 asset_id 不成为与 tool_id 同义的第二个工具身份。

## Serialization, queries and storage

- `record_document(record)` / `record_from_document(document)`:严格往返
  (字段集精确,未知键拒绝);文档即记录,无平行摘要类型。
- `DiscoveryQuery` / `DiscoveryPage`:分页与过滤沿用既有界(limit 默认
  10,范围 1–50);页内条目就是三类记录的文档;诊断与查询错误独立于
  ToolResult 业务状态。
- `open_record_store(path=None)`:`data/` 是库的家——默认打开
  `data/records.sqlite3`;冻结 DDL 唯一权威在 `data/record_schema.sql`,
  种子数据在 `data/seed.sql`;临时/缓存/产物属于 `.cache/`、`.tmp/`、
  `.artifacts/`,不进 `data/`。

## Migration boundary (explicit)

- 旧能力 ID 与旧 asset_id 留在确有来源的旧契约/历史数据中,**不作为
  新工具主键**;新公共对象一律 tool_id / group_id / access_id。
- 旧格式读取/转换只存在于最外层的 `legacy_convert.py`,**临时代码**:
  旧组文档可转换(catalog_ref 丢弃),旧入口摘要因缺 method/target 给出
  明确「unsupported」结论;适配完成后该文件删除,记录层零兼容。
- 后续任务(#32 登记 B、#33 资产 C、#34 入口 D、#35 发现 E)以本交付
  为实施输入;发布过的任务文本不改写,冲突由其分支在本根上重建解决。
