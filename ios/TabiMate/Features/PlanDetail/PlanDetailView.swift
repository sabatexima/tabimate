import SwiftUI

/// しおりの中身。カウントダウン・地図・スケジュール・費用・持ち物。
struct PlanDetailView: View {
    @StateObject private var model: PlanDetailViewModel
    @State private var showingShare = false

    init(plan: TravelPlan) {
        _model = StateObject(wrappedValue: PlanDetailViewModel(plan: plan))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                cover

                if let countdown = model.plan.countdownLabel {
                    countdownNote(countdown)
                }

                PlanMapCard(planId: model.plan.id, plan: model.plan)

                sections

                // 記録・持ち物・感想はサーバー側が本人しか受け付けないので、
                // もらったしおりでは出さない（押しても失敗するだけのため）
                if model.plan.isOwner {
                    LedgerCard(plan: model.plan, onSave: { amount in
                        await model.saveActualTotal(amount)
                    })

                    PackingCard(planId: model.plan.id,
                                items: model.plan.packingList,
                                isWorking: model.isMakingPackingList,
                                onGenerate: { await model.makePackingList() })

                    RatingCard(rating: model.plan.rating ?? 0,
                               comment: model.plan.ratingComment ?? "",
                               onSave: { rating, comment in
                                   await model.rate(rating: rating, comment: comment)
                               })
                }

                if let error = model.errorMessage {
                    ErrorNote(message: error)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 40)
        }
        .paperBackground()
        .navigationTitle(model.plan.destination)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if model.plan.isOwner {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingShare = true } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel("このしおりを共有する")
                }
            }
        }
        .sheet(isPresented: $showingShare) {
            ShareSheetView(resource: .plan, resourceId: model.plan.id,
                           title: model.plan.destination)
        }
    }

    // MARK: - 表紙

    private var cover: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("ITINERARY")
                .font(.kicker)
                .tracking(4.2)
                .foregroundStyle(.white.opacity(0.85))
            Text(model.plan.destination)
                .font(Theme.Font_.rounded(24, weight: .bold))
                .foregroundStyle(.white)
            if !model.plan.summaryLine.isEmpty {
                Text(model.plan.summaryLine)
                    .font(.meta)
                    .foregroundStyle(.white.opacity(0.9))
            }
            if !model.plan.themes.isEmpty {
                FlowLayout(spacing: 7) {
                    ForEach(model.plan.themes, id: \.self) { theme in
                        Text(theme)
                            .font(Theme.Font_.rounded(11, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 9)
                            .padding(.vertical, 4)
                            .background(Color.white.opacity(0.22), in: Capsule())
                    }
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Palette.headerGradient, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
        .cardShadow()
        .padding(.top, 6)
    }

    private func countdownNote(_ text: String) -> some View {
        StickyNote(style: .mint) {
            Text(text)
                .font(Theme.Font_.rounded(17, weight: .bold))
                .foregroundStyle(Theme.Sticky.mint.ink)
        }
        .padding(.horizontal, 6)
    }

    private var sections: some View {
        Card(padding: 0) {
            PlanSectionList(schedule: model.plan.schedule,
                            spots: model.plan.spots,
                            restaurants: model.plan.restaurants,
                            accommodation: model.plan.accommodation,
                            budgetEstimate: model.plan.budgetEstimate)
        }
    }
}

// MARK: - 旅のおこづかい帳

/// 見積もりと、実際にかかった金額を並べて見る。
private struct LedgerCard: View {
    let plan: TravelPlan
    let onSave: (Int?) async -> Void

    @State private var isEditing = false
    @State private var input = ""
    @State private var isSaving = false

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                Text("💰 旅のおこづかい帳")
                    .font(.cardTitle)
                    .foregroundStyle(Theme.Palette.textMain)

                HStack(spacing: 22) {
                    amount("見つもり", value: plan.totalPerPerson)
                    amount("じっさい", value: plan.actualTotal)
                }

                if let difference {
                    Text(difference.text)
                        .font(.meta)
                        .foregroundStyle(difference.color)
                }

                if isEditing {
                    editor
                } else {
                    Button(plan.actualTotal == nil ? "じっさいの金額を記録する" : "修正する") {
                        input = plan.actualTotal.map(String.init) ?? ""
                        isEditing = true
                    }
                    .buttonStyle(QuietButtonStyle())
                }
            }
        }
    }

    private func amount(_ label: String, value: Int?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.meta).foregroundStyle(Theme.Palette.textMuted)
            Text(value.map { "\($0.yen)/人" } ?? "—")
                .font(Theme.Font_.rounded(19, weight: .bold))
                .foregroundStyle(Theme.Palette.textMain)
        }
    }

    /// 予算内なら緑、超えたら赤。差額だけを短く伝える。
    private var difference: (text: String, color: Color)? {
        guard let estimate = plan.totalPerPerson, let actual = plan.actualTotal else { return nil }
        let gap = actual - estimate
        if gap == 0 { return ("見つもりぴったり！", Theme.Palette.primaryDark) }
        return gap < 0
            ? ("見つもりより \((-gap).yen) おさえられました🍀", Theme.Palette.primaryDark)
            : ("見つもりより \(gap.yen) 多くかかりました", Theme.Palette.danger)
    }

    private var editor: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField("例: 24000", text: $input)
                .keyboardType(.numberPad)
                .font(.body_)
                .padding(.horizontal, 13)
                .padding(.vertical, 10)
                .background(Theme.Palette.surface, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10)
                    .stroke(Theme.Palette.borderInput, lineWidth: 1))

            HStack(spacing: 10) {
                Button(isSaving ? "記録しています…" : "記録する") {
                    Task {
                        isSaving = true
                        // 「24,000」「24000円」のような書き方も受け取れるよう数字だけ拾う。
                        // 空欄なら nil ＝ 記録を消す
                        await onSave(Int(input.filter(\.isNumber)))
                        isSaving = false
                        isEditing = false
                    }
                }
                .buttonStyle(CloverButtonStyle(expands: false))
                .disabled(isSaving)

                // 「修正」で前の記録が消えてしまわないよう、やめる道を必ず用意する
                Button("やめる") { isEditing = false }
                    .buttonStyle(QuietButtonStyle())
                    .disabled(isSaving)
            }
        }
    }
}

// MARK: - 持ち物リスト

private struct PackingCard: View {
    let items: [String]
    let isWorking: Bool
    let onGenerate: () async -> Void

    /// チェックは端末に覚えさせる（サーバーに持たせるほどの情報ではない）。
    /// しおりごとに別の記憶にする（別の旅で同じ持ち物にチェックが付かないように）。
    @AppStorage private var checkedRaw: String

    init(planId: Int, items: [String], isWorking: Bool, onGenerate: @escaping () async -> Void) {
        self.items = items
        self.isWorking = isWorking
        self.onGenerate = onGenerate
        _checkedRaw = AppStorage(wrappedValue: "", "tabimate.packingChecks.\(planId)")
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("🎒 持ち物リスト")
                        .font(.cardTitle)
                        .foregroundStyle(Theme.Palette.textMain)
                    Spacer()
                    if !items.isEmpty {
                        Button(isWorking ? "作り直しています…" : "作り直す") {
                            Task { await onGenerate() }
                        }
                        .buttonStyle(QuietButtonStyle())
                        .disabled(isWorking)
                    }
                }

                if items.isEmpty {
                    Text("ちゃむが旅の内容から持ち物を考えます。")
                        .font(.body_)
                        .foregroundStyle(Theme.Palette.textMuted)
                    Button(isWorking ? "考えています…" : "持ち物を考えてもらう") {
                        Task { await onGenerate() }
                    }
                    .buttonStyle(CloverButtonStyle())
                    .disabled(isWorking)
                } else {
                    ForEach(items, id: \.self) { item in
                        Button { toggle(item) } label: {
                            HStack(spacing: 10) {
                                Image(systemName: isChecked(item) ? "checkmark.square.fill" : "square")
                                    .foregroundStyle(isChecked(item) ? Theme.Palette.primary
                                                                     : Theme.Palette.border)
                                Text(item)
                                    .font(.body_)
                                    .strikethrough(isChecked(item), color: Theme.Palette.textMuted)
                                    .foregroundStyle(isChecked(item) ? Theme.Palette.textMuted
                                                                     : Theme.Palette.textMain)
                                Spacer()
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private var checked: Set<String> {
        Set(checkedRaw.split(separator: "\n").map(String.init))
    }

    private func isChecked(_ item: String) -> Bool { checked.contains(item) }

    private func toggle(_ item: String) {
        var set = checked
        if set.contains(item) { set.remove(item) } else { set.insert(item) }
        checkedRaw = set.sorted().joined(separator: "\n")
    }
}

// MARK: - 旅の感想

/// 帰ってきたあとの★とひとこと。次のプランの好みの参考にも使われる。
private struct RatingCard: View {
    let rating: Int
    let comment: String
    let onSave: (Int, String) async -> Void

    @State private var draftRating = 0
    @State private var draftComment = ""
    @State private var isSaving = false

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                Text("🌟 旅の感想")
                    .font(.cardTitle)
                    .foregroundStyle(Theme.Palette.textMain)

                HStack(spacing: 6) {
                    ForEach(1...5, id: \.self) { star in
                        Button {
                            draftRating = star
                        } label: {
                            Image(systemName: star <= draftRating ? "star.fill" : "star")
                                .font(.system(size: 24))
                                .foregroundStyle(star <= draftRating
                                                 ? Theme.Palette.kicker : Theme.Palette.border)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("星\(star)つ")
                    }
                }

                TextField("よかったこと、次に活かしたいこと", text: $draftComment, axis: .vertical)
                    .font(.body_)
                    .lineLimit(1...4)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(Theme.Palette.surface, in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10)
                        .stroke(Theme.Palette.borderInput, lineWidth: 1))

                Button(isSaving ? "残しています…" : "感想を残す") {
                    Task {
                        isSaving = true
                        await onSave(draftRating, draftComment)
                        isSaving = false
                    }
                }
                .buttonStyle(CloverButtonStyle())
                // ★未選択では送れない（サーバーが1〜5しか受け付けないため）
                .disabled(draftRating == 0 || isSaving)
            }
        }
        .onAppear {
            // 既に残した感想があれば、それを初期値にする（上書きで消えないように）
            draftRating = rating
            draftComment = comment
        }
    }
}

// MARK: - 状態

@MainActor
final class PlanDetailViewModel: ObservableObject {
    @Published var plan: TravelPlan
    @Published var isMakingPackingList = false
    @Published var errorMessage: String?

    init(plan: TravelPlan) {
        self.plan = plan
    }

    func makePackingList() async {
        isMakingPackingList = true
        errorMessage = nil
        defer { isMakingPackingList = false }
        do {
            plan.packingList = try await PlanService.generatePackingList(planId: plan.id)
            NotificationCenter.default.post(name: .plansChanged, object: nil)
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "持ち物リストを作れませんでした。もう一度ためしてね。"
        }
    }

    func saveActualTotal(_ amount: Int?) async {
        let backup = plan.actualTotal
        plan.actualTotal = amount
        do {
            try await PlanService.saveActualTotal(planId: plan.id, amount: amount)
            errorMessage = nil
            // 一覧が古いままだと、開き直したときに前の値に戻って見える
            NotificationCenter.default.post(name: .plansChanged, object: nil)
        } catch {
            plan.actualTotal = backup
            errorMessage = (error as? APIError)?.errorDescription
                ?? "記録できませんでした。もう一度ためしてね。"
        }
    }

    func rate(rating: Int, comment: String) async {
        let backup = (plan.rating, plan.ratingComment)
        plan.rating = rating
        plan.ratingComment = comment
        do {
            try await PlanService.rate(planId: plan.id, rating: rating, comment: comment)
            errorMessage = nil
            NotificationCenter.default.post(name: .plansChanged, object: nil)
        } catch {
            (plan.rating, plan.ratingComment) = backup
            errorMessage = (error as? APIError)?.errorDescription
                ?? "感想を残せませんでした。もう一度ためしてね。"
        }
    }
}
