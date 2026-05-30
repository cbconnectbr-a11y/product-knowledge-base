#!/usr/bin/env python3
"""
批量生成产品客服问答（多客模版）

读取 data/duoke_generated/sku_list.json（表1的234个在售SKU），逐个调用
generate_product_qa.process_sku，带 manifest 断点续跑 + 失败隔离。

注意（见 docs/产品问答-批量注意事项.md）：
- 无 FIRECRAWL_API_KEY，本脚本不抓 ML；若 data/duoke_generated/ml_{sku}.md 存在会自动用。
- 默认提取并使用说明书正文（图片版/CID乱码PDF走OCR，较慢）。
- 单进程串行，避免并发数据冲突。

用法：
    python3.13 scripts/batch_generate_qa.py --limit 5          # 验证波：只跑前5个
    python3.13 scripts/batch_generate_qa.py                    # 跑全部（续跑未完成的）
    python3.13 scripts/batch_generate_qa.py --skus CBC004-452,CBC004-342
    python3.13 scripts/batch_generate_qa.py --redo             # 忽略manifest，全部重跑
"""
import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_product_qa import process_sku, OUTPUT_DIR
from scripts.utils import get_supabase_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SKU_LIST = OUTPUT_DIR / "sku_list.json"
MANIFEST = OUTPUT_DIR / "batch_manifest.json"


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def save_manifest(m: dict):
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description="批量生成产品客服问答")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个（验证波；0=全部）")
    ap.add_argument("--skus", default="", help="只跑指定 SKU（逗号分隔）")
    ap.add_argument("--max-rounds", type=int, default=2, help="每个SKU补充轮上限（默认2，控成本）")
    ap.add_argument("--max-history", type=int, default=50)
    ap.add_argument("--no-manual", action="store_true", help="不提取说明书（更快）")
    ap.add_argument("--redo", action="store_true", help="忽略manifest，全部重跑")
    args = ap.parse_args()

    if not SKU_LIST.exists():
        logger.error(f"找不到 SKU 清单：{SKU_LIST}")
        sys.exit(1)
    sku_items = json.loads(SKU_LIST.read_text())
    skus = [it["sku"] for it in sku_items if it.get("sku")]

    if args.skus:
        want = {s.strip() for s in args.skus.split(",") if s.strip()}
        skus = [s for s in skus if s in want]
    if args.limit:
        skus = skus[: args.limit]

    manifest = {} if args.redo else load_manifest()
    todo = [s for s in skus if manifest.get(s, {}).get("status") != "done"]
    logger.info(f"待处理 {len(todo)}/{len(skus)} 个 SKU（已完成 {len(skus)-len(todo)}，断点续跑）")

    client = get_supabase_client()
    done = fail = 0
    t0 = time.time()
    for i, sku in enumerate(todo, 1):
        start = time.time()
        try:
            out_path, md_path, n = process_sku(
                sku, client=client, use_manual=not args.no_manual,
                max_history=args.max_history, max_rounds=args.max_rounds,
            )
            dt = time.time() - start
            manifest[sku] = {"status": "done", "count": n, "file": out_path.name,
                             "secs": round(dt, 1), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            done += 1
            logger.info(f"[{i}/{len(todo)}] ✅ {sku} → {n} 条（{dt:.0f}s）")
        except Exception as e:
            manifest[sku] = {"status": "failed", "error": str(e)[:300],
                             "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            fail += 1
            logger.error(f"[{i}/{len(todo)}] ❌ {sku} 失败：{e}")
            logger.debug(traceback.format_exc())
        save_manifest(manifest)  # 每个SKU后落盘，可随时中断续跑
        processed = done + fail
        if processed % 10 == 0:
            total_done = sum(1 for v in manifest.values() if v.get("status") == "done")
            logger.info(f"===PROGRESS=== 本次已处理 {processed}/{len(todo)} | 本次成功 {done} 失败 {fail} "
                        f"| 累计完成 {total_done}/{len(skus)} | 最近 {sku}:{manifest[sku].get('count','-')}条")

    total = time.time() - t0
    avg = total / max(done + fail, 1)
    logger.info(f"批量结束：成功 {done}、失败 {fail}、用时 {total/60:.1f} 分钟、均 {avg:.0f}s/个")
    failed = [s for s, v in manifest.items() if v.get("status") == "failed"]
    if failed:
        logger.warning(f"失败清单（{len(failed)}）：{', '.join(failed)}")
    print(f"\n批量结束：成功 {done}、失败 {fail}。输出目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
