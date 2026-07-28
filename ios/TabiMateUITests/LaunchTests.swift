import XCTest

/// アプリがちゃんと立ち上がるかを見る。
///
/// ビルドが通ってもここで落ちることはある（Info.plist の不足、起動直後の
/// クラッシュ、画面が何も出ないなど）。単体テストでは分からない部分なので、
/// 実際にシミュレータで起動して最初の画面が出ることだけ確かめる。
final class LaunchTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testLaunchesToSignInScreen() {
        let app = XCUIApplication()
        app.launch()

        // サインインしていない状態なので、はじめの画面が出る
        XCTAssertTrue(app.staticTexts["たびメイト"].waitForExistence(timeout: 30),
                      "起動しても「たびメイト」の見出しが出てこない")
        XCTAssertTrue(app.buttons["Googleではじめる"].waitForExistence(timeout: 5),
                      "サインインのボタンが出てこない")
        // 立ち上がった直後に落ちていないこと
        XCTAssertEqual(app.state, .runningForeground)
    }

    func testStaysUpAfterAWhile() {
        // 起動直後の非同期処理（保存済みトークンの確認など）で落ちないこと。
        // 接続先はダミーなので通信は失敗するが、それで落ちてはいけない。
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.staticTexts["たびメイト"].waitForExistence(timeout: 30))

        Thread.sleep(forTimeInterval: 5)
        XCTAssertEqual(app.state, .runningForeground, "しばらくすると落ちている")
        // 通信に失敗しても、はじめの画面は出たままであること
        XCTAssertTrue(app.buttons["Googleではじめる"].exists)
    }
}
