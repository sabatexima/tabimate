import Foundation

#if DEBUG

/// UIテストのための仕込み。**Debug ビルドにしか入らない**（配布物には含まれない）。
///
/// サインインには Google の認証が要るため、そのままだと UIテストは最初の画面から
/// 先へ進めない。結果、サインイン後の画面は一度も描画されないまま残る。
/// SwiftUI は「コンパイルは通るが実行時に落ちる／何も出ない」ことがあるので、
/// そこを機械的に確かめられるようにする。
///
/// やっていること:
///   1. 起動引数に -uiTesting があれば、ダミーのトークンを入れる
///   2. 通信を横取りして、決め打ちの応答を返す（サーバーは要らない）
enum UITestSupport {

    static var isEnabled: Bool {
        ProcessInfo.processInfo.arguments.contains("-uiTesting")
    }

    /// サインイン済みに見せかけるための、意味のない文字列。
    static let token = "ui-test-token"

    /// アプリの起動時に一度だけ呼ぶ。
    ///
    /// registerClass が効くのは URLSession.shared だけ（RemoteImage と
    /// ChatService がこれを使う）。APIClient は自前の URLSession を持っているので、
    /// そちらは APIClient 側で protocolClasses に差し込んでいる。
    static func activate() {
        guard isEnabled else { return }
        TokenBox.current = token
        if !URLProtocol.registerClass(StubURLProtocol.self) {
            print("[UITest] 通信の差し替えに失敗しました（写真と相談だけ本物に出ていきます）")
        }
    }
}

/// すべての通信を横取りして、決め打ちの応答を返す。
final class StubURLProtocol: URLProtocol {

    override class func canInit(with request: URLRequest) -> Bool { UITestSupport.isEnabled }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        let path = request.url?.path ?? ""
        let (body, contentType) = StubResponses.forPath(path)
        let response = HTTPURLResponse(
            url: request.url ?? URL(string: "https://example.invalid")!,
            statusCode: 200, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": contentType]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

/// 画面が中身入りで描画されるだけの、最低限の応答。
enum StubResponses {

    static func forPath(_ path: String) -> (Data, String) {
        // 写真は小さな画像を返す（RemoteImage が「読めなかった」表示にならないように）
        if path.contains("/reflection/photo/") {
            return (onePixelPNG, "image/png")
        }
        // プラン生成だけは SSE。「考え中」を1回はさんで、すぐ出来上がりにする
        if path.hasSuffix("/send_message") {
            let stream = """
            data: {"status":"thinking"}\n\n\
            data: {"status":"OK","id":"r1"}\n\n
            """
            return (Data(stream.utf8), "text/event-stream")
        }
        return (Data(json(for: path).utf8), "application/json")
    }

    private static func json(for path: String) -> String {
        switch true {
        case path.hasSuffix("/auth/app/me"):
            return #"{"status":"OK","user":{"email":"tester@example.com","name":"てく"}}"#

        case path.hasSuffix("/api/ideas"):
            return """
            {"status":"OK","ideas":[
              {"emoji":"♨️","label":"温泉でほっこり","prompt":"温泉でゆっくり過ごす旅がしたい"},
              {"emoji":"🍡","label":"食べ歩き日帰り","prompt":"近場で食べ歩きの日帰り旅がしたい"},
              {"emoji":"🎨","label":"ひとり美術館めぐり","prompt":"一人で美術館をめぐる旅がしたい"}]}
            """

        case path.hasSuffix("/get_my_plans"):
            return #"{"status":"OK","plans":[\#(plan)]}"#

        case path.hasSuffix("/get_shared_plans"):
            return #"{"status":"OK","plans":[]}"#

        case path.hasSuffix("/api/chat_messages"):
            return """
            {"status":"OK","messages":[
              {"role":"user","content":"熱海に行きたい","request_id":"r1","plan":null},
              {"role":"ai","content":"プランを作りました","request_id":"r1","plan":{
                 "destination":"熱海","travel_date":"8月14日","duration":"1泊2日",
                 "num_people":2,"budget_limit":30000,"departure_location":"東京",
                 "total_per_person":24000,"status":"approved","feedback":"よい旅を",
                 "themes":["温泉"],"spots":["起雲閣","熱海城"],"restaurants":["おさかな食堂"],
                 "accommodation":["ホテル熱海"],"schedule":["09:00 出発","12:00 昼食"],
                 "budget_estimate":["交通費 4,000円","宿泊 12,000円"]}}]}
            """

        case path.contains("/reflection/api/digest"):
            return """
            {"year":"2026","years":["2026","2025"],"photo_total":12,
             "stickers":["海がきれいだった","波の音がずっと聞こえてた"],
             "trips":[\(trip)]}
            """

        case path.contains("/reflection/api/trips/"):
            return """
            {"trip":\(trip),
             "photos":[{"id":11,"url":"/reflection/photo/a.jpg","thumb_url":"/reflection/photo/t.jpg",
                        "taken_at":"2026-08-14 09:00:00","lat":35.09,"lng":139.07},
                       {"id":12,"url":"/reflection/photo/b.jpg","thumb_url":"/reflection/photo/t2.jpg",
                        "taken_at":null,"lat":null,"lng":null}],
             "stickers":[{"id":5,"text":"波の音がずっと聞こえてた"}],
             "best_shots":[{"url":"/reflection/photo/a.jpg","thumb_url":"/reflection/photo/t.jpg",
                            "reason":"光のはいり方がやわらかくて、旅のはじまりの感じがした"}],
             "footprints":[{"lat":35.09,"lng":139.07,"thumb":"/reflection/photo/t.jpg",
                            "taken":"2026-08-14"}]}
            """

        case path.hasSuffix("/reflection/api/trips"):
            return #"{"trips":[\#(trip)],"shared_trips":[]}"#

        case path.contains("/share/"):
            return """
            {"editable_supported":true,
             "links":[{"id":1,"token":"abc","url":"https://example.com/s/abc","permission":"view"}],
             "grants":[{"id":7,"grantee_email":"friend@example.com","permission":"edit"}]}
            """

        case path.contains("/api/plan_geo/"):
            return """
            {"spot_coords":[{"name":"起雲閣","lat":35.096,"lng":139.070},
                            {"name":"熱海城","lat":35.089,"lng":139.063}],
             "restaurant_coords":[{"name":"おさかな食堂","lat":35.095,"lng":139.073}],
             "accommodation_coords":[{"name":"ホテル熱海","lat":35.098,"lng":139.075}]}
            """

        default:
            // 個別に用意していないもの（保存・削除・生成など）。
            // 呼び出し側がどの形で読もうとしても通るよう、必要な鍵をまとめて入れておく
            // （id=保存の結果 / count=写真の枚数 / items=持ち物 / active=生成中か）。
            return #"""
            {"status":"OK","id":1,"count":1,"active":false,"is_favorite":true,
             "items":["水着","日焼け止め","酔い止め"],
             "token":"abc","url":"https://example.com/s/abc","permission":"view",
             "email":"friend@example.com","grantee_email":"friend@example.com"}
            """#
        }
    }

    private static let plan = """
    {"id":1,"destination":"熱海でのんびり","travel_date":"2026-08-14","duration":"1泊2日",
     "num_people":2,"budget_limit":30000,"departure_location":"東京","transport_cost":4000,
     "total_per_person":24000,"themes":["温泉","海"],"special_requirements":[],
     "spots":["起雲閣","熱海城"],"restaurants":["おさかな食堂"],"accommodation":["ホテル熱海"],
     "schedule":["09:00 出発","10:00 熱海城","12:00 おさかな食堂で昼食","14:00 起雲閣",
                 "17:00 ホテル熱海にチェックイン"],
     "budget_estimate":["交通費 4,000円","宿泊 12,000円","食事 5,000円","合計 24,000円"],
     "packing_list":["水着","日焼け止め"],"actual_total":22000,"rating":4,
     "rating_comment":"のんびりできた","created_at":"2026-08-16",
     "depart_iso":"2099-08-14",
     "spot_coords":[{"name":"起雲閣","lat":35.096,"lng":139.070},
                    {"name":"熱海城","lat":35.089,"lng":139.063}],
     "restaurant_coords":[{"name":"おさかな食堂","lat":35.095,"lng":139.073}],
     "accommodation_coords":[{"name":"ホテル熱海","lat":35.098,"lng":139.075}]}
    """

    private static let trip = """
    {"id":1,"title":"熱海でのんびり","start_date":"2026-08-14","end_date":"2026-08-15",
     "is_favorite":1,"photo_count":2,"cover_url":"/reflection/photo/t.jpg",
     "stickers_preview":["海がきれいだった"],"created_at":"2026-08-16"}
    """

    /// 1x1 の透明PNG。
    private static let onePixelPNG = Data(base64Encoded: """
    iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==
    """)!
}

#endif
