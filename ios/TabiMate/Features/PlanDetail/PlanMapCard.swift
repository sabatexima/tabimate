import MapKit
import SwiftUI

/// しおりの地図。移動する順に番号を振ったピンを、その順で線でつなぐ。
struct PlanMapCard: View {
    let planId: Int
    let plan: TravelPlan

    @State private var pins: [PlanPin] = []
    @State private var state: LoadState = .loading
    @State private var camera: MapCameraPosition = .automatic
    @State private var selected: PlanPin?

    enum LoadState { case loading, ready, empty, failed(String) }

    var body: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                header

                switch state {
                case .loading:
                    LoadingClover(label: "地図を用意しています").frame(maxWidth: .infinity, minHeight: 220)
                case .failed(let message):
                    Text(message)
                        .font(.body_)
                        .foregroundStyle(Theme.Palette.textMuted)
                        .padding(16)
                case .empty:
                    Text("この旅の場所はまだ地図に出せませんでした。")
                        .font(.body_)
                        .foregroundStyle(Theme.Palette.textMuted)
                        .padding(16)
                case .ready:
                    map
                    legend
                }
            }
        }
        .task { await load() }
    }

    private var header: some View {
        Text("🗺 地図")
            .font(.cardTitle)
            .foregroundStyle(Theme.Palette.textMain)
            .padding(.horizontal, 16)
            .padding(.top, 15)
            .padding(.bottom, 11)
    }

    private var map: some View {
        Map(position: $camera, selection: $selected) {
            // 番号どおりに全ピンをつなぐ線（順番＝線の並び）
            if pins.count >= 2 {
                MapPolyline(coordinates: pins.map(\.coordinate))
                    .stroke(Theme.Palette.primary.opacity(0.65),
                            style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round,
                                               dash: [7, 6]))
            }
            ForEach(pins) { pin in
                Annotation(pin.name, coordinate: pin.coordinate) {
                    NumberedPin(pin: pin)
                }
                .annotationTitles(.hidden)
                .tag(pin)   // これが無いと選択（下の名前表示）が働かない
            }
        }
        .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
        .frame(height: 280)
        .overlay(alignment: .bottom) {
            if let selected {
                Text("\(selected.order). \(selected.name)")
                    .font(Theme.Font_.rounded(13, weight: .semibold))
                    .foregroundStyle(Theme.Palette.textMain)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 8)
                    .background(Theme.Palette.surface, in: Capsule())
                    .shadow(color: Theme.Shadow.card.color, radius: 6, y: 2)
                    .padding(.bottom, 12)
            }
        }
    }

    private var legend: some View {
        HStack(spacing: 14) {
            ForEach(presentCategories, id: \.self) { category in
                HStack(spacing: 5) {
                    Circle().fill(Color(hex: category.hex)).frame(width: 9, height: 9)
                    Text(category.label)
                        .font(.meta)
                        .foregroundStyle(Theme.Palette.textMuted)
                }
            }
            Spacer()
            Text("番号は移動する順番です")
                .font(.meta)
                .foregroundStyle(Theme.Palette.textMuted)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    private var presentCategories: [PlanPin.Category] {
        [.spot, .restaurant, .accommodation].filter { category in
            pins.contains { $0.category == category }
        }
    }

    @MainActor
    private func load() async {
        // 座標は一覧の応答に入ってくる。取得済みならそれをそのまま使い、
        // 余計な問い合わせをしない（人からもらったしおりは取りに行けないので、なおさら）。
        var geo = plan.embeddedGeo
        if geo.isEmpty {
            guard plan.isOwner else {
                state = .empty
                return
            }
            do {
                // 未取得のときだけサーバーに頼む（サーバー側がここで取得して覚える）
                geo = try await PlanService.geo(planId: planId)
            } catch {
                state = .failed((error as? APIError)?.errorDescription
                                ?? "地図を読み込めませんでした。")
                return
            }
        }

        pins = PlanItinerary.pins(plan: plan, geo: geo)
        guard !pins.isEmpty else {
            state = .empty
            return
        }
        camera = .region(region(for: pins))
        state = .ready
    }

    /// すべてのピンが収まる範囲。1点だけのときは適度に寄る。
    /// ピンが無いときは日本全体（呼び出し側で弾いているが、落ちないようにしておく）。
    private func region(for pins: [PlanPin]) -> MKCoordinateRegion {
        let lats = pins.map(\.lat), lngs = pins.map(\.lng)
        guard let minLat = lats.min(), let maxLat = lats.max(),
              let minLng = lngs.min(), let maxLng = lngs.max() else {
            return MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: 36.2, longitude: 138.3),
                span: MKCoordinateSpan(latitudeDelta: 12, longitudeDelta: 12)
            )
        }
        return MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: (minLat + maxLat) / 2,
                                           longitude: (minLng + maxLng) / 2),
            span: MKCoordinateSpan(latitudeDelta: max((maxLat - minLat) * 1.4, 0.02),
                                   longitudeDelta: max((maxLng - minLng) * 1.4, 0.02))
        )
    }
}

/// 番号入りのしずく型ピン。色は種類ごと（観光=緑／グルメ=橙／宿=青）。
private struct NumberedPin: View {
    let pin: PlanPin

    var body: some View {
        ZStack {
            Circle()
                .fill(Color(hex: pin.category.hex))
                .frame(width: 28, height: 28)
                .overlay(Circle().stroke(.white, lineWidth: 2))
                .shadow(color: .black.opacity(0.2), radius: 3, y: 2)
            Text("\(pin.order)")
                .font(Theme.Font_.rounded(13, weight: .bold))
                .foregroundStyle(.white)
        }
        .accessibilityLabel("\(pin.order)番目、\(pin.name)、\(pin.category.label)")
    }
}

extension PlanPin {
    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: lat, longitude: lng)
    }
}
