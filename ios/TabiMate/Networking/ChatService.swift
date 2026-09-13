import Foundation

/// ちゃむとの相談（プラン生成）のAPI。
///
/// 生成は数分かかることがあるので、サーバーは SSE で「まだ考えてるよ」を送り続け、
/// 終わったときに最後の1件で結果を知らせる（src/views/planner.py の send_message）。
enum ChatService {

    /// サーバーから届く出来事。
    enum Event {
        /// まだ考え中（3秒ごとに届く）。
        case thinking
        /// できあがり。履歴を取り直せば新しい返事が入っている。
        case done(requestId: String)
        /// 中断された。
        case aborted
        /// 生成に失敗した。
        case failed(message: String)
    }

    // MARK: - 履歴

    /// 会話の履歴。AIが出したプランは plan に構造化された形で入る。
    static func messages() async throws -> [ChatMessage] {
        try await APIClient.shared.get("api/chat_messages", as: MessagesResponse.self).messages
    }

    /// 提示されたプランを保存する。保存後の plan_id を返す。
    static func save(plan: DraftPlan) async throws -> Int {
        let encoder = JSONEncoder()
        let req = APIClient.request("save_plan", method: "POST",
                                    body: try encoder.encode(plan),
                                    contentType: "application/json")
        return try await APIClient.shared.send(req, as: SavedPlanResponse.self).id
    }

    /// /api/chat_messages の応答。
    private struct MessagesResponse: Codable {
        let status: String
        let messages: [ChatMessage]
    }

    /// /save_plan の応答（保存された plan_id が返る）。
    private struct SavedPlanResponse: Codable {
        let status: String
        let id: Int
    }

    /// 会話をまっさらにする（「新しいチャット」）。
    static func resetHistory() async throws {
        let req = APIClient.request("reset_chat", method: "POST")
        try await APIClient.shared.send(req)
    }

    // MARK: - 送信（ストリーミング）

    /// メッセージを送り、進み具合を順に受け取る。
    ///
    /// 呼び出し側は request_id を先に決めて渡す。こうしておくと、
    /// アプリを閉じてしまっても「あの生成」を後から追いかけられる。
    static func send(message: String, requestId: String) -> AsyncThrowingStream<Event, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let body = APIClient.formBody(["message": message, "request_id": requestId])
                    var req = APIClient.request(
                        "send_message", method: "POST", body: body,
                        contentType: "application/x-www-form-urlencoded"
                    )
                    req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    // 生成中は応答が途切れないので、リクエスト単位のタイムアウトを外す
                    req.timeoutInterval = 600

                    let (bytes, response) = try await URLSession.shared.bytes(for: req)
                    guard let http = response as? HTTPURLResponse else { throw APIError.server(nil) }
                    guard (200..<300).contains(http.statusCode) else {
                        // エラー時は SSE ではなく普通の JSON が返る。
                        // check は 2xx 以外で必ず throw するので、ここから先へは進まない
                        var data = Data()
                        for try await byte in bytes { data.append(byte) }
                        try APIClient.check(http, data: data)
                        throw APIError.server(nil)
                    }

                    for try await line in bytes.lines {
                        guard let event = parse(line: line) else { continue }
                        continuation.yield(event)
                        // 最後の1件が来たらそこで終わり
                        if case .thinking = event { continue }
                        break
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: normalize(error))
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// "data: {...}" の1行を Event に変換する（それ以外の行は nil）。
    private static func parse(line: String) -> Event? {
        guard line.hasPrefix("data:") else { return nil }
        let json = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
        guard let obj = try? JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any],
              let status = obj["status"] as? String else { return nil }
        switch status {
        case "thinking": return .thinking
        case "OK":       return .done(requestId: (obj["id"] as? String) ?? "")
        case "ABORTED":  return .aborted
        default:         return .failed(message: (obj["message"] as? String)
                                        ?? "プランの生成中にエラーが起きたみたい。")
        }
    }

    /// 通信の失敗を、画面にそのまま出せる APIError にそろえる。
    /// 取り消しだけは区別する（「やめる」を押したときにエラーを出さないため）。
    private static func normalize(_ error: Error) -> Error {
        if error is APIError { return error }
        if let urlError = error as? URLError {
            return urlError.code == .cancelled ? APIError.cancelled : APIError.offline
        }
        return APIError.server(nil)
    }

    // MARK: - 中断と復帰

    /// 生成をやめる。サーバー側でそのやりとりも消される。
    static func abort(requestId: String) async throws {
        let body = APIClient.formBody(["request_id": requestId])
        let req = APIClient.request("abort_request", method: "POST", body: body,
                                    contentType: "application/x-www-form-urlencoded")
        try await APIClient.shared.send(req)
    }

    /// 生成の行きつく先。アプリを閉じて戻ってきたときの状態復元に使う。
    enum GenerationState: String {
        /// まだ作っている最中。
        case pending
        /// 出来上がって履歴に入った。
        case done
        /// 失敗か中断。その回の行はサーバーが片付けているので残っていない。
        case gone
    }

    /// その生成がどうなったかを尋ねる。
    ///
    /// 見るのは state。サーバーが返す active は「このインスタンスがいま抱えているか」で、
    /// Cloud Run のように複数インスタンスで動いていると、別のインスタンスが走らせている
    /// 生成を取りこぼして「もう終わった」と答えてしまう。state は保存された行から
    /// 決まるので、どのインスタンスに当たっても同じ答えになる（src/db.py の
    /// chat_request_state）。active は state を返さない古いサーバー向けの保険。
    static func generationState(requestId: String) async throws -> GenerationState {
        let res = try await APIClient.shared
            .get("generation_status", query: ["request_id": requestId],
                 as: GenerationStatus.self)
        return resolveState(state: res.state, active: res.active)
    }

    /// 応答の2つの欄から行きつく先を決める（通信を伴わないので単体で試せる）。
    static func resolveState(state: String?, active: Bool?) -> GenerationState {
        if let state, let known = GenerationState(rawValue: state) { return known }
        return (active ?? false) ? .pending : .gone
    }

    /// /generation_status の応答。state が本命で、active は古いサーバー向けの保険。
    private struct GenerationStatus: Codable {
        let active: Bool?
        let state: String?
    }
}
