import Foundation

/// 地図に立てる1本のピン。
struct PlanPin: Identifiable, Hashable {
    enum Category: Hashable {
        case spot, restaurant, accommodation

        var label: String {
            switch self {
            case .spot:          return "観光"
            case .restaurant:    return "グルメ"
            case .accommodation: return "宿"
            }
        }

        /// Web版の地図と同じ色（static/js/plan-map.js の CATEGORIES）。
        var hex: UInt32 {
            switch self {
            case .spot:          return 0x4FA83A
            case .restaurant:    return 0xE8883A
            case .accommodation: return 0x4A90D9
            }
        }
    }

    let id = UUID()
    let name: String
    let category: Category
    var lat: Double
    var lng: Double
    /// 移動する順番（1始まり）。
    var order: Int = 0
}

/// ピンを「移動する順番」に並べる。
///
/// Web版 static/js/plan-map.js の orderByItinerary をそのまま移したもの。
/// スケジュール本文に名前が最初に出てくる位置で並べ、観光・グルメ・宿を横断した
/// 通し番号を振る。照合できなかったピンは末尾に続き番号で置く。
enum PlanItinerary {

    /// 店名の断片として照合すると誤マッチしやすい一般語。
    private static let genericWords = ["レストラン", "ラーメン", "ビュッフェ", "カフェテリア"]

    /// プランと座標からピンを組み立て、順番を振って返す。
    static func pins(plan: TravelPlan, geo: PlanGeo) -> [PlanPin] {
        var pins = build(names: plan.spots, coords: geo.spotCoords, category: .spot)
            + build(names: plan.restaurants, coords: geo.restaurantCoords, category: .restaurant)
            + build(names: plan.accommodation, coords: geo.accommodationCoords, category: .accommodation)

        pins = ordered(pins, schedule: plan.schedule)
        spreadOverlaps(&pins)
        return pins
    }

    /// 名前と座標を突き合わせる（座標が取れなかった名前は地図に出さない）。
    private static func build(names: [String],
                              coords: [PlaceCoordinate],
                              category: PlanPin.Category) -> [PlanPin] {
        let byName = Dictionary(coords.map { ($0.name, $0) }, uniquingKeysWith: { first, _ in first })
        return names.compactMap { name in
            guard let coord = byName[name] else { return nil }
            return PlanPin(name: name, category: category, lat: coord.lat, lng: coord.lng)
        }
    }

    /// スケジュール本文での登場順に並べ替えて番号を振る。
    /// 照合できた点が2つ未満なら並べ替えず、元の順（観光→グルメ→宿）のままにする。
    static func ordered(_ pins: [PlanPin], schedule: [String]) -> [PlanPin] {
        let text = normalize(schedule.joined(separator: "\n"))
        guard !text.isEmpty, !pins.isEmpty else { return numbered(pins) }

        let allNames = pins.map { normalize($0.name) }
        var hits: [(pin: PlanPin, at: Int)] = []
        var misses: [PlanPin] = []
        for pin in pins {
            if let at = firstIndex(of: pin.name, in: text, otherNames: allNames) {
                hits.append((pin, at))
            } else {
                misses.append(pin)
            }
        }
        guard hits.count >= 2 else { return numbered(pins) }

        hits.sort { $0.at < $1.at }
        return numbered(hits.map(\.pin) + misses)
    }

    private static func numbered(_ pins: [PlanPin]) -> [PlanPin] {
        pins.enumerated().map { index, pin in
            var pin = pin
            pin.order = index + 1
            return pin
        }
    }

    /// ピン名がスケジュール本文に最初に出てくる位置。
    ///
    /// 完全一致で見つからなければ、名前の部分文字列（長い順・4文字以上）でも探す
    /// （「熱海銀座おさかな食堂」→「おさかな食堂で昼食」のように省略されがちなため）。
    /// 誤マッチを避けるため、一般語そのものと、他のピン名にも含まれる断片は使わない。
    private static func firstIndex(of name: String, in text: String, otherNames: [String]) -> Int? {
        let needle = normalize(name)
        guard !needle.isEmpty else { return nil }
        if let range = text.range(of: needle) {
            return text.distance(from: text.startIndex, to: range.lowerBound)
        }

        let chars = Array(needle)
        var length = min(chars.count - 1, 10)
        while length >= 4 {
            for start in 0...(chars.count - length) {
                let fragment = String(chars[start..<(start + length)])
                if isGenericFragment(fragment) { continue }
                if otherNames.contains(where: { $0 != needle && $0.contains(fragment) }) { continue }
                if let range = text.range(of: fragment) {
                    return text.distance(from: text.startIndex, to: range.lowerBound)
                }
            }
            length -= 1
        }
        return nil
    }

    /// 一般語の断片（「レスト」「ストラン」等）も情報を持たないので除く。
    /// 一般語＋固有部分を含む長い断片（「ガーデンレストラン」等）は有効なまま。
    private static func isGenericFragment(_ fragment: String) -> Bool {
        genericWords.contains { $0.contains(fragment) }
    }

    /// NFKC で正規化し、空白をすべて落とす（Web版の normText と同じ前処理）。
    /// 全角と半角、スペースの有無で照合が外れるのを防ぐ。
    private static func normalize(_ text: String) -> String {
        text.precomposedStringWithCompatibilityMapping
            .components(separatedBy: .whitespacesAndNewlines)
            .joined()
    }

    /// 同じ座標のピンが重なって1本に見えるのを防ぐ（1段ごとに約20m 北東へずらす）。
    ///
    /// 「重なっている数」でずらすだけだと、3件目が2件目と同じ位置に落ちる。
    /// 空いている場所が見つかるまで押しやる。
    private static func spreadOverlaps(_ pins: inout [PlanPin]) {
        var placed: [(lat: Double, lng: Double)] = []
        for index in pins.indices {
            var bump = 0
            while bump < placed.count + 1,
                  placed.contains(where: {
                      abs(pins[index].lat + 0.00013 * Double(bump) - $0.lat) < 0.00015
                          && abs(pins[index].lng + 0.00022 * Double(bump) - $0.lng) < 0.00015
                  }) {
                bump += 1
            }
            if bump > 0 {
                pins[index].lat += 0.00013 * Double(bump)
                pins[index].lng += 0.00022 * Double(bump)
            }
            placed.append((pins[index].lat, pins[index].lng))
        }
    }
}
