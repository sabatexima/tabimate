import SwiftUI

/// 共有のシート。公開リンクの発行と、メールを指定した共有。
struct ShareSheetView: View {
    let resource: ShareService.Resource
    let resourceId: Int
    let title: String

    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: ShareViewModel
    @State private var email = ""
    @State private var allowEdit = false

    init(resource: ShareService.Resource, resourceId: Int, title: String) {
        self.resource = resource
        self.resourceId = resourceId
        self.title = title
        _model = StateObject(wrappedValue: ShareViewModel(resource: resource, resourceId: resourceId))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    ChamuBubble(text: "「\(title)」を見せてあげる？")

                    switch model.state {
                    case .loading:
                        LoadingClover().frame(maxWidth: .infinity)
                    case .failed(let message):
                        ErrorNote(message: message) { Task { await model.load() } }
                    case .ready:
                        linkCard
                        emailCard
                    }

                    if let error = model.errorMessage {
                        ErrorNote(message: error)
                    }
                }
                .padding(20)
            }
            .paperBackground()
            .navigationTitle("共有")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("閉じる") { dismiss() }
                }
            }
            .task { await model.load() }
        }
    }

    // MARK: - 公開リンク

    private var linkCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                Text("🔗 リンクで見せる")
                    .font(.cardTitle)
                    .foregroundStyle(Theme.Palette.textMain)
                Text("URLを知っている人なら誰でも見られます（見るだけ）。")
                    .font(.meta)
                    .foregroundStyle(Theme.Palette.textMuted)

                if model.links.isEmpty {
                    Button(model.isWorking ? "作っています…" : "リンクをつくる") {
                        Task { await model.createLink() }
                    }
                    .buttonStyle(CloverButtonStyle())
                    .disabled(model.isWorking)
                } else {
                    ForEach(model.links) { link in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(link.url ?? "")
                                .font(Theme.Font_.rounded(12))
                                .foregroundStyle(Theme.Palette.textMuted)
                                .lineLimit(2)
                                .textSelection(.enabled)

                            HStack(spacing: 10) {
                                if let url = link.url, let shareURL = URL(string: url) {
                                    ShareLink(item: shareURL) {
                                        Label("送る", systemImage: "square.and.arrow.up")
                                    }
                                    .buttonStyle(QuietButtonStyle(tint: Theme.Palette.primaryDark))
                                }
                                Button("リンクを止める") {
                                    Task { await model.revokeLink(link) }
                                }
                                .buttonStyle(QuietButtonStyle(tint: Theme.Palette.danger))
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
    }

    // MARK: - メールで共有

    private var emailCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                Text("✉️ 相手を選んで見せる")
                    .font(.cardTitle)
                    .foregroundStyle(Theme.Palette.textMain)
                Text("そのメールアドレスでログインした人だけが見られます。")
                    .font(.meta)
                    .foregroundStyle(Theme.Palette.textMuted)

                TextField("相手のメールアドレス", text: $email)
                    .font(.body_)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.emailAddress)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(Theme.Palette.surface, in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10)
                        .stroke(Theme.Palette.borderInput, lineWidth: 1))

                if model.editableSupported {
                    Toggle("直すこともできるようにする", isOn: $allowEdit)
                        .font(.body_)
                        .tint(Theme.Palette.primary)
                }

                Button(model.isWorking ? "送っています…" : "この人に見せる") {
                    Task {
                        if await model.addGrant(email: email, canEdit: allowEdit) {
                            email = ""
                            allowEdit = false
                        }
                    }
                }
                .buttonStyle(CloverButtonStyle())
                .disabled(email.isEmpty || model.isWorking)

                if !model.grants.isEmpty {
                    Divider().padding(.vertical, 2)
                    ForEach(model.grants) { grant in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(grant.email)
                                    .font(Theme.Font_.rounded(13, weight: .semibold))
                                    .foregroundStyle(Theme.Palette.textMain)
                                Text(grant.permission == "edit" ? "見る・直す" : "見るだけ")
                                    .font(.meta)
                                    .foregroundStyle(Theme.Palette.textMuted)
                            }
                            Spacer()
                            Button("やめる") { Task { await model.revokeGrant(grant) } }
                                .buttonStyle(QuietButtonStyle(tint: Theme.Palette.danger))
                        }
                        .padding(.vertical, 3)
                    }
                }
            }
        }
    }
}

// MARK: - 状態

@MainActor
final class ShareViewModel: ObservableObject {
    @Published private(set) var links: [PublicLink] = []
    @Published private(set) var grants: [ShareGrant] = []
    @Published private(set) var editableSupported = false
    @Published private(set) var state: LoadState = .loading
    @Published private(set) var isWorking = false
    @Published var errorMessage: String?

    enum LoadState { case loading, ready, failed(String) }

    private let resource: ShareService.Resource
    private let resourceId: Int

    init(resource: ShareService.Resource, resourceId: Int) {
        self.resource = resource
        self.resourceId = resourceId
    }

    func load() async {
        do {
            let shareState = try await ShareService.state(resource, id: resourceId)
            links = shareState.links
            grants = shareState.grants
            editableSupported = shareState.editableSupported
            state = .ready
        } catch {
            state = .failed((error as? APIError)?.errorDescription
                            ?? "共有の状態を読み込めませんでした。")
        }
    }

    func createLink() async {
        await work {
            _ = try await ShareService.createLink(self.resource, id: self.resourceId)
        }
    }

    func revokeLink(_ link: PublicLink) async {
        await work { try await ShareService.revokeLink(linkId: link.id) }
    }

    func addGrant(email: String, canEdit: Bool) async -> Bool {
        let address = email.trimmingCharacters(in: .whitespaces)
        guard address.contains("@") else {
            errorMessage = "メールアドレスを確かめてね。"
            return false
        }
        return await work {
            _ = try await ShareService.addGrant(self.resource, id: self.resourceId,
                                                email: address,
                                                permission: canEdit ? "edit" : "view")
        }
    }

    func revokeGrant(_ grant: ShareGrant) async {
        await work { try await ShareService.revokeGrant(grantId: grant.id) }
    }

    /// 共通の後始末（実行中の表示・エラー文言・一覧の読み直し）。
    @discardableResult
    private func work(_ action: @escaping () async throws -> Void) async -> Bool {
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }
        do {
            try await action()
            await load()
            return true
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "うまくいきませんでした。もう一度ためしてね。"
            return false
        }
    }
}
