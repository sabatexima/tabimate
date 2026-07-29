import XCTest
@testable import TabiMate

/// 写真の種類を中身から見分けられるか。
///
/// サーバーはファイル名の拡張子だけで HEIC の変換要否を決めているため、
/// ここを間違えるとWeb版で開けない写真が保存される。
final class ImageKindTests: XCTestCase {

    private func data(_ bytes: [UInt8], padTo count: Int = 16) -> Data {
        var all = bytes
        while all.count < count { all.append(0x00) }
        return Data(all)
    }

    func testJPEG() {
        XCTAssertEqual(ImageKind.detect(data([0xFF, 0xD8, 0xFF, 0xE0])), .jpeg)
        XCTAssertEqual(ImageKind.detect(data([0xFF, 0xD8, 0xFF, 0xDB])).ext, ".jpg")
    }

    func testPNG() {
        let png: [UInt8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        XCTAssertEqual(ImageKind.detect(data(png)), .png)
        XCTAssertEqual(ImageKind.detect(data(png)).mime, "image/png")
    }

    func testGIF() {
        XCTAssertEqual(ImageKind.detect(data(Array("GIF89a".utf8))), .gif)
    }

    func testWEBP() {
        // RIFF ....(サイズ) WEBP
        var bytes = Array("RIFF".utf8)
        bytes += [0x00, 0x00, 0x00, 0x00]
        bytes += Array("WEBP".utf8)
        XCTAssertEqual(ImageKind.detect(data(bytes)), .webp)
    }

    func testHEICBrands() {
        // iPhone の写真。....ftypheic のように 4バイト目から ftyp が来る
        for brand in ["heic", "heix", "mif1", "msf1", "hevc"] {
            var bytes: [UInt8] = [0x00, 0x00, 0x00, 0x18]
            bytes += Array("ftyp".utf8)
            bytes += Array(brand.utf8)
            XCTAssertEqual(ImageKind.detect(data(bytes)), .heic, "\(brand) を HEIC と見分けられていない")
        }
        XCTAssertEqual(ImageKind.detect(data([0x00, 0x00, 0x00, 0x18] + Array("ftypheic".utf8))).ext,
                       ".heic")
    }

    func testNonHeifFtypIsNotHeic() {
        // 動画（mp4）などの ftyp は HEIC ではない
        var bytes: [UInt8] = [0x00, 0x00, 0x00, 0x18]
        bytes += Array("ftyp".utf8)
        bytes += Array("mp42".utf8)
        XCTAssertEqual(ImageKind.detect(data(bytes)), .jpeg)   // 既定に落ちる
    }

    func testTooShortDataFallsBack() {
        XCTAssertEqual(ImageKind.detect(Data([0xFF, 0xD8])), .jpeg)
        XCTAssertEqual(ImageKind.detect(Data()), .jpeg)
    }

    func testEveryKindIsAcceptedByServer() {
        // サーバーの許可拡張子（views/reflection.py の _ALLOWED_EXT）と一致すること
        let allowed = Set([".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"])
        for kind in [ImageKind.jpeg, .png, .heic, .webp, .gif] {
            XCTAssertTrue(allowed.contains(kind.ext), "\(kind.ext) はサーバーに弾かれる")
        }
    }
}
