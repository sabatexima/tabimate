import Foundation
import SwiftUI

/// サインイン状態をアプリ全体で共有する。
///
/// 流れ:
///   1. GoogleSignIn で ID トークンをもらう
///   2. サーバー /auth/app/signin に渡して、アプリ用トークンを受け取る
///   3. Keychain に保存し、以降のAPIに Bearer で付ける
///
/// GoogleSignIn SDK は SPM で追加する（手順は ios/README.md）。
/// SDK 未導入でもビルドが通るよう、`GOOGLE_SIGN_IN` フラグで切り分けている。
#if canImport(GoogleSignIn)
import GoogleSignIn
#endif

@MainActor
final class AuthStore: ObservableObject {
    static let shared = AuthStore()

    @Published private(set) var user: AppUser?
    @Published private(set) var isRestoring = true
    @Published var errorMessage: String?

    var isSignedIn: Bool { user != nil }

    private static let account = "app-token"

    private init() {
        // 前回のトークンを Keychain から復帰させ、どのスレッドからも読める箱に入れる
        TokenBox.current = Keychain.get(Self.account)
    }

    // MARK: - 起動時

    /// 保存済みトークンがまだ有効かをサーバーに確かめる。
    /// 期限切れ（30日）ならサインアウト扱いにして、ログイン画面へ戻す。
    func restoreSession() async {
        defer { isRestoring = false }
        guard TokenBox.current != nil else { return }
        do {
            let me = try await APIClient.shared.get("auth/app/me", as: MeResponse.self)
            user = me.user
        } catch APIError.unauthorized {
            clearToken()
        } catch {
            // 通信できないだけなら、トークンは消さずに保持したまま起動する
            // （オフラインで開いただけでサインアウトさせられるのは理不尽なので）
            user = nil
        }
    }

    // MARK: - サインイン

    #if canImport(GoogleSignIn)
    /// Google のサインイン画面を出し、得た ID トークンをサーバーに渡す。
    func signIn(presenting: UIViewController) async {
        errorMessage = nil
        do {
            let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenting)
            guard let idToken = result.user.idToken?.tokenString else {
                errorMessage = "Googleからの返事が受け取れませんでした。もう一度ためしてね。"
                return
            }
            try await exchange(idToken: idToken)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            // ユーザーが自分で閉じたときはエラー扱いにしない
            let cancelled = (error as NSError).code == GIDSignInError.canceled.rawValue
            errorMessage = cancelled ? nil : "サインインできませんでした。もう一度ためしてね。"
        }
    }
    #endif

    /// ID トークンをアプリ用トークンに交換する。
    func exchange(idToken: String) async throws {
        let res = try await APIClient.shared.post(
            "auth/app/signin", json: ["id_token": idToken], as: SignInResponse.self
        )
        TokenBox.current = res.token
        Keychain.set(res.token, for: Self.account)
        user = res.user
    }

    // MARK: - サインアウト

    func signOut() {
        #if canImport(GoogleSignIn)
        GIDSignIn.sharedInstance.signOut()
        #endif
        clearToken()
    }

    /// トークンが無効になったときの後始末（APIが401を返したときにも使う）。
    func clearToken() {
        TokenBox.current = nil
        Keychain.remove(Self.account)
        user = nil
    }

    private struct MeResponse: Codable {
        let status: String
        let user: AppUser
    }
}
