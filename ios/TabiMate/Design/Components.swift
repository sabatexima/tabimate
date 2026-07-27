import SwiftUI
import UIKit

/// 画面をまたいで使う部品たち。Web版の見出し・カード・付箋と同じ様式にそろえる。

// MARK: - 見出し

/// 英字キッカー ＋ タイトル ＋ リード文。各一覧ページ共通の見出し。
struct PageHeader: View {
    let kicker: String
    let title: String
    /// タイトルのうち、緑の波線を引く部分（Web版の .accent）。
    var accent: String? = nil
    var lead: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(kicker.uppercased())
                .font(.kicker)
                .tracking(4.2)
                .foregroundStyle(Theme.Palette.kicker)

            HStack(alignment: .firstTextBaseline, spacing: 0) {
                Text(title)
                    .font(.pageTitle)
                    .foregroundStyle(Theme.Palette.textMain)
                if let accent {
                    WavyUnderline { Text(accent).font(.pageTitle) }
                        .foregroundStyle(Theme.Palette.textMain)
                }
            }

            if let lead {
                Text(lead)
                    .font(.body_)
                    .lineSpacing(6)
                    .foregroundStyle(Theme.Palette.textMuted)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// 文字の下に手描き風の波線を引く（Web版の text-decoration: underline wavy）。
struct WavyUnderline<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content.overlay(alignment: .bottom) {
            WaveShape()
                .stroke(Theme.Palette.primary.opacity(0.5),
                        style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                .frame(height: 5)
                .offset(y: 8)
        }
    }

    private struct WaveShape: Shape {
        func path(in rect: CGRect) -> Path {
            var path = Path()
            let wavelength: CGFloat = 7
            let mid = rect.midY
            path.move(to: CGPoint(x: rect.minX, y: mid))
            var x = rect.minX
            var up = true
            while x < rect.maxX {
                let next = min(x + wavelength, rect.maxX)
                path.addQuadCurve(
                    to: CGPoint(x: next, y: mid),
                    control: CGPoint(x: (x + next) / 2, y: up ? rect.minY : rect.maxY)
                )
                x = next
                up.toggle()
            }
            return path
        }
    }
}

// MARK: - 面

/// 共通のカード。やわらかい境界線と控えめな影。
struct Card<Content: View>: View {
    var padding: CGFloat = 16
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.Palette.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.card)
                    .stroke(Theme.Palette.border, lineWidth: 1)
            )
            .cardShadow()
    }
}

/// パステルの付箋。少しだけ傾けて「貼ってある」ように見せる。
struct StickyNote<Content: View>: View {
    var style: Theme.Sticky = .yellow
    var tilted: Bool = true
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(style.paper, in: RoundedRectangle(cornerRadius: Theme.Radius.paper))
            .shadow(color: Theme.Shadow.sticky.color,
                    radius: Theme.Shadow.sticky.radius,
                    y: Theme.Shadow.sticky.y)
            .rotationEffect(.degrees(tilted ? style.tilt : 0))
    }
}

/// 付箋やカードを留めるマスキングテープ。
struct WashiTape: View {
    var angle: Double = -6
    var width: CGFloat = 62

    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(
                LinearGradient(colors: [Color(hex: 0xEFE7C8, opacity: 0.92),
                                        Color(hex: 0xE3D9B4, opacity: 0.86)],
                               startPoint: .leading, endPoint: .trailing)
            )
            .frame(width: width, height: 20)
            .overlay(Rectangle().stroke(Color.white.opacity(0.5), lineWidth: 0.5))
            .rotationEffect(.degrees(angle))
            .shadow(color: .black.opacity(0.08), radius: 2, y: 1)
    }
}

// MARK: - ボタン

/// 主役のボタン（四つ葉の緑）。
struct CloverButtonStyle: ButtonStyle {
    var expands: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Font_.rounded(15, weight: .bold))
            .foregroundStyle(.white)
            .padding(.horizontal, 22)
            .padding(.vertical, 13)
            .frame(maxWidth: expands ? .infinity : nil)
            .background(
                configuration.isPressed ? Theme.Palette.primaryHover : Theme.Palette.primary,
                in: Capsule()
            )
            .shadow(color: Theme.Palette.primaryDark.opacity(0.25), radius: 6, y: 3)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// 控えめなボタン（紙の面に線だけ）。
struct QuietButtonStyle: ButtonStyle {
    var tint: Color = Theme.Palette.textMuted

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Font_.rounded(13, weight: .semibold))
            .foregroundStyle(tint)
            .padding(.horizontal, 16)
            .padding(.vertical, 9)
            .background(Theme.Palette.surface, in: Capsule())
            .overlay(Capsule().stroke(Theme.Palette.border, lineWidth: 1))
            .opacity(configuration.isPressed ? 0.7 : 1)
    }
}

// MARK: - ちゃむ

/// ちゃむのひとこと。吹き出しの向きは左（ちゃむの隣）に固定。
struct ChamuBubble: View {
    let text: String
    var size: CGFloat = 46

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            ChamuAvatar(size: size)
            Text(text)
                .font(.body_)
                .lineSpacing(5)
                .foregroundStyle(Theme.Palette.textMain)
                .padding(.horizontal, 15)
                .padding(.vertical, 12)
                .background(Theme.Palette.surface, in: BubbleShape())
                .overlay(BubbleShape().stroke(Theme.Palette.border, lineWidth: 1))
                .shadow(color: Theme.Shadow.soft.color, radius: Theme.Shadow.soft.radius, y: 2)
        }
    }

    /// 左下にしっぽの付いた吹き出し。
    private struct BubbleShape: Shape {
        func path(in rect: CGRect) -> Path {
            var path = Path(roundedRect: rect, cornerRadius: 14)
            path.move(to: CGPoint(x: rect.minX + 2, y: rect.maxY - 16))
            path.addLine(to: CGPoint(x: rect.minX - 7, y: rect.maxY - 6))
            path.addLine(to: CGPoint(x: rect.minX + 4, y: rect.maxY - 4))
            path.closeSubpath()
            return path
        }
    }
}

/// ちゃむの絵。画像アセット "chamu" があればそれを、無ければ四つ葉で代用する。
struct ChamuAvatar: View {
    var size: CGFloat = 46

    var body: some View {
        Group {
            if UIImage(named: "chamu") != nil {
                Image("chamu").resizable().scaledToFit()
            } else {
                Text("🍀").font(.system(size: size * 0.62))
                    .frame(width: size, height: size)
                    .background(Theme.Palette.glowCream.opacity(0.55), in: Circle())
            }
        }
        .frame(width: size, height: size)
        .accessibilityLabel("ちゃむ")
    }
}

// MARK: - 状態表示

/// まだ何もない画面（プランゼロ件など）。
struct EmptyStateView: View {
    let message: String
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: 18) {
            ChamuAvatar(size: 72)
            Text(message)
                .font(.body_)
                .multilineTextAlignment(.center)
                .lineSpacing(6)
                .foregroundStyle(Theme.Palette.textMuted)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(CloverButtonStyle(expands: false))
            }
        }
        .padding(32)
        .frame(maxWidth: .infinity)
    }
}

/// 読み込み中。四つ葉がゆっくり回る。
struct LoadingClover: View {
    var label: String? = nil
    @State private var spinning = false

    var body: some View {
        VStack(spacing: 12) {
            Text("🍀")
                .font(.system(size: 30))
                .rotationEffect(.degrees(spinning ? 360 : 0))
                .animation(.linear(duration: 2.4).repeatForever(autoreverses: false), value: spinning)
            if let label {
                Text(label).font(.meta).foregroundStyle(Theme.Palette.textMuted)
            }
        }
        .padding(24)
        .onAppear { spinning = true }
    }
}

/// エラーの見せ方も世界観の一部。責めない言葉で、やり直せる導線を必ず添える。
struct ErrorNote: View {
    let message: String
    /// ボタンの文言。やり直しではなく単に閉じるときは「とじる」などに変える。
    var retryTitle: String = "もういちど"
    var retry: (() -> Void)? = nil

    var body: some View {
        StickyNote(style: .pink) {
            VStack(alignment: .leading, spacing: 10) {
                Text(message)
                    .font(.body_)
                    .lineSpacing(5)
                    .foregroundStyle(Theme.Sticky.pink.ink)
                if let retry {
                    Button(retryTitle, action: retry)
                        .buttonStyle(QuietButtonStyle(tint: Theme.Sticky.pink.ink))
                }
            }
        }
    }
}
