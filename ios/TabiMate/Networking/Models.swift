import Foundation

/// サーバーが返す JSON をそのまま写した型。
/// 形は src/db.py の _PLAN_SELECT_COLS / _normalize_plan_row に合わせている。

// MARK: - 旅行プラン

/// 保存済みのしおり1件。サーバーの travel_plans 表と1対1で対応する。
///
/// JSON のキーはスネークケースなので CodingKeys で読み替える。
/// デコードは `id` 以外すべて decodeIfPresent（欠けても落とさない）にしてある。
/// サーバーに列が増えたり、古いプランに新しい項目が無かったりしても、
/// アプリが起動しなくなることを避けるため。
struct TravelPlan: Codable, Identifiable, Hashable {
    var id: Int
    var destination: String
    var travelDate: String?
    var duration: String?
    var numPeople: Int?
    var budgetLimit: Int?
    var departureLocation: String?
    var transportCost: Int?
    var totalPerPerson: Int?
    var themes: [String]
    var specialRequirements: [String]
    var spots: [String]
    var restaurants: [String]
    var accommodation: [String]
    var schedule: [String]
    var budgetEstimate: [String]
    var packingList: [String]
    var actualTotal: Int?
    var rating: Int?
    var ratingComment: String?
    var createdAt: String?
    /// 出発日を ISO 8601 に正規化したもの。サーバーが付ける（パース不能なら nil）。
    var departIso: String?
    /// 共有されたしおりのときだけ入る（view / edit）。
    var permission: String?
    var grantId: Int?
    /// 地図の座標。取得済みなら一覧の応答に含まれてくるので、そのまま使える。
    var spotCoords: [PlaceCoordinate]
    var restaurantCoords: [PlaceCoordinate]
    var accommodationCoords: [PlaceCoordinate]

    enum CodingKeys: String, CodingKey {
        case id, destination, duration, themes, spots, restaurants, accommodation
        case schedule, rating, permission
        case travelDate = "travel_date"
        case numPeople = "num_people"
        case budgetLimit = "budget_limit"
        case departureLocation = "departure_location"
        case transportCost = "transport_cost"
        case totalPerPerson = "total_per_person"
        case specialRequirements = "special_requirements"
        case budgetEstimate = "budget_estimate"
        case packingList = "packing_list"
        case actualTotal = "actual_total"
        case ratingComment = "rating_comment"
        case createdAt = "created_at"
        case departIso = "depart_iso"
        case grantId = "grant_id"
        case spotCoords = "spot_coords"
        case restaurantCoords = "restaurant_coords"
        case accommodationCoords = "accommodation_coords"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id                  = try c.decode(Int.self, forKey: .id)
        destination         = (try? c.decode(String.self, forKey: .destination)) ?? "旅のプラン"
        travelDate          = try? c.decode(String.self, forKey: .travelDate)
        duration            = try? c.decode(String.self, forKey: .duration)
        numPeople           = try? c.decode(Int.self, forKey: .numPeople)
        budgetLimit         = try? c.decode(Int.self, forKey: .budgetLimit)
        departureLocation   = try? c.decode(String.self, forKey: .departureLocation)
        transportCost       = try? c.decode(Int.self, forKey: .transportCost)
        totalPerPerson      = try? c.decode(Int.self, forKey: .totalPerPerson)
        themes              = (try? c.decode([String].self, forKey: .themes)) ?? []
        specialRequirements = (try? c.decode([String].self, forKey: .specialRequirements)) ?? []
        spots               = (try? c.decode([String].self, forKey: .spots)) ?? []
        restaurants         = (try? c.decode([String].self, forKey: .restaurants)) ?? []
        accommodation       = (try? c.decode([String].self, forKey: .accommodation)) ?? []
        schedule            = (try? c.decode([String].self, forKey: .schedule)) ?? []
        budgetEstimate      = (try? c.decode([String].self, forKey: .budgetEstimate)) ?? []
        packingList         = (try? c.decode([String].self, forKey: .packingList)) ?? []
        actualTotal         = try? c.decode(Int.self, forKey: .actualTotal)
        rating              = try? c.decode(Int.self, forKey: .rating)
        ratingComment       = try? c.decode(String.self, forKey: .ratingComment)
        createdAt           = try? c.decode(String.self, forKey: .createdAt)
        departIso           = try? c.decode(String.self, forKey: .departIso)
        permission          = try? c.decode(String.self, forKey: .permission)
        grantId             = try? c.decode(Int.self, forKey: .grantId)
        spotCoords          = (try? c.decode([PlaceCoordinate].self, forKey: .spotCoords)) ?? []
        restaurantCoords    = (try? c.decode([PlaceCoordinate].self, forKey: .restaurantCoords)) ?? []
        accommodationCoords = (try? c.decode([PlaceCoordinate].self, forKey: .accommodationCoords)) ?? []
    }

    /// 一覧の応答に入っていた座標。空なら未取得（サーバーに取りに行く必要がある）。
    var embeddedGeo: PlanGeo {
        PlanGeo(spotCoords: spotCoords,
                restaurantCoords: restaurantCoords,
                accommodationCoords: accommodationCoords)
    }

    /// 共有されたしおりかどうか（自分のものには permission が付かない）。
    var isShared: Bool { permission != nil }
    /// 記録や感想を残せるのは自分のしおりだけ（サーバー側も本人しか受け付けない）。
    var isOwner: Bool { !isShared }
}

/// 画面に出すための派生値（サーバーからは来ない、ここで組み立てるもの）。
extension TravelPlan {
    /// 「1泊2日・2人」のような一行の要約。
    var summaryLine: String {
        [duration, numPeople.map { "\($0)人" }, travelDate]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: "・")
    }

    /// 出発までの残り日数。過去・日付不明なら nil。
    var daysUntilDeparture: Int? {
        guard let iso = departIso,
              let date = DateFormatter.plainDate.date(from: iso) else { return nil }
        let cal = Calendar.current
        let days = cal.dateComponents([.day],
                                      from: cal.startOfDay(for: Date()),
                                      to: cal.startOfDay(for: date)).day
        guard let days, days >= 0 else { return nil }
        return days
    }

    /// カウントダウンの言い回し（Web版 plan-detail.js の countdownLabel と同じ）。
    var countdownLabel: String? {
        switch daysUntilDeparture {
        case .none:   return nil
        case 0:       return "今日は出発の日！"
        case 1:       return "明日は出発！"
        case let d?:  return "🍀 旅まであと\(d)日"
        }
    }
}

/// 日付の整形をひとまとめに（各画面で作り直さないように）。
extension DateFormatter {
    /// "2026-08-14" のような日付だけの文字列を読むための整形器。
    /// 端末のタイムゾーンで解釈する（「あと何日」は生活時間で数えたいので）。
    static let plainDate: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
}

// MARK: - 地図

/// 地図に置く1点（名前つき）。観光・グルメ・宿で共通。
struct PlaceCoordinate: Codable, Hashable {
    let name: String
    let lat: Double
    let lng: Double
}

/// しおりの座標一式。地図を開いたときに /api/plan_geo/<id> から取り直す。
struct PlanGeo: Codable {
    var spotCoords: [PlaceCoordinate]
    var restaurantCoords: [PlaceCoordinate]
    var accommodationCoords: [PlaceCoordinate]

    enum CodingKeys: String, CodingKey {
        case spotCoords = "spot_coords"
        case restaurantCoords = "restaurant_coords"
        case accommodationCoords = "accommodation_coords"
    }

    init(spotCoords: [PlaceCoordinate] = [], restaurantCoords: [PlaceCoordinate] = [],
         accommodationCoords: [PlaceCoordinate] = []) {
        self.spotCoords = spotCoords
        self.restaurantCoords = restaurantCoords
        self.accommodationCoords = accommodationCoords
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        spotCoords          = (try? c.decode([PlaceCoordinate].self, forKey: .spotCoords)) ?? []
        restaurantCoords    = (try? c.decode([PlaceCoordinate].self, forKey: .restaurantCoords)) ?? []
        accommodationCoords = (try? c.decode([PlaceCoordinate].self, forKey: .accommodationCoords)) ?? []
    }

    var isEmpty: Bool {
        spotCoords.isEmpty && restaurantCoords.isEmpty && accommodationCoords.isEmpty
    }
}

// MARK: - まだ保存していないプラン

/// チャットでちゃむが提示した、保存前のプラン（src/chat/formatter.py の plan_payload）。
/// 保存するときはそのまま /save_plan に送り返す。
/// 相談中にちゃむが出してくる「まだ保存していないプラン案」。
/// TravelPlan と似ているが id を持たず、保存して初めて TravelPlan になる。
struct DraftPlan: Codable, Hashable {
    var destination: String?
    var travelDate: String?
    var duration: String?
    var numPeople: Int?
    var budgetLimit: Int?
    var departureLocation: String?
    var transportCost: Int?
    var remainingBudget: Int?
    var totalPerPerson: Int?
    var status: String?
    var feedback: String?
    var themes: [String]?
    var specialRequirements: [String]?
    var spots: [String]?
    var restaurants: [String]?
    var schedule: [String]?
    var accommodation: [String]?
    var budgetEstimate: [String]?

    enum CodingKeys: String, CodingKey {
        case destination, duration, status, feedback, themes, spots
        case restaurants, schedule, accommodation
        case travelDate = "travel_date"
        case numPeople = "num_people"
        case budgetLimit = "budget_limit"
        case departureLocation = "departure_location"
        case transportCost = "transport_cost"
        case remainingBudget = "remaining_budget"
        case totalPerPerson = "total_per_person"
        case specialRequirements = "special_requirements"
        case budgetEstimate = "budget_estimate"
    }

    /// 予算が足りずに組めなかったプラン。保存させず、理由だけを見せる。
    var isInfeasible: Bool { status == "budget_infeasible" }

    var summaryLine: String {
        [duration, numPeople.map { "\($0)人" }, travelDate]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: "・")
    }
}

// MARK: - チャット

/// 相談の1発言。ai の発言にはプラン案が添えられることがある。
///
/// Web版は content に HTML が入るが、アプリはその HTML を使わない。
/// 代わりに plan（構造化データ）を受け取り、SwiftUI で組み直して描く。
struct ChatMessage: Codable, Identifiable, Hashable {
    /// サーバーは id を返さないので、表示のために手元で採番する。
    var id = UUID()
    let role: String
    let content: String
    let requestId: String?
    /// AIがプランを提示したメッセージだけ中身が入る。
    let plan: DraftPlan?

    var isUser: Bool { role == "user" }

    enum CodingKeys: String, CodingKey {
        case role, content, plan
        case requestId = "request_id"
    }
}

// MARK: - サインイン

/// サインインした人。表示に使うぶんだけ持つ。
struct AppUser: Codable, Hashable {
    let email: String
    let name: String
}

/// /auth/app/signin の返事。token を Keychain に保管して以降 Bearer で使う。
struct SignInResponse: Codable {
    let status: String
    let token: String
    let user: AppUser
}
