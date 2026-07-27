import SwiftUI
import UIKit

/// サーバーの写真を表示する。
///
/// AsyncImage を使えない事情がある:
/// 写真のURLは保存先によって2種類ある。
///   - GCS   : 署名付きの絶対URL（そのまま取れる）
///   - ローカル: "/reflection/photo/..." という相対パスで、しかも認証が要る
/// 後者に Authorization ヘッダを付ける必要があるため、自前で読み込む。
struct RemoteImage<Placeholder: View>: View {
    let urlString: String?
    var contentMode: ContentMode = .fill
    @ViewBuilder var placeholder: Placeholder

    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
            } else if failed {
                // 出せなかったことが分かるように。読み込み中の回転は止める
                placeholder.overlay(
                    Image(systemName: "photo")
                        .foregroundStyle(Theme.Palette.textMuted.opacity(0.5))
                )
            } else {
                placeholder.overlay(ProgressView().tint(Theme.Palette.primary))
            }
        }
        .task(id: urlString) { await load() }
    }

    private func load() async {
        image = nil
        failed = false
        guard let urlString, !urlString.isEmpty else {
            failed = true
            return
        }
        guard let loaded = await ImageCache.shared.image(urlString) else {
            failed = true
            return
        }
        image = loaded
    }
}

extension RemoteImage where Placeholder == Color {
    /// 既定の下地（クリーム色の面）。回転や写真アイコンは body 側で重ねる。
    init(_ urlString: String?, contentMode: ContentMode = .fill) {
        self.init(urlString: urlString, contentMode: contentMode) {
            Theme.Palette.surface
        }
    }
}

/// 読み込んだ写真をしばらく覚えておく置き場。
/// 一覧⇄詳細を行き来するたびに取り直すと、署名URLの発行も通信も無駄になる。
actor ImageCache {
    static let shared = ImageCache()

    private let cache = NSCache<NSString, UIImage>()
    /// 同じ写真を同時に何度も取りにいかないよう、進行中の読み込みを共有する。
    private var loading: [String: Task<UIImage?, Never>] = [:]

    private init() {
        cache.countLimit = 200
        // だいたい 60MB まで。写真が多い旅でも端末を圧迫しない程度に
        cache.totalCostLimit = 60 * 1024 * 1024
    }

    /// 覚えていればそれを、無ければ取りに行って覚える。
    func image(_ urlString: String) async -> UIImage? {
        if let cached = cache.object(forKey: urlString as NSString) { return cached }
        if let inFlight = loading[urlString] { return await inFlight.value }

        // detached にするのは、ここで作った Task がこのアクターに縛られると
        // 写真の展開が1枚ずつ順番待ちになり、一覧の表示が目に見えて遅くなるため。
        let task = Task<UIImage?, Never>.detached(priority: .userInitiated) {
            guard let request = Self.makeRequest(urlString) else { return nil }
            guard let (data, response) = try? await URLSession.shared.data(for: request),
                  let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode),
                  let image = UIImage(data: data) else { return nil }
            return image
        }
        loading[urlString] = task
        let image = await task.value
        loading[urlString] = nil
        if let image {
            // 実データを再エンコードすると重いので、画素数から概算する（1画素4バイト）
            let pixels = image.size.width * image.size.height * image.scale * image.scale
            cache.setObject(image, forKey: urlString as NSString, cost: Int(pixels) * 4)
        }
        return image
    }

    /// 絶対URLならそのまま、相対パスならサーバーのURLに繋いで認証を付ける。
    private nonisolated static func makeRequest(_ urlString: String) -> URLRequest? {
        if urlString.hasPrefix("http://") || urlString.hasPrefix("https://") {
            guard let url = URL(string: urlString) else { return nil }
            return URLRequest(url: url)
        }
        let path = urlString.hasPrefix("/") ? String(urlString.dropFirst()) : urlString
        var request = URLRequest(url: APIClient.baseURL.appendingPathComponent(path))
        if let token = TokenBox.current {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }
}
