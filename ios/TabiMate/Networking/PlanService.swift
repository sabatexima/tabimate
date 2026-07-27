import Foundation

/// 保存プランまわりのAPI。Web版と同じエンドポイントをそのまま使う。
enum PlanService {

    /// 自分の保存プラン一覧（新しい順）。
    /// 一覧の応答に詳細もすべて含まれるので、詳細画面のための追加取得は要らない。
    static func myPlans() async throws -> [TravelPlan] {
        try await APIClient.shared.get("get_my_plans", as: PlansResponse.self).plans
    }

    /// プランを消す。
    static func delete(planId: Int) async throws {
        let req = APIClient.request("delete_plan/\(planId)", method: "DELETE")
        try await APIClient.shared.send(req)
    }

    /// 地図に出す座標。未取得ならサーバー側がこの呼び出しの中で取りに行く（初回だけ遅い）。
    static func geo(planId: Int) async throws -> PlanGeo {
        try await APIClient.shared.get("api/plan_geo/\(planId)", as: PlanGeo.self)
    }

    /// 持ち物リストをAIに作ってもらう（作り直すと前の内容は置き換わる）。
    static func generatePackingList(planId: Int) async throws -> [String] {
        try await APIClient.shared
            .post("api/packing_list/\(planId)", as: PackingResponse.self).items
    }

    /// 実際にかかった金額を記録する。nil を渡すと記録を消す。
    static func saveActualTotal(planId: Int, amount: Int?) async throws {
        let body = APIClient.formBody(["actual_total": amount.map(String.init) ?? ""])
        let req = APIClient.request("save_actual_total/\(planId)", method: "POST",
                                    body: body,
                                    contentType: "application/x-www-form-urlencoded")
        try await APIClient.shared.send(req)
    }

    /// 旅の感想（★と一言）を残す。
    static func rate(planId: Int, rating: Int, comment: String) async throws {
        let body = APIClient.formBody(["rating": String(rating), "comment": comment])
        let req = APIClient.request("rate_plan/\(planId)", method: "POST",
                                    body: body,
                                    contentType: "application/x-www-form-urlencoded")
        try await APIClient.shared.send(req)
    }

    private struct PlansResponse: Codable {
        let status: String
        let plans: [TravelPlan]
    }

    private struct PackingResponse: Codable {
        let status: String
        let items: [String]
    }
}
