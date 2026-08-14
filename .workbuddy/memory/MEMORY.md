# 项目长期笔记：新员工培训 AI 助手

## 目标
给入职新人做一个手机浏览器直接打开就能提问的 AI 助手，回答基于内部「新员工培训」资料库 + 实时联网核验的时效性信息。

## 架构
- 后端 `app.py`（Flask）：BM25 检索（`kb/text`，jieba 分词）+ SerpAPI 联网核验（`SEARCH_ENGINE=baidu`）+ DeepSeek 流式生成带出处回答。
- 前端 `static/index.html`：移动端优先对话页。
- 部署目标：**Render.com**（免费云，跑 Python 后端；CloudStudio 仅支持纯静态无法满足）。配置见 `Procfile` / `render.yaml` / `requirements.txt`。

## 知识库
- 来源：workbuddy.cn 资料库「新员工培训」空间（spaceId `obj0gboWcbKCS6OI3nrxWj`），下载 45 节点，抽取 14 篇文本 / 96 片段到 `kb/text/`。
- 抽取脚本 `kb/extract_text.py`、下载脚本 `kb/download_kb.py`。

## 关键约定
- API Key 存于 `.env`（已被 `.gitignore` 忽略），**切勿提交到 git**。本地用 `_load_local_env()` 手写解析；Render 用平台环境变量注入。
- 联网核验：SerpAPI 优先，未配置则回退百度/搜狗免费搜索（云服务器 IP 可能被反爬）。

## 上线待办
1. 用户 `git push` 到 GitHub。
2. Render 连仓库部署，填 `DEEPSEEK_API_KEY`、`SEARCH_API_KEY` 环境变量。
3. 拿到 `https://xxx.onrender.com` 发新员工群。
