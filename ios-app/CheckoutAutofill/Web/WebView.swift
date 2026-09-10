import SwiftUI
import WebKit

/// Porta la WKWebView dentro SwiftUI.
///
/// La web view è **una sola** per tutta la vita dell'app: cronologia, cookie e
/// sessioni restano dove sono anche cambiando scheda. Proprio per questo non
/// può essere consegnata nuda a SwiftUI: se due rappresentazioni cercassero di
/// ospitare lo stesso oggetto, UIKit si troverebbe a spostare una vista da un
/// genitore all'altro — magari mentre sta consegnando un tocco, ed è così che
/// l'app crollava dentro il codice dei gesti.
///
/// Qui SwiftUI riceve sempre un contenitore suo, e la web view ci viene
/// agganciata dentro una volta sola.
struct WebView: UIViewRepresentable {
    let webView: WKWebView

    func makeUIView(context: Context) -> ContenitoreWeb {
        let contenitore = ContenitoreWeb()
        contenitore.aggancia(webView)
        return contenitore
    }

    func updateUIView(_ uiView: ContenitoreWeb, context: Context) {
        uiView.aggancia(webView)
    }
}

/// Il contenitore che ospita la web view e le tiene la misura.
final class ContenitoreWeb: UIView {
    private weak var ospite: WKWebView?

    func aggancia(_ w: WKWebView) {
        // Se e' gia' qui non si tocca niente: e' proprio il rimbalzo da un
        // genitore all'altro che fa danni.
        guard w.superview !== self else { return }
        w.removeFromSuperview()
        w.frame = bounds
        w.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        addSubview(w)
        ospite = w
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        ospite?.frame = bounds
    }
}
