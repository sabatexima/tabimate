import XCTest
@testable import TabiMate

/// 送信内容の組み立て。ここが崩れると、送った文章が黙って化ける。
final class RequestBuildingTests: XCTestCase {

    private func body(_ fields: [String: String]) -> String {
        String(data: APIClient.formBody(fields), encoding: .utf8) ?? ""
    }

    func testReservedCharactersAreEscaped() {
        // + をそのまま通すとサーバー側で空白になる（URLComponents の既定の挙動）
        XCTAssertEqual(body(["message": "A+B案"]), "message=A%2BB%E6%A1%88")
        // & や = を通すとフィールドの区切りとして解釈され、文章が切れる
        XCTAssertEqual(body(["message": "a&b=c"]), "message=a%26b%3Dc")
    }

    func testSpacesAndJapanese() {
        XCTAssertEqual(body(["message": "熱海 に行きたい"]),
                       "message=%E7%86%B1%E6%B5%B7%20%E3%81%AB%E8%A1%8C%E3%81%8D%E3%81%9F%E3%81%84")
    }

    func testMultipleFieldsAreJoinedWithAmpersand() {
        let text = body(["a": "1", "b": "2"])
        XCTAssertEqual(Set(text.split(separator: "&").map(String.init)), ["a=1", "b=2"])
    }

    func testEmptyValue() {
        // 空文字は「記録を消す」の意味で送ることがある
        XCTAssertEqual(body(["actual_total": ""]), "actual_total=")
    }

    func testRequestCarriesBearerTokenAndAcceptsJSON() {
        TokenBox.current = "test-token"
        defer { TokenBox.current = nil }

        let request = APIClient.request("get_my_plans")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertTrue(request.url?.path.hasSuffix("/get_my_plans") ?? false)
    }

    func testRequestWithoutTokenHasNoAuthorization() {
        TokenBox.current = nil
        XCTAssertNil(APIClient.request("api/ideas").value(forHTTPHeaderField: "Authorization"))
    }

    func testQueryItemsAreAttached() {
        TokenBox.current = nil
        let request = APIClient.request("generation_status", query: ["request_id": "abc-123"])
        XCTAssertEqual(request.url?.query, "request_id=abc-123")
    }

    func testErrorMessagesAreReadableJapanese() {
        // 画面にそのまま出るので、必ず文言があること
        let errors: [APIError] = [.offline, .unauthorized, .rateLimited(nil), .notFound,
                                  .server(nil), .decoding, .cancelled]
        for error in errors {
            XCTAssertFalse(error.errorDescription?.isEmpty ?? true, "\(error) に文言が無い")
        }
        // サーバーが文言を寄こしたときはそれを優先する
        XCTAssertEqual(APIError.rateLimited("混んでいます").errorDescription, "混んでいます")
    }
}
