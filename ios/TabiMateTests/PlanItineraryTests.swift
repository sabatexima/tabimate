import XCTest
@testable import TabiMate

/// 地図のピンを「移動する順番」に並べる処理。
/// Web版（static/js/plan-map.js の orderByItinerary）と同じ答えになることを固定する。
final class PlanItineraryTests: XCTestCase {

    private func pins(_ names: [String]) -> [PlanPin] {
        names.map { PlanPin(name: $0, category: .spot, lat: 35, lng: 139) }
    }

    private func order(_ names: [String], _ schedule: [String]) -> [String] {
        PlanItinerary.ordered(pins(names), schedule: schedule).map(\.name)
    }

    func testOrdersByFirstAppearanceInSchedule() {
        XCTAssertEqual(
            order(["金閣寺", "銀閣寺", "清水寺"],
                  ["09:00 清水寺", "13:00 銀閣寺", "15:00 金閣寺"]),
            ["清水寺", "銀閣寺", "金閣寺"]
        )
    }

    func testMatchesAbbreviatedNames() {
        // スケジュール側は「熱海銀座おさかな食堂」→「おさかな食堂で昼食」と省略されがち
        XCTAssertEqual(
            order(["起雲閣", "熱海銀座おさかな食堂", "熱海城", "ホテル熱海"],
                  ["09:00 熱海駅に到着", "10:00 熱海城で景色を楽しむ",
                   "12:00 おさかな食堂で昼食", "14:00 起雲閣を見学",
                   "17:00 ホテル熱海にチェックイン"]),
            ["熱海城", "熱海銀座おさかな食堂", "起雲閣", "ホテル熱海"]
        )
    }

    func testGenericWordsDoNotCauseFalseMatches() {
        // 「レストランで食事」がどちらの店を指すか分からないので、断片照合には使わない。
        // 照合できたのが1件以下なら並べ替えずに元の順を保つ
        XCTAssertEqual(
            order(["ガーデンレストラン", "海鮮レストラン", "美術館"],
                  ["11:00 レストランで食事", "14:00 美術館へ"]),
            ["ガーデンレストラン", "海鮮レストラン", "美術館"]
        )
    }

    func testNormalizesWidthAndSpaces() {
        // 全角・半角、空白の有無で照合が外れないこと
        XCTAssertEqual(
            order(["Ａ　スポット", "Bスポット"], ["10:00 Bスポット", "12:00 A スポット"]),
            ["Bスポット", "Ａ　スポット"]
        )
    }

    func testUnmatchedPinsGoToTheEnd() {
        XCTAssertEqual(
            order(["謎の場所", "浅草寺", "上野公園"],
                  ["10:00 上野公園を散歩", "14:00 浅草寺にお参り"]),
            ["上野公園", "浅草寺", "謎の場所"]
        )
    }

    func testEmptyScheduleKeepsOriginalOrder() {
        XCTAssertEqual(
            order(["東京タワー", "スカイツリー", "浅草寺"], []),
            ["東京タワー", "スカイツリー", "浅草寺"]
        )
    }

    func testShortNamesAreNotUsedAsFragments() {
        // 「あ」のような短い名前で誤マッチしない（断片は4文字以上）
        XCTAssertEqual(
            order(["あ", "いろは食堂", "にほへと museum"],
                  ["10:00 にほへと museum", "12:00 いろは食堂"]),
            ["にほへと museum", "いろは食堂", "あ"]
        )
    }

    func testNumbersAreContinuousAcrossCategories() {
        let built = PlanItinerary.ordered([
            PlanPin(name: "起雲閣", category: .spot, lat: 35.10, lng: 139.07),
            PlanPin(name: "おさかな食堂", category: .restaurant, lat: 35.09, lng: 139.06),
            PlanPin(name: "ホテル熱海", category: .accommodation, lat: 35.11, lng: 139.08),
        ], schedule: ["10:00 起雲閣", "12:00 おさかな食堂", "17:00 ホテル熱海"])

        // 観光・グルメ・宿をまたいで 1,2,3 と続き番号になる
        XCTAssertEqual(built.map(\.order), [1, 2, 3])
        XCTAssertEqual(built.map(\.category), [.spot, .restaurant, .accommodation])
    }

    func testPinsAreBuiltOnlyForKnownCoordinates() {
        // 座標が取れなかったスポットは地図に出さない
        let plan = try! JSONDecoder().decode(TravelPlan.self, from: Data("""
        {"id": 1, "destination": "熱海", "spots": ["起雲閣", "座標不明の場所"],
         "restaurants": [], "accommodation": [], "schedule": []}
        """.utf8))

        let geo = try! JSONDecoder().decode(PlanGeo.self, from: Data("""
        {"spot_coords": [{"name": "起雲閣", "lat": 35.10, "lng": 139.07}],
         "restaurant_coords": [], "accommodation_coords": []}
        """.utf8))

        let built = PlanItinerary.pins(plan: plan, geo: geo)
        XCTAssertEqual(built.map(\.name), ["起雲閣"])
    }

    func testOverlappingPinsAreSpreadApart() {
        // まったく同じ座標の3件が、重なって1本に見えないようにずらされる
        let geo = try! JSONDecoder().decode(PlanGeo.self, from: Data("""
        {"spot_coords": [{"name": "A", "lat": 35.0, "lng": 139.0},
                         {"name": "B", "lat": 35.0, "lng": 139.0},
                         {"name": "C", "lat": 35.0, "lng": 139.0}],
         "restaurant_coords": [], "accommodation_coords": []}
        """.utf8))
        var plan = try! JSONDecoder().decode(TravelPlan.self, from: Data(#"{"id": 1}"#.utf8))
        plan.spots = ["A", "B", "C"]

        let built = PlanItinerary.pins(plan: plan, geo: geo)
        let coordinates = Set(built.map { "\($0.lat),\($0.lng)" })
        XCTAssertEqual(coordinates.count, 3, "同じ位置のピンが重なったまま")
    }

    // MARK: - 日ごと

    func testRecognisesDayHeaders() {
        XCTAssertEqual(PlanItinerary.dayNumber(of: "1日目"), 1)
        XCTAssertEqual(PlanItinerary.dayNumber(of: "【2日目】"), 2)
        XCTAssertEqual(PlanItinerary.dayNumber(of: "3日目：熱海へ"), 3)
        XCTAssertEqual(PlanItinerary.dayNumber(of: "１日目"), 1)          // 全角
        XCTAssertEqual(PlanItinerary.dayNumber(of: "  [10日目] 帰路"), 10)
        XCTAssertNil(PlanItinerary.dayNumber(of: "10:00 出発"))
        // 判定は先頭一致（agents.py の _days_in・plan-map.js と同じ）。行頭が「N日目」なら見出し
        XCTAssertEqual(PlanItinerary.dayNumber(of: "2日目の予定は未定"), 2)
        XCTAssertNil(PlanItinerary.dayNumber(of: ""))
    }

    func testAssignsPinsToTheDaysTheyAppearIn() {
        var built = [PlanPin(name: "熱海城", category: .spot, lat: 35, lng: 139),
                     PlanPin(name: "ホテル熱海", category: .accommodation, lat: 35, lng: 139),
                     PlanPin(name: "起雲閣", category: .spot, lat: 35, lng: 139),
                     PlanPin(name: "謎の場所", category: .spot, lat: 35, lng: 139)]
        PlanItinerary.assignDays(&built, schedule: [
            "1日目", "10:00 熱海城", "17:00 ホテル熱海にチェックイン",
            "2日目", "09:00 ホテル熱海を出発", "10:00 起雲閣",
        ])
        XCTAssertEqual(built[0].days, [1])
        XCTAssertEqual(built[1].days, [1, 2])      // 宿は両日に出る
        XCTAssertEqual(built[2].days, [2])
        XCTAssertEqual(built[3].days, [])          // 見つからなければ空
        XCTAssertEqual(PlanItinerary.selectableDays(built), [1, 2])
    }

    func testSingleDayPlansHaveNoDayFilter() {
        var built = [PlanPin(name: "熱海城", category: .spot, lat: 35, lng: 139)]
        PlanItinerary.assignDays(&built, schedule: ["09:00 熱海城", "12:00 昼食"])
        XCTAssertEqual(built[0].days, [])
        XCTAssertEqual(PlanItinerary.selectableDays(built), [])

        // 見出しはあっても、ピンのある日が1日だけなら切り替えは出さない
        var two = [PlanPin(name: "熱海城", category: .spot, lat: 35, lng: 139)]
        PlanItinerary.assignDays(&two, schedule: ["1日目", "10:00 熱海城", "2日目", "終日フリー"])
        XCTAssertEqual(PlanItinerary.selectableDays(two), [])
    }
}

/// 年間ダイジェストの月まとめ。
final class DigestGroupingTests: XCTestCase {

    private func digest(_ trips: String) throws -> Digest {
        try JSONDecoder().decode(Digest.self, from: Data("""
        {"year": "2026", "years": ["2026"], "trips": [\(trips)],
         "photo_total": 0, "stickers": []}
        """.utf8))
    }

    func testGroupsByMonthInOrder() throws {
        let d = try digest("""
        {"id": 1, "title": "夏", "start_date": "2026-08-14"},
        {"id": 2, "title": "冬", "start_date": "2026-01-09"},
        {"id": 3, "title": "夏その2", "start_date": "2026-08-20"}
        """)
        let groups = d.monthGroups
        XCTAssertEqual(groups.map(\.month), [1, 8])          // 古い順
        XCTAssertEqual(groups[1].trips.map(\.id), [1, 3])    // 同じ月はまとまる
        XCTAssertEqual(groups[0].label, "1月")
    }

    func testFallsBackToCreatedAtThenUnknown() throws {
        let d = try digest("""
        {"id": 1, "title": "日付なし", "created_at": "2026-03-02 10:00:00"},
        {"id": 2, "title": "まったく不明"}
        """)
        XCTAssertEqual(d.monthGroups.map(\.month), [0, 3])
        XCTAssertEqual(d.monthGroups[0].label, "日にちのない旅")
    }
}
