import SwiftUI

/// 旅のアイデア（サーバーの季節チップ）。
struct TravelIdea: Codable, Identifiable, Hashable {
    var id: String { label }
    let emoji: String
    let label: String
    let prompt: String
}

/// ホーム。ちゃむのあいさつと、次の旅までのカウントダウン、季節のアイデア。
struct HomeView: View {
    let startChat: () -> Void
    let openPlans: () -> Void

    @EnvironmentObject private var auth: AuthStore
    @StateObject private var model = HomeViewModel()
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    ChamuBubble(text: greeting, size: 54)
                        .padding(.top, 4)

                    if let next = model.nextTrip, let label = next.countdownLabel {
                        countdownCard(next, label: label)
                    }

                    ideasSection

                    Button("ちゃむに相談する", action: startChat)
                        .buttonStyle(CloverButtonStyle())
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 32)
            }
            .paperBackground()
            .navigationTitle("たびメイト")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("設定")
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .task { await model.load() }
            .refreshable { await model.load() }
            .onReceive(NotificationCenter.default.publisher(for: .plansChanged)) { _ in
                Task { await model.load() }
            }
        }
    }

    private var greeting: String {
        let name = auth.user?.name ?? ""
        let hour = Calendar.current.component(.hour, from: Date())
        let time = hour < 11 ? "おはよう" : (hour < 18 ? "こんにちは" : "こんばんは")
        return name.isEmpty ? "\(time)。きょうはどんな旅にする？"
                            : "\(time)、\(name)さん。\nきょうはどんな旅にする？"
    }

    /// 次の旅のカウントダウン。押すと保存プランへ。
    private func countdownCard(_ plan: TravelPlan, label: String) -> some View {
        Button(action: openPlans) {
            Card {
                VStack(alignment: .leading, spacing: 8) {
                    Text(label)
                        .font(Theme.Font_.rounded(19, weight: .bold))
                        .foregroundStyle(Theme.Palette.primaryDark)
                    Text(plan.destination)
                        .font(.cardTitle)
                        .foregroundStyle(Theme.Palette.textMain)
                    if !plan.summaryLine.isEmpty {
                        Text(plan.summaryLine)
                            .font(.meta)
                            .foregroundStyle(Theme.Palette.textMuted)
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var ideasSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            PageHeader(kicker: "Where to", title: "こんな旅は", accent: "どう？")

            if model.ideas.isEmpty {
                LoadingClover().frame(maxWidth: .infinity)
            } else {
                FlowLayout(spacing: 10) {
                    ForEach(Array(model.ideas.enumerated()), id: \.element) { index, idea in
                        Button {
                            ChatDraft.shared.pending = idea.prompt
                            startChat()
                        } label: {
                            HStack(spacing: 6) {
                                Text(idea.emoji)
                                Text(idea.label)
                                    .font(Theme.Font_.rounded(13, weight: .semibold))
                            }
                            .foregroundStyle(Theme.Sticky.forIndex(index).ink)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .background(Theme.Sticky.forIndex(index).paper, in: Capsule())
                            .shadow(color: Theme.Shadow.soft.color, radius: 3, y: 2)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var ideas: [TravelIdea] = []
    @Published var nextTrip: TravelPlan?

    func load() async {
        async let ideasTask = try? APIClient.shared.get("api/ideas", as: IdeasResponse.self)
        async let plansTask = try? PlanService.myPlans()

        ideas = (await ideasTask)?.ideas ?? []
        // 出発日が近い順にひとつだけ。過ぎた旅は daysUntilDeparture が nil になる
        nextTrip = (await plansTask)?
            .filter { $0.daysUntilDeparture != nil }
            .min { ($0.daysUntilDeparture ?? .max) < ($1.daysUntilDeparture ?? .max) }
    }

    struct IdeasResponse: Codable {
        let status: String
        let ideas: [TravelIdea]
    }
}

/// チップから相談画面へ文章を渡すための、ごく小さな受け渡し箱。
@MainActor
final class ChatDraft {
    static let shared = ChatDraft()
    var pending: String?
    private init() {}
}

/// 幅に合わせて折り返す並べ方（チップ用）。
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: proposal.width ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for item in row.items {
                let size = subviews[item].sizeThatFits(.unspecified)
                subviews[item].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var items: [Int] = []
        var height: CGFloat = 0
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows = [Row()]
        var x: CGFloat = 0
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if x + size.width > width, !rows[rows.count - 1].items.isEmpty {
                rows.append(Row())
                x = 0
            }
            rows[rows.count - 1].items.append(index)
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
            x += size.width + spacing
        }
        return rows
    }
}
