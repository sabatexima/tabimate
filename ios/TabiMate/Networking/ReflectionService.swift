import Foundation

extension Notification.Name {
    /// おもいでが増えた・減ったときの合図（一覧とダイジェストを読み直す）。
    static let tripsChanged = Notification.Name("tabimate.tripsChanged")
}

/// 旅の振り返り（おもいで）のAPI。
enum ReflectionService {

    /// 写真や付箋を変える操作は、自分の旅と共有された旅で入口が違う。
    ///   自分の旅  : /reflection/trips/<id>/...
    ///   共有の旅  : /shared/trip/<id>/...   （編集権限がある場合のみ通る）
    /// 呼び出し側が Trip.isShared を渡す。
    private static func editBase(tripId: Int, shared: Bool) -> String {
        shared ? "shared/trip/\(tripId)" : "reflection/trips/\(tripId)"
    }

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

    /// 名前と日にちを直す。
    ///
    /// サーバーの PATCH は1回につき1項目しか見ない（表紙 → 日付 → タイトルの順で
    /// 最初に見つかったものだけを更新して返す）ので、まとめて送らず順に呼ぶ。
    static func updateTrip(tripId: Int, title: String?, startDate: String?, endDate: String?) async throws {
        if let title, !title.isEmpty {
            try await patch(tripId: tripId, json: ["title": title])
        }
        if startDate != nil || endDate != nil {
            // 空文字は「日付を消す」の意味。サーバーが None に読み替える
            try await patch(tripId: tripId, json: ["start_date": startDate ?? "",
                                                   "end_date": endDate ?? ""])
        }
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }

    private static func patch(tripId: Int, json: [String: Any]) async throws {
        let body = try JSONSerialization.data(withJSONObject: json)
        let req = APIClient.request("reflection/trips/\(tripId)", method: "PATCH",
                                    body: body, contentType: "application/json")
        try await APIClient.shared.send(req)
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
    ///
    /// 写真は撮ったままのデータで送る（作り直すとEXIFが落ち、撮影日時と場所が
    /// 取れなくなるため）。そのぶんファイル名は中身に合わせて正しく付ける必要がある。
    static func uploadPhotos(tripId: Int, shared: Bool, images: [Data]) async throws -> Int {
        let boundary = "tabimate-\(UUID().uuidString)"
        var body = Data()
        for (index, image) in images.enumerated() {
            let kind = ImageKind.detect(image)
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"photos\"; "
                        + "filename=\"photo\(index)\(kind.ext)\"\r\n")
            body.append("Content-Type: \(kind.mime)\r\n\r\n")
            body.append(image)
            body.append("\r\n")
        }
        body.append("--\(boundary)--\r\n")

        var req = APIClient.request("\(editBase(tripId: tripId, shared: shared))/photos",
                                    method: "POST", body: body,
                                    contentType: "multipart/form-data; boundary=\(boundary)")
        // 枚数が多いと時間がかかる（サーバー側でEXIF抽出とサムネイル生成をしている）
        req.timeoutInterval = 300
        let res = try await APIClient.shared.send(req, as: UploadResponse.self)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
        return res.count
    }

    static func deletePhoto(tripId: Int, shared: Bool, photoId: Int) async throws {
        let req = APIClient.request(
            "\(editBase(tripId: tripId, shared: shared))/photos/\(photoId)", method: "DELETE")
        try await APIClient.shared.send(req)
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }

    // MARK: - ちゃむの解釈

    /// 写真から思い出の言葉（付箋）を作る。
    static func generateStickers(tripId: Int, shared: Bool) async throws {
        var req = APIClient.request(
            "\(editBase(tripId: tripId, shared: shared))/stickers/generate", method: "POST")
        req.timeoutInterval = 180
        try await APIClient.shared.send(req)
    }

    /// 飾りたい一枚を選んでもらう（写真が3枚以上必要）。
    static func generateBestShots(tripId: Int) async throws {
        var req = APIClient.request("reflection/trips/\(tripId)/best_shots", method: "POST")
        req.timeoutInterval = 180
        try await APIClient.shared.send(req)
    }

    static func deleteSticker(tripId: Int, shared: Bool, stickerId: Int) async throws {
        let req = APIClient.request(
            "\(editBase(tripId: tripId, shared: shared))/stickers/\(stickerId)", method: "DELETE")
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

/// 画像の種類を中身の先頭バイトから見分ける。
///
/// サーバーは「ファイル名の拡張子」だけで受け入れとHEIC変換を判断している
/// （src/services/images.py の normalize）。iPhone の写真はたいてい HEIC なので、
/// これを .jpg と名乗って送ると変換されず、Web版で開けない写真になってしまう。
enum ImageKind {
    case jpeg, png, heic, webp, gif

    var ext: String {
        switch self {
        case .jpeg: return ".jpg"
        case .png:  return ".png"
        case .heic: return ".heic"
        case .webp: return ".webp"
        case .gif:  return ".gif"
        }
    }

    var mime: String {
        switch self {
        case .jpeg: return "image/jpeg"
        case .png:  return "image/png"
        case .heic: return "image/heic"
        case .webp: return "image/webp"
        case .gif:  return "image/gif"
        }
    }

    /// 判別できないときは jpeg として扱う（サーバーが受け入れる形の中で最も無難）。
    static func detect(_ data: Data) -> ImageKind {
        let head = [UInt8](data.prefix(16))
        guard head.count >= 12 else { return .jpeg }

        func matches(_ pattern: [UInt8], at offset: Int) -> Bool {
            guard head.count >= offset + pattern.count else { return false }
            return Array(head[offset..<(offset + pattern.count)]) == pattern
        }

        if matches([0xFF, 0xD8, 0xFF], at: 0) { return .jpeg }
        if matches([0x89, 0x50, 0x4E, 0x47], at: 0) { return .png }   // \x89PNG
        if matches([0x47, 0x49, 0x46, 0x38], at: 0) { return .gif }   // GIF8
        if matches([0x52, 0x49, 0x46, 0x46], at: 0),                  // RIFF
           matches([0x57, 0x45, 0x42, 0x50], at: 8) {                 // WEBP
            return .webp
        }
        // ....ftyp<brand>  HEIF系のブランドかどうかで判定する
        if matches([0x66, 0x74, 0x79, 0x70], at: 4) {                 // ftyp
            let brand = String(bytes: head[8..<12], encoding: .ascii) ?? ""
            let heifBrands = ["heic", "heix", "hevc", "hevx", "heim", "heis",
                              "hevm", "hevs", "mif1", "msf1"]
            if heifBrands.contains(brand) { return .heic }
        }
        return .jpeg
    }
}
