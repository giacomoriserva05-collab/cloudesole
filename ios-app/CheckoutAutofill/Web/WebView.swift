import SwiftUI
import WebKit

/// Porta la WKWebView dentro SwiftUI.
///
/// La web view è **una sola** per tutta la vita dell'app: cronologia, cookie e
/// sessioni restano dove sono anche cambiando scheda. E da quando si è capito
/// che il crollo nasceva proprio lì, non lascia mai l'albero delle viste:
/// `BrowserView` la tiene montata sempre e le mette sopra l'elenco dei negozi
/// invece di scambiarle. Uscire e rientrare nella gerarchia mentre UIKit sta
/// consegnando un tocco è ciò che mandava in pezzi il codice dei gesti.
///
/// Il contenitore serve alla stessa causa: SwiftUI riceve sempre una vista
/// sua, e la web view ci viene agganciata dentro una volta sola.
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
        ContenitoreWeb.spegniRitardoTocchi(da: w)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        ospite?.frame = bounds
    }

    /// Toglie il ritardo dei tocchi a tutte le viste a scorrimento della
    /// pagina, non solo a quella principale.
    ///
    /// `-[UIGestureRecognizer _delayTouchesForEvent:inPhase:]` è l'ultima
    /// chiamata prima dell'abort in ogni resoconto di crash raccolto finora,
    /// e la eseguono soltanto le viste a scorrimento che trattengono i tocchi
    /// per decidere a chi consegnarli. WebKit ne crea una per la pagina e
    /// altre per i riquadri interni.
    ///
    /// Si perde poco: i pulsanti della pagina rispondono subito invece di
    /// aspettare di capire se stavi cominciando a scorrere.
    static func spegniRitardoTocchi(da vista: UIView) {
        if let scorrimento = vista as? UIScrollView {
            scorrimento.delaysContentTouches = false
            scorrimento.canCancelContentTouches = true
        }
        for figlia in vista.subviews {
            spegniRitardoTocchi(da: figlia)
        }
    }
}
