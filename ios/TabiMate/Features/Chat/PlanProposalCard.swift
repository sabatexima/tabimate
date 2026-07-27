import SwiftUI

/// ちゃむが提案してきたプランのカード。
/// Web版のプランカード（概要＋折りたたみ＋総評＋保存ボタン）と同じ構成にする。
struct PlanProposalCard: View {
    let plan: DraftPlan
    /// 保存できたら true を返す。失敗したらボタンを押せる状態に戻す。
    let onSave: () async -> Bool

    @State private var isSaving = false
    @State private var isSaved = false

    var body: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                header

                if plan.isInfeasible {
                    infeasibleBody
                } else {
                    sections
                    if let feedback = plan.feedback, !feedback.isEmpty {
                        review(feedback)
                    }
                    editHint
                    saveArea
                }
            }
        }
    }

    // MARK: - 見出し

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("🗾 \(plan.destination ?? "旅のプラン")")
                .font(Theme.Font_.rounded(19, weight: .bold))
                .foregroundStyle(.white)

            FlowLayout(spacing: 8) {
                ForEach(headerChips, id: \.self) { chip in
                    Text(chip)
                        .font(Theme.Font_.rounded(12, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.white.opacity(0.2), in: Capsule())
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Palette.headerGradient)
    }

    private var headerChips: [String] {
        var chips: [String] = []
        if let from = plan.departureLocation, !from.isEmpty { chips.append("📍 \(from)") }
        if let duration = plan.duration, !duration.isEmpty { chips.append("⏱️ \(duration)") }
        if let people = plan.numPeople { chips.append("👥 \(people)人") }
        if let total = plan.totalPerPerson, total > 0 {
            chips.append("💴 \(total.yen)/人")
        } else if let limit = plan.budgetLimit, limit > 0 {
            chips.append("💴 予算 \(limit.yen)/人")
        }
        return chips
    }

    // MARK: - 中身

    private var sections: some View {
        VStack(spacing: 0) {
            PlanSection(icon: "📅", title: "スケジュール", items: plan.schedule ?? [], initiallyOpen: true)
            PlanSection(icon: "📸", title: "観光スポット", items: plan.spots ?? [])
            PlanSection(icon: "🍽", title: "食事", items: plan.restaurants ?? [])
            PlanSection(icon: "🏨", title: "宿泊", items: plan.accommodation ?? [])
            PlanSection(icon: "💴", title: "費用の内訳", items: plan.budgetEstimate ?? [])
        }
    }

    private func review(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("💬 総評")
                .font(Theme.Font_.rounded(13, weight: .bold))
                .foregroundStyle(Theme.Palette.primaryDark)
            Text(text)
                .font(.body_)
                .lineSpacing(5)
                .foregroundStyle(Theme.Palette.textMain)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Palette.glowCream.opacity(0.28))
    }

    /// プランは出して終わりではなく、会話で直せることを伝える。
    private var editHint: some View {
        Text("このプランはチャットで調整できます。\n「2日目をゆっくりに」「もう少し予算を抑えて」のように送ってくださいね🍀")
            .font(.meta)
            .lineSpacing(4)
            .foregroundStyle(Theme.Palette.textMuted)
            .padding(.horizontal, 16)
            .padding(.top, 14)
    }

    private var saveArea: some View {
        Button {
            guard !isSaved, !isSaving else { return }
            Task {
                isSaving = true
                isSaved = await onSave()
                isSaving = false
            }
        } label: {
            HStack(spacing: 8) {
                if isSaving { ProgressView().tint(.white) }
                Text(isSaved ? "✓ 保存しました" : (isSaving ? "保存しています…" : "このプランを保存する"))
            }
        }
        .buttonStyle(CloverButtonStyle())
        .disabled(isSaved || isSaving)
        .padding(16)
    }

    /// 予算が足りなかったとき。断念した理由をそのまま伝える。
    private var infeasibleBody: some View {
        StickyNote(style: .pink, tilted: false) {
            VStack(alignment: .leading, spacing: 8) {
                Text("この予算では組めませんでした")
                    .font(Theme.Font_.rounded(14, weight: .bold))
                    .foregroundStyle(Theme.Sticky.pink.ink)
                if let feedback = plan.feedback, !feedback.isEmpty {
                    Text(feedback)
                        .font(.body_)
                        .lineSpacing(5)
                        .foregroundStyle(Theme.Sticky.pink.subInk)
                }
            }
        }
        .padding(16)
    }
}

/// 折りたたみの1ブロック。Web版の <details> と同じく、既定は閉じておく。
struct PlanSection: View {
    let icon: String
    let title: String
    let items: [String]
    var initiallyOpen: Bool = false

    @State private var isOpen: Bool?

    var body: some View {
        if !items.isEmpty {
            VStack(spacing: 0) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { isOpen = !open }
                } label: {
                    HStack {
                        Text("\(icon) \(title)")
                            .font(Theme.Font_.rounded(14, weight: .bold))
                            .foregroundStyle(Theme.Palette.textMain)
                        Spacer()
                        Image(systemName: "chevron.down")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Theme.Palette.textMuted)
                            .rotationEffect(.degrees(open ? 0 : -90))
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 13)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if open {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                            HStack(alignment: .top, spacing: 8) {
                                Text("・").foregroundStyle(Theme.Palette.primary)
                                Text(item)
                                    .font(.body_)
                                    .lineSpacing(4)
                                    .foregroundStyle(Theme.Palette.textMain)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 14)
                }

                Rectangle().fill(Theme.Palette.border).frame(height: 1)
            }
        }
    }

    private var open: Bool { isOpen ?? initiallyOpen }
}

extension Int {
    /// 3桁区切りの「12,000円」。
    var yen: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        let number = formatter.string(from: NSNumber(value: self)) ?? "\(self)"
        return "\(number)円"
    }
}
