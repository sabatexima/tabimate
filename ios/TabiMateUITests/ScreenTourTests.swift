import XCTest

/// サインインした後の画面を、実際にひとつずつ開いて回る。
///
/// これまでの UIテストは最初の画面までしか行けず、ホーム・そうだん・保存プラン・
/// おもいで以降は一度も描画されていなかった（Google のサインインを通れないため）。
/// SwiftUI は「ビルドは通るのに実行時に何も出ない／落ちる」ことがあるので、
/// そこは動かしてみないと分からない。
///
/// 仕組み: 起動引数 -uiTesting でダミーのトークンを入れ、通信はアプリに仕込んだ
/// スタブ（UITestSupport.swift, Debug ビルドのみ）が受ける。サーバーは要らない。
@MainActor
final class ScreenTourTests: XCTestCase {

    private var app: XCUIApplication!

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-uiTesting"]
        app.launch()
    }

    override func tearDown() {
        app = nil
        super.tearDown()
    }

    // MARK: - ひとまわり

    /// 4つのタブと、そこから開ける画面をすべて通る。
    func testWalksThroughEveryScreen() {
        // --- ホーム -------------------------------------------------
        expect(text: "こんな旅は", where: "ホーム")
        expect(text: "温泉でほっこり", where: "ホームの季節のアイデア")
        // depart_iso が未来なのでカウントダウンの札が出る
        expect(text: "熱海でのんびり", where: "ホームの次の旅")

        // --- 設定（ホームのシート） ----------------------------------
        tapButton("設定")
        expect(text: "たびメイトについて", where: "設定")
        expect(text: "tester@example.com", where: "設定のアカウント")
        tapButton("閉じる")
        expect(text: "こんな旅は", where: "設定を閉じたあとのホーム")

        // --- そうだん -----------------------------------------------
        tapTab("そうだん")
        expect(text: "熱海に行きたい", where: "そうだんの履歴")
        expect(text: "🗾 熱海", where: "そうだんのプラン提案カード")

        // --- 保存プラン ---------------------------------------------
        tapTab("保存プラン")
        expect(text: "旅のしおり", where: "保存プランの見出し")
        tapText("熱海でのんびり")

        // しおりの中身
        expect(text: "ITINERARY", where: "しおりの表紙")
        expect(text: "💰 旅のおこづかい帳", where: "しおりの費用")
        expect(text: "🎒 持ち物リスト", where: "しおりの持ち物")
        expect(text: "🌟 旅の感想", where: "しおりの感想")

        // 共有シート
        tapButton("このしおりを共有する")
        expect(text: "🔗 リンクで見せる", where: "しおりの共有")
        expect(text: "✉️ 相手を選んで見せる", where: "しおりの共有（メール）")
        tapButton("閉じる")
        goBack()

        // --- おもいで -----------------------------------------------
        tapTab("おもいで")
        expect(text: "おもいで", where: "おもいでの見出し")

        // 年間ダイジェスト
        tapButton("年間ダイジェスト")
        expect(text: "この1年でもらった言葉", where: "年間ダイジェスト")
        goBack()

        // 旅をつくるシート
        tapButton("旅をつくる")
        expect(text: "旅の名前", where: "旅をつくる")
        tapButton("やめる")

        // 旅の中身
        tapText("夏の海、熱海")
        expect(text: "MEMORIES", where: "旅の中身")
        expect(text: "🌟 ちゃむが選んだ一枚", where: "ちゃむが選んだ一枚")
        expect(text: "🍀 ことばの付箋", where: "ことばの付箋")
        expect(text: "📷 写真", where: "写真")

        // 旅の共有（メニュー経由）
        tapButton("この旅の操作")
        tapButton("共有する")
        expect(text: "🔗 リンクで見せる", where: "旅の共有")
        tapButton("閉じる")

        // 旅の名前を直すシート
        tapButton("この旅の操作")
        tapButton("名前・日にちを直す")
        expect(text: "旅を直す", where: "旅を直す")
        tapButton("やめる")

        goBack()
        XCTAssertEqual(app.state, .runningForeground, "ひとまわりの途中で落ちている")
    }

    /// 相談で送信して、生成中の見た目まで出ること。
    ///
    /// SSE は URLSession.shared を通るので、スタブが効かない環境では
    /// エラーの札が出る。どちらでも「落ちない」ことだけは必ず確かめる。
    func testSendingAMessageDoesNotCrash() {
        tapTab("そうだん")
        // 複数行に伸びる TextField（axis: .vertical）は textView として出るが、
        // OS のバージョンによっては textField のままのこともある
        var field = app.textViews.firstMatch
        if !field.waitForExistence(timeout: 15) {
            field = app.textFields.firstMatch
            XCTAssertTrue(field.waitForExistence(timeout: 10), "相談の入力欄が見つからない")
        }
        field.tap()
        field.typeText("熱海に行きたい")

        tapButton("送る")
        // 「考え中」かエラーの札か、どちらかには必ずたどり着く
        Thread.sleep(forTimeInterval: 3)
        XCTAssertEqual(app.state, .runningForeground, "送信したあとに落ちている")
    }

    /// 保存プランを引っぱって読み直しても崩れないこと。
    func testPullToRefreshKeepsTheListAlive() {
        tapTab("保存プラン")
        expect(text: "熱海でのんびり", where: "保存プラン")

        // 引っぱる場所は保存プランにしかない文言で選ぶ（他のタブと取り違えないため）
        let header = app.staticTexts["保存した"].firstMatch
        XCTAssertTrue(header.waitForExistence(timeout: 15), "保存プランの見出しが出てこない")
        header.swipeDown(velocity: .slow)

        expect(text: "熱海でのんびり", where: "引っぱって読み直したあとの保存プラン")
        XCTAssertEqual(app.state, .runningForeground)
    }

    // MARK: - 小さな道具

    private func expect(text: String, where place: String,
                        file: StaticString = #filePath, line: UInt = #line) {
        let element = app.staticTexts[text].firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: 15),
                      "\(place)に「\(text)」が出てこない", file: file, line: line)
        XCTAssertEqual(app.state, .runningForeground,
                       "\(place)を出そうとして落ちている", file: file, line: line)
    }

    private func tapButton(_ label: String,
                           file: StaticString = #filePath, line: UInt = #line) {
        tap(app.buttons.matching(identifier: label), what: "「\(label)」のボタン",
            file: file, line: line)
    }

    /// 付箋やポラロイドは Button だが、読み上げ名は中の文言の寄せ集めになる。
    /// 名前で引くと当てにくいので、見えている文字をそのまま押す。
    private func tapText(_ text: String,
                         file: StaticString = #filePath, line: UInt = #line) {
        tap(app.staticTexts.matching(identifier: text), what: "「\(text)」",
            file: file, line: line)
    }

    /// 同じ文言が複数あっても、いま押せるものを選ぶ。
    ///
    /// TabView は一度開いたタブの中身を残すので、`firstMatch` だと裏のタブの
    /// 見えていない方をつかんでしまうことがある（そのまま押しても何も起きない）。
    private func tap(_ query: XCUIElementQuery, what: String,
                     file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(query.firstMatch.waitForExistence(timeout: 15),
                      "\(what)が見つからない", file: file, line: line)

        let deadline = Date().addingTimeInterval(10)
        repeat {
            for element in query.allElementsBoundByIndex where element.isHittable {
                element.tap()
                return
            }
        } while Date() < deadline
        XCTFail("\(what)は見つかったが、押せる状態にならない", file: file, line: line)
    }

    private func tapTab(_ name: String,
                        file: StaticString = #filePath, line: UInt = #line) {
        let tab = app.tabBars.buttons[name]
        XCTAssertTrue(tab.waitForExistence(timeout: 15),
                      "「\(name)」のタブが見つからない", file: file, line: line)
        tab.tap()
    }

    /// 戻る（ナビゲーションバーの先頭のボタン）。
    private func goBack() {
        let back = app.navigationBars.buttons.element(boundBy: 0)
        if back.exists, back.isHittable { back.tap() }
    }
}
