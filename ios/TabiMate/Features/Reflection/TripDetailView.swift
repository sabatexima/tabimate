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
                    if model.trip.canEdit {
                        Button { showingEditor = true } label: {
                            Label("名前・日にちを直す", systemImage: "pencil")
                        }
                    }
                    if !model.trip.isShared {
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
            PhotoZoomView(photo: photo, canEdit: model.trip.canEdit) {
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
                    if model.trip.canEdit && !(model.detail?.photos.isEmpty ?? true) {
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
                    if model.trip.canEdit && !(model.detail?.photos.isEmpty ?? true) {
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
                HStack {
                    Text("📷 写真")
                        .font(.cardTitle)
                        .foregroundStyle(Theme.Palette.textMain)
                    Spacer()
                    if model.trip.canEdit {
                        PhotosPicker(selection: $picked, maxSelectionCount: 50,
                                     matching: .images, photoLibrary: .shared()) {
                            Text(model.isUploading ? "入れています…" : "写真を入れる")
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

                    if photos.count >= 3 && model.trip.canEdit {
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

    private func upload() async {
        guard !picked.isEmpty else { return }
        let items = picked
        picked = []
        await model.upload(items)
    }
}

// MARK: - 写真を大きく見る

private struct PhotoZoomView: View {
    let photo: TripPhoto
    let canEdit: Bool
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
                if canEdit {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button {
                                Task { await onSetCover(); dismiss() }
                            } label: {
                                Label("表紙にする", systemImage: "star")
                            }
                            Button(role: .destructive) {
                                showingDeleteConfirm = true
                            } label: {
                                Label("この写真を消す", systemImage: "trash")
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

        // 先に端末から画像データを取り出す（取り出せなかったものは黙って飛ばす）
        var images: [Data] = []
        for item in items {
            if let data = try? await item.loadTransferable(type: Data.self) {
                images.append(data)
            }
        }
        guard !images.isEmpty else {
            errorMessage = "写真を読み込めませんでした。"
            return
        }

        var sent = 0
        for batch in stride(from: 0, to: images.count, by: batchSize) {
            let slice = Array(images[batch..<min(batch + batchSize, images.count)])
            do {
                sent += try await ReflectionService.uploadPhotos(tripId: trip.id, images: slice)
                uploadProgress = Double(sent) / Double(images.count)
            } catch {
                errorMessage = (error as? APIError)?.errorDescription
                    ?? "写真を入れられませんでした。"
                break   // 途中まで入った分はそのまま残す（読み直せば見える）
            }
        }
        await load()
    }

    func deletePhoto(_ photo: TripPhoto) async {
        do {
            try await ReflectionService.deletePhoto(tripId: trip.id, photoId: photo.id)
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
            try await ReflectionService.generateStickers(tripId: trip.id)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "言葉を書けませんでした。もう一度ためしてね。"
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

    func rename(title: String, startDate: String?, endDate: String?) async -> Bool {
        do {
            try await ReflectionService.updateTrip(tripId: trip.id, title: title,
                                                   startDate: startDate, endDate: endDate)
            await load()
            return true
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? "直せませんでした。"
            return false
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
