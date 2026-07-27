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
                    } else if model.plans.isEmpty && model.sharedPlans.isEmpty {
                        EmptyStateView(message: "まだしおりがありません。\n「そうだん」でちゃむに話しかけてみてね。")
                    } else {
                        if let message = model.actionError {
                            ErrorNote(message: message) { model.actionError = nil }
                                .padding(.horizontal, 20)
                        }
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
            .onReceive(NotificationCenter.default.publisher(for: .plansChanged)) { _ in
                Task { await model.load() }
            }
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
        VStack(alignment: .leading, spacing: 26) {
            ForEach(Array(model.plans.enumerated()), id: \.element.id) { index, plan in
                planRow(plan, index: index)
            }

            if !model.sharedPlans.isEmpty {
                Text("共有してもらったしおり")
                    .font(Theme.Font_.rounded(13, weight: .bold))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .padding(.top, 8)
                ForEach(Array(model.sharedPlans.enumerated()), id: \.element.id) { index, plan in
                    planRow(plan, index: index + model.plans.count)
                }
            }
        }
        .padding(.horizontal, 24)
        .padding(.top, 6)
    }

    private func planRow(_ plan: TravelPlan, index: Int) -> some View {
        NavigationLink(value: plan) {
            PlanStickyCard(plan: plan, style: Theme.Sticky.forIndex(index))
        }
        .buttonStyle(.plain)
        .contextMenu {
            if plan.isOwner {
                Button(role: .destructive) { planToDelete = plan } label: {
                    Label("消す", systemImage: "trash")
                }
            } else if let grantId = plan.grantId {
                // 人からもらったしおりは消せない。自分の一覧から外すだけ
                Button(role: .destructive) {
                    Task { await model.leaveShared(plan, grantId: grantId) }
                } label: {
                    Label("一覧から外す", systemImage: "person.badge.minus")
                }
            }
        }
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
    @Published private(set) var sharedPlans: [TravelPlan] = []
    @Published private(set) var isLoading = true
    /// 読み込みの失敗（一覧を出せない）。
    @Published var errorMessage: String?
    /// 操作の失敗。一覧は出せているので、消さずに添えるだけにする。
    @Published var actionError: String?

    func load() async {
        errorMessage = nil
        actionError = nil
        do {
            // 共有ぶんは取れなくても自分のしおりは見せる（付随情報のため）
            async let mine = PlanService.myPlans()
            async let shared = try? PlanService.sharedPlans()
            plans = try await mine
            sharedPlans = await shared ?? []
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
            NotificationCenter.default.post(name: .plansChanged, object: nil)
        } catch {
            plans = backup
            actionError = (error as? APIError)?.errorDescription
                ?? "消せませんでした。もう一度ためしてね。"
        }
    }

    /// もらったしおりを自分の一覧から外す（相手の元データは消えない）。
    func leaveShared(_ plan: TravelPlan, grantId: Int) async {
        let backup = sharedPlans
        sharedPlans.removeAll { $0.id == plan.id }
        do {
            try await PlanService.leaveShared(grantId: grantId)
        } catch {
            sharedPlans = backup
            actionError = (error as? APIError)?.errorDescription
                ?? "外せませんでした。もう一度ためしてね。"
        }
    }
}
