import SwiftUI

/// おもいでの一覧。Web版と同じ、ボードにポラロイドと付箋を貼った見立て。
struct TripListView: View {
    @StateObject private var model = TripListViewModel()
    @State private var showingNewTrip = false
    @State private var tripToDelete: Trip?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    PageHeader(kicker: "Memories",
                               title: "旅の",
                               accent: "おもいで",
                               lead: "写真を入れると、ちゃむが言葉と一枚を選びます。")
                        .padding(.horizontal, 20)
                        .padding(.top, 4)

                    switch model.state {
                    case .loading:
                        LoadingClover(label: "アルバムを開いています").frame(maxWidth: .infinity)
                    case .failed(let message):
                        ErrorNote(message: message) { Task { await model.load() } }
                            .padding(.horizontal, 20)
                    case .ready:
                        if let message = model.actionError {
                            ErrorNote(message: message) { model.actionError = nil }
                                .padding(.horizontal, 20)
                        }
                        if model.trips.isEmpty && model.sharedTrips.isEmpty {
                            EmptyStateView(message: "まだおもいでがありません。\n旅から帰ったら、写真をまとめてみてね。",
                                           actionTitle: "はじめての旅をつくる") { showingNewTrip = true }
                        } else {
                            board
                        }
                    }
                }
                .padding(.bottom, 40)
            }
            .paperBackground()
            .navigationTitle("おもいで")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Trip.self) { TripDetailView(trip: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { DigestView() } label: {
                        Image(systemName: "book.pages")
                    }
                    .accessibilityLabel("年間ダイジェスト")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingNewTrip = true } label: { Image(systemName: "plus") }
                        .accessibilityLabel("旅をつくる")
                }
            }
            .sheet(isPresented: $showingNewTrip) {
                TripEditorView { title, start, end in
                    await model.create(title: title, startDate: start, endDate: end)
                }
            }
            .task { await model.load() }
            .refreshable { await model.load() }
            .onReceive(NotificationCenter.default.publisher(for: .tripsChanged)) { _ in
                Task { await model.load() }
            }
            .confirmationDialog("このおもいでを消す？",
                                isPresented: Binding(get: { tripToDelete != nil },
                                                     set: { if !$0 { tripToDelete = nil } }),
                                titleVisibility: .visible) {
                Button("消す", role: .destructive) {
                    if let trip = tripToDelete { Task { await model.delete(trip) } }
                    tripToDelete = nil
                }
                Button("やめる", role: .cancel) { tripToDelete = nil }
            } message: {
                Text("「\(tripToDelete?.title ?? "")」の写真も一緒に消えます。元に戻せません。")
            }
        }
    }

    private var board: some View {
        VStack(alignment: .leading, spacing: 26) {
            ForEach(Array(model.trips.enumerated()), id: \.element.id) { index, trip in
                tripRow(trip, index: index)
            }

            if !model.sharedTrips.isEmpty {
                Text("共有してもらった旅")
                    .font(Theme.Font_.rounded(13, weight: .bold))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .padding(.top, 8)
                ForEach(Array(model.sharedTrips.enumerated()), id: \.element.id) { index, trip in
                    tripRow(trip, index: index + model.trips.count)
                }
            }
        }
        .padding(.horizontal, 22)
        .padding(.top, 6)
    }

    private func tripRow(_ trip: Trip, index: Int) -> some View {
        NavigationLink(value: trip) {
            TripCard(trip: trip, style: Theme.Sticky.forIndex(index))
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button {
                Task { await model.toggleFavorite(trip) }
            } label: {
                Label(trip.isFavorite ? "お気に入りを外す" : "お気に入りにする",
                      systemImage: trip.isFavorite ? "heart.slash" : "heart")
            }
            if trip.isOwner {
                Button(role: .destructive) { tripToDelete = trip } label: {
                    Label("消す", systemImage: "trash")
                }
            } else if let grantId = trip.grantId {
                // 人からもらった旅は消せない。自分の一覧から外すだけ
                Button(role: .destructive) {
                    Task { await model.leaveShared(trip, grantId: grantId) }
                } label: {
                    Label("一覧から外す", systemImage: "person.badge.minus")
                }
            }
        }
    }
}

/// 1つの旅。左にポラロイド、右に付箋。
struct TripCard: View {
    let trip: Trip
    let style: Theme.Sticky

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            polaroid
            note
        }
    }

    private var polaroid: some View {
        VStack(spacing: 0) {
            RemoteImage(trip.coverURL)
                .frame(width: 116, height: 116)
                .clipped()
                .background(Theme.Palette.glowCream.opacity(0.35))
        }
        .padding(7)
        .padding(.bottom, 16)   // ポラロイドの下の余白
        .background(Color.white)
        .shadow(color: Theme.Shadow.sticky.color, radius: 8, y: 5)
        .rotationEffect(.degrees(-2))
        .overlay(alignment: .top) { WashiTape(angle: 8, width: 46).offset(y: -8) }
    }

    private var note: some View {
        StickyNote(style: style) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 5) {
                    if trip.isFavorite {
                        Image(systemName: "heart.fill")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.Palette.accentPink)
                    }
                    if trip.isShared {
                        Image(systemName: "person.2.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(style.subInk)
                    }
                }

                Text(trip.title)
                    .font(Theme.Font_.rounded(16, weight: .bold))
                    .lineLimit(2)
                    .foregroundStyle(style.ink)

                if let memo = trip.stickersPreview.first {
                    Text(memo)
                        .font(.meta)
                        .lineLimit(2)
                        .foregroundStyle(style.subInk)
                }

                Spacer(minLength: 4)

                HStack(spacing: 6) {
                    if let range = trip.dateRange {
                        Text(range)
                    }
                    if trip.photoCount > 0 {
                        Text("・").opacity(0.45)
                        Text("\(trip.photoCount)枚")
                    }
                }
                .font(Theme.Font_.rounded(10))
                .foregroundStyle(style.subInk.opacity(0.85))
            }
            .frame(minHeight: 116, alignment: .topLeading)
        }
    }
}

// MARK: - 状態

@MainActor
final class TripListViewModel: ObservableObject {
    @Published private(set) var trips: [Trip] = []
    @Published private(set) var sharedTrips: [Trip] = []
    @Published private(set) var state: LoadState = .loading
    /// 操作（作成・削除・共有解除）の失敗。読み込みの失敗と分けておかないと、
    /// 消し損ねただけで一覧そのものが画面から消えてしまう。
    @Published var actionError: String?

    enum LoadState { case loading, ready, failed(String) }

    func load() async {
        actionError = nil
        do {
            let result = try await ReflectionService.trips()
            trips = result.mine
            sharedTrips = result.shared
            state = .ready
        } catch {
            state = .failed((error as? APIError)?.errorDescription
                            ?? "アルバムを読み込めませんでした。")
        }
    }

    func create(title: String, startDate: String?, endDate: String?) async -> Bool {
        do {
            _ = try await ReflectionService.createTrip(title: title,
                                                       startDate: startDate, endDate: endDate)
            return true
        } catch {
            actionError = (error as? APIError)?.errorDescription ?? "つくれませんでした。"
            return false
        }
    }

    func delete(_ trip: Trip) async {
        let backup = trips
        trips.removeAll { $0.id == trip.id }
        do {
            try await ReflectionService.deleteTrip(tripId: trip.id)
        } catch {
            trips = backup
            actionError = (error as? APIError)?.errorDescription ?? "消せませんでした。"
        }
    }

    /// もらった旅を自分の一覧から外す（相手の元データは消えない）。
    func leaveShared(_ trip: Trip, grantId: Int) async {
        let backup = sharedTrips
        sharedTrips.removeAll { $0.id == trip.id }
        do {
            try await ShareService.leaveShared(grantId: grantId)
        } catch {
            sharedTrips = backup
            actionError = (error as? APIError)?.errorDescription ?? "外せませんでした。"
        }
    }

    func toggleFavorite(_ trip: Trip) async {
        _ = try? await ReflectionService.setFavorite(tripId: trip.id, favorite: !trip.isFavorite)
        await load()
    }
}
