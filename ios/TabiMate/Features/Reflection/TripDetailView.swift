import PhotosUI
import SwiftUI

/// 1つの旅の中身。ちゃむの一枚・言葉・写真のタイムライン。
struct TripDetailView: View {
    @StateObject private var model: TripDetailViewModel
    @State private var picked: [PhotosPickerItem] = []
    @State private var showingEditor = false
    @State private var showingShare = false
    @State private var zoomed: TripPhoto?

    init(trip: Trip) {
        _model = StateObject(wrappedValue: TripDetailViewModel(trip: trip))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header

                switch model.state {
                case .loading:
                    LoadingClover(label: "写真を並べています").frame(maxWidth: .infinity)
                case .failed(let message):
                    ErrorNote(message: message) { Task { await model.load() } }
                case .ready:
                    if let best = model.detail?.bestShots.first {
                        bestShotCard(best)
                    }
                    stickersCard
                    photosCard
                }

                if let error = model.errorMessage {
                    ErrorNote(message: error)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 40)
        }
        .paperBackground()
        .navigationTitle(model.trip.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button {
                        Task { await model.toggleFavorite() }
                    } label: {
                        Label(model.trip.isFavorite ? "お気に入りを外す" : "お気に入りにする",
                              systemImage: model.trip.isFavorite ? "heart.slash" : "heart")
                    }
                    if model.trip.isOwner {
                        Button { showingEditor = true } label: {
                            Label("名前・日にちを直す", systemImage: "pencil")
                        }
                    }
                    if model.trip.isOwner {
                        Button { showingShare = true } label: {
                            Label("共有する", systemImage: "person.badge.plus")
                        }
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .accessibilityLabel("この旅の操作")
            }
        }
        .sheet(isPresented: $showingEditor) {
            TripEditorView(trip: model.trip) { title, start, end in
                await model.rename(title: title, startDate: start, endDate: end)
            }
        }
        .sheet(isPresented: $showingShare) {
            ShareSheetView(resource: .trip, resourceId: model.trip.id, title: model.trip.title)
        }
        .sheet(item: $zoomed) { photo in
            PhotoZoomView(photo: photo, canDelete: model.trip.canEditPhotos,
                          canSetCover: model.trip.isOwner) {
                await model.deletePhoto(photo)
            } onSetCover: {
                await model.setCover(photo)
            }
        }
        .task { await model.load() }
        .onChange(of: picked) { Task { await upload() } }
    }

    // MARK: - 見出し

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("MEMORIES")
                .font(.kicker).tracking(4.2)
                .foregroundStyle(.white.opacity(0.85))
            Text(model.trip.title)
                .font(Theme.Font_.rounded(23, weight: .bold))
                .foregroundStyle(.white)
            HStack(spacing: 8) {
                if let range = model.trip.dateRange { Text(range) }
                if model.trip.photoCount > 0 {
                    Text("・").opacity(0.5)
                    Text("写真\(model.trip.photoCount)枚")
                }
            }
            .font(.meta)
            .foregroundStyle(.white.opacity(0.9))
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Palette.headerGradient,
                    in: RoundedRectangle(cornerRadius: Theme.Radius.card))
        .cardShadow()
        .padding(.top, 6)
    }

    // MARK: - ちゃむの一枚

    private func bestShotCard(_ best: BestShot) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                Text("🌟 ちゃむが選んだ一枚")
                    .font(.cardTitle)
                    .foregroundStyle(Theme.Palette.textMain)

                VStack(spacing: 0) {
                    RemoteImage(best.thumbURL ?? best.url)
                        .frame(maxWidth: .infinity)
                        .frame(height: 220)
                        .clipped()
                }
                .padding(9)
                .padding(.bottom, 20)
                .background(Color.white)
                .shadow(color: Theme.Shadow.sticky.color, radius: 10, y: 6)
                .rotationEffect(.degrees(-1.2))
                .padding(.vertical, 6)

                if !best.reason.isEmpty {
                    ChamuBubble(text: best.reason, size: 38)
                }
            }
        }
    }

    // MARK: - 付箋

    private var stickersCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("🍀 ことばの付箋")
                        .font(.cardTitle)
                        .foregroundStyle(Theme.Palette.textMain)
                    Spacer()
                    if model.trip.canEditPhotos && !(model.detail?.photos.isEmpty ?? true) {
                        Button(model.isInterpreting ? "考えています…" : "作り直す") {
                            Task { await model.makeStickers() }
                        }
                        .buttonStyle(QuietButtonStyle())
                        .disabled(model.isInterpreting)
                    }
                }

                let stickers = model.detail?.stickers ?? []
                if stickers.isEmpty {
                    Text(model.detail?.photos.isEmpty ?? true
                         ? "写真を入れると、ちゃむが思い出の言葉を書いてくれます。"
                         : "ちゃむに、この旅の言葉を書いてもらえます。")
                        .font(.body_)
                        .foregroundStyle(Theme.Palette.textMuted)
                    if model.trip.canEditPhotos && !(model.detail?.photos.isEmpty ?? true) {
                        Button(model.isInterpreting ? "考えています…" : "言葉を書いてもらう") {
                            Task { await model.makeStickers() }
                        }
                        .buttonStyle(CloverButtonStyle())
                        .disabled(model.isInterpreting)
                    }
                } else {
                    VStack(spacing: 12) {
                        ForEach(Array(stickers.enumerated()), id: \.element.id) { index, sticker in
                            StickyNote(style: Theme.Sticky.forIndex(index)) {
                                Text(sticker.text)
                                    .font(.body_)
                                    .lineSpacing(5)
                                    .foregroundStyle(Theme.Sticky.forIndex(index).ink)
                            }
                            .contextMenu {
                                if model.trip.canEditPhotos {
                                    Button(role: .destructive) {
                                        Task { await model.deleteSticker(sticker) }
                                    } label: {
                                        Label("この付箋をはがす", systemImage: "trash")
                                    }
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    // MARK: - 写真

    private var photosCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                // PhotosPicker のラベルは @Sendable なクロージャなので、その中から
                // ViewModel（@MainActor）を読むと警告になる。値をここで確定させる
                let pickerTitle = model.isUploading ? "入れています…" : "写真を入れる"

                HStack {
                    Text("📷 写真")
                        .font(.cardTitle)
                        .foregroundStyle(Theme.Palette.textMain)
                    Spacer()
                    if model.trip.canEditPhotos {
                        PhotosPicker(selection: $picked, maxSelectionCount: 50,
                                     matching: .images, photoLibrary: .shared()) {
                            Text(pickerTitle)
                        }
                        .buttonStyle(QuietButtonStyle(tint: Theme.Palette.primaryDark))
                        .disabled(model.isUploading)
                    }
                }

                if model.isUploading {
                    ProgressView(value: model.uploadProgress)
                        .tint(Theme.Palette.primary)
                }

                let photos = model.detail?.photos ?? []
                if photos.isEmpty {
                    Text("まだ写真がありません。")
                        .font(.body_)
                        .foregroundStyle(Theme.Palette.textMuted)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 18)
                } else {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6),
                                             count: 3), spacing: 6) {
                        ForEach(photos) { photo in
                            Button { zoomed = photo } label: {
                                RemoteImage(photo.displayURL)
                                    .aspectRatio(1, contentMode: .fill)
                                    .frame(maxWidth: .infinity)
                                    .clipped()
                                    .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    if photos.count >= 3 && model.trip.isOwner {
                        Button(model.isInterpreting ? "選んでいます…" : "ちゃむに一枚選んでもらう") {
                            Task { await model.makeBestShot() }
                        }
                        .buttonStyle(CloverButtonStyle())
                        .disabled(model.isInterpreting)
                        .padding(.top, 4)
                    }
                }
            }
        }
    }

    @MainActor
    private func upload() async {
        // 送っている最中にもう一度選ばれると、二重に走って進み具合が飛ぶ
        guard !picked.isEmpty, !model.isUploading else { return }
        let items = picked
        picked = []
        await model.upload(items)
    }
}

// MARK: - 写真を大きく見る

private struct PhotoZoomView: View {
    let photo: TripPhoto
    let canDelete: Bool
    let canSetCover: Bool
    let onDelete: () async -> Void
    let onSetCover: () async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var showingDeleteConfirm = false

    var body: some View {
        NavigationStack {
            VStack {
                Spacer()
                RemoteImage(photo.fullURL, contentMode: .fit)
                    .frame(maxWidth: .infinity)
                Spacer()
                if let taken = photo.takenAt {
                    Text(taken)
                        .font(.meta)
                        .foregroundStyle(Theme.Palette.textMuted)
                        .padding(.bottom, 10)
                }
            }
            .paperBackground()
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("閉じる") { dismiss() }
                }
                if canDelete || canSetCover {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            if canSetCover {
                                Button {
                                    Task { await onSetCover(); dismiss() }
                                } label: {
                                    Label("表紙にする", systemImage: "star")
                                }
                            }
                            if canDelete {
                                Button(role: .destructive) {
                                    showingDeleteConfirm = true
                                } label: {
                                    Label("この写真を消す", systemImage: "trash")
                                }
                            }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                        }
                    }
                }
            }
            .confirmationDialog("この写真を消す？", isPresented: $showingDeleteConfirm,
                                titleVisibility: .visible) {
                Button("消す", role: .destructive) { Task { await onDelete(); dismiss() } }
                Button("やめる", role: .cancel) {}
            }
        }
    }
}

// MARK: - 状態

@MainActor
final class TripDetailViewModel: ObservableObject {
    @Published private(set) var trip: Trip
    @Published private(set) var detail: TripDetail?
    @Published private(set) var state: LoadState = .loading
    @Published private(set) var isUploading = false
    @Published private(set) var uploadProgress: Double = 0
    @Published private(set) var isInterpreting = false
    @Published var errorMessage: String?

    enum LoadState { case loading, ready, failed(String) }

    /// 1回のアップロードで送る枚数。サーバーの上限は50枚だが、
    /// 通信が長引きすぎないよう小分けにして進み具合も見せる。
    private let batchSize = 10

    init(trip: Trip) {
        self.trip = trip
    }

    func load() async {
        do {
            let loaded = try await ReflectionService.detail(tripId: trip.id)
            detail = loaded
            trip = loaded.trip
            state = .ready
        } catch {
            state = .failed((error as? APIError)?.errorDescription
                            ?? "この旅を読み込めませんでした。")
        }
    }

    // MARK: - 写真

    func upload(_ items: [PhotosPickerItem]) async {
        isUploading = true
        uploadProgress = 0
        errorMessage = nil
        defer {
            isUploading = false
            uploadProgress = 0
        }

        // 端末からの読み出しも一度に全部やらず、送るぶんだけ取り出す。
        // 50枚ぶんのHEICを一度に抱えると数百MBになり、端末に落とされてしまう。
        var sent = 0
        var failed = false
        for start in stride(from: 0, to: items.count, by: batchSize) {
            let chunk = Array(items[start..<min(start + batchSize, items.count)])
            var images: [Data] = []
            for item in chunk {
                if let data = try? await item.loadTransferable(type: Data.self) {
                    images.append(data)   // 取り出せなかったものは黙って飛ばす
                }
            }
            guard !images.isEmpty else { continue }
            do {
                sent += try await ReflectionService.uploadPhotos(tripId: trip.id, shared: trip.isShared, images: images)
                uploadProgress = Double(min(start + chunk.count, items.count)) / Double(items.count)
            } catch {
                errorMessage = (error as? APIError)?.errorDescription
                    ?? "写真を入れられませんでした。"
                failed = true
                break   // 途中まで入った分はそのまま残す（読み直せば見える）
            }
        }
        if sent == 0 && !failed {
            errorMessage = "写真を読み込めませんでした。"
        }
        await load()
    }

    func deletePhoto(_ photo: TripPhoto) async {
        do {
            try await ReflectionService.deletePhoto(tripId: trip.id, shared: trip.isShared, photoId: photo.id)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? "消せませんでした。"
        }
    }

    func setCover(_ photo: TripPhoto) async {
        do {
            try await ReflectionService.setCover(tripId: trip.id, photoId: photo.id)
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? "表紙にできませんでした。"
        }
    }

    // MARK: - ちゃむの解釈

    func makeStickers() async {
        isInterpreting = true
        errorMessage = nil
        defer { isInterpreting = false }
        do {
            try await ReflectionService.generateStickers(tripId: trip.id, shared: trip.isShared)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "言葉を書けませんでした。もう一度ためしてね。"
        }
    }

    func deleteSticker(_ sticker: Sticker) async {
        do {
            try await ReflectionService.deleteSticker(tripId: trip.id, shared: trip.isShared,
                                                      stickerId: sticker.id)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? "はがせませんでした。"
        }
    }

    func makeBestShot() async {
        isInterpreting = true
        errorMessage = nil
        defer { isInterpreting = false }
        do {
            try await ReflectionService.generateBestShots(tripId: trip.id)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "一枚を選べませんでした。もう一度ためしてね。"
        }
    }

    // MARK: - 旅そのもの

    /// 名前と日にちを直す。できなければ理由の文言を返す（エディタのシート内で見せる）。
    func rename(title: String, startDate: String?, endDate: String?) async -> String? {
        do {
            try await ReflectionService.updateTrip(tripId: trip.id, title: title,
                                                   startDate: startDate, endDate: endDate)
            await load()
            return nil
        } catch {
            return (error as? APIError)?.errorDescription ?? "直せませんでした。"
        }
    }

    func toggleFavorite() async {
        guard let updated = try? await ReflectionService.setFavorite(tripId: trip.id,
                                                                    favorite: !trip.isFavorite)
        else { return }
        _ = updated
        await load()
        NotificationCenter.default.post(name: .tripsChanged, object: nil)
    }
}
