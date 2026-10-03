#!/usr/bin/env python3
"""アルバムのスライドの下見を作る（写真の切り抜きから、文字のあふれまで）。

preview_slides.py と同じく、services/album_slides.py が作る要求を HTML に描いて
Chromium で開く。写真は本番と同じ道筋（向きを直す → 縮める → 枠の形に切り抜く）を
通したものを、手元のファイルとして貼る。

  使い方: python3 scripts/preview_album.py [出力先フォルダ] [--photos 写真のフォルダ]

写真のフォルダを渡すと、その写真を順に使う（無ければ、空・山・人の形を描いた
見本の写真を作る。人の頭が切れていないかを見るため、人は少し上に描く）。
"""
import glob
import os
import random
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("SECRET_KEY", "preview")

import preview_slides as PS  # noqa: E402

# 見本の写真の形（横, 縦, EXIF の向き）。6 は「横向きに保存して、90度回して見る」スマホの縦写真
SHAPES = [(2016, 1512, 1), (1512, 2016, 1), (2016, 1512, 6), (2016, 1134, 1),
          (1600, 1600, 1), (2016, 1512, 1), (2016, 1512, 6), (3000, 1000, 1)]

STICKERS = ["波の音がずっと聞こえてた", "坂の途中のパン屋さん", "夕焼けで顔が真っ赤",
            "地図にない近道", "おばあちゃんのおすすめ", "雨のち虹", "帰りの電車でうとうと",
            "また来ようねって言った"]


def _scene(path, w, h, orientation, n, rng):
    from PIL import Image, ImageDraw
    # 見て向きが正しくなる絵を描いてから、EXIF の向きのぶん逆に回して保存する
    vw, vh = (h, w) if orientation == 6 else (w, h)
    img = Image.new("RGB", (vw, vh))
    d = ImageDraw.Draw(img)
    top, bottom = rng.choice([((120, 170, 230), (230, 240, 250)), ((250, 160, 110), (250, 225, 180)),
                              ((90, 140, 200), (200, 225, 240))])
    for y in range(vh):
        t = y / vh
        d.line([(0, y), (vw, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    d.ellipse([vw * .72, vh * .1, vw * .72 + vh * .12, vh * .22], fill=(255, 240, 200))
    d.polygon([(0, vh * .7), (vw * .3, vh * .45), (vw * .55, vh * .68), (vw * .8, vh * .5), (vw, vh * .7),
               (vw, vh), (0, vh)], fill=rng.choice([(90, 140, 90), (120, 150, 100), (80, 110, 130)]))
    # 人（顔は上から3割あたり）
    cx, r = vw * rng.uniform(.35, .65), min(vw, vh) * .07
    d.ellipse([cx - r, vh * .3 - r, cx + r, vh * .3 + r], fill=(240, 205, 175))
    d.ellipse([cx - r * .35, vh * .3 - r * .2, cx - r * .15, vh * .3], fill=(60, 50, 40))
    d.ellipse([cx + r * .15, vh * .3 - r * .2, cx + r * .35, vh * .3], fill=(60, 50, 40))
    d.rounded_rectangle([cx - r * 1.4, vh * .3 + r * 1.1, cx + r * 1.4, vh * .75], radius=r,
                        fill=rng.choice([(230, 120, 140), (90, 130, 200), (240, 200, 90)]))
    d.text((vw * .03, vh * .03), f"#{n}", fill=(255, 255, 255))
    if orientation == 6:
        img = img.rotate(90, expand=True)   # 保存は横向き。見るときに EXIF で右へ90度回す
    exif = Image.Exif()
    exif[0x0112] = orientation
    img.save(path, quality=88, exif=exif.tobytes())


def _photos(out_dir, count, start, days, rng, real=None, undated=0):
    """見本の写真を作り、album の photos と「id → ファイル」を返す。"""
    os.makedirs(os.path.join(out_dir, "photos"), exist_ok=True)
    files, photos = {}, []
    t = start.replace(hour=8, minute=40)
    per_day = max(1, count // days)
    for i in range(count):
        pid = i + 1
        if real:
            path = real[i % len(real)]
        else:
            path = os.path.join(out_dir, "photos", f"s{pid:03d}.jpg")
            if not os.path.exists(path):
                w, h, o = SHAPES[rng.randrange(len(SHAPES))]
                _scene(path, w, h, o, pid, rng)
        files[pid] = path
        day = min(days - 1, i // per_day)
        t = max(t, start + timedelta(days=day, hours=8, minutes=40))
        t += timedelta(minutes=rng.randint(5, 50))
        taken = None if i >= count - undated else t.strftime("%Y-%m-%d %H:%M:%S")
        photos.append({"id": pid, "taken_at": taken, "storage_path": path})
    return photos, files


def scenarios(out_dir, real=None):
    rng = random.Random(7)
    start = datetime(2026, 8, 14)
    p, f = _photos(out_dir, 26, start, 2, rng, real)
    yield "2日・26枚・横の表紙", {
        "id": 1, "title": "熱海でのんびり夏休み", "start_date": "2026-08-14", "end_date": "2026-08-15",
        "cover_photo_id": 1, "best": [{"photo_id": 9, "reason": "光の入り方がやわらかくて、その場の静けさが伝わる一枚"}],
        "stickers": STICKERS[:7], "photos": p}, f
    p, f = _photos(out_dir, 6, start, 1, random.Random(3), real)
    yield "日帰り・6枚・縦の表紙", {
        "id": 2, "title": "鎌倉さんぽ", "start_date": "2026-08-14", "end_date": "2026-08-14",
        "cover_photo_id": 2, "best": [], "stickers": [], "photos": p}, f
    p, f = _photos(out_dir, 130, start, 4, random.Random(11), real, undated=5)
    yield "4日・130枚（80枚に選ぶ）・長い題名", {
        "id": 3, "title": "北海道ぐるっと一周！ 富良野のラベンダー畑と美瑛の青い池と小樽の運河をめぐる家族旅行2026",
        "start_date": "2026-08-14", "end_date": "2026-08-17", "cover_photo_id": None,
        "best": [{"photo_id": 40, "reason": "みんなの笑顔がそろった、旅のいちばんの思い出"}],
        "stickers": STICKERS + ["ラベンダーのソフトクリーム", "青い池は本当に青かった", "運河の夜景",
                                "車の中でしりとり"], "photos": p}, f
    p, f = _photos(out_dir, 1, start, 1, random.Random(5), real)
    yield "1枚だけ", {"id": 4, "title": "", "start_date": None, "end_date": None,
                      "cover_photo_id": None, "best": [], "stickers": ["ひとこと"], "photos": p}, f


def main():
    args = sys.argv[1:]
    real = None
    if "--photos" in args:
        i = args.index("--photos")
        real = sorted(glob.glob(os.path.join(args[i + 1], "*.*")))
        del args[i:i + 2]
    out_dir = os.path.abspath(args[0] if args else "album-preview")
    os.makedirs(out_dir, exist_ok=True)
    PS.fonts(out_dir)

    from services import album_slides as A
    chrome = PS._chrome()
    failed = 0
    for n, (name, album, files) in enumerate(scenarios(out_dir, real)):
        works, photos = {}, []
        for p in album["photos"]:
            got = A.working_copy(open(files[p["id"]], "rb").read())
            works[p["id"]] = got[0]
            photos.append(A.Photo(p["id"], got[1], A._parse_dt(p["taken_at"])))
        photos.sort(key=lambda p: (p.taken is None, p.taken or datetime.min, p.id))
        pages = A.layout(album, photos)
        crops = os.path.join(out_dir, f"crops{n}")
        os.makedirs(crops, exist_ok=True)
        urls = {}
        for slot in A.all_slots(pages):
            path = os.path.join(crops, f"{slot.key}.jpg")
            open(path, "wb").write(A.render_crop(works[slot.photo_id], slot))
            urls[slot.key] = "file://" + path
        body, images, zorder = A.build_requests(album, photos, pages, urls)
        page = os.path.join(out_dir, f"album{n}.html")
        # 重ね順の要求（写真より手前に出す物）を、描く順に反映する
        front = {i for z in zorder for i in z["updatePageElementsZOrder"]["pageElementObjectIds"]}
        later = [q for q in body if q.get("createShape", {}).get("objectId") in front]
        ids = {q["createShape"]["objectId"] for q in later}
        rest = [q for q in body if not any(q.get(k, {}).get("objectId") in ids for k in
                                           ("createShape", "updateShapeProperties", "insertText"))
                and not (("updateTextStyle" in q or "updateParagraphStyle" in q)
                         and next(iter(q.values()))["objectId"] in ids)]
        moved = [q for q in body if q not in rest]
        count = PS.render(rest + images + moved, page, image_src=lambda u: u[len("file://"):])
        kinds = [p.kind for p in pages]
        print(f"▸ {name}: {len(pages)}ページ {kinds.count('grid')}グリッド {kinds.count('hero')}全面 "
              f"写真{len(A.all_slots(pages))}枠")
        failed += not PS.check(chrome, page, count, name)
    print(f"▸ 下見: {out_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
