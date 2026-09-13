"""ロジックの層。views（HTTPの入口）と db（永続化）の間に立つ。

  exif             写真の撮影日時・GPS を読む
  features         写真の集まりから「その旅の特徴」を数える
  images           サムネイル生成・HEIC 変換
  storage          写真の置き場所（GCS / ローカルを差し替え式で）
  trip_interpreter AIに写真を読ませて付箋とベストショットを作る
  packing          行き先と天気から持ち物を提案する
  weather          旅行日の天気予報（Open-Meteo）
  geocoding        地名 → 緯度経度（Places → Nominatim → 地理院と落ちる）

ここに置くものの基準: HTTP のことも SQL のことも知らず、単体で呼べること。
そのおかげで、テストでは丸ごと差し替えられる。
"""
