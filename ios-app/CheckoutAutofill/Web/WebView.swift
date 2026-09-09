import SwiftUI
import WebKit

/// Porta la WKWebView dentro SwiftUI. La vista è una sola per tutta la vita
/// dell'app: la cronologia e i cookie del negozio restano dove sono anche
/// passando dalle altre schede.
struct WebView: UIViewRepresentable {
    let webView: WKWebView

    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) { }
}
