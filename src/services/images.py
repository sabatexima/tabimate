"""アップロード画像の正規化（HEIC→JPEG）とサムネイル生成。

- normalize(): iPhone等のHEIC/HEIFをブラウザ表示できるJPEGへ変換する。
- thumbnail(): 一覧表示用の軽量サムネイル（長辺を縮小したJPEG）を作る。

pillow-heif が無い／PILで開けない場合でも例外を投げず、
normalize は元データを、thumbnail は None を返して呼び出し側でフォールバックできるようにする。
"""
import io
import os

from logger import get_logger

logger = get_logger("services.images")

# HEIC/HEIF を PIL で開けるようにする（未導入環境でも動くよう失敗は無視）
try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _HEIF_OK = True
except Exception:
    _HEIF_OK = False
    logger.info("pillow-heif が利用できません。HEIC はそのまま保存されます。")

from PIL import Image, ImageOps

_THUMB_MAX_EDGE = 480  # サムネイルの長辺（px）
_HEIC_EXT = {".heic", ".heif"}


def normalize(data: bytes, filename: str):
    """アップロード画像をWeb表示しやすい形式に整える。

    HEIC/HEIF は JPEG に変換して (jpeg_bytes, "image/jpeg", ".jpg") を返す。
    それ以外、または変換できない場合は (元データ, None, 元の拡張子) を返す。
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in _HEIC_EXT:
        try:
            img = Image.open(io.BytesIO(data))
            # 原寸の画像はメモリを食う（1200万画素で約36MB）。回転と色の変換で
            # 原寸の写しを増やさないよう、変換してから同じ画像の上で回す
            if img.mode != "RGB":
                img = img.convert("RGB")
            ImageOps.exif_transpose(img, in_place=True)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=88)
            return out.getvalue(), "image/jpeg", ".jpg"
        except Exception:
            logger.warning("HEIC変換に失敗（元データのまま保存）: %s", filename, exc_info=True)
    return data, None, ext


def thumbnail(data: bytes, max_edge: int = _THUMB_MAX_EDGE):
    """長辺 max_edge px のJPEGサムネイルを返す。生成できなければ None。

    先に縮めてから回す。以前は原寸のまま回転・色の変換をしてから縮めていて、
    1枚で原寸の写しが3つでき（1200万画素で100MB超）、Cloud Run の512MBを
    写真2枚の同時処理で使い切りかねなかった。JPEG は読み込みの段階で
    縮めて読める（draft）ので、原寸を丸ごと展開しない。
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.draft("RGB", (max_edge * 2, max_edge * 2))   # JPEG のときだけ効く
        img.thumbnail((max_edge, max_edge))
        img = ImageOps.exif_transpose(img).convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82)
        return out.getvalue()
    except Exception:
        logger.warning("サムネイル生成に失敗", exc_info=True)
        return None
