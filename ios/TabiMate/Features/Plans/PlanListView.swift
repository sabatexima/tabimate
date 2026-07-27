import SwiftUI

/// 保存プランの一覧。Web版と同じく、付箋を並べたボードの見立て。
struct PlanListView: View {
    @StateObject private var model = PlanListViewModel()
    @State private var planToDelete: TravelPlan?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    PageHeader(kicker: "Your trips",
                               title: "保存した",
                               accent: "旅のしおり",
                               lead: "行き先をえらぶと、しおりの中身がひらきます。")
                        .padding(.horizontal, 20)
                        .padding(.top, 4)

                    if model.isLoading {
                        LoadingClover(label: "しおりを開いています").frame(maxWidth: .infinity)
                    } else if let error = model.errorMessage {
                        ErrorNote(message: error) { Task { await model.load() } }
                            .padding(.horizontal, 20)
                    } else if model.plans.isEmpty {
                        EmptyStateView(message: "まだしおりがありません。\n「そうだん」でちゃむに話しかけてみてね。")
                    } else {
                        board
                    }
                }
                .padding(.bottom, 36)
            }
            .paperBackground()
            .navigationTitle("保存プラン")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: TravelPlan.self) { PlanDetailView(plan: $0) }
            .task { await model.load() }
            .refreshable { await model.load() }
            .confirmationDialog("このしおりを消す？",
                                isPresented: Binding(get: { planToDelete != nil },
                                                     set: { if !$0 { planToDelete = nil } }),
                                titleVisibility: .visible) {
                Button("消す", role: .destructive) {
                    if let plan = planToDelete {
                        Task { await model.delete(plan) }
                    }
                    planToDelete = nil
                }
                Button("やめる", role: .cancel) { planToDelete = nil }
            } message: {
                Text("「\(planToDelete?.destination ?? "")」の記録は元に戻せません。")
            }
        }
    }

    private var board: some View {
        VStack(spacing: 26) {
            ForEach(Array(model.plans.enumerated()), id: \.element.id) { index, plan in
                NavigationLink(value: plan) {
                    PlanStickyCard(plan: plan, style: Theme.Sticky.forIndex(index))
                }
                .buttonStyle(.plain)
                .contextMenu {
                    Button("消す", systemImage: "trash", role: .destructive) {
                        planToDelete = plan
                    }
                }
            }
        }
        .padding(.horizontal, 24)
        .padding(.top, 6)
    }
}

/// 1枚の付箋。行き先・要約・カウントダウンだけを見せて、中身は詳細で開く。
struct PlanStickyCard: View {
    let plan: TravelPlan
    let style: Theme.Sticky

    var body: some View {
        StickyNote(style: style) {
            VStack(alignment: .leading, spacing: 7) {
                if let countdown = plan.countdownLabel {
                    Text(countdown)
                        .font(Theme.Font_.rounded(12, weight: .bold))
                        .foregroundStyle(style.ink.opacity(0.9))
                }

                Text(plan.destination)
                    .font(Theme.Font_.rounded(18, weight: .bold))
                    .lineLimit(2)
                    .foregroundStyle(style.ink)

                if !plan.summaryLine.isEmpty {
                    Text(plan.summaryLine)
                        .font(.meta)
                        .foregroundStyle(style.subInk)
                }

                if let rating = plan.rating, rating > 0 {
                    Text(String(repeating: "★", count: rating))
                        .font(.meta)
                        .foregroundStyle(style.subInk)
                }
            }
            .padding(.vertical, 2)
        }
        .overlay(alignment: .top) {
            WashiTape(angle: style == .pink ? 5 : -6)
                .offset(y: -9)
        }
    }
}

@MainActor
final class PlanListViewModel: ObservableObject {
    @Published private(set) var plans: [TravelPlan] = []
    @Published private(set) var isLoading = true
    @Published var errorMessage: String?

    func load() async {
        errorMessage = nil
        do {
            plans = try await PlanService.myPlans()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "しおりを読み込めませんでした。"
        }
        isLoading = false
    }

    func delete(_ plan: TravelPlan) async {
        // 先に画面から消して、失敗したら戻す（待たされないように）
        let backup = plans
        plans.removeAll { $0.id == plan.id }
        do {
            try await PlanService.delete(planId: plan.id)
        } catch {
            plans = backup
            errorMessage = (error as? APIError)?.errorDescription
                ?? "消せませんでした。もう一度ためしてね。"
        }
    }
}
