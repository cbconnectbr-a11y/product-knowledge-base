#!/usr/bin/env python3
"""
把生成的问答 xlsx 按 SKU 上传到飞书表格的「问答附件」列。

流程：列出目标表所有记录建 sku->record_id 映射 → 对 out-dir 下每个 {SKU}_*.xlsx：
上传为该 Base 的素材(file_token) → 写入该 SKU 记录的附件字段。
带 manifest(upload_manifest.json) 断点续跑 + 失败隔离。

依赖权限：drive 上传素材(已验证) + base:record:update(写记录)。附件列需已存在。

用法：
  # 表1(CBC004)
  python3.13 scripts/upload_qa_to_feishu.py --app-token WypHb12oZadMpps1sklcY27innC \
      --table-id tblPgP1nW2MW5FwH --out-dir data/duoke_generated --sku-field SKU
  # 单个测试
  ... --skus CBC004-452
  # 运营一组(BRME/CBC008)
  ... --app-token JhUIbjFGVagkCTsaIk5c89Eonfe --table-id tblJmkifuU19WIYi \
      --out-dir data/duoke_generated_BRME --sku-field Sku
"""
import argparse
import glob
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.bitable.v1 import (
    ListAppTableRecordRequest,
    UpdateAppTableRecordRequest,
    AppTableRecord,
)
from lark_oapi.api.drive.v1 import UploadAllMediaRequest, UploadAllMediaRequestBody

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_client():
    return lark.Client.builder().app_id(os.environ["FEISHU_APP_ID"]).app_secret(os.environ["FEISHU_APP_SECRET"]).build()


def _flatten(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "".join(_flatten(x) for x in v).strip()
    if isinstance(v, dict):
        return str(v.get("text") or v.get("name") or "").strip()
    return str(v).strip()


def build_sku_map(client, app_token, table_id, sku_field) -> dict:
    """sku(大写) -> record_id"""
    m = {}
    page_token = None
    while True:
        b = ListAppTableRecordRequest.builder().app_token(app_token).table_id(table_id).page_size(500).field_names(json.dumps([sku_field]))
        if page_token:
            b = b.page_token(page_token)
        resp = client.bitable.v1.app_table_record.list(b.build())
        if not resp.success():
            raise RuntimeError(f"列记录失败: code={resp.code} msg={resp.msg}")
        for it in (resp.data.items or []):
            sku = _flatten((it.fields or {}).get(sku_field))
            if sku:
                m[sku.upper()] = it.record_id
        if resp.data.has_more:
            page_token = resp.data.page_token
        else:
            break
    return m


def upload_media(client, app_token, file_path) -> str:
    sz = os.path.getsize(file_path)
    body = (UploadAllMediaRequestBody.builder()
            .file_name(os.path.basename(file_path)).parent_type("bitable_file")
            .parent_node(app_token).size(sz).file(open(file_path, "rb")).build())
    resp = client.drive.v1.media.upload_all(UploadAllMediaRequest.builder().request_body(body).build())
    if not resp.success():
        raise RuntimeError(f"上传失败: code={resp.code} msg={resp.msg}")
    return resp.data.file_token


def set_attachment(client, app_token, table_id, record_id, attach_field, file_token):
    rec = AppTableRecord.builder().fields({attach_field: [{"file_token": file_token}]}).build()
    resp = client.bitable.v1.app_table_record.update(
        UpdateAppTableRecordRequest.builder().app_token(app_token).table_id(table_id)
        .record_id(record_id).request_body(rec).build())
    if not resp.success():
        raise RuntimeError(f"写附件失败: code={resp.code} msg={resp.msg}")


def main():
    ap = argparse.ArgumentParser(description="按SKU上传问答xlsx到飞书附件列")
    ap.add_argument("--app-token", required=True)
    ap.add_argument("--table-id", required=True)
    ap.add_argument("--out-dir", required=True, help="xlsx 所在目录")
    ap.add_argument("--sku-field", default="SKU")
    ap.add_argument("--attach-field", default="问答附件")
    ap.add_argument("--skus", default="", help="只传指定SKU(逗号分隔)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    manifest_path = out_dir / "upload_manifest.json"
    manifest = {} if args.redo else (json.loads(manifest_path.read_text()) if manifest_path.exists() else {})

    # 找出所有 {SKU}_*.xlsx（排除汇总等非SKU文件）
    files = {}
    for f in glob.glob(str(out_dir / "*.xlsx")):
        base = os.path.basename(f)
        if "_" in base and base.split("_")[0]:
            sku = base.split("_")[0]
            if sku.upper().startswith(("CBC", "BRME", "OSA")):
                files[sku] = f
    skus = sorted(files)
    if args.skus:
        want = {s.strip() for s in args.skus.split(",")}
        skus = [s for s in skus if s in want]
    if args.limit:
        skus = skus[: args.limit]
    skus = [s for s in skus if manifest.get(s, {}).get("status") != "done"]

    client = get_client()
    logger.info(f"目标表 {args.table_id} | 构建 SKU→record 映射…")
    sku_map = build_sku_map(client, args.app_token, args.table_id, args.sku_field)
    logger.info(f"表内记录 {len(sku_map)} 条 | 待上传 {len(skus)} 个")

    done = fail = miss = 0
    for i, sku in enumerate(skus, 1):
        rid = sku_map.get(sku.upper())
        if not rid:
            manifest[sku] = {"status": "no_record", "ts": time.strftime("%F %T")}
            miss += 1
            logger.warning(f"[{i}/{len(skus)}] ⚠️ {sku} 表中无对应记录")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
            continue
        try:
            ft = upload_media(client, args.app_token, files[sku])
            set_attachment(client, args.app_token, args.table_id, rid, args.attach_field, ft)
            manifest[sku] = {"status": "done", "record_id": rid, "ts": time.strftime("%F %T")}
            done += 1
            logger.info(f"[{i}/{len(skus)}] ✅ {sku}")
        except Exception as e:
            manifest[sku] = {"status": "failed", "error": str(e)[:200], "ts": time.strftime("%F %T")}
            fail += 1
            logger.error(f"[{i}/{len(skus)}] ❌ {sku}: {e}")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))

    logger.info(f"上传结束：成功 {done}、失败 {fail}、表中无记录 {miss}")
    print(f"\n✅ 上传结束：成功 {done}、失败 {fail}、无记录 {miss}")


if __name__ == "__main__":
    main()
