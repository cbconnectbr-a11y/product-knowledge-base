#!/usr/bin/env python3
"""
说明书使用汇总

批量生成完成后运行，汇总 234 个 SKU 的说明书使用情况，方便补充缺失说明书：
- ✅ 用到说明书：日志中 说明书=有（成功下载+提取）
- ⚠️ 有说明书文件但未提取：products.manual_files 有链接，但提取为空（下载/OCR失败，需排查）
- ❌ 无说明书：products.manual_files 无链接 → 需要补充说明书

输出：
- docs/产品问答-说明书使用汇总.md（分类统计 + 需补充清单）
- data/duoke_generated/说明书使用汇总.xlsx（全量明细，可筛选）

用法：python3.13 scripts/summarize_manual_usage.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openpyxl import Workbook
from scripts.utils import get_supabase_client

import argparse

ROOT = Path(__file__).parent.parent
DEFAULT_LOGS = "/tmp/batch_qa_full.log,/tmp/batch_qa.log,/tmp/batch2_qa.log,/tmp/batch2_finish.log"


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    ap = argparse.ArgumentParser(description="说明书使用汇总")
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "duoke_generated"))
    ap.add_argument("--logs", default=DEFAULT_LOGS, help="逗号分隔的日志路径")
    ap.add_argument("--name", default="", help="汇总名称(用于md文件名)")
    args = ap.parse_args()
    OUTPUT_DIR = Path(args.out_dir)
    SKU_LIST = OUTPUT_DIR / "sku_list.json"
    MANIFEST = OUTPUT_DIR / "batch_manifest.json"
    LOGS = [x for x in args.logs.split(",") if x]
    name = args.name or OUTPUT_DIR.name

    sku_items = json.loads(SKU_LIST.read_text())
    skus = [it["sku"] for it in sku_items if it.get("sku")]
    store_of = {it["sku"]: it.get("store", "") for it in sku_items}

    # products.manual_files
    client = get_supabase_client()
    prod = {}
    for ch in chunks(skus, 100):
        r = client.table("products").select("sku,name_cn,manual_files").in_("sku", ch).execute()
        for p in r.data:
            prod[p["sku"]] = p

    # 日志解析：每个 SKU 最后一次 说明书=有/无
    extracted = {}
    for lf in LOGS:
        p = Path(lf)
        if not p.exists():
            continue
        for line in p.read_text(errors="ignore").splitlines():
            m = re.search(r"SKU=(\S+)\b.*说明书=(有|无)", line)
            if m:
                extracted[m.group(1)] = (m.group(2) == "有")

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    rows = []
    for sku in skus:
        p = prod.get(sku, {})
        mf = p.get("manual_files")
        has_link = isinstance(mf, dict) and bool(mf.get("link"))
        mname = (mf.get("text", "") if isinstance(mf, dict) else "") or ""
        used = extracted.get(sku)  # True/False/None
        cnt = manifest.get(sku, {}).get("count", "")
        done = manifest.get(sku, {}).get("status") == "done"
        if not done:
            cat = "⏳ 未处理"
        elif used is True:
            cat = "✅ 用到说明书"
        elif has_link:
            cat = "⚠️ 有说明书未提取"
        else:
            cat = "❌ 无说明书(需补充)"
        rows.append({
            "sku": sku, "store": store_of.get(sku, ""), "name": p.get("name_cn", ""),
            "manual_name": mname, "has_link": "有" if has_link else "无",
            "used": {True: "是", False: "否", None: "未处理"}[used],
            "count": cnt, "category": cat,
        })

    used_rows = [r for r in rows if r["category"].startswith("✅")]
    fail_rows = [r for r in rows if r["category"].startswith("⚠️")]
    none_rows = [r for r in rows if r["category"].startswith("❌")]
    pending_rows = [r for r in rows if r["category"].startswith("⏳")]

    # xlsx 明细
    wb = Workbook()
    ws = wb.active
    ws.title = "说明书使用汇总"
    ws.append(["SKU", "店铺", "产品名", "说明书文件名", "有无说明书文件", "是否用到说明书", "问答条数", "分类"])
    for r in rows:
        ws.append([r["sku"], r["store"], r["name"], r["manual_name"], r["has_link"], r["used"], r["count"], r["category"]])
    xlsx_path = OUTPUT_DIR / "说明书使用汇总.xlsx"
    wb.save(xlsx_path)

    # md 汇总
    lines = [
        f"# 产品问答 — 说明书使用汇总（{name}）", "",
        f"- 总 SKU：{len(rows)}",
        f"- ✅ 用到说明书：{len(used_rows)}",
        f"- ⚠️ 有说明书文件但未提取成功：{len(fail_rows)}（下载/OCR 失败，可排查后重跑）",
        f"- ❌ 无说明书文件：{len(none_rows)}（**需补充说明书**）",
        f"- ⏳ 未处理(批量还没跑到)：{len(pending_rows)}",
        "", f"明细表：`{xlsx_path}`", "",
        "## ❌ 无说明书 —— 建议补充说明书的 SKU", "",
        "| SKU | 店铺 | 产品名 |", "|---|---|---|",
    ]
    for r in none_rows:
        lines.append(f"| {r['sku']} | {r['store']} | {r['name']} |")
    if fail_rows:
        lines += ["", "## ⚠️ 有说明书文件但未提取成功（需排查下载/OCR）", "",
                  "| SKU | 店铺 | 产品名 | 说明书文件名 |", "|---|---|---|---|"]
        for r in fail_rows:
            lines.append(f"| {r['sku']} | {r['store']} | {r['name']} | {r['manual_name']} |")
    lines += ["", "---", "*补充说明书后，对相应 SKU 重跑：*",
              "`python3.13 scripts/generate_product_qa.py --sku <SKU> --use-manual`"]
    md_path = ROOT / "docs" / f"产品问答-说明书使用汇总-{name}.md"
    md_path.write_text("\n".join(lines))

    print(f"✅ 汇总完成：\n  明细 xlsx：{xlsx_path}\n  汇总 md：{md_path}")
    print(f"  用到说明书 {len(used_rows)} | 有文件未提取 {len(fail_rows)} | 无说明书 {len(none_rows)}")


if __name__ == "__main__":
    main()
