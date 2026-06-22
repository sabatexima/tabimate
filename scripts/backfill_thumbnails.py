#!/usr/bin/env python3
"""既存写真のサムネイルを一括生成するバックフィルスクリプト。

サムネイル機能の導入前にアップロードされた写真には縮小版が無く、一覧では
原寸へフォールバックしている。本スクリプトで既存写真の縮小版をまとめて作る。

使い方:
    cd src && python3 ../scripts/backfill_thumbnails.py

.env を読み込み、本番と同じDB/ストレージ（GCS or ローカル）に接続する。
既にサムネイルがある写真はスキップする（冪等）。
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, _SRC)

from dotenv import load_dotenv

load_dotenv(os.path.join(_SRC, ".env"))

from sqlalchemy import text  # noqa: E402

from db import get_engine  # noqa: E402
from services import images, storage  # noqa: E402


def main() -> None:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT storage_path FROM photos")).fetchall()
    paths = [r[0] for r in rows if r and r[0]]
    print(f"対象写真: {len(paths)}件（ストレージ: {'GCS' if storage.using_gcs() else 'ローカル'}）")

    made = skipped = failed = 0
    for i, p in enumerate(paths, 1):
        thumb_key = storage._thumb_key(p)
        if storage.exists(thumb_key):
            skipped += 1
            continue
        data = storage.read_bytes(p)
        if not data:
            failed += 1
            continue
        thumb = images.thumbnail(data)
        if not thumb:
            failed += 1
            continue
        storage.save_at(thumb_key, thumb, "image/jpeg")
        made += 1
        if made % 20 == 0:
            print(f"  生成 {made}件...（{i}/{len(paths)}）")

    print(f"完了: 生成 {made} / スキップ {skipped} / 失敗 {failed}")


if __name__ == "__main__":
    main()
