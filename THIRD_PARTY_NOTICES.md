# Third-party notices

TabiMate builds on the work of others. This file lists what it depends on and
under which licenses, together with the attribution required by the map and
geocoding services it uses.

The list is generated from the actual installed distributions (see
`requirements.txt`), not written by hand. Regenerate it after changing
dependencies.

たびメイトは多くの成果物の上に成り立っています。このファイルは、依存している
ものとそのライセンス、および地図・位置情報サービスが求める帰属表示をまとめた
ものです。一覧は実際にインストールされた配布物から生成しています（手書きでは
ありません）。依存を変えたら作り直してください。

---

## Map and location data

The map is rendered with [Leaflet](https://leafletjs.com/) (BSD-2-Clause).
Tiles and geocoding come from the following services; the attribution below is
displayed in the application (`src/static/js/plan-map.js`).

| Source | Used for | Attribution / terms |
|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | Base map tiles, geocoding via Nominatim | © OpenStreetMap contributors — ODbL. Nominatim has a [usage policy](https://operations.osmfoundation.org/policies/nominatim/) with rate limits |
| [Stadia Maps](https://stadiamaps.com/) · [Stamen Design](https://stamen.com/) | Watercolor tiles (only when `STADIA_API_KEY` is set) | © Stadia Maps © Stamen Design © OpenStreetMap — check the plan you are on before using it commercially |
| [GSI (国土地理院)](https://maps.gsi.go.jp/development/ichiran.html) | Geocoding fallback in Japan | Follow the GSI terms of use |
| [Google Places API](https://developers.google.com/maps/documentation/places/web-service) | Verifying that a place really exists | Google Maps Platform terms |
| [Open-Meteo](https://open-meteo.com/) | Weather for the travel dates | CC-BY 4.0 |

## AI services

| Service | Used for |
|---|---|
| [Google Gemini](https://ai.google.dev/) | Plan generation, sticky notes from photos, best-shot selection |
| [Tavily](https://tavily.com/) | Web search while building a plan |

Both are used under their own terms of service. Review them before any
commercial use — free tiers often differ from paid ones in how input data may
be handled.

## Fonts and artwork

| Item | License |
|---|---|
| [Zen Maru Gothic](https://fonts.google.com/specimen/Zen+Maru+Gothic) | SIL Open Font License 1.1 |
| [OpenMoji](https://openmoji.org/) | CC BY-SA 4.0 |
| Chamu (ちゃむ) and the screen artwork | © 2026 sabatexima — not covered by any third-party license |

## A note on pillow-heif

`pillow-heif` itself is BSD-3-Clause, but its wheels bundle libraries with
stronger terms — libheif and libde265 (LGPL), and x265 (GPL-2.0) for HEIF
*encoding*. TabiMate only *decodes* HEIC (converting iPhone photos to JPEG),
so the encoder is never exercised. Those terms attach on **distribution** of
the binary; running the application as a hosted service is not distribution.
Redistributing the container image is, so check the terms if you do that.

`pillow-heif` 自体は BSD-3-Clause ですが、wheel は libheif / libde265（LGPL）と、
HEIF の*書き出し*に使う x265（GPL-2.0）を同梱しています。たびメイトは HEIC を
*読む*だけ（iPhone の写真を JPEG に変換する）なので書き出しは使いません。
これらの義務はバイナリを**配布**したときに生じるもので、サービスとして動かす
ことは配布に当たりません。コンテナイメージを再配布する場合は確認が必要です。

---

## Python dependencies

Generated from the installed distributions. Regenerate with:

```bash
python - <<'PY' >> THIRD_PARTY_NOTICES.md
from importlib.metadata import distributions
import re
rows = []
for d in distributions():
    m = d.metadata
    if m["Name"].lower() in {"pip", "pytest", "iniconfig", "pluggy"}:
        continue
    lic = (m.get("License-Expression") or "").strip()
    if not lic:
        cls = [c.split("::")[-1].strip()
               for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
        lic = cls[0] if cls else (m.get("License") or "").strip()
    rows.append((m["Name"], m["Version"], re.sub(r"\s+", " ", lic) or "—"))
for n, v, l in sorted(rows, key=lambda r: r[0].lower()):
    print(f"| {n} | {v} | {l} |")
PY
```

| Package | Version | License |
|---|---|---|
| [aiofiles](https://github.com/Tinche/aiofiles) | 25.1.0 | Apache Software |
| [aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) | 2.7.1 | Python Software Foundation |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.14.3 | Apache-2.0 AND MIT |
| [aiosignal](https://github.com/aio-libs/aiosignal) | 1.4.0 | Apache Software |
| [annotated-types](https://github.com/annotated-types/annotated-types) | 0.8.0 | MIT |
| [anyio](https://github.com/agronholm/anyio) | 4.14.2 | MIT |
| attrs | 26.1.0 | MIT |
| [Authlib](https://github.com/lepture/authlib) | 1.3.2 | BSD |
| [blinker](https://github.com/pallets-eco/blinker/) | 1.9.0 | MIT |
| [certifi](https://github.com/certifi/python-certifi) | 2026.7.22 | Mozilla Public 2.0 (MPL 2.0) |
| [cffi](https://github.com/python-cffi/cffi) | 2.1.0 | MIT-0 |
| charset-normalizer | 3.4.9 | MIT |
| [click](https://github.com/pallets/click/) | 8.4.2 | BSD-3-Clause |
| [cloud-sql-python-connector](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector) | 1.14.0 | Apache Software |
| [cryptography](https://github.com/pyca/cryptography) | 49.0.0 | Apache-2.0 OR BSD-3-Clause |
| [distro](https://github.com/python-distro/distro) | 1.9.0 | Apache Software |
| [filetype](https://github.com/h2non/filetype.py) | 1.2.0 | MIT |
| [Flask](https://github.com/pallets/flask/) | 3.1.3 | BSD-3-Clause |
| [frozenlist](https://github.com/aio-libs/frozenlist) | 1.8.0 | Apache-2.0 |
| [google-api-core](https://github.com/googleapis/google-cloud-python/tree/main/packages/google-api-core) | 2.33.0 | Apache Software |
| [google-auth](https://github.com/googleapis/google-auth-library-python) | 2.53.0 | Apache Software |
| [google-cloud-core](https://github.com/googleapis/google-cloud-python/tree/main/packages/google-cloud-core) | 2.6.0 | Apache Software |
| [google-cloud-storage](https://github.com/googleapis/python-storage) | 2.18.2 | Apache Software |
| [google-crc32c](https://github.com/googleapis/python-crc32c) | 1.8.0 | — |
| [google-genai](https://github.com/googleapis/python-genai) | 1.75.0 | Apache-2.0 |
| [google-resumable-media](https://github.com/googleapis/google-cloud-python/tree/main/packages/google-resumable-media) | 2.10.0 | Apache Software |
| [googleapis-common-protos](https://github.com/googleapis/google-cloud-python/tree/main/packages/googleapis-common-protos) | 1.75.0 | Apache Software |
| [greenlet](https://greenlet.readthedocs.io) | 3.5.4 | MIT AND PSF-2.0 |
| [gunicorn](https://gunicorn.org) | 23.0.0 | MIT |
| [h11](https://github.com/python-hyper/h11) | 0.16.0 | MIT |
| [httpcore](https://www.encode.io/httpcore/) | 1.0.9 | BSD-3-Clause |
| [httpx](https://github.com/encode/httpx) | 0.28.1 | BSD |
| [idna](https://github.com/kjd/idna) | 3.18 | BSD-3-Clause |
| [itsdangerous](https://github.com/pallets/itsdangerous/) | 2.2.0 | BSD |
| [Jinja2](https://github.com/pallets/jinja/) | 3.1.6 | BSD |
| [jsonpatch](https://github.com/stefankoegl/python-json-patch.git) | 1.33 | BSD |
| [jsonpointer](https://github.com/stefankoegl/python-json-pointer) | 3.1.1 | BSD |
| [langchain](https://docs.langchain.com/) | 1.3.2 | MIT |
| [langchain-core](https://docs.langchain.com/) | 1.4.0 | MIT |
| [langchain-google-genai](https://docs.langchain.com/oss/python/integrations/providers/google) | 4.2.3 | MIT |
| [langchain-protocol](https://github.com/langchain-ai/agent-protocol/tree/main/streaming) | 0.0.18 | MIT |
| [langchain-tavily](https://github.com/tavily-ai/langchain-tavily) | 0.2.18 | MIT |
| [langgraph](https://docs.langchain.com/oss/python/langgraph/overview) | 1.2.2 | MIT |
| [langgraph-checkpoint](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint) | 4.1.1 | MIT |
| [langgraph-prebuilt](https://github.com/langchain-ai/langgraph/tree/main/libs/prebuilt) | 1.1.0 | MIT |
| [langgraph-sdk](https://github.com/langchain-ai/langgraph/tree/main/libs/sdk-py) | 0.3.15 | MIT |
| [langsmith](https://smith.langchain.com/) | 0.10.13 | MIT |
| [MarkupSafe](https://github.com/pallets/markupsafe/) | 3.0.3 | BSD-3-Clause |
| [multidict](https://github.com/aio-libs/multidict) | 6.7.1 | Apache 2.0 |
| [nest-asyncio](https://github.com/erdewit/nest_asyncio) | 1.6.0 | BSD |
| [orjson](https://github.com/ijl/orjson) | 3.11.9 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| [ormsgpack](https://github.com/ormsgpack/ormsgpack) | 1.12.2 | Apache-2.0 OR MIT |
| [packaging](https://github.com/pypa/packaging) | 26.2 | Apache-2.0 OR BSD-2-Clause |
| [pillow](https://python-pillow.org) | 11.0.0 | CMU (MIT-CMU) |
| [pillow_heif](https://github.com/bigcat88/pillow_heif) | 0.18.0 | GNU General Public v2 (GPLv2) |
| [propcache](https://github.com/aio-libs/propcache) | 0.5.2 | Apache Software |
| [proto-plus](https://github.com/googleapis/google-cloud-python) | 1.28.2 | Apache Software |
| [protobuf](https://developers.google.com/protocol-buffers/) | 7.35.1 | 3-Clause BSD |
| [pyasn1](https://github.com/pyasn1/pyasn1) | 0.6.4 | BSD-2-Clause |
| [pyasn1_modules](https://github.com/pyasn1/pyasn1-modules) | 0.4.2 | BSD |
| [pycparser](https://github.com/eliben/pycparser) | 3.0 | BSD-3-Clause |
| [pydantic](https://github.com/pydantic/pydantic) | 2.13.4 | MIT |
| [pydantic_core](https://github.com/pydantic) | 2.46.4 | MIT |
| [Pygments](https://pygments.org) | 2.20.0 | BSD-2-Clause |
| PyMySQL | 1.1.1 | MIT |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.2.2 | BSD-3-Clause |
| [PyYAML](https://github.com/yaml/pyyaml) | 6.0.3 | MIT |
| [redis](https://github.com/redis/redis-py) | 5.2.1 | MIT |
| [requests](https://github.com/psf/requests) | 2.34.2 | Apache Software |
| [requests-toolbelt](https://github.com/requests/toolbelt) | 1.0.0 | Apache Software |
| [sniffio](https://github.com/python-trio/sniffio) | 1.3.1 | MIT |
| [SQLAlchemy](https://www.sqlalchemy.org) | 2.0.49 | MIT |
| [tenacity](https://github.com/jd/tenacity) | 9.1.4 | Apache Software |
| [typing-inspection](https://github.com/pydantic/typing-inspection) | 0.4.2 | MIT |
| [typing_extensions](https://github.com/python/typing_extensions) | 4.16.0 | PSF-2.0 |
| urllib3 | 2.7.0 | MIT |
| [uuid_utils](https://github.com/aminalaee/uuid-utils) | 0.17.0 | BSD-3-Clause |
| [websockets](https://github.com/python-websockets/websockets) | 16.1.1 | BSD-3-Clause |
| [Werkzeug](https://github.com/pallets/werkzeug/) | 3.1.8 | BSD-3-Clause |
| [xxhash](https://github.com/ifduyue/python-xxhash) | 3.8.1 | BSD-2-Clause |
| [yarl](https://github.com/aio-libs/yarl) | 1.24.5 | Apache-2.0 |
| [zstandard](https://github.com/indygreg/python-zstandard) | 0.25.0 | BSD-3-Clause |
