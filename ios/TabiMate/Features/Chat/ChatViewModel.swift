import Foundation
import SwiftUI

/// ちゃむとの相談の状態。
///
/// 生成中にアプリを閉じても迷子にならないよう、進行中の request_id を端末に控えておき、
/// 起動時にサーバーへ「あれ、まだ動いてる？」と尋ねて画面を戻す（Web版と同じ考え方）。
@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isGenerating = false
    @Published private(set) var isLoading = true
    @Published var draft = ""
    @Published var errorMessage: String?

    private var streamTask: Task<Void, Never>?
    private var pollTask: Task<Void, Never>?
    private var currentRequestId: String?

    /// 進行中の生成を覚えておく場所。
    private static let pendingKey = "tabimate.pendingRequestId"

    // MARK: - 読み込み

    func load() async {
        isLoading = true
        defer { isLoading = false }
        await reloadMessages()
        await resumeIfGenerating()
    }

    /// ホームのチップから渡された文章を入力欄に入れる。
    ///
    /// タブは一度表示されると作り直されない（＝load は初回しか走らない）ので、
    /// 画面が出るたびに呼ぶ。書きかけの文章があるときは邪魔しない。
    func consumePendingDraft() {
        guard let pending = ChatDraft.shared.pending else { return }
        ChatDraft.shared.pending = nil
        guard draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        draft = pending
    }

    private func reloadMessages() async {
        do {
            messages = try await ChatService.messages()
            errorMessage = nil
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "履歴を読み込めませんでした。"
        }
    }

    // MARK: - 送信

    func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isGenerating else { return }

        let requestId = UUID().uuidString
        currentRequestId = requestId
        UserDefaults.standard.set(requestId, forKey: Self.pendingKey)
        draft = ""
        errorMessage = nil
        isGenerating = true

        // 送った言葉はすぐ画面に出す（サーバーの保存を待たない）
        messages.append(ChatMessage(role: "user", content: text,
                                    requestId: requestId, plan: nil))

        streamTask = Task { [weak self] in
            guard let self else { return }
            do {
                for try await event in ChatService.send(message: text, requestId: requestId) {
                    switch event {
                    case .thinking:
                        continue
                    case .done:
                        await self.finish(reload: true)
                    case .aborted:
                        await self.finish(reload: true)
                    case .failed(let message):
                        await self.finish(reload: true, error: message)
                    }
                }
                // ストリームが結末を告げずに切れた場合（回線断など）も状態を戻す
                await self.finishIfStillGenerating()
            } catch is CancellationError {
                // 自分で「やめる」を押したとき。後始末は abort() 側がやるので何も出さない
            } catch APIError.cancelled {
                // 同上（URLSession 側から取り消しが返ってきた場合）
            } catch {
                let message = (error as? APIError)?.errorDescription
                    ?? "うまく送れませんでした。もう一度ためしてね。"
                await self.finish(reload: true, error: message)
            }
        }
    }

    /// 生成をやめる。サーバー側でもそのやりとりが消される。
    func abort() async {
        guard let requestId = currentRequestId else { return }
        streamTask?.cancel()
        pollTask?.cancel()
        try? await ChatService.abort(requestId: requestId)
        await finish(reload: true)
    }

    private func finish(reload: Bool, error: String? = nil) async {
        isGenerating = false
        currentRequestId = nil
        UserDefaults.standard.removeObject(forKey: Self.pendingKey)
        if reload { await reloadMessages() }
        // 履歴の読み直しでエラーが消えてしまわないよう、後から入れる
        if let error { errorMessage = error }
    }

    /// ストリームが黙って終わったときの後始末。
    private func finishIfStillGenerating() async {
        guard isGenerating else { return }
        await finish(reload: true,
                     error: "通信が途切れちゃったみたい。結果は履歴で確かめてね。")
    }

    // MARK: - 中断からの復帰

    /// 前回の生成がまだ動いていれば、作成中の見た目に戻して結果を待つ。
    private func resumeIfGenerating() async {
        guard let requestId = UserDefaults.standard.string(forKey: Self.pendingKey) else { return }

        let active: Bool
        do {
            active = try await ChatService.isGenerating(requestId: requestId)
        } catch {
            return  // 通信できないだけなら、次に開いたときに任せる
        }
        guard active else {
            // もう決着している（完了か中断）。履歴はさっき読んだ内容で正しい
            UserDefaults.standard.removeObject(forKey: Self.pendingKey)
            return
        }

        currentRequestId = requestId
        isGenerating = true
        startPolling(requestId: requestId)
    }

    /// SSE は再接続できないので、終わったかどうかを一定間隔で尋ねる。
    private func startPolling(requestId: String) {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            // 2.5秒ごと、最長15分まで。それを超えたら見た目だけ元に戻す
            for _ in 0..<360 {
                try? await Task.sleep(for: .seconds(2.5))
                if Task.isCancelled { return }
                guard let self else { return }
                guard let stillGenerating = try? await ChatService.isGenerating(requestId: requestId)
                else { continue }  // 一時的な通信エラーは次の周回で
                if !stillGenerating {
                    await self.finish(reload: true)
                    return
                }
            }
            await self?.finish(reload: true)
        }
    }

    // MARK: - 保存とリセット

    /// プランを保存する。保存できたら true（失敗したらボタンを押せる状態に戻す）。
    func save(plan: DraftPlan) async -> Bool {
        do {
            _ = try await ChatService.save(plan: plan)
            NotificationCenter.default.post(name: .plansChanged, object: nil)
            return true
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "保存できませんでした。もう一度ためしてね。"
            return false
        }
    }

    func resetConversation() async {
        do {
            try await ChatService.resetHistory()
            messages = []
            errorMessage = nil
        } catch {
            errorMessage = (error as? APIError)?.errorDescription
                ?? "履歴を消せませんでした。"
        }
    }
}
