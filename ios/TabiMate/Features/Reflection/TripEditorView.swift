import SwiftUI

/// 旅をつくる／名前と日付を直す小さなシート。
struct TripEditorView: View {
    /// 直すときだけ渡す。nil なら新規作成。
    var trip: Trip? = nil
    /// 保存できたら nil、できなければ理由の文言を返す。
    /// シートの裏側にエラーを出しても見えないので、ここで受け取って自分で見せる。
    let onSave: (String, String?, String?) async -> String?

    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var hasDates = false
    @State private var startDate = Date()
    @State private var endDate = Date()
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    ChamuBubble(text: trip == nil
                                ? "どんな旅だった？\n名前をつけてあげてね。"
                                : "名前や日にちを直せるよ。")
                        .padding(.bottom, 2)

                    if let errorMessage {
                        ErrorNote(message: errorMessage)
                    }

                    Card {
                        VStack(alignment: .leading, spacing: 14) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("旅の名前").font(.meta).foregroundStyle(Theme.Palette.textMuted)
                                TextField("例: 熱海でのんびり２日", text: $title)
                                    .font(.body_)
                                    .padding(.horizontal, 13)
                                    .padding(.vertical, 10)
                                    .background(Theme.Palette.surface,
                                                in: RoundedRectangle(cornerRadius: 10))
                                    .overlay(RoundedRectangle(cornerRadius: 10)
                                        .stroke(Theme.Palette.borderInput, lineWidth: 1))
                            }

                            Toggle("日にちを入れる", isOn: $hasDates)
                                .font(.body_)
                                .tint(Theme.Palette.primary)

                            if hasDates {
                                DatePicker("出発", selection: $startDate, displayedComponents: .date)
                                    .font(.body_)
                                DatePicker("帰宅", selection: $endDate, in: startDate...,
                                           displayedComponents: .date)
                                    .font(.body_)
                            }
                        }
                    }
                }
                .padding(20)
            }
            .paperBackground()
            .navigationTitle(trip == nil ? "旅をつくる" : "旅を直す")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("やめる") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(isSaving ? "保存中…" : "保存") { Task { await save() } }
                        .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
                }
            }
            .onAppear(perform: fillFromTrip)
        }
    }

    private func fillFromTrip() {
        guard let trip else { return }
        title = trip.title
        if let start = trip.startDate, let date = DateFormatter.plainDate.date(from: start) {
            hasDates = true
            startDate = date
            // 帰宅日が無ければ出発日と同じ扱いにする（日帰り）
            endDate = trip.endDate.flatMap { DateFormatter.plainDate.date(from: $0) } ?? date
        }
    }

    @MainActor
    private func save() async {
        isSaving = true
        errorMessage = nil
        let name = title.trimmingCharacters(in: .whitespaces)
        // 日にちを外したときは空文字を送って記録を消す
        let start = hasDates ? DateFormatter.plainDate.string(from: startDate) : ""
        let end = hasDates ? DateFormatter.plainDate.string(from: endDate) : ""
        errorMessage = await onSave(name, start, end)
        isSaving = false
        if errorMessage == nil { dismiss() }
    }
}
