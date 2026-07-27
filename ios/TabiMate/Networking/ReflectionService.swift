import Foundation

extension Notification.Name {
    /// おもいでが増えた・減ったときの合図（一覧とダイジェストを読み直す）。
    static let tripsChanged = Notification.Name("tabimate.tripsChanged")
}

/// 旅の振り返り（おもいで）のAPI。
enum ReflectionService {

    // MARK: - 読み取り

    /// 自分の旅と、共有された旅。
    static func trips() async throws -> (mine: [Trip], shared: [Trip]) {
        let res = try await APIClient.shared.get("reflection/api/trips", as: TripsResponse.self)
        return (res.trips, res.sharedTrips)
    }

    static func detail(tripId: Int) async throws -> TripDetail {
        try await APIClient.shared.get("reflection/api/trips/\(tripId)", as: TripDetail.self)
    }

    /// 年間ダイジェスト。year を省くといちばん新しい年。
    static func digest(year: String? = nil) async throws -> Digest {
        try await APIClient.shared.get(
            "reflection/api/digest",
            query: year.map { ["year": $0] } ?? [:],
            as: Digest.self
        )
    }

    // MARK: - 旅の作成・編集

    static func createTrip(title: String, startDate: String?, endDate: String?) async throws -> Int {
        var json: [String: Any] = ["title": title]
        if let startDate, !startDate.isEmpty { json["start_date"] = startDate }
        if let endDate, !endDate.isEmpty { json["end_date"] = endDate }
        let created = try await APIClient.shared.post("reflection/trips", json: json,
                                                      as: CreatedTrip.self)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
        return created.id
    }

    static func updateTrip(tripId: Int, title: String?, startDate: String?, endDate: String?) async throws {
        var json: [String: Any] = [:]
        if let title { json["title"] = title }
        // 空文字は「日付を消す」の意味でそのまま送る
        if let startDate { json["start_date"] = startDate }
        if let endDate { json["end_date"] = endDate }
        let body = try JSONSerialization.data(withJSONObject: json)
        let req = APIClient.request("reflection/trips/\(tripId)", method: "PATCH",
                                    body: body, contentType: "application/json")
        try await APIClient.shared.send(req)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }

    /// 一覧の表紙にする写真を選ぶ。
    static func setCover(tripId: Int, photoId: Int) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["cover_photo_id": photoId])
        let req = APIClient.request("reflection/trips/\(tripId)", method: "PATCH",
                                    body: body, contentType: "application/json")
        try await APIClient.shared.send(req)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }

    static func deleteTrip(tripId: Int) async throws {
        let req = APIClient.request("reflection/trips/\(tripId)", method: "DELETE")
        try await APIClient.shared.send(req)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }

    /// お気に入りを切り替える。返り値は切り替え後の状態。
    static func setFavorite(tripId: Int, favorite: Bool) async throws -> Bool {
        let body = try JSONSerialization.data(withJSONObject: ["favorite": favorite])
        let req = APIClient.request("reflection/trips/\(tripId)/favorite", method: "PATCH",
                                    body: body, contentType: "application/json")
        return try await APIClient.shared.send(req, as: FavoriteResponse.self).isFavorite
    }

    // MARK: - 写真

    /// 写真をまとめて送る。1回あたり50枚までなので、多いときは分けて呼ぶこと。
    static func uploadPhotos(tripId: Int, images: [Data]) async throws -> Int {
        let boundary = "tabimate-\(UUID().uuidString)"
        var body = Data()
        for (index, image) in images.enumerated() {
            body.append("--\(boundary)\r\n")
            // サーバーは拡張子で受け入れを判定するので、必ず付けて送る
            body.append("Content-Disposition: form-data; name=\"photos\"; filename=\"photo\(index).jpg\"\r\n")
            body.append("Content-Type: image/jpeg\r\n\r\n")
            body.append(image)
            body.append("\r\n")
        }
        body.append("--\(boundary)--\r\n")

        var req = APIClient.request("reflection/trips/\(tripId)/photos", method: "POST",
                                    body: body,
                                    contentType: "multipart/form-data; boundary=\(boundary)")
        // 枚数が多いと時間がかかる（サーバー側でEXIF抽出とサムネイル生成をしている）
        req.timeoutInterval = 300
        let res = try await APIClient.shared.send(req, as: UploadResponse.self)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
        return res.count
    }

    static func deletePhoto(tripId: Int, photoId: Int) async throws {
        let req = APIClient.request("reflection/trips/\(tripId)/photos/\(photoId)", method: "DELETE")
        try await APIClient.shared.send(req)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }

    // MARK: - ちゃむの解釈

    /// 写真から思い出の言葉（付箋）を作る。
    static func generateStickers(tripId: Int) async throws {
        var req = APIClient.request("reflection/trips/\(tripId)/stickers/generate", method: "POST")
        req.timeoutInterval = 180
        try await APIClient.shared.send(req)
    }

    /// 飾りたい一枚を選んでもらう（写真が3枚以上必要）。
    static func generateBestShots(tripId: Int) async throws {
        var req = APIClient.request("reflection/trips/\(tripId)/best_shots", method: "POST")
        req.timeoutInterval = 180
        try await APIClient.shared.send(req)
    }

    static func deleteSticker(tripId: Int, stickerId: Int) async throws {
        let req = APIClient.request("reflection/trips/\(tripId)/stickers/\(stickerId)",
                                    method: "DELETE")
        try await APIClient.shared.send(req)
    }

    // MARK: - 応答の形

    private struct TripsResponse: Codable {
        let trips: [Trip]
        let sharedTrips: [Trip]
        enum CodingKeys: String, CodingKey {
            case trips
            case sharedTrips = "shared_trips"
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            trips = (try? c.decode([Trip].self, forKey: .trips)) ?? []
            sharedTrips = (try? c.decode([Trip].self, forKey: .sharedTrips)) ?? []
        }
    }

    private struct CreatedTrip: Codable { let id: Int }
    private struct UploadResponse: Codable { let count: Int }
    private struct FavoriteResponse: Codable {
        let isFavorite: Bool
        enum CodingKeys: String, CodingKey { case isFavorite = "is_favorite" }
    }
}

extension Data {
    /// multipart の組み立て用。文字列部分は必ずUTF-8で足す。
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}
