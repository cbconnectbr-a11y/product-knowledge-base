#!/usr/bin/env python3
"""
产品客服智能问答生成

为指定 SKU 生成中葡双语客服问答，填入多客知识库模版（xlsx）。
该问答库应用于多个销售平台，答案不含任何平台名。

流程（两步走，最大化条数）：
1. 生成（葡语）：q_pt / variants_pt / a_pt / source —— 紧凑，能塞更多条
2. 补充一轮：基于已覆盖问题，再挖未覆盖的不同问题
3. 核查：ML与内部冲突标【⚠️数据不一致】、政策类换通用模板、无依据标【待核实】、剔除平台名
4. 翻译：补 q_cn / variants_cn / a_cn（分批，避免截断）

数据源：knowledge_entries(真实问答) + products(产品信息+feishu_raw_data基础信息白名单) + 可选ML页面

用法：
    python3.13 scripts/generate_product_qa.py --sku CBC004-452 [--ml-file path] [--no-verify]
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openpyxl import Workbook
from scripts.utils import get_supabase_client
from bot.rag import _get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 导入用列（前3列，葡语）+ 审核用列（中文/来源/标记，导入前可删除）
TEMPLATE_HEADERS = [
    "买家问题名称", "买家可能问法", "答案",                # 1-3 导入用（葡语）
    "问题名称(中文)", "可能问法(中文)", "答案(中文参考)",   # 4-6 审核用
    "数据来源", "核查标记",                               # 7-8 审核用
]
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "duoke_generated"

# 政策类（运费/时效/退换货/保修）通用模板：直接、积极、平台中性，不甩"看产品页"。
POLICY_TEMPLATE_PT = (
    "Oferecemos garantia contra defeitos de fabricação e suporte pós-venda. "
    "Em caso de dúvida sobre frete, prazo de entrega, troca ou devolução, "
    "fale conosco que ajudaremos você o mais rápido possível."
)
POLICY_TEMPLATE_CN = (
    "我们提供制造缺陷保修及售后支持。如对运费、物流时效、退换货有疑问，"
    "请直接联系我们，我们会尽快为您处理。"
)

# feishu_raw_data 中可用于买家答案的“基础信息”白名单（原始字段名 -> 展示标签）。
# 仅取买家相关字段；成本/采购/供应商/库存/开发员等敏感字段一律不取。
BASIC_INFO_WHITELIST = {
    "一级品牌": "品牌",
    "商品材质": "材质",
    "商品用途": "用途",
    "功率": "功率",
    "单位": "销售单位",
    "装箱数": "每箱数量",
    "商品包材": "包装材质",
    "电器类型": "电器类型",
    "认证类型": "认证类型",
    "认证号码": "认证编号",
    "需要认证": "是否需认证",
    "商品一级目录": "一级类目",
    "商品二级目录": "二级类目",
    "商品三级目录": "三级类目",
    "申报品名(中文)": "品名(中文)",
    "申报品名(英文)": "品名(英文)",
    "主SKU中文名称": "主SKU中文名",
    "商品备注": "商品备注(颜色/尺寸/零件清单)",
}

ANSWER_STYLE = (
    "【回复风格】直接给出答案、只陈述事实本身。"
    "**禁止**任何把买家甩给页面的搪塞措辞（consulte a página do produto / verifique o anúncio 等）；"
    "**禁止**在答案里加来源引用尾巴（如 'conforme a ficha técnica' / 'conforme especificado na página' / "
    "'na página do produto' / 'no anúncio' / 'conforme a descrição'）——来源只写进 source 字段，答案不出现；"
    "**禁止**出现任何平台名（Mercado Livre/Shopee/美客多/Amazon 等）。"
    "信息确凿就直接答；确实没有的信息才保守说明。"
)


def _flatten(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("text") or v.get("name") or "").strip()
    if isinstance(v, list):
        return " ".join(_flatten(x) for x in v).strip()
    return str(v).strip()


def build_basic_info(product: dict) -> str:
    raw = product.get("feishu_raw_data") or {}
    lines = []
    for key, label in BASIC_INFO_WHITELIST.items():
        val = _flatten(raw.get(key))
        if val and val not in ("0", "0.00", "否", "无", "--"):
            lines.append(f"- {label}：{val}")
    return "\n".join(lines) if lines else "（无额外基础信息）"


def fetch_product(client, sku: str) -> dict | None:
    r = (
        client.table("products")
        .select("sku,name_cn,name_en,brand,category,features,description,manual_files,feishu_raw_data")
        .eq("sku", sku)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def get_manual_content(product: dict) -> str:
    """尝试提取说明书 PDF/Word 正文（需飞书应用具备 drive 下载权限）。失败返回空串。"""
    mf = product.get("manual_files")
    if not mf or not isinstance(mf, dict) or not mf.get("link"):
        return ""
    try:
        import os
        import lark_oapi as lark
        from scripts.extract_manual import extract_manual_content
        lc = lark.Client.builder().app_id(os.environ["FEISHU_APP_ID"]).app_secret(os.environ["FEISHU_APP_SECRET"]).build()
        content = extract_manual_content(mf, lc) or ""
        if content.strip():
            logger.info(f"说明书提取成功：{len(content)} 字")
        else:
            logger.warning("说明书提取为空（可能仍无 drive 权限）")
        return content.strip()
    except Exception as e:
        logger.warning(f"说明书提取失败：{e}")
        return ""


def fetch_history(client, sku: str, limit: int) -> list[dict]:
    r = (
        client.table("knowledge_entries")
        .select("title,content,source_type,status")
        .eq("sku", sku)
        .eq("status", "approved")
        .limit(limit)
        .execute()
    )
    return r.data or []


def _loads_with_salvage(raw: str, key: str) -> list:
    """解析 {key:[...]} 的 JSON；被截断时抢救出已完成的对象。"""
    try:
        return json.loads(raw).get(key, [])
    except json.JSONDecodeError:
        cut = raw.rfind("}")
        if cut != -1:
            try:
                arr = json.loads(raw[: cut + 1] + "]}").get(key, [])
                logger.warning(f"JSON 被截断，已抢救出 {len(arr)} 条")
                return arr
            except json.JSONDecodeError:
                pass
        raise


def _sources_block(product: dict, history: list[dict], ml_content: str) -> str:
    manual = product.get("manual_files") or {}
    manual_text = manual.get("text", "") if isinstance(manual, dict) else ""
    hist_lines = []
    for i, h in enumerate(history):
        hist_lines.append(f"[{i+1}] {(h.get('title') or '').strip()} | {(h.get('content') or '').strip()[:700]}")
    hist_block = "\n".join(hist_lines) if hist_lines else "（暂无历史客服记录）"
    ml_block = ml_content.strip() if ml_content.strip() else "（本次未提供产品页面抓取）"
    manual_full = (product.get("_manual_content") or "").strip()
    manual_section = f"\n\n=== 源2c 说明书正文（安装/使用步骤权威来源）===\n{manual_full[:4000]}" if manual_full else ""
    return f"""=== 源1 产品页面（买家可见规格以此为权威）===
{ml_block}

=== 源2a 内部产品信息 ===
产品中文名：{product.get('name_cn') or ''}
英文名：{product.get('name_en') or ''}
卖点 features：
{product.get('features') or '（无）'}
描述 description：
{product.get('description') or '（无）'}
说明书：{manual_text or '（无）'}

=== 源2b 产品基础信息（重点用于基础信息类问答）===
{build_basic_info(product)}

=== 源3 真实客服历史（{len(history)} 条；忽略其中平台名）===
{hist_block}{manual_section}"""


GEN_SYSTEM = f"""你是跨境电商客服知识库专家。为一个产品生成「尽可能多、尽可能细」的客服问答（QA），用于多平台 AI 自动回复买家。

【数据源】源1 产品页面（买家可见规格权威）；源2a 内部产品信息；源2b 产品基础信息（品牌/材质/用途/类目/认证/包装/单位等，**重点用于基础信息类问答**）；源3 真实客服历史（仅取“问什么”，忽略平台名）。

【生成策略：尽量多、尽量细】
- 每条 QA 只聚焦一个具体点，**不要**把多个事实塞进一条。
- 系统化穷举所有维度：每项技术参数、每种保护、每类适用/不适用对象、包装内每个配件、每个认证、常见故障、电压/频率/兼容性；以及**基础信息**：品牌、材质、用途、产品类别、认证(类型/编号)、包装材质、销售单位、每箱数量等——每项单独成条。
- **【重点】使用与安装类（买家高频）**：必须充分覆盖——如何使用（como usar / como funciona）、如何安装/组装（como instalar / como montar，尽量拆成分步骤）、安装/使用中的注意事项与禁忌（cuidados, o que evitar, precauções）、首次使用准备、连接方式与极性、维护保养与清洁、收纳。优先取材于说明书要点、描述/卖点、客服历史里的真实问答。**步骤类信息若数据里没有，仍要生成该问题，但答案保守说明并标待核实，方便人工照说明书补。**
- 真实历史里的问题各自独立成条，保留真实问法。
- **至少生成 40 条**，有多少有效信息就尽量拆多少条，但**严禁为凑数编造**。

{ANSWER_STYLE}

【铁律·防编造】只能用数据源中明确出现的事实；**严禁推算/换算/估计**；没有依据的信息保守说明、不编。
【来源优先级（冲突时）】买家可见规格(功率/尺寸/电压等)以**产品页面**为准；**配件清单/数量/安装步骤/搭建以说明书(源2c)为准**；两者都没有再用内部信息。冲突时取权威源的值，并在 a_cn 注明差异（如「（内部数据：14）」）。

【每条字段】q_pt（葡语问题）、variants_pt（6~10 种葡语问法，优先取自历史真实表述）、a_pt（葡语答案，直接作答）、source（信息来源简短中文，如“页面参数表/内部基础信息/内部描述/客服历史/说明书”，多源用+连接）。

【输出】严格 JSON：{{"qa":[{{"q_pt":"...","variants_pt":["..."],"a_pt":"...","source":"..."}}]}}。只输出 JSON。"""


def generate_qa(sku: str, product: dict, history: list[dict], ml_content: str) -> list[dict]:
    client, model = _get_client()
    user = f"产品 SKU：{sku}\n\n{_sources_block(product, history, ml_content)}\n\n请生成尽可能多、尽可能细（含丰富基础信息类）的 QA，输出 JSON。"
    logger.info(f"[生成] 调用 LLM ({model})…")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": user}],
        temperature=0.4, max_tokens=8000, response_format={"type": "json_object"},
    )
    return _loads_with_salvage(resp.choices[0].message.content.strip(), "qa")


def generate_more(sku: str, product: dict, history: list[dict], ml_content: str, covered: list[str]) -> list[dict]:
    """补充一轮：基于已覆盖问题，挖未覆盖的不同问题。"""
    client, model = _get_client()
    covered_block = "\n".join(f"- {q}" for q in covered)
    user = (
        f"产品 SKU：{sku}\n\n{_sources_block(product, history, ml_content)}\n\n"
        f"=== 已覆盖的问题（不要重复）===\n{covered_block}\n\n"
        f"请基于数据源，**补充至少 15 条上面没覆盖到的、不同角度的新问题**（同样遵守防编造与回复风格），输出 JSON。"
    )
    logger.info("[补充] 再挖一轮未覆盖问题…")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": user}],
        temperature=0.6, max_tokens=8000, response_format={"type": "json_object"},
    )
    return _loads_with_salvage(resp.choices[0].message.content.strip(), "qa")


def _norm(q: str) -> str:
    return re.sub(r"[\s\?？。.!！,，]+", "", (q or "").lower())


def dedupe(qa_list: list[dict]) -> list[dict]:
    seen, out = set(), []
    for qa in qa_list:
        k = _norm(qa.get("q_pt", ""))
        if k and k not in seen:
            seen.add(k)
            out.append(qa)
    return out


def verify_qa(qa_list: list[dict], product: dict, history: list[dict], ml_content: str) -> list[dict]:
    """核查：只返回需改动条目 {i, flag, a_pt}。"""
    if not qa_list:
        return qa_list
    client, model = _get_client()
    for qa in qa_list:
        qa.setdefault("flag", "")
    qa_for_check = [{"i": i, "q_pt": qa.get("q_pt", ""), "a_pt": qa.get("a_pt", "")} for i, qa in enumerate(qa_list)]
    system = f"""你是严格的客服问答事实核查员。给你数据源与一批 QA，逐条核查。

规则（按序判断）：
1. **政策类**（运费/物流时效/退换货/保修/退款）→ a_pt 替换为：{POLICY_TEMPLATE_PT}；flag="【通用模板·待补充政策】"。
2. **计数/清单**（USB 口数、配件件数等）与源不符 → 改成源里的正确值。例：内部写“1个USB”就只能说 1 个。
3. 某事实**任何源都无依据**（含推算/平台默认值）→ 删除或软化，flag="【待核实】"。
4. **权威源与内部冲突**：页面/说明书 与 内部数据不一致时（如内部14根地钉、说明书16根；内部850W、页面1000W）→ a_pt 用权威源(页面/说明书)的值，flag="【⚠️数据不一致 内部:X / 权威:Y】"。配件清单/数量/安装步骤以说明书为准。
5. **平台中性 & 直接作答**：若 a_pt 含平台名、“consulte a página/verifique o anúncio”等搪塞措辞、或“conforme a ficha técnica/na página/no anúncio/conforme a descrição”等来源引用尾巴 → 去掉，改为直接陈述事实的表述。
6. 无需改动 → 不返回。

**只返回需改动的条目**：{{"items":[{{"i":原序号,"flag":"...","a_pt":"..."}}]}}。只输出 JSON。"""
    user = f"{_sources_block(product, history, ml_content)}\n\n=== 待核查 QA ===\n{json.dumps(qa_for_check, ensure_ascii=False)}"
    logger.info(f"[核查] {len(qa_list)} 条…")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0, max_tokens=8000, response_format={"type": "json_object"},
    )
    try:
        items = json.loads(resp.choices[0].message.content.strip()).get("items", [])
    except json.JSONDecodeError as e:
        logger.warning(f"核查 JSON 解析失败，跳过核查：{e}")
        return qa_list
    by_i = {it.get("i"): it for it in items if isinstance(it, dict)}
    for i, qa in enumerate(qa_list):
        it = by_i.get(i)
        if not it:
            continue
        if it.get("a_pt"):
            qa["a_pt"] = it["a_pt"]
        qa["flag"] = (it.get("flag") or "").strip()
    logger.info(f"[核查] 标记 {sum(1 for q in qa_list if q.get('flag'))} 条")
    return qa_list


def translate_qa(qa_list: list[dict], chunk: int = 15) -> list[dict]:
    """翻译步：补 q_cn / variants_cn / a_cn（分批避免截断）。"""
    if not qa_list:
        return qa_list
    client, model = _get_client()
    system = """你是中葡翻译。把每条 QA 的葡语字段准确翻译成中文，供内部审核。
输入每条含 i / q_pt / variants_pt / a_pt。输出 JSON：{"items":[{"i":原序号,"q_cn":"...","variants_cn":["..."],"a_cn":"..."}]}，
variants_cn 与 variants_pt 一一对应。只输出 JSON。"""
    for start in range(0, len(qa_list), chunk):
        batch = qa_list[start:start + chunk]
        payload = [
            {"i": start + j, "q_pt": qa.get("q_pt", ""), "variants_pt": qa.get("variants_pt", []), "a_pt": qa.get("a_pt", "")}
            for j, qa in enumerate(batch)
        ]
        logger.info(f"[翻译] 第 {start+1}-{start+len(batch)} 条…")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            temperature=0.1, max_tokens=8000, response_format={"type": "json_object"},
        )
        try:
            items = json.loads(resp.choices[0].message.content.strip()).get("items", [])
        except json.JSONDecodeError:
            logger.warning("翻译批次 JSON 解析失败，跳过该批")
            continue
        by_i = {it.get("i"): it for it in items if isinstance(it, dict)}
        for idx, qa in enumerate(batch):
            it = by_i.get(start + idx)
            if not it:
                continue
            qa["q_cn"] = it.get("q_cn", "")
            qa["variants_cn"] = it.get("variants_cn", [])
            qa["a_cn"] = it.get("a_cn", "")
    return qa_list


_CITATION_RE = re.compile(
    r"[,，]?\s*(conforme\s+(a\s+|o\s+)?(descrição|ficha\s+técnica|especifica[çc][ãa]o)[^.。;；]*"
    r"|conforme\s+especificado\s+na\s+p[áa]gina[^.。;；]*"
    r"|na\s+p[áa]gina\s+do\s+produto"
    r"|no\s+an[úu]ncio)\b",
    re.IGNORECASE,
)


def strip_citations(text: str) -> str:
    """去掉答案里的来源引用尾巴（来源信息单独放在 source 列）。"""
    if not text:
        return text
    cleaned = _CITATION_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.。,，])", r"\1", cleaned)
    return cleaned.strip()


def sanitize_filename(text: str, maxlen: int = 30) -> str:
    text = re.sub(r'[\\/:*?"<>|\n\r\t]', "", text or "").strip()
    return text[:maxlen]


def write_xlsx(sku: str, product: dict, qa_list: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(TEMPLATE_HEADERS)
    for qa in qa_list:
        variants_pt = "\n".join(v.strip() for v in (qa.get("variants_pt") or []) if v.strip())
        variants_cn = "\n".join(v.strip() for v in (qa.get("variants_cn") or []) if v.strip())
        a_cn = (qa.get("a_cn") or "").strip()
        ws.append([
            (qa.get("q_pt") or "").strip(),
            variants_pt,
            strip_citations((qa.get("a_pt") or "").strip()),
            (qa.get("q_cn") or "").strip(),
            variants_cn,
            f"[{sku}] {a_cn}",
            (qa.get("source") or "").strip(),
            (qa.get("flag") or "").strip(),
        ])
    name = sanitize_filename(product.get("name_cn") or "")
    out_path = OUTPUT_DIR / f"{sku}_{name}.xlsx"
    wb.save(out_path)
    return out_path


def write_verification_md(sku: str, product: dict, qa_list: list[dict]) -> Path:
    from datetime import datetime

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conflicts = [q for q in qa_list if "数据不一致" in (q.get("flag") or "")]
    todo = [q for q in qa_list if "待核实" in (q.get("flag") or "")]
    policy = [q for q in qa_list if "通用模板" in (q.get("flag") or "")]
    flagged = len(conflicts) + len(todo) + len(policy)
    lines = [
        f"# {sku} 待核验清单", "",
        f"- 产品：{product.get('name_cn') or ''}",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 问答总数：{len(qa_list)} | 需核验：{flagged}（数据不一致 {len(conflicts)} · 待核实 {len(todo)} · 政策模板 {len(policy)}）",
        "",
    ]

    def block(title, items):
        lines.append(f"## {title}（{len(items)} 条）")
        lines.append("")
        if not items:
            lines.append("（无）\n")
            return
        for n, q in enumerate(items, 1):
            lines.append(f"{n}. **{q.get('q_pt','')}** — {q.get('q_cn','')}")
            lines.append(f"   - 标记：{q.get('flag','')} | 来源：{q.get('source','')}")
            lines.append(f"   - 答案(PT)：{q.get('a_pt','')}")
            lines.append(f"   - 中文：{q.get('a_cn','')}")
            lines.append("")

    block("⚠️ 数据不一致（链接 vs 内部，需确认以哪个为准）", conflicts)
    block("🔶 待核实（缺乏来源依据，需人工补充或确认）", todo)
    block("📋 政策类（通用模板，需补充本店具体政策）", policy)
    lines += [
        "## ❗ 重点人工复核提示", "",
        "- **计数/数量类**（USB 口数、配件件数等）：AI 核查不可靠，请对照产品原始信息逐条确认。",
        "- xlsx 第 8 列「核查标记」可在 Excel 中筛选审核；前 3 列为导入用，后 5 列导入前可删除。",
        "",
    ]
    out_path = OUTPUT_DIR / f"{sku}_待核验.md"
    out_path.write_text("\n".join(lines))
    return out_path


def process_sku(sku, client=None, ml_content="", use_manual=True, max_history=50,
                max_rounds=4, do_verify=True, do_supplement=True):
    """完整管线处理一个 SKU，返回 (out_path, md_path, 条数)。供单跑与批量复用。"""
    client = client or get_supabase_client()
    product = fetch_product(client, sku)
    if not product:
        raise ValueError(f"products 表中找不到 SKU={sku}")
    # 无显式 ml_content 时，尝试读取预抓取的页面文件 data/duoke_generated/ml_{sku}.md
    if not ml_content:
        ml_file = OUTPUT_DIR / f"ml_{sku}.md"
        if ml_file.exists():
            ml_content = ml_file.read_text()
    if use_manual:
        product["_manual_content"] = get_manual_content(product)
    history = fetch_history(client, sku, max_history)
    logger.info(f"SKU={sku} | 历史 {len(history)} 条 | 页面={'有' if ml_content else '无'} | 说明书={'有' if product.get('_manual_content') else '无'}")

    qa_list = dedupe(generate_qa(sku, product, history, ml_content))
    logger.info(f"[生成] {len(qa_list)} 条")
    if do_supplement:
        for rnd in range(1, max_rounds + 1):
            covered = [q.get("q_pt", "") for q in qa_list]
            more = generate_more(sku, product, history, ml_content, covered)
            merged = dedupe(qa_list + more)
            added = len(merged) - len(qa_list)
            qa_list = merged
            logger.info(f"[补充第{rnd}轮] 新增 {added} 条 → 共 {len(qa_list)} 条")
            if added < 5:
                break
    if do_verify:
        qa_list = verify_qa(qa_list, product, history, ml_content)
    qa_list = translate_qa(qa_list)

    out_path = write_xlsx(sku, product, qa_list)
    md_path = write_verification_md(sku, product, qa_list)
    return out_path, md_path, len(qa_list)


def main():
    parser = argparse.ArgumentParser(description="生成产品客服双语问答（多客模版）")
    parser.add_argument("--sku", required=True, help="产品 SKU，如 CBC004-452")
    parser.add_argument("--max-history", type=int, default=50, help="最多读取多少条历史记录")
    parser.add_argument("--ml-file", default="", help="预抓取的产品页面 markdown 文件路径（可选）")
    parser.add_argument("--no-verify", action="store_true", help="跳过核查")
    parser.add_argument("--no-supplement", action="store_true", help="跳过补充轮")
    parser.add_argument("--max-rounds", type=int, default=4, help="最多补充几轮（每轮挖未覆盖问题，新增<5则停）")
    parser.add_argument("--use-manual", action="store_true", help="提取并使用说明书正文（需飞书应用 drive 下载权限）")
    args = parser.parse_args()

    ml_content = ""
    if args.ml_file and Path(args.ml_file).exists():
        ml_content = Path(args.ml_file).read_text()
        logger.info(f"已加载产品页面：{args.ml_file}（{len(ml_content)} 字）")

    out_path, md_path, n = process_sku(
        args.sku, ml_content=ml_content, use_manual=args.use_manual,
        max_history=args.max_history, max_rounds=args.max_rounds,
        do_verify=not args.no_verify, do_supplement=not args.no_supplement,
    )
    print(f"\n✅ 完成：{out_path}\n   问答条数：{n}\n   待核验清单：{md_path}")


if __name__ == "__main__":
    main()
