import XCTest
@testable import TabiMate

/// サーバーが実際に返す形のJSONを、そのまま読めるかを固定する。
/// キー名のずれ（grantee_email など）は画面が丸ごと空になる形で表れるため、
/// ここで気づけるようにしておく。
final class ModelDecodingTests: XCTestCase {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(type, from: Data(json.utf8))
    }

    // MARK: - しおり

    func testTravelPlanDecodesServerShape() throws {
        let plan = try decode(TravelPlan.self, """
        {"id": 3, "destination": "熱海", "travel_date": "2026-08-14",
         "duration": "1泊2日", "num_people": 2, "budget_limit": 30000,
         "departure_location": "東京", "transport_cost": 4000,
         "total_per_person": 24000, "themes": ["温泉"], "special_requirements": [],
         "spots": ["起雲閣"], "restaurants": [], "accommodation": [],
         "schedule": ["09:00 出発"], "budget_estimate": [], "packing_list": ["水着"],
         "actual_total": null, "rating": 4, "rating_comment": "よかった",
         "created_at": "2026-08-16", "depart_iso": "2026-08-14"}
        """)

        XCTAssertEqual(plan.id, 3)
        XCTAssertEqual(plan.destination, "熱海")
        XCTAssertEqual(plan.totalPerPerson, 24000)
        XCTAssertNil(plan.actualTotal)          // null は nil として読む
        XCTAssertEqual(plan.packingList, ["水着"])
        XCTAssertEqual(plan.summaryLine, "1泊2日・2人・2026-08-14")
        XCTAssertTrue(plan.isOwner)             // permission が無い＝自分のしおり
    }

    func testTravelPlanSurvivesMissingFields() throws {
        // 古いプランや作りかけでも、id さえあれば落ちない
        let plan = try decode(TravelPlan.self, #"{"id": 1}"#)
        XCTAssertEqual(plan.destination, "旅のプラン")
        XCTAssertEqual(plan.spots, [])
        XCTAssertEqual(plan.summaryLine, "")
        XCTAssertNil(plan.countdownLabel)
    }

    func testSharedPlanIsNotOwned() throws {
        let plan = try decode(TravelPlan.self,
                              #"{"id": 1, "destination": "京都", "permission": "view", "grant_id": 12}"#)
        XCTAssertTrue(plan.isShared)
        XCTAssertFalse(plan.isOwner)
        XCTAssertEqual(plan.grantId, 12)
    }

    // MARK: - おもいで

    func testTripDecodesFavoriteAsNumber() throws {
        // サーバーは 0/1 で返す（true/false ではない）
        let trip = try decode(Trip.self, """
        {"id": 1, "title": "熱海でのんびり", "start_date": "2026-08-14",
         "end_date": "2026-08-16", "is_favorite": 1, "photo_count": 12,
         "cover_url": "/reflection/photo/thumb/a.jpg",
         "stickers_preview": ["海がきれいだった"], "created_at": "2026-08-16"}
        """)
        XCTAssertTrue(trip.isFavorite)
        XCTAssertEqual(trip.photoCount, 12)
        XCTAssertEqual(trip.stickersPreview, ["海がきれいだった"])
    }

    func testTripPermissionDecidesWhatIsAllowed() throws {
        let mine = try decode(Trip.self, #"{"id": 1, "title": "自分の旅", "is_favorite": 0}"#)
        XCTAssertTrue(mine.isOwner)
        XCTAssertTrue(mine.canEditPhotos)

        let readOnly = try decode(Trip.self,
                                  #"{"id": 2, "title": "見るだけ", "permission": "view"}"#)
        XCTAssertFalse(readOnly.isOwner)
        XCTAssertFalse(readOnly.canEditPhotos)

        // 編集権限をもらっていても、名前の変更や共有は所有者だけ
        let editable = try decode(Trip.self,
                                  #"{"id": 3, "title": "直せる", "permission": "edit"}"#)
        XCTAssertFalse(editable.isOwner)
        XCTAssertTrue(editable.canEditPhotos)
    }

    func testTripDateRange() throws {
        func range(_ start: String?, _ end: String?) throws -> String? {
            var json = #"{"id": 1, "title": "t""#
            if let start { json += #", "start_date": "\#(start)""# }
            if let end { json += #", "end_date": "\#(end)""# }
            return try decode(Trip.self, json + "}").dateRange
        }
        // 同じ年なら後半は月日だけ
        XCTAssertEqual(try range("2026-08-14", "2026-08-16"), "2026/08/14 〜 08/16")
        // 年をまたぐときは省略しない
        XCTAssertEqual(try range("2026-12-30", "2027-01-02"), "2026/12/30 〜 2027/01/02")
        // 日帰り・片方だけ
        XCTAssertEqual(try range("2026-08-14", "2026-08-14"), "2026/08/14")
        XCTAssertEqual(try range("2026-08-14", nil), "2026/08/14")
        XCTAssertNil(try range(nil, nil))
    }

    func testTripDetailAndBestShot() throws {
        let detail = try decode(TripDetail.self, """
        {"trip": {"id": 1, "title": "熱海", "photo_count": 2},
         "photos": [{"id": 11, "url": "/p/a.jpg", "thumb_url": "/t/a.jpg",
                     "taken_at": "2026-08-14 09:00:00", "lat": 35.09, "lng": 139.07},
                    {"id": 12, "url": "/p/b.jpg", "thumb_url": null,
                     "taken_at": null, "lat": null, "lng": null}],
         "stickers": [{"id": 5, "text": "波の音"}],
         "best_shots": [{"url": "/p/a.jpg", "thumb_url": "/t/a.jpg", "reason": "光がきれい"}],
         "footprints": [{"lat": 35.09, "lng": 139.07, "thumb": "/t/a.jpg", "taken": "2026-08-14"}]}
        """)
        XCTAssertEqual(detail.photos.count, 2)
        // サムネイルが無い写真は原寸で表示する
        XCTAssertEqual(detail.photos[1].displayURL, "/p/b.jpg")
        XCTAssertEqual(detail.bestShots.first?.reason, "光がきれい")
        XCTAssertEqual(detail.footprints.count, 1)
    }

    // MARK: - 共有

    func testShareGrantReadsGranteeEmail() throws {
        // サーバーは grantee_email という名前で返す。email で読もうとすると
        // 共有一覧が丸ごと失敗する
        let state = try decode(ShareState.self, """
        {"editable_supported": true,
         "links": [{"id": 1, "token": "abc", "url": "https://example.com/s/abc",
                    "permission": "view"}],
         "grants": [{"id": 7, "grantee_email": "friend@example.com",
                     "permission": "edit", "created_at": "2026-08-16"}]}
        """)
        XCTAssertEqual(state.grants.first?.email, "friend@example.com")
        XCTAssertEqual(state.grants.first?.permission, "edit")
        XCTAssertEqual(state.links.first?.url, "https://example.com/s/abc")
        XCTAssertTrue(state.editableSupported)
    }

    // MARK: - チャット

    func testChatMessageCarriesStructuredPlan() throws {
        let messages = try decode([ChatMessage].self, """
        [{"role": "user", "content": "熱海に行きたい", "request_id": "r1", "plan": null},
         {"role": "ai", "content": "<div>…</div>", "request_id": "r1",
          "plan": {"destination": "熱海", "spots": ["起雲閣"], "status": "approved"}}]
        """)
        XCTAssertTrue(messages[0].isUser)
        XCTAssertNil(messages[0].plan)
        XCTAssertEqual(messages[1].plan?.destination, "熱海")
        XCTAssertFalse(messages[1].plan?.isInfeasible ?? true)
    }

    func testDraftPlanRoundTripsForSaving() throws {
        // 提示されたプランは、そのまま /save_plan へ送り返せなければならない
        let original = try decode(DraftPlan.self, """
        {"destination": "熱海", "travel_date": "2026-08-14", "duration": "1泊2日",
         "num_people": 2, "budget_limit": 30000, "departure_location": "東京",
         "total_per_person": 24000, "themes": ["温泉"], "spots": ["起雲閣"],
         "schedule": ["09:00 出発"], "status": "approved", "feedback": "よい旅を"}
        """)
        let encoded = try JSONEncoder().encode(original)
        let object = try JSONSerialization.jsonObject(with: encoded) as? [String: Any]
        // サーバーが読むキー名（スネークケース）で出ていること
        XCTAssertEqual(object?["travel_date"] as? String, "2026-08-14")
        XCTAssertEqual(object?["num_people"] as? Int, 2)
        XCTAssertEqual(object?["total_per_person"] as? Int, 24000)
    }
}
