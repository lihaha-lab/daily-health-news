# 每日健康新闻 / Daily Health News

面向中国大陆普通读者的可配置健康新闻简报工作流，重点关注心脑血管健康。
项目采集公开新闻，按来源和关键词筛选，使用本地 Ollama 或可选的云端
模型整理简报，并可发布到飞书文档、飞书多维表格及企业微信。

> 当前仍在迭代。来源可用性、筛选质量和自动发布权限需要在实际环境中
> 持续核对；不要把自动生成的健康内容当作医疗建议。

## 工作流

`来源采集 -> 筛选与去重 -> 排序与摘要 -> 本地简报 -> 飞书/企业微信发布`

健康主题的来源、关键词、读者定位和编辑规则放在
[`config/topic-packs/health/`](config/topic-packs/health/)。复制该目录并修改配置，
可以建立财经、体育等其他主题，不必改动核心采集流程。

## 本地运行

需要 Docker Compose。首次运行：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

打开 `http://localhost:8899`。在 `.env` 中设置登录密码和飞书凭证；
不要将 `.env` 上传到 Git。健康主题的版本化默认计划为新西兰时间每天
11:00，管理页中的定时设置会覆盖这个默认值。

## 调试与发布

| 环节 | 管理页 | 当前能力 |
| --- | --- | --- |
| 来源 | `/admin/sources` | 增删、启停、关键词规则及抓取状态 |
| 筛选 | `/admin/digest-settings` | 时效、条数、语言和全局排除词 |
| 模型 | `/admin/llm` | 模型及提供方配置 |
| 定时 | `/admin/schedule` | 时区、运行时间和自动运行开关 |
| 诊断 | `/admin/logs` | 每次运行的日志和错误 |

首页的 `Run digest` 会运行全流程，**可能直接写入真实飞书目标**。
逐环节预览、人工确认和单独重跑的页面尚未完成；调试时请先关闭定时。
发布到统一飞书文档需要配置 `FEISHU_DIGEST_DOCUMENT_ID` 和文档编辑权限；
不配置时会使用旧的按月建文档逻辑。飞书新闻表格是单独的发布目标。

详细配置、迁移和当前限制见
[`docs/daily-health-news.md`](docs/daily-health-news.md)。

## 数据与安全

`.env`、SQLite 数据库、新闻缓存、简报、日志和备份均留在本机的项目
绑定目录中，不进入 Git。迁移时请单独安全备份这些目录与 `.env`；
仅克隆仓库不会恢复历史简报或飞书发布记录。

## 开源来源

本项目基于 [CondenseIt](https://github.com/wildlifechorus/condenseit)
修改，遵循原项目的 [MIT 许可证](LICENSE)。原项目说明保存在
[`docs/upstream-readme.md`](docs/upstream-readme.md)。
