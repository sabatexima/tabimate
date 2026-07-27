import SwiftUI

/// たびメイトの世界観をひとまとめにした定義。
/// Web版 (static/css/layout.css) の CSS 変数と同じ値を使い、
/// どちらから見ても「同じ絵本の続き」に見えるようにしている。
enum Theme {

    // MARK: - 色

    enum Palette {
        /// 四つ葉の緑。主役の色。
        static let primary      = Color(hex: 0x4FA83A)
        static let primaryDark  = Color(hex: 0x3B8A2C)
        static let primaryHover = Color(hex: 0x418C30)
        /// ちゃむの耳のやわらかいピンク。
        static let accentPink   = Color(hex: 0xF08BA0)
        /// 四つ葉まわりの淡い光。
        static let glowCream    = Color(hex: 0xF6F6A5)
        /// 英字キッカーの金茶。
        static let kicker       = Color(hex: 0xC2A05E)

        static let textMain     = Color(hex: 0x4A4540)
        static let textMuted    = Color(hex: 0x8A817A)

        /// カードなどの面。
        static let surface      = Color(hex: 0xFFFDF8)
        static let border       = Color(hex: 0xE7DDCA)
        static let borderInput  = Color(hex: 0xE0D5C0)

        /// 削除・取消。暖色寄りにして絵本トーンに馴染ませる。
        static let danger       = Color(hex: 0xE05A4A)
        static let dangerHover  = Color(hex: 0xCF4636)

        /// クリーム→淡い若葉色。全画面共通の背景。
        static let background = LinearGradient(
            colors: [Color(hex: 0xFDFAF2), Color(hex: 0xF4F6E9), Color(hex: 0xEDF3DE)],
            startPoint: .top, endPoint: .bottom
        )

        /// プランヘッダーの葉色グラデ。
        static let headerGradient = LinearGradient(
            colors: [Color(hex: 0x4A9D3A), Color(hex: 0x6FB152)],
            startPoint: .topLeading, endPoint: .bottomTrailing
        )
    }

    // MARK: - 付箋

    /// パステルの付箋。Web版と同じ 黄→ピンク→ミント の順でめぐらせる。
    enum Sticky: CaseIterable {
        case yellow, pink, mint

        /// 並び順から色を決める（Web版の :nth-child(3n) と同じ配色になる）。
        static func forIndex(_ index: Int) -> Sticky {
            switch index % 3 {
            case 1:  return .pink
            case 2:  return .mint
            default: return .yellow
            }
        }

        var paper: LinearGradient {
            let pair: (UInt32, UInt32)
            switch self {
            case .yellow: pair = (0xFFF6C9, 0xFDEFAC)
            case .pink:   pair = (0xFFE0E6, 0xFFD0DA)
            case .mint:   pair = (0xE2F6EA, 0xCDEEDD)
            }
            return LinearGradient(colors: [Color(hex: pair.0), Color(hex: pair.1)],
                                  startPoint: .topLeading, endPoint: .bottomTrailing)
        }

        var ink: Color {
            switch self {
            case .yellow: return Color(hex: 0x5B4A2A)
            case .pink:   return Color(hex: 0x7A3B48)
            case .mint:   return Color(hex: 0x2F6B4F)
            }
        }

        var subInk: Color {
            switch self {
            case .yellow: return Color(hex: 0x7A6A3A)
            case .pink:   return Color(hex: 0x96566A)
            case .mint:   return Color(hex: 0x4D8A6D)
            }
        }

        /// 手で貼ったような、ほんの少しの傾き。
        var tilt: Double {
            switch self {
            case .yellow: return 1.8
            case .pink:   return -1.4
            case .mint:   return 1.1
            }
        }
    }

    // MARK: - かたち

    enum Radius {
        static let card: CGFloat = 16
        static let pill: CGFloat = 20
        /// 付箋は角丸をほとんど付けない（紙の四角さを残す）。
        static let paper: CGFloat = 3
    }

    enum Shadow {
        static let card   = (color: Color(red: 0.47, green: 0.43, blue: 0.35, opacity: 0.08),
                             radius: CGFloat(10), y: CGFloat(4))
        static let soft   = (color: Color(red: 0.47, green: 0.43, blue: 0.35, opacity: 0.06),
                             radius: CGFloat(5), y: CGFloat(2))
        static let sticky = (color: Color(red: 0.47, green: 0.39, blue: 0.16, opacity: 0.14),
                             radius: CGFloat(12), y: CGFloat(8))
    }

    // MARK: - 文字

    /// Zen Maru Gothic。バンドルに無ければ端末標準の丸ゴシック系に自動で落ちる
    /// （フォントの導入手順は ios/README.md を参照）。
    enum Font_ {
        static let familyRegular = "ZenMaruGothic-Regular"
        static let familyBold    = "ZenMaruGothic-Bold"

        static var isBundled: Bool {
            UIFont(name: familyRegular, size: 12) != nil
        }

        static func rounded(_ size: CGFloat, weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            guard isBundled else {
                return .system(size: size, weight: weight, design: .rounded)
            }
            let name = (weight == .bold || weight == .semibold) ? familyBold : familyRegular
            return .custom(name, size: size)
        }
    }
}

// MARK: - よく使う文字スタイル

extension Font {
    /// 英字キッカー（大きく字間を空けた小さな見出し）。
    static var kicker: Font { Theme.Font_.rounded(11, weight: .bold) }
    /// ページタイトル。
    static var pageTitle: Font { Theme.Font_.rounded(28, weight: .bold) }
    /// カード見出し。
    static var cardTitle: Font { Theme.Font_.rounded(17, weight: .bold) }
    /// 本文。
    static var body_: Font { Theme.Font_.rounded(15) }
    /// 補足・メタ情報。
    static var meta: Font { Theme.Font_.rounded(12) }
}

// MARK: - 便利

extension Color {
    /// 0xRRGGBB 形式で色を作る（CSS の値をそのまま書き写せるように）。
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red:   Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >>  8) & 0xFF) / 255,
            blue:  Double( hex        & 0xFF) / 255,
            opacity: opacity
        )
    }
}

extension View {
    /// 画面全体の背景（クリーム→若葉）。
    func paperBackground() -> some View {
        background(Theme.Palette.background.ignoresSafeArea())
    }

    /// カードの共通の影。
    func cardShadow() -> some View {
        shadow(color: Theme.Shadow.card.color,
               radius: Theme.Shadow.card.radius,
               y: Theme.Shadow.card.y)
    }
}
