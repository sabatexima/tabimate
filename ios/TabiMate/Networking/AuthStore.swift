import Foundation
import SwiftUI
import UIKit

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
    private static let cachedUserKey = "tabimate.cachedUser"

    private init() {
        #if DEBUG
        // UIテストは Google のサインインを通れないので、ここだけ差し替える。
        // （@StateObject の既定値は遅延評価なので、この init は
        //   TabiMateApp.init の UITestSupport.activate より後に走る）
        if UITestSupport.isEnabled {
            TokenBox.current = UITestSupport.token
            return
        }
        #endif
        // 前回のトークンを Keychain から復帰させ、どのスレッドからも読める箱に入れる
        TokenBox.current = Keychain.get(Self.account)
    }

    // MARK: - 起動時

    /// 前回のサインインを引き継ぐ。
    ///
    /// 先に手元の記録で画面を出し、そのあとサーバーにトークンの有効性を確かめる。
    /// こうしないと、圏外で開いただけでサインイン画面に逆戻りしてしまう。
    /// 期限切れ（30日）と分かったときだけサインアウト扱いにする。
    func restoreSession() async {
        defer { isRestoring = false }
        guard TokenBox.current != nil else { return }

        user = cachedUser          // まず手元の記録で入れる
        do {
            let me = try await APIClient.shared.get("auth/app/me", as: MeResponse.self)
            user = me.user
            cacheUser(me.user)
        } catch APIError.unauthorized {
            clearToken()           // トークンが無効。ここだけがサインアウトの条件
        } catch {
            // 通信できないだけ。手元の記録のまま使い続ける
        }
    }

    // MARK: - 手元の記録

    private var cachedUser: AppUser? {
        guard let data = UserDefaults.standard.data(forKey: Self.cachedUserKey) else { return nil }
        return try? JSONDecoder().decode(AppUser.self, from: data)
    }

    private func cacheUser(_ user: AppUser?) {
        guard let user, let data = try? JSONEncoder().encode(user) else {
            return UserDefaults.standard.removeObject(forKey: Self.cachedUserKey)
        }
        UserDefaults.standard.set(data, forKey: Self.cachedUserKey)
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
        cacheUser(res.user)
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
        cacheUser(nil)
        user = nil
    }

    private struct MeResponse: Codable {
        let status: String
        let user: AppUser
    }
}
