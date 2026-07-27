import SwiftUI

/// しおりの中身（スケジュール・観光・食事・宿・費用）を折りたたみで並べる。
/// 提案中のプランと保存済みのしおりで同じ見せ方になるよう、ここに1つだけ置く。
struct PlanSectionList: View {
    var schedule: [String] = []
    var spots: [String] = []
    var restaurants: [String] = []
    var accommodation: [String] = []
    var budgetEstimate: [String] = []

    private struct Section {
        let icon: String
        let title: String
        let items: [String]
    }

    /// 中身のある区画だけを、決まった順で。
    private var sections: [Section] {
        [
            Section(icon: "📅", title: "スケジュール", items: schedule),
            Section(icon: "📸", title: "観光スポット", items: spots),
            Section(icon: "🍽", title: "食事", items: restaurants),
            Section(icon: "🏨", title: "宿泊", items: accommodation),
            Section(icon: "💴", title: "費用の内訳", items: budgetEstimate),
        ].filter { !$0.items.isEmpty }
    }

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(sections.enumerated()), id: \.offset) { index, section in
                PlanSection(icon: section.icon,
                            title: section.title,
                            items: section.items,
                            // 最初（スケジュール）だけ開いておく
                            initiallyOpen: index == 0,
                            // 最後の区画の下に線を引くと、カードの縁と二重に見える
                            showsDivider: index < sections.count - 1)
            }
        }
    }
}

/// 折りたたみの1ブロック。Web版の <details> と同じく、既定は閉じておく。
struct PlanSection: View {
    let icon: String
    let title: String
    let items: [String]
    var initiallyOpen: Bool = false
    var showsDivider: Bool = true

    @State private var isOpen: Bool?

    var body: some View {
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
            .accessibilityLabel("\(title)、\(open ? "開いている" : "閉じている")")

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

            if showsDivider {
                Rectangle().fill(Theme.Palette.border).frame(height: 1)
            }
        }
    }

    private var open: Bool { isOpen ?? initiallyOpen }
}
