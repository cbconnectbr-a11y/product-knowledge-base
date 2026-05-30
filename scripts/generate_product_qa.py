#!/usr/bin/env python3
"""
产品客服智能问答生成

为指定 SKU 生成中葡双语客服问答，填入多客知识库模版（xlsx）。

数据源（两条生成轨，合并去重）：
- 轨 A：knowledge_entries 中该 SKU 的真实客服历史问答
- 轨 B：products 中该 SKU 的产品信息（name_cn / features / description / 说明书）

用法：
    python3.13 scripts/generate_product_qa.py --sku CBC004-452
    python3.13 scripts/generate_product_qa.py --sku CBC004-452 --max-history 50
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

# 政策类问题（运费/时效/退换货/保修）统一通用模板。多平台通用，不出现具体平台名。
POLICY_TEMPLATE_PT = (
    "Para informações sobre frete, prazo de entrega, garantia, troca ou devolução, "
    "consulte a página do produto ou entre em contato conosco. Teremos prazer em ajudar!"
)
POLICY_TEMPLATE_CN = (
    "关于运费、物流时效、保修、退换货等政策，请查看产品页面或联系我们，我们很乐意为您提供帮助！"
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


def _flatten(v) -> str:
    """把飞书字段值（可能是 str/list/dict）压成纯文本。"""
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


def build_prompt(sku: str, product: dict, history: list[dict], ml_content: str = "") -> tuple[str, str]:
    manual = product.get("manual_files") or {}
    manual_text = manual.get("text", "") if isinstance(manual, dict) else ""

    hist_lines = []
    for i, h in enumerate(history):
        title = (h.get("title") or "").strip()
        content = (h.get("content") or "").strip()[:400]
        hist_lines.append(f"[{i+1}] 标题: {title}\n    记录: {content}")
    hist_block = "\n".join(hist_lines) if hist_lines else "（暂无历史客服记录）"

    basic_info = build_basic_info(product)

    system_prompt = """你是跨境电商客服知识库专家。
你的任务：为一个产品生成「尽可能多、尽可能细」的客服智能问答（QA），用于 AI 自动回复买家。该问答库**应用于多个销售平台**。

【数据源，合并去重】
- 源1 产品页面（listing）：买家实际看到的页面信息（卖点、技术参数表、描述）。**买家可见规格以此为权威。**
- 源2a 内部产品信息：产品名/卖点/描述/参数/零件清单/说明书。
- 源2b 产品基础信息：品牌、材质、用途、类目、认证、包装、单位、装箱数等基础字段——**重点利用它生成丰富的“产品基础信息”类问答**。
- 源3 真实客服历史：买家真正问过的问题与真实问法（仅供提取“问什么”，其中的平台名一律忽略）。

【生成策略：尽量细、尽量多】
- 不要把多个事实塞进一条 QA。**每条 QA 只聚焦一个具体点**。
- 系统化穷举所有维度：每项技术参数、每种保护、每类适用/不适用对象、包装内每个配件、每个认证、安装每一步、常见故障、电压/频率/兼容性，以及**基础信息**：品牌、材质、用途、产品类别、认证(类型/编号)、包装材质、销售单位、每箱数量、产地用途等——每项可单独成条。
- 真实历史里的问题各自独立成条，保留真实问法。
- 有多少有效信息就尽量拆多少条（鼓励 40 条以上），但**严禁为凑数编造**。

【每条 QA 字段】
- q_pt：葡语问题标题（自然、地道 PT-BR）
- q_cn：q_pt 的中文翻译
- variants_pt：6~10 种葡语问法（优先取自历史/页面的真实表述）
- variants_cn：variants_pt 各条的中文翻译（一一对应）
- a_pt：葡语答案（完整、可直接回复买家；礼貌专业）
- a_cn：a_pt 的中文对照（供审核）
- source：该答案信息来源（简短中文），如「页面参数表 / 页面描述 / 内部基础信息 / 内部描述 / 内部卖点 / 客服历史 / 说明书 / 产品名称」，多来源用「+」连接

【铁律】
1. **多平台通用**：a_pt 与 a_cn **严禁出现任何具体平台名称**（如 Mercado Livre、Shopee、美客多、虾皮、Amazon 等）；需要时用中性表述（"na página do produto"、"no anúncio"、"entre em contato conosco"）。
2. **严防编造**：只能用数据源中**明确出现**的数字与事实；**严禁任何推算/换算/估计**（如由持续功率算峰值、由尺寸算重量）。
3. 多源**冲突**（如内部850W、页面1000W）：以**页面**为准，a_cn 末尾用「（内部数据：…）」注明。
4. 任何源都没有明确给出的信息：a_pt 保守表述，a_cn 以「【待核实】」开头。
5. 宁可少答、保守答，绝不编造。

【输出格式】
严格输出 JSON：{"qa": [{"q_pt":"...","q_cn":"...","variants_pt":["..."],"variants_cn":["..."],"a_pt":"...","a_cn":"...","source":"..."}, ...]}
只输出 JSON。"""

    ml_block = ml_content.strip() if ml_content.strip() else "（本次未提供产品页面抓取）"

    user_prompt = f"""产品 SKU：{sku}

=== 源1 产品页面（买家可见规格以此为权威）===
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
{basic_info}

=== 源3 真实客服历史（{len(history)} 条；忽略其中平台名）===
{hist_block}

请遵守系统提示的铁律，生成尽可能多、尽可能细（含丰富的基础信息类）的多语 QA，输出 JSON。"""

    return system_prompt, user_prompt


def generate_qa(sku: str, product: dict, history: list[dict], ml_content: str = "") -> list[dict]:
    client, model = _get_client()
    system_prompt, user_prompt = build_prompt(sku, product, history, ml_content)
    logger.info(f"调用 LLM ({model}) 生成问答…")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=8000,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    try:
        return json.loads(raw).get("qa", [])
    except json.JSONDecodeError:
        # 输出被截断时，截到最后一个完整对象并补全闭合
        cut = raw.rfind("}")
        if cut != -1:
            salvaged = raw[: cut + 1] + "]}"
            try:
                qa = json.loads(salvaged).get("qa", [])
                logger.warning(f"生成 JSON 被截断，已抢救出 {len(qa)} 条")
                return qa
            except json.JSONDecodeError:
                pass
        raise


def verify_qa(qa_list: list[dict], sku: str, product: dict, history: list[dict], ml_content: str) -> list[dict]:
    """第二遍核查：逐条回查来源，标记 flag 并修正答案。"""
    if not qa_list:
        return qa_list
    client, model = _get_client()
    manual = product.get("manual_files") or {}
    manual_text = manual.get("text", "") if isinstance(manual, dict) else ""
    sources = f"""=== 源1 美客多页面（买家可见规格权威）===
{ml_content.strip() or '（无）'}

=== 源2 内部产品信息 ===
名称：{product.get('name_cn') or ''}
features：{product.get('features') or '（无）'}
description：{product.get('description') or '（无）'}
说明书：{manual_text or '（无）'}"""

    qa_for_check = [
        {"i": i, "q_pt": qa.get("q_pt", ""), "a_pt": qa.get("a_pt", ""), "a_cn": qa.get("a_cn", "")}
        for i, qa in enumerate(qa_list)
    ]

    system_prompt = f"""你是严格的客服问答事实核查员。给你三个数据源和一批已生成的 QA，请逐条核查并修正。

对每条 QA，按以下规则处理，输出一个对象 {{"i": 原序号, "flag": "...", "a_pt": "...", "a_cn": "..."}}：

1. 若问题属于**政策类**（运费 frete / 物流时效 prazo・entrega / 退换货 devolução・troca / 保修 garantia / 退款 reembolso）：
   - a_pt 替换为：{POLICY_TEMPLATE_PT}
   - a_cn 替换为：{POLICY_TEMPLATE_CN}
   - flag = "【通用模板·待补充政策】"

2. 否则，核查 a_pt 里的每一个数字与事实是否能在三个源中**逐字找到**：
   - **【数量/计数/清单——最易出错，重点核查】**：USB 口数量、配件清单与件数、保护种类等，必须在源里逐字核对。
     · 例：内部写「带**1个** 5V 3.4A USB-A」→ 答案只能说 1 个 USB，写「2 个」就是错，必须改成 1。
     · 例：内部「零件清单：逆变器*1，线束*2，保险*2，固定螺帽*2，垫片*4」→ 配件必须严格照此列举，**不得新增**源里没有的项（如"汽车连接线"），也不得漏项。
     · 源里没有的配件/数量一律删除，并 flag = "【待核实】"。
   - 某事实在**任何源都找不到依据**（含推算/估计/平台默认值）→ 删除或软化该表述，flag = "【待核实】"。
   - 同一事实 **ML 与内部数据冲突**（如内部 850W、ML 1000W）→ a_pt 用 ML 的值，flag = "【⚠️数据不一致 内部:X / ML:Y】"（把 X、Y 换成真实数值）。
   - 全部事实都有据且无冲突 → flag = ""。

3.5 **平台中性**：若 a_pt 或 a_cn 出现任何具体平台名（Mercado Livre、Shopee、美客多、虾皮、Amazon 等），改写为中性表述（"na página do produto" / "产品页面"），此条也要返回。

3. a_cn 始终是修正后 a_pt 的中文对照（政策类用上面的中文模板）。不要加 [SKU] 前缀。

**只返回需要改动或标记的条目**（即 flag 非空、或答案需更正的）；无需改动的条目不要返回，节省篇幅。
严格输出 JSON：{{"items": [{{"i":原序号,"flag":"...","a_pt":"...","a_cn":"..."}}, ...]}}。只输出 JSON。"""

    user_prompt = f"""{sources}

=== 待核查 QA（{len(qa_for_check)} 条）===
{json.dumps(qa_for_check, ensure_ascii=False)}"""

    logger.info(f"核查 {len(qa_list)} 条…")
    for qa in qa_list:
        qa.setdefault("flag", "")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.0,
        max_tokens=8000,
        response_format={"type": "json_object"},
    )
    try:
        items = json.loads(resp.choices[0].message.content.strip()).get("items", [])
    except json.JSONDecodeError as e:
        logger.warning(f"核查结果 JSON 解析失败，跳过核查：{e}")
        return qa_list
    by_i = {it.get("i"): it for it in items if isinstance(it, dict)}
    for i, qa in enumerate(qa_list):
        it = by_i.get(i)
        if not it:
            continue
        if it.get("a_pt"):
            qa["a_pt"] = it["a_pt"]
        if it.get("a_cn"):
            qa["a_cn"] = it["a_cn"]
        qa["flag"] = (it.get("flag") or "").strip()
    n_flag = sum(1 for qa in qa_list if qa.get("flag"))
    logger.info(f"核查完成：{n_flag} 条被标记")
    return qa_list


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
        a_cn = qa.get("a_cn", "").strip()
        ws.append([
            qa.get("q_pt", "").strip(),                 # 1 买家问题名称(PT)
            variants_pt,                                 # 2 买家可能问法(PT)
            qa.get("a_pt", "").strip(),                  # 3 答案(PT)
            qa.get("q_cn", "").strip(),                  # 4 问题名称(中文)
            variants_cn,                                 # 5 可能问法(中文)
            f"[{sku}] {a_cn}",                           # 6 答案(中文参考)
            qa.get("source", "").strip(),                # 7 数据来源
            qa.get("flag", "").strip(),                  # 8 核查标记
        ])
    name = sanitize_filename(product.get("name_cn") or "")
    out_path = OUTPUT_DIR / f"{sku}_{name}.xlsx"
    wb.save(out_path)
    return out_path


def write_verification_md(sku: str, product: dict, qa_list: list[dict]) -> Path:
    """把需要人工核验的条目写入 markdown 清单，便于审核。"""
    from datetime import datetime

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conflicts = [q for q in qa_list if "数据不一致" in (q.get("flag") or "")]
    todo = [q for q in qa_list if "待核实" in (q.get("flag") or "")]
    policy = [q for q in qa_list if "通用模板" in (q.get("flag") or "")]
    flagged = len(conflicts) + len(todo) + len(policy)

    lines = [
        f"# {sku} 待核验清单",
        "",
        f"- 产品：{product.get('name_cn') or ''}",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 问答总数：{len(qa_list)} | 需核验：{flagged}（数据不一致 {len(conflicts)} · 待核实 {len(todo)} · 政策模板 {len(policy)}）",
        "",
    ]

    def block(title, items):
        lines.append(f"## {title}（{len(items)} 条）")
        lines.append("")
        if not items:
            lines.append("（无）")
            lines.append("")
            return
        for n, q in enumerate(items, 1):
            lines.append(f"{n}. **{q.get('q_pt','')}**")
            lines.append(f"   - 标记：{q.get('flag','')}")
            lines.append(f"   - 答案(PT)：{q.get('a_pt','')}")
            lines.append(f"   - 中文：{q.get('a_cn','')}")
            lines.append("")

    block("⚠️ 数据不一致（链接 vs 内部，需确认以哪个为准）", conflicts)
    block("🔶 待核实（缺乏来源依据，需人工补充或确认）", todo)
    block("📋 政策类（通用模板，需补充本店具体政策）", policy)

    lines += [
        "## ❗ 重点人工复核提示",
        "",
        "- **计数 / 数量类**（USB 口数、配件件数、保护种类数等）：AI 核查对这类不可靠，请对照产品原始信息**逐条确认**。",
        "- 表格中文参考列已带 `[SKU]` 与上述标记，可在 Excel 中按标记筛选审核。",
        "",
    ]
    out_path = OUTPUT_DIR / f"{sku}_待核验.md"
    out_path.write_text("\n".join(lines))
    return out_path


def main():
    parser = argparse.ArgumentParser(description="生成产品客服双语问答（多客模版）")
    parser.add_argument("--sku", required=True, help="产品 SKU，如 CBC004-452")
    parser.add_argument("--max-history", type=int, default=50, help="最多读取多少条历史记录")
    parser.add_argument("--ml-file", default="", help="预抓取的美客多页面 markdown 文件路径（可选）")
    parser.add_argument("--no-verify", action="store_true", help="跳过第二遍核查（默认执行核查）")
    args = parser.parse_args()

    ml_content = ""
    if args.ml_file:
        ml_path = Path(args.ml_file)
        if ml_path.exists():
            ml_content = ml_path.read_text()
            logger.info(f"已加载 ML 页面：{ml_path}（{len(ml_content)} 字）")
        else:
            logger.warning(f"ML 文件不存在，跳过：{ml_path}")

    client = get_supabase_client()
    product = fetch_product(client, args.sku)
    if not product:
        logger.error(f"products 表中找不到 SKU={args.sku}")
        sys.exit(1)

    history = fetch_history(client, args.sku, args.max_history)
    logger.info(f"SKU={args.sku} | 历史记录 {len(history)} 条 | ML={'有' if ml_content else '无'} | 开始生成")

    qa_list = generate_qa(args.sku, product, history, ml_content)
    logger.info(f"生成 {len(qa_list)} 条问答")

    if not args.no_verify:
        qa_list = verify_qa(qa_list, args.sku, product, history, ml_content)

    out_path = write_xlsx(args.sku, product, qa_list)
    md_path = write_verification_md(args.sku, product, qa_list)
    logger.info(f"已写出：{out_path}")
    logger.info(f"待核验清单：{md_path}")
    print(f"\n✅ 完成：{out_path}\n   问答条数：{len(qa_list)}\n   待核验清单：{md_path}")


if __name__ == "__main__":
    main()
