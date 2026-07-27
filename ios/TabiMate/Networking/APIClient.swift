import Foundation

/// サーバーとの通信の入口。トークンの付与とエラーの日本語化をここに集約する。
///
/// 認証は Authorization: Bearer <アプリ用トークン>。サーバー側の login_required が
/// セッションCookieと同じように扱ってくれる（src/api_auth.py）。
actor APIClient {
    static let shared = APIClient()

    /// 接続先。Info.plist の TabiMateBaseURL で差し替えられる（開発中はローカルに向ける）。
    nonisolated static var baseURL: URL {
        if let s = Bundle.main.object(forInfoDictionaryKey: "TabiMateBaseURL") as? String,
           let url = URL(string: s), !s.isEmpty {
            return url
        }
        return URL(string: "https://tabimate.example.com")!
    }

    private let session: URLSession

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        // 持ち物リストの生成や初回のジオコーディングは十数秒かかるので少し長めに。
        // 数分かかるプラン生成だけは別扱いで、ChatService が個別に延ばしている。
        config.timeoutIntervalForResource = 120
        // 圏外のときは待たずに失敗させる。待たせると「ネットにつながらないみたい」を
        // 出せず、いつまでも回り続けるだけになる
        config.waitsForConnectivity = false
        session = URLSession(configuration: config)
    }

    // MARK: - リクエスト組み立て

    /// 認証ヘッダ入りのリクエストを作る。
    nonisolated static func request(
        _ path: String,
        method: String = "GET",
        query: [String: String] = [:],
        body: Data? = nil,
        contentType: String? = nil
    ) -> URLRequest {
        var comps = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        )!
        if !query.isEmpty {
            comps.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var req = URLRequest(url: comps.url!)
        req.httpMethod = method
        req.httpBody = body
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let contentType {
            req.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        if let token = TokenBox.current {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return req
    }

    /// フォーム形式（application/x-www-form-urlencoded）の本文を作る。
    nonisolated static func formBody(_ fields: [String: String]) -> Data {
        var comps = URLComponents()
        comps.queryItems = fields.map { URLQueryItem(name: $0.key, value: $0.value) }
        return (comps.percentEncodedQuery ?? "").data(using: .utf8) ?? Data()
    }

    // MARK: - 送受信

    /// JSON を取得してデコードする。
    func get<T: Decodable>(_ path: String, query: [String: String] = [:], as type: T.Type) async throws -> T {
        try await send(APIClient.request(path, query: query), as: type)
    }

    /// JSON を送って結果をデコードする。
    func post<T: Decodable>(_ path: String, json: [String: Any] = [:], as type: T.Type) async throws -> T {
        let body = try JSONSerialization.data(withJSONObject: json)
        return try await send(
            APIClient.request(path, method: "POST", body: body, contentType: "application/json"),
            as: type
        )
    }

    /// 応答の中身を使わない送信（削除など）。
    @discardableResult
    func send(_ request: URLRequest) async throws -> Data {
        try await perform(request).0
    }

    func send<T: Decodable>(_ request: URLRequest, as type: T.Type) async throws -> T {
        let (data, _) = try await perform(request)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    private func perform(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError where error.code == .cancelled {
            throw APIError.cancelled
        } catch {
            throw APIError.offline
        }
        guard let http = response as? HTTPURLResponse else { throw APIError.server(nil) }
        try APIClient.check(http, data: data)
        return (data, http)
    }

    /// ステータスコードを見て、必要なら APIError に変換する。
    ///
    /// 401 の後始末（トークン破棄→サインイン画面へ）もここで行う。通常のAPIも
    /// チャットのSSEも必ずこの関数を通るので、片方だけ取り残されることがない。
    nonisolated static func check(_ http: HTTPURLResponse, data: Data) throws {
        guard !(200..<300).contains(http.statusCode) else { return }
        // サーバーは {"status":"ERROR","message":"..."} を返すので、その言葉をそのまま使う
        let message = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?
            .flatMap { $0["message"] as? String }
        switch http.statusCode {
        case 401:
            // トークンが切れていた。持っていても無駄なので捨て、ログイン画面に戻す
            Task { @MainActor in AuthStore.shared.clearToken() }
            throw APIError.unauthorized
        case 429: throw APIError.rateLimited(message)
        case 404: throw APIError.notFound
        default:  throw APIError.server(message)
        }
    }
}

// MARK: - エラー

/// 画面にそのまま出せる日本語を持つエラー。
/// ちゃむの世界観を壊さないよう、責める言い方はしない。
enum APIError: LocalizedError, Equatable {
    case offline
    case unauthorized
    case rateLimited(String?)
    case notFound
    case server(String?)
    case decoding
    case cancelled

    var errorDescription: String? {
        switch self {
        case .offline:
            return "ネットにつながらないみたい。電波のいいところでもう一度ためしてね。"
        case .unauthorized:
            return "ログインの有効期限が切れちゃった。もう一度サインインしてね。"
        case .rateLimited(let m):
            return m ?? "ちょっと急ぎすぎかも。少し待ってからもう一度おねがい。"
        case .notFound:
            return "見つからなかったみたい。"
        case .server(let m):
            return m ?? "うまくいかなかったみたい。少ししてからもう一度ためしてね。"
        case .decoding:
            return "返ってきた内容が読めなかったみたい。"
        case .cancelled:
            return "とりやめました。"
        }
    }
}
