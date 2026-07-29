import Foundation

/// しおり・おもいでの共有。Web版と同じ /share エンドポイントを使う。
///
/// 公開リンクは「URLを知っていれば誰でも閲覧」。編集を渡せるのはメール共有だけ
/// （サーバー側でそう決まっている）。
enum ShareService {

    /// 共有できるものの種類。
    enum Resource: String {
        case plan
        case trip

        var label: String {
            switch self {
            case .plan: return "しおり"
            case .trip: return "おもいで"
            }
        }
    }

    static func state(_ resource: Resource, id: Int) async throws -> ShareState {
        try await APIClient.shared.get("share/\(resource.rawValue)/\(id)", as: ShareState.self)
    }

    /// 公開リンクを発行する（常に閲覧専用）。
    static func createLink(_ resource: Resource, id: Int) async throws -> PublicLink {
        try await APIClient.shared.post("share/\(resource.rawValue)/\(id)/link", as: PublicLink.self)
    }

    static func revokeLink(linkId: Int) async throws {
        let req = APIClient.request("share/link/\(linkId)", method: "DELETE")
        try await APIClient.shared.send(req)
    }

    /// メールを指定して渡す。permission は "view" か "edit"。
    static func addGrant(_ resource: Resource, id: Int,
                         email: String, permission: String) async throws -> ShareGrant {
        try await APIClient.shared.post(
            "share/\(resource.rawValue)/\(id)/grant",
            json: ["email": email, "permission": permission],
            as: ShareGrant.self
        )
    }

    static func revokeGrant(grantId: Int) async throws {
        let req = APIClient.request("share/grant/\(grantId)", method: "DELETE")
        try await APIClient.shared.send(req)
    }

    /// 共有された側が、自分宛の共有を外す。
    static func leaveShared(grantId: Int) async throws {
        let req = APIClient.request("shared/grant/\(grantId)", method: "DELETE")
        try await APIClient.shared.send(req)
    }
}
