import SwiftUI

/// 年間ダイジェスト。その年の旅を、絵本の1ページのようにまとめて見せる。
struct DigestView: View {
    @StateObject private var model = DigestViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                PageHeader(kicker: "This year",
                           title: "今年の",
                           accent: "旅ぜんぶ",
                           lead: "歩いた道のりを、1ページにまとめました。")
                    .padding(.top, 4)

                switch model.state {
                case .loading:
                    LoadingClover(label: "1年を並べています").frame(maxWidth: .infinity)
                case .failed(let message):
                    ErrorNote(message: message) { Task { await model.load() } }
                case .ready:
                    if let digest = model.digest {
                        yearPicker(digest)
                        summary(digest)
                        if digest.trips.isEmpty {
                            EmptyStateView(message: "\(digest.year)年の旅はまだありません。")
                        } else {
                            timeline(digest)
                            stickerWall(digest)
                        }
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 40)
        }
        .paperBackground()
        .navigationTitle("年間ダイジェスト")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    // MARK: - 年えらび

    private func yearPicker(_ digest: Digest) -> some View {
        Group {
            if digest.years.count > 1 {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(digest.years, id: \.self) { year in
                            Button {
                                Task { await model.load(year: year) }
                            } label: {
                                Text("\(year)年")
                                    .font(Theme.Font_.rounded(13, weight: .semibold))
                                    .foregroundStyle(year == digest.year
                                                     ? .white : Theme.Palette.textMuted)
                                    .padding(.horizontal, 15)
                                    .padding(.vertical, 8)
                                    .background(year == digest.year
                                                ? AnyShapeStyle(Theme.Palette.primary)
                                                : AnyShapeStyle(Theme.Palette.surface),
                                                in: Capsule())
                                    .overlay(Capsule().stroke(Theme.Palette.border,
                                                              lineWidth: year == digest.year ? 0 : 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    // MARK: - まとめ

    private func summary(_ digest: Digest) -> some View {
        Card {
            HStack(spacing: 0) {
                stat("旅した回数", "\(digest.trips.count)", unit: "回")
                divider
                stat("撮った写真", "\(digest.photoTotal)", unit: "枚")
                divider
                stat("もらった言葉", "\(digest.stickers.count)", unit: "つ")
            }
        }
    }

    private func stat(_ label: String, _ value: String, unit: String) -> some View {
        VStack(spacing: 4) {
            Text(label).font(.meta).foregroundStyle(Theme.Palette.textMuted)
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(value)
                    .font(Theme.Font_.rounded(26, weight: .bold))
                    .foregroundStyle(Theme.Palette.primaryDark)
                Text(unit).font(.meta).foregroundStyle(Theme.Palette.textMuted)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var divider: some View {
        Rectangle().fill(Theme.Palette.border).frame(width: 1, height: 34)
    }

    // MARK: - 月ごとの並び

    private func timeline(_ digest: Digest) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(digest.monthGroups) { group in
                VStack(alignment: .leading, spacing: 10) {
                    Text(group.label)
                        .font(Theme.Font_.rounded(15, weight: .bold))
                        .foregroundStyle(Theme.Palette.kicker)

                    ForEach(group.trips) { trip in
                        // 一覧の navigationDestination に頼らず、行き先をここで持つ
                        // （ダイジェストは一覧の上に積まれた画面なので確実にする）
                        NavigationLink {
                            TripDetailView(trip: trip)
                        } label: {
                            HStack(spacing: 12) {
                                RemoteImage(trip.coverURL)
                                    .frame(width: 64, height: 64)
                                    .clipped()
                                    .clipShape(RoundedRectangle(cornerRadius: 8))
                                    .background(Theme.Palette.glowCream.opacity(0.35))

                                VStack(alignment: .leading, spacing: 3) {
                                    Text(trip.title)
                                        .font(Theme.Font_.rounded(15, weight: .bold))
                                        .foregroundStyle(Theme.Palette.textMain)
                                        .lineLimit(1)
                                    if let range = trip.dateRange {
                                        Text(range).font(.meta)
                                            .foregroundStyle(Theme.Palette.textMuted)
                                    }
                                    if trip.photoCount > 0 {
                                        Text("写真\(trip.photoCount)枚").font(.meta)
                                            .foregroundStyle(Theme.Palette.textMuted)
                                    }
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(Theme.Palette.border)
                            }
                            .padding(12)
                            .background(Theme.Palette.surface,
                                        in: RoundedRectangle(cornerRadius: Theme.Radius.card))
                            .overlay(RoundedRectangle(cornerRadius: Theme.Radius.card)
                                .stroke(Theme.Palette.border, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: - ことばの壁

    private func stickerWall(_ digest: Digest) -> some View {
        Group {
            if !digest.stickers.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("この1年でもらった言葉")
                        .font(Theme.Font_.rounded(15, weight: .bold))
                        .foregroundStyle(Theme.Palette.textMain)

                    ForEach(Array(digest.stickers.enumerated()), id: \.offset) { index, text in
                        StickyNote(style: Theme.Sticky.forIndex(index)) {
                            Text(text)
                                .font(.body_)
                                .lineSpacing(5)
                                .foregroundStyle(Theme.Sticky.forIndex(index).ink)
                        }
                    }
                }
                .padding(.top, 6)
            }
        }
    }
}

@MainActor
final class DigestViewModel: ObservableObject {
    @Published private(set) var digest: Digest?
    @Published private(set) var state: LoadState = .loading

    enum LoadState { case loading, ready, failed(String) }

    func load(year: String? = nil) async {
        state = .loading
        do {
            digest = try await ReflectionService.digest(year: year)
            state = .ready
        } catch {
            state = .failed((error as? APIError)?.errorDescription
                            ?? "ダイジェストを読み込めませんでした。")
        }
    }
}
