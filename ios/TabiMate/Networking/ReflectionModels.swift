import Foundation

/// 旅の振り返り（おもいで）まわりの型。
/// 形は src/db_reflection.py と src/views/reflection.py の返り値に合わせている。

// MARK: - 旅

struct Trip: Codable, Identifiable, Hashable {
    var id: Int
    var title: String
    var startDate: String?
    var endDate: String?
    var isFavorite: Bool
    var photoCount: Int
    var coverURL: String?
    var stickersPreview: [String]
    var createdAt: String?
    /// 共有された旅のときだけ入る（view / edit）。
    var permission: String?
    var grantId: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, permission
        case startDate = "start_date"
        case endDate = "end_date"
        case isFavorite = "is_favorite"
        case photoCount = "photo_count"
        case coverURL = "cover_url"
        case stickersPreview = "stickers_preview"
        case createdAt = "created_at"
        case grantId = "grant_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id              = try c.decode(Int.self, forKey: .id)
        title           = (try? c.decode(String.self, forKey: .title)) ?? "（無題の旅）"
        startDate       = try? c.decode(String.self, forKey: .startDate)
        endDate         = try? c.decode(String.self, forKey: .endDate)
        // サーバーは 0/1 で返す
        isFavorite      = ((try? c.decode(Int.self, forKey: .isFavorite)) ?? 0) != 0
        photoCount      = (try? c.decode(Int.self, forKey: .photoCount)) ?? 0
        coverURL        = try? c.decode(String.self, forKey: .coverURL)
        stickersPreview = (try? c.decode([String].self, forKey: .stickersPreview)) ?? []
        createdAt       = try? c.decode(String.self, forKey: .createdAt)
        permission      = try? c.decode(String.self, forKey: .permission)
        grantId         = try? c.decode(Int.self, forKey: .grantId)
    }

    /// 共有された旅かどうか（自分の旅には permission が付かない）。
    var isShared: Bool { permission != nil }
    var canEdit: Bool { permission == nil || permission == "edit" }

    /// 「2026/08/14 〜 08/16」のような期間表示。
    var dateRange: String? {
        guard let start = startDate, !start.isEmpty else { return nil }
        let startText = start.replacingOccurrences(of: "-", with: "/")
        guard let end = endDate, !end.isEmpty, end != start else { return startText }
        // 同じ年なら後半は月日だけにする
        let endText = end.hasPrefix(String(start.prefix(4)))
            ? String(end.dropFirst(5)).replacingOccurrences(of: "-", with: "/")
            : end.replacingOccurrences(of: "-", with: "/")
        return "\(startText) 〜 \(endText)"
    }
}

// MARK: - 写真

struct TripPhoto: Codable, Identifiable, Hashable {
    var id: Int
    var url: String?
    var thumbURL: String?
    var takenAt: String?
    var lat: Double?
    var lng: Double?

    enum CodingKeys: String, CodingKey {
        case id, url, lat, lng
        case thumbURL = "thumb_url"
        case takenAt = "taken_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id       = try c.decode(Int.self, forKey: .id)
        url      = try? c.decode(String.self, forKey: .url)
        thumbURL = try? c.decode(String.self, forKey: .thumbURL)
        takenAt  = try? c.decode(String.self, forKey: .takenAt)
        lat      = try? c.decode(Double.self, forKey: .lat)
        lng      = try? c.decode(Double.self, forKey: .lng)
    }

    /// 一覧はサムネイル、拡大は原寸。片方しか無ければあるほうを使う。
    var displayURL: String? { thumbURL ?? url }
    var fullURL: String? { url ?? thumbURL }
}

// MARK: - 付箋・ベストショット

struct Sticker: Codable, Identifiable, Hashable {
    var id: Int
    var text: String
}

struct BestShot: Codable, Hashable {
    var url: String?
    var thumbURL: String?
    var reason: String

    enum CodingKeys: String, CodingKey {
        case url, reason
        case thumbURL = "thumb_url"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        url      = try? c.decode(String.self, forKey: .url)
        thumbURL = try? c.decode(String.self, forKey: .thumbURL)
        reason   = (try? c.decode(String.self, forKey: .reason)) ?? ""
    }
}

struct Footprint: Codable, Hashable {
    var lat: Double
    var lng: Double
    var thumb: String?
    var taken: String?
}

/// 旅の中身ひとまとめ。
struct TripDetail: Codable {
    var trip: Trip
    var photos: [TripPhoto]
    var stickers: [Sticker]
    var bestShots: [BestShot]
    var footprints: [Footprint]

    enum CodingKeys: String, CodingKey {
        case trip, photos, stickers, footprints
        case bestShots = "best_shots"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        trip       = try c.decode(Trip.self, forKey: .trip)
        photos     = (try? c.decode([TripPhoto].self, forKey: .photos)) ?? []
        stickers   = (try? c.decode([Sticker].self, forKey: .stickers)) ?? []
        bestShots  = (try? c.decode([BestShot].self, forKey: .bestShots)) ?? []
        footprints = (try? c.decode([Footprint].self, forKey: .footprints)) ?? []
    }
}

// MARK: - 年間ダイジェスト

struct Digest: Codable {
    var year: String
    var years: [String]
    var trips: [Trip]
    var photoTotal: Int
    var stickers: [String]

    enum CodingKeys: String, CodingKey {
        case year, years, trips, stickers
        case photoTotal = "photo_total"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        year       = (try? c.decode(String.self, forKey: .year)) ?? ""
        years      = (try? c.decode([String].self, forKey: .years)) ?? []
        trips      = (try? c.decode([Trip].self, forKey: .trips)) ?? []
        photoTotal = (try? c.decode(Int.self, forKey: .photoTotal)) ?? 0
        stickers   = (try? c.decode([String].self, forKey: .stickers)) ?? []
    }

    /// 月ごとのまとまり。
    /// タプルではなく構造体にする（タプルの要素へは KeyPath を作れず、
    /// ForEach の id: に渡せないため）。
    struct MonthGroup: Identifiable {
        let month: Int
        let trips: [Trip]
        var id: Int { month }

        var label: String { month > 0 ? "\(month)月" : "日にちのない旅" }
    }

    /// 旅がある月だけ、古い順。
    var monthGroups: [MonthGroup] {
        var buckets: [Int: [Trip]] = [:]
        for trip in trips {
            let source = trip.startDate ?? trip.createdAt ?? ""
            let month = Int(source.dropFirst(5).prefix(2)) ?? 0
            buckets[month, default: []].append(trip)
        }
        return buckets.keys.sorted().map { MonthGroup(month: $0, trips: buckets[$0] ?? []) }
    }
}

// MARK: - 共有

struct PublicLink: Codable, Identifiable, Hashable {
    var id: Int
    var token: String
    var url: String?
    var permission: String?
}

struct ShareGrant: Codable, Identifiable, Hashable {
    var id: Int
    var email: String
    var permission: String
}

struct ShareState: Codable {
    var links: [PublicLink]
    var grants: [ShareGrant]
    var editableSupported: Bool

    enum CodingKeys: String, CodingKey {
        case links, grants
        case editableSupported = "editable_supported"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        links  = (try? c.decode([PublicLink].self, forKey: .links)) ?? []
        grants = (try? c.decode([ShareGrant].self, forKey: .grants)) ?? []
        editableSupported = (try? c.decode(Bool.self, forKey: .editableSupported)) ?? false
    }
}
