#!/usr/bin/env bash
# iOSアプリのうち「Foundation だけで書かれた部分」を Linux の Swift で検査する。
#
# Mac が無くても、モデル・通信・地図の並び順といった中核の型と挙動を
# 本物のコンパイラで確かめられる（SwiftUI 側は Apple の SDK が要るので対象外）。
#
#   使い方: scripts/check_ios_logic.sh
#   必要なもの: swift（PATH に無ければ Docker Hub の公式イメージから取り出す）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/ios/TabiMate"
TESTS="$ROOT/ios/TabiMateTests"
WORK="${TMPDIR:-/tmp}/tabimate-swift-check"
SWIFT_TAG="${SWIFT_TAG:-6.0}"

# ----------------------------------------------------------------------
# Swift の用意
# ----------------------------------------------------------------------
if command -v swift >/dev/null 2>&1; then
  SWIFT_BIN="$(command -v swift)"
else
  TOOLCHAIN="${TMPDIR:-/tmp}/swiftroot"
  if [ ! -x "$TOOLCHAIN/usr/bin/swift" ]; then
    echo "▸ Swift が無いので公式イメージ（swift:$SWIFT_TAG）から取り出します"
    # Docker Hub 本体は blob を別ホストへ逃がすため、同一ホストで配る
    # Google のミラーを使う（プロキシ環境でも通りやすい）
    REG="https://mirror.gcr.io/v2/library/swift"
    ACCEPT="application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"
    mkdir -p "$TOOLCHAIN"
    curl -sSL -H "Accept: $ACCEPT" "$REG/manifests/$SWIFT_TAG" -o "$WORK.idx.json"
    DIGEST=$(python3 -c "
import json;d=json.load(open('$WORK.idx.json'))
print(next(m['digest'] for m in d.get('manifests',[])
           if m.get('platform',{}).get('architecture')=='amd64'
           and m['platform']['os']=='linux') if 'manifests' in d else '')")
    [ -n "$DIGEST" ] && curl -sSL -H "Accept: $ACCEPT" "$REG/manifests/$DIGEST" -o "$WORK.man.json" \
                     || mv "$WORK.idx.json" "$WORK.man.json"
    python3 -c "
import json,subprocess
for i,l in enumerate(json.load(open('$WORK.man.json'))['layers']):
    print(f'   layer{i}: {l[\"size\"]/1e6:.0f}MB', flush=True)
    subprocess.run(['curl','-sSL','-o',f'$WORK.l{i}.tgz','$REG/blobs/'+l['digest']],check=True)
    subprocess.run(['tar','xzf',f'$WORK.l{i}.tgz','-C','$TOOLCHAIN'],check=False)"
  fi
  SWIFT_BIN="$TOOLCHAIN/usr/bin/swift"
fi
echo "▸ $("$SWIFT_BIN" --version | head -1)"

# ----------------------------------------------------------------------
# 検査用パッケージを組み立てる（本物のソースをそのまま使う）
# ----------------------------------------------------------------------
rm -rf "$WORK"
mkdir -p "$WORK/Sources/TabiMate" "$WORK/Tests/TabiMateTests"

# SwiftUI / UIKit / MapKit / PhotosUI / Security / GoogleSignIn を使わないファイルだけ
found=0
while IFS= read -r f; do
  if ! grep -q "^import \(SwiftUI\|UIKit\|MapKit\|PhotosUI\|Security\|GoogleSignIn\)" "$f"; then
    cp "$f" "$WORK/Sources/TabiMate/"
    found=$((found + 1))
  fi
done < <(find "$APP" -name '*.swift')
cp "$TESTS"/*.swift "$WORK/Tests/TabiMateTests/"
echo "▸ 対象 $found ファイル + テスト $(ls "$TESTS"/*.swift | wc -l | tr -d ' ') ファイル"

# Linux の Foundation は URLSession/URLRequest が別モジュールなので補う
python3 - "$WORK/Sources/TabiMate" <<'PY'
import pathlib, sys
add = "#if canImport(FoundationNetworking)\nimport FoundationNetworking\n#endif\n"
for f in pathlib.Path(sys.argv[1]).glob('*.swift'):
    s = f.read_text()
    if "FoundationNetworking" in s or "import Foundation\n" not in s:
        continue
    f.write_text(s.replace("import Foundation\n", "import Foundation\n" + add, 1))
PY

# Apple 専用の部分だけ、本体と同じ形の代役を置く
cat > "$WORK/Sources/TabiMate/_LinuxShims.swift" <<'SWIFT'
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

// Keychain.swift（Security を import するため対象外）から TokenBox だけを写したもの
enum TokenBox {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var value: String?
    static var current: String? {
        get { lock.withLock { value } }
        set { lock.withLock { value = newValue } }
    }
}

// AuthStore（SwiftUI 側）のうち APIClient が触る部分だけ
@MainActor
final class AuthStore {
    static let shared = AuthStore()
    func clearToken() {}
}

#if canImport(FoundationNetworking)
// URLSession.bytes(for:) は Apple 版のみ。型だけ合わせた代役
struct _BytesShim: AsyncSequence {
    typealias Element = UInt8
    struct AsyncIterator: AsyncIteratorProtocol {
        mutating func next() async throws -> UInt8? { nil }
    }
    func makeAsyncIterator() -> AsyncIterator { AsyncIterator() }
    var lines: _LinesShim { _LinesShim() }
}
struct _LinesShim: AsyncSequence {
    typealias Element = String
    struct AsyncIterator: AsyncIteratorProtocol {
        mutating func next() async throws -> String? { nil }
    }
    func makeAsyncIterator() -> AsyncIterator { AsyncIterator() }
}
extension URLSession {
    func bytes(for request: URLRequest) async throws -> (_BytesShim, URLResponse) {
        (_BytesShim(), URLResponse(url: URL(string: "https://example.invalid")!,
                                   mimeType: nil, expectedContentLength: 0,
                                   textEncodingName: nil))
    }
}
#endif
SWIFT

# waitsForConnectivity は Linux では読み取り専用（iOS では設定できる）
sed -i.bak 's|^\( *\)config.waitsForConnectivity = false|\1#if !canImport(FoundationNetworking)\n\1config.waitsForConnectivity = false\n\1#endif|' \
  "$WORK/Sources/TabiMate/APIClient.swift" && rm -f "$WORK/Sources/TabiMate/APIClient.swift.bak"

cat > "$WORK/Package.swift" <<'SWIFT'
// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TabiMate",
    targets: [
        .target(name: "TabiMate"),
        .testTarget(name: "TabiMateTests", dependencies: ["TabiMate"]),
    ]
)
SWIFT

# ----------------------------------------------------------------------
# 型検査（Swift 5 / 6 の両モード）とテスト
# ----------------------------------------------------------------------
cd "$WORK"
for mode in 5 6; do
  echo "▸ Swift $mode モードで型検査"
  "$SWIFT_BIN"c -typecheck -swift-version "$mode" Sources/TabiMate/*.swift 2>&1 \
    | grep -E "error:" && { echo "  ✗ 型エラーあり"; exit 1; } || echo "  ✓ エラーなし"
done

echo "▸ テスト実行"
"$SWIFT_BIN" test 2>&1 | tail -4
