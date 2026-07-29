# Resources

ここに置くもの（どちらも任意。無くてもビルドは通ります）。

## フォント

Web版と同じ字面にしたいときは、[Zen Maru Gothic](https://fonts.google.com/specimen/Zen+Maru+Gothic)
から次の2つを落として置き、Info.plist の `UIAppFonts` に並べます。

- `ZenMaruGothic-Regular.ttf`
- `ZenMaruGothic-Bold.ttf`

無いときは端末標準の丸ゴシック（SF Rounded）に自動で落ちます（`Design/Theme.swift`）。

## ちゃむの絵

Assets に `chamu` という名前で画像を足すと、吹き出しの隣やあいさつに出ます。
無いときは 🍀 で代用します。

`Info.plist` は XcodeGen が `project.yml` から生成するので、ここには置きません。
