# -*- coding: utf-8 -*-
"""
新员工培训 AI 助手 - 后端服务
功能：
  1. 从 kb/text 加载内部培训资料，做 BM25 检索
  2. 对时效性/外部信息自动联网核验（DuckDuckGo lite）
  3. 调用 DeepSeek 流式生成带出处的回答
员工通过手机浏览器访问前端即可提问。
"""
import os, re, json, time
from flask import Flask, request, Response, send_from_directory
import requests
from bs4 import BeautifulSoup

try:
    import jieba
    jieba.setLogLevel(20)
    def tokenize(text):
        return [t for t in jieba.lcut(text) if t.strip()]
except Exception:
    def tokenize(text):
        return list(text)

from rank_bm25 import BM25Okapi

# 本地开发时从 .env 读取密钥（手写解析，不依赖第三方包，避免安装/网络问题）
# 用 setdefault，不会覆盖 Render 等平台已注入的环境变量
def _load_local_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)
_load_local_env()

BASE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE, "kb", "text")
STATIC_DIR = os.path.join(BASE, "static")

# ---- 配置（可通过环境变量覆盖）----
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
WEB_SEARCH_ENABLED = os.environ.get("WEB_SEARCH_ENABLED", "1") != "0"
# 生产级联网核验：配置 SerpAPI Key 后走结构化搜索（稳定）；未配置则尽力用免费搜索
SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY", "")
SEARCH_ENGINE = os.environ.get("SEARCH_ENGINE", "baidu")  # serpapi 引擎，baidu 对中文更友好
TOP_K = int(os.environ.get("TOP_K", "5"))
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "400"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "80"))

# ---- 知识库加载 ----
_chunks = []      # {id, source, text, tokens}
_bm25 = None

def load_kb():
    global _chunks, _bm25
    _chunks = []
    files = [f for f in os.listdir(KB_DIR) if f.endswith(".txt")]
    for f in files:
        source = os.path.splitext(f)[0]
        path = os.path.join(KB_DIR, f)
        with open(path, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        # 按段落切分，再按长度合并
        paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        buf = ""
        idx = 0
        for p in paras:
            if len(buf) + len(p) > CHUNK_SIZE and buf:
                _chunks.append({"id": f"{source}#{idx}", "source": source,
                                "text": buf, "tokens": tokenize(buf)})
                idx += 1
                buf = p
            else:
                buf = (buf + "\n" + p).strip()
        if buf:
            _chunks.append({"id": f"{source}#{idx}", "source": source,
                            "text": buf, "tokens": tokenize(buf)})
    corpus = [c["tokens"] for c in _chunks]
    _bm25 = BM25Okapi(corpus)
    print(f"[KB] 已加载 {len(files)} 篇文档, {len(_chunks)} 个片段")

def retrieve(query, k=TOP_K, max_per_source=2):
    # 懒加载：gunicorn 多 worker 时每个 worker 进程独立加载 KB，
    # 第一个接到请求的 worker 若尚未加载则补一次，避免空 KB 命中
    if _bm25 is None:
        load_kb()
        if _bm25 is None:
            return []
    scores = _bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    out = []
    per_source = {}
    for i in ranked:
        if scores[i] <= 0:
            continue
        c = _chunks[i]
        cnt = per_source.get(c["source"], 0)
        if cnt >= max_per_source:
            continue
        per_source[c["source"]] = cnt + 1
        out.append({"source": c["source"], "text": c["text"], "score": float(scores[i])})
        if len(out) >= k:
            break
    return out

# ---- 时效性判断 ----
TIME_WORDS = ["最新", "今天", "今日", "今年", "去年", "2024", "2025", "2026", "政策", "规定",
              "法规", "法律", "补贴", "个税", "社保", "公积金", "价格", "报价", "活动", "截止",
              "新闻", "上市", "财报", "利率", "标准", "通知", "公告", "趋势", "行情", "工资",
              "最低工资", "放假", "假期", "节日", "限时", "新规", "调整"]

def is_time_sensitive(q):
    return any(w in q for w in TIME_WORDS)

# ---- 联网搜索 ----
# 优先级：SerpAPI（结构稳定）> 百度免费搜索 > 搜狗免费搜索
def _search_serpapi(q, top=5):
    try:
        r = requests.get("https://serpapi.com/search.json",
                         params={"engine": SEARCH_ENGINE, "q": q, "api_key": SEARCH_API_KEY,
                                 "hl": "zh-cn", "gl": "cn"}, timeout=15)
        data = r.json()
        out = []
        for item in data.get("organic_results", [])[:top]:
            out.append({"title": item.get("title", ""),
                        "url": item.get("link") or item.get("url", ""),
                        "snippet": item.get("snippet", "")})
        return out
    except Exception as e:
        print(f"[WEB] serpapi 失败: {e}")
        return []

def _scrape_baidu(q, top=5):
    try:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
             "Accept-Language": "zh-CN,zh;q=0.9"}
        r = requests.get("https://www.baidu.com/s", params={"wd": q, "rn": str(top)}, headers=h, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for c in soup.select("div.c-container"):
            a = c.select_one("h3 a") or c.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = a.get("href", "")
            sn = c.select_one("div.c-abstract, span.content-right_8Zs40")
            snippet = sn.get_text(strip=True) if sn else ""
            if title:
                out.append({"title": title, "url": link, "snippet": snippet})
            if len(out) >= top:
                break
        return out
    except Exception as e:
        print(f"[WEB] baidu 失败: {e}")
        return []

def _scrape_sogou(q, top=5):
    try:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
        r = requests.get("https://www.sogou.com/web", params={"query": q}, headers=h, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for c in soup.select("div.vrwrap, div.rb"):
            a = c.select_one("h3 a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = a.get("href", "")
            sn = c.select_one("div.text-layout, p.str_info, div.fz-mid")
            snippet = sn.get_text(strip=True) if sn else ""
            if title:
                out.append({"title": title, "url": link, "snippet": snippet})
            if len(out) >= top:
                break
        return out
    except Exception as e:
        print(f"[WEB] sogou 失败: {e}")
        return []

def web_search(q, top=5):
    if not WEB_SEARCH_ENABLED:
        return []
    if SEARCH_API_KEY:
        res = _search_serpapi(q, top)
        if res:
            return res
        print("[WEB] serpapi 无结果，回退免费搜索")
    for fn in (_scrape_baidu, _scrape_sogou):
        try:
            res = fn(q, top)
            if res:
                return res
        except Exception as e:
            print(f"[WEB] 引擎异常: {e}")
    return []

# ---- 构建提示 ----
SYSTEM_PROMPT = """你是「泌园春AI小助手」，名字叫小黄。你的本职工作是帮助公司新人解答入职后的各类业务与流程问题。

# 身份与风格
- 姓名：小黄
- 职业背景：八年产品经理，有丰富的公司管理经验，对市场风向与风口具有敏锐的感受。
- 思维习惯：面对用户问题时，能发散不同方向的思维；除了解答问题本身，会主动给出下一步动作的专业建议与专业看法（比如「你可以先…再…」「这类情况建议同步报备…」「下一步可以考虑…」）。
- 对话风格：温柔、理性、专业。不浮夸、不说教、有同理心；用词平实但有分量。

# 回答规则
1. 优先依据【内部资料库】内容回答公司相关信息（品牌、产品、卖点、话术、办证流程、拓店标准等）。
2. 当问题涉及时效性/外部信息（如政策、法规、补贴、价格、活动、行业动态等），必须结合【联网检索结果】核验，并在回答中说明信息来源与日期；若联网结果与公司制度冲突，提示以公司内部最新通知为准。
3. 若内部资料库与联网结果都不足以回答，明确说明「暂未找到确切依据」，不要编造。
4. 回答要简洁、口语化、对新人友好，能分点给出操作步骤的尽量分点。
5. 回答末尾用「📚 参考来源」列出引用（文档名 / 网页标题与链接）。
6. 涉及具体流程（办证、拓店登记等）要给出清晰步骤。
7. 排版紧凑：Markdown 段落之间不要插空行，列表项之间只用一个换行；用 # / ## 区分层级即可，不要多余空行拉大间距。手机屏幕阅读，保持视觉紧凑。"""

def build_messages(q, kb_chunks, web_results):
    kb_block = "\n\n".join(
        f"【资料片段 {i+1}｜来源：{c['source']}】\n{c['text']}"
        for i, c in enumerate(kb_chunks)
    ) or "（内部资料库未检索到相关内容）"
    web_block = "\n\n".join(
        f"【网页 {i+1}｜{w['title']}】\n{w['snippet']}\n链接：{w['url']}"
        for i, w in enumerate(web_results)
    ) if web_results else "（未触发联网核验 / 联网未返回结果）"
    user = f"""# 内部资料库检索结果
{kb_block}

# 联网核验结果
{web_block}

# 新员工提问
{q}

请综合以上信息作答，遵守系统设定中的回答规则。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

# ---- DeepSeek 流式调用 ----
def stream_deepseek(messages):
    if not DEEPSEEK_API_KEY:
        return None
    try:
        r = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL, "messages": messages, "stream": True,
                  "temperature": 0.3},
            timeout=60, stream=True,
        )
        if r.status_code != 200:
            print(f"[DEEPSEEK] {r.status_code} {r.text[:200]}")
            return None
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
            except Exception:
                continue
    except Exception as e:
        print(f"[DEEPSEEK] 异常: {e}")
        return None

def fallback_answer(q, kb_chunks, web_results):
    """无 API Key 时的降级回答：直接呈现检索到的资料片段。"""
    parts = ["（演示模式：未配置 DeepSeek API Key，以下为检索到的内部资料片段）\n"]
    if kb_chunks:
        parts.append("📚 内部资料库相关片段：")
        for c in kb_chunks:
            parts.append(f"\n— 来源《{c['source']}》—\n{c['text']}")
    if web_results:
        parts.append("\n🌐 联网核验结果：")
        for w in web_results:
            parts.append(f"\n· {w['title']}\n  {w['snippet']}\n  {w['url']}")
    if not kb_chunks and not web_results:
        parts.append("未检索到相关内容，请换一种问法或联系培训负责人。")
    return "\n".join(parts)

# ---- SSE 工具 ----
def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

app = Flask(__name__, static_folder=STATIC_DIR)

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.route("/api/health")
def health():
    return json.dumps({"status": "ok", "kb_chunks": len(_chunks),
                       "web": WEB_SEARCH_ENABLED, "key": bool(DEEPSEEK_API_KEY)})

@app.route("/api/reload", methods=["POST"])
def reload_kb():
    """热重载知识库：kb/text 文件更新后（如本地同步后），无需重启服务即可生效。"""
    try:
        load_kb()
        return json.dumps({"status": "ok", "kb_chunks": len(_chunks)})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@app.route("/api/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    q = (data.get("question") or "").strip()
    if not q:
        return Response(sse("error", {"message": "请输入问题"}), mimetype="text/event-stream")

    kb_chunks = retrieve(q, TOP_K)
    need_web = is_time_sensitive(q) or (not kb_chunks)
    web_results = web_search(q) if need_web else []

    def gen():
        yield sse("sources", {"kb": [c["source"] for c in kb_chunks],
                              "web": [w["title"] for w in web_results],
                              "web_used": bool(web_results)})
        messages = build_messages(q, kb_chunks, web_results)
        if DEEPSEEK_API_KEY:
            gen_ = stream_deepseek(messages)
            if gen_ is None:
                # 调用失败降级
                for piece in fallback_answer(q, kb_chunks, web_results).split("\n"):
                    yield sse("token", piece + "\n")
            else:
                for delta in gen_:
                    yield sse("token", delta)
        else:
            for piece in fallback_answer(q, kb_chunks, web_results).split("\n"):
                yield sse("token", piece + "\n")
        yield sse("done", {"kb_count": len(kb_chunks), "web_count": len(web_results)})

    return Response(gen(), mimetype="text/event-stream")

if __name__ == "__main__":
    load_kb()
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
