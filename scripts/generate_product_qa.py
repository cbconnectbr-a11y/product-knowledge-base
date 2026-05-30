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

TEMPLATE_HEADERS = ["买家问题名称", "买家可能问法", "答案", "答案(中文参考·审核用)"]
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "duoke_generated"

# 政策类问题（运费/时效/退换货/保修）统一通用模板，避免编造具体天数/金额
POLICY_TEMPLATE_PT = (
    "Para informações sobre frete, prazo de entrega, garantia, troca ou devolução, "
    "consulte a página do produto no Mercado Livre ou entre em contato conosco pelo chat. "
    "Teremos prazer em ajudar!"
)
POLICY_TEMPLATE_CN = (
    "关于运费、物流时效、保修、退换货等政策，请查看美客多产品页面或通过聊天联系我们，"
    "我们很乐意为您提供帮助！"
)


def fetch_product(client, sku: str) -> dict | None:
    r = (
        client.table("products")
        .select("sku,name_cn,name_en,brand,category,features,description,manual_files")
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

    system_prompt = """你是跨境电商（巴西美客多 Mercado Livre）客服知识库专家。
你的任务：为一个产品生成「尽可能多、尽可能细」的客服智能问答（QA），用于 AI 自动回复巴西买家。

【三个数据源，合并去重】
- 源1 美客多页面（ML）：买家实际看到的 listing 信息（卖点、技术参数表 ficha técnica、描述）。**买家可见规格以此为权威。**
- 源2 产品信息（products）：内部产品名/卖点/描述/参数/零件清单/说明书。
- 源3 真实客服历史：买家真正问过的问题与真实葡语问法。

【生成策略：尽量细、尽量多】
- 不要把多个事实塞进一条 QA。**每条 QA 只聚焦一个具体点**（如：峰值功率单独一条、持续功率单独一条、重量单独一条、某一种保护单独一条、某一类适用电器单独一条）。
- 系统化穷举所有维度：每一项技术参数、每一种保护功能、每一类适用/不适用电器、包装内每一个配件、安装每一步、每一个认证、每一个常见故障场景、电压/频率/兼容性、退换货与保修流程等。
- 把真实历史里的问题也各自独立成条，保留真实问法。
- 数据里有多少有效信息，就尽量拆成多少条不同的问题（鼓励 30 条以上），但**严禁为凑数编造**。

【每条 QA 字段】
- q_pt：葡语问题标题（简洁、自然、地道 PT-BR）
- variants_pt：6~10 种葡语问法（优先采用历史/listing 里的真实表述，不足由你扩展）
- a_pt：葡语答案（完整、可直接回复买家；礼貌专业）
- a_cn：上面葡语答案的中文对照（供内部审核）

【铁律 · 严防编造（最重要）】
1. 只能使用三个数据源中**明确出现**的数字与事实。
2. **严禁任何推算、换算、估计、四舍五入**（例如：不得由持续功率推算峰值功率、不得由尺寸推算重量、不得由型号猜参数）。每个数字必须能在某个源里逐字找到。
3. 多个源**冲突**时（如内部写持续850W、ML写1000W）：买家可见规格**以 ML 页面为准**，并在 a_cn 末尾用「（内部数据：…）」注明差异。
4. 任何源都**没有明确给出**的信息：a_pt 用保守、引导联系客服的措辞，且对应 a_cn **必须以「【待核实】」开头**。
5. 宁可少答、保守答，也不许编。

【输出格式】
严格输出 JSON 对象：{"qa": [{"q_pt": "...", "variants_pt": ["...", ...], "a_pt": "...", "a_cn": "..."}, ...]}
不要输出 JSON 以外的任何文字。"""

    ml_block = ml_content.strip() if ml_content.strip() else "（本次未提供 ML 页面）"

    user_prompt = f"""产品 SKU：{sku}

=== 源1 美客多页面（买家可见规格以此为权威）===
{ml_block}

=== 源2 内部产品信息 ===
产品中文名：{product.get('name_cn') or ''}
英文名：{product.get('name_en') or ''}
品牌：{product.get('brand') or ''}
卖点 features：
{product.get('features') or '（无）'}
描述 description：
{product.get('description') or '（无）'}
说明书：{manual_text or '（无）'}

=== 源3 真实客服历史（{len(history)} 条）===
{hist_block}

请严格遵守系统提示的「严防编造」铁律，生成尽可能多、尽可能细的双语 QA，输出 JSON。"""

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
    data = json.loads(raw)
    return data.get("qa", [])


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

3. a_cn 始终是修正后 a_pt 的中文对照（政策类用上面的中文模板）。不要加 [SKU] 前缀。

严格输出 JSON：{{"items": [{{"i":0,"flag":"...","a_pt":"...","a_cn":"..."}}, ...]}}，items 数量与顺序必须与输入完全一致。只输出 JSON。"""

    user_prompt = f"""{sources}

=== 待核查 QA（{len(qa_for_check)} 条）===
{json.dumps(qa_for_check, ensure_ascii=False)}"""

    logger.info(f"核查 {len(qa_list)} 条…")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.0,
        max_tokens=8000,
        response_format={"type": "json_object"},
    )
    items = json.loads(resp.choices[0].message.content.strip()).get("items", [])
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
        variants = qa.get("variants_pt") or []
        variants_text = "\n".join(v.strip() for v in variants if v.strip())
        a_cn = qa.get("a_cn", "").strip()
        flag = qa.get("flag", "").strip()
        a_cn_marked = f"[{sku}] " + (f"{flag} " if flag else "") + a_cn
        ws.append([
            qa.get("q_pt", "").strip(),
            variants_text,
            qa.get("a_pt", "").strip(),
            a_cn_marked,
        ])
    name = sanitize_filename(product.get("name_cn") or "")
    out_path = OUTPUT_DIR / f"{sku}_{name}.xlsx"
    wb.save(out_path)
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
    logger.info(f"已写出：{out_path}")
    print(f"\n✅ 完成：{out_path}\n   问答条数：{len(qa_list)}")


if __name__ == "__main__":
    main()
