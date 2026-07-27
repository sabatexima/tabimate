import Foundation
import Security

/// アプリ用トークンの保管庫。
/// UserDefaults ではなく Keychain に置く（バックアップや他アプリから読めないように）。
enum Keychain {
    private static let service = "app.tabimate.token"

    static func set(_ value: String?, for account: String) {
        guard let value, !value.isEmpty else { return remove(account) }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attributes: [String: Any] = [
            kSecValueData as String: Data(value.utf8),
            // 端末のロック解除後のみ読める。他端末へは持ち出さない
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            SecItemAdd(query.merging(attributes) { $1 } as CFDictionary, nil)
        }
    }

    static func get(_ account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func remove(_ account: String) {
        SecItemDelete([
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ] as CFDictionary)
    }
}

/// 現在のトークンをどのスレッドからでも読めるようにしておく置き場。
///
/// AuthStore は画面と結びつくので @MainActor に置きたい。一方 APIClient は
/// バックグラウンドから Authorization ヘッダを組む。両方の都合を満たすため、
/// 値そのものはここ（アクター非依存・ロック付き）に持たせる。
enum TokenBox {
    private static let lock = NSLock()
    private static var value: String?

    static var current: String? {
        get { lock.withLock { value } }
        set { lock.withLock { value = newValue } }
    }
}
