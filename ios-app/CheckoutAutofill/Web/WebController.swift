import Foundation
import WebKit
import Combine

/// Il browser dentro l'app, con il pilota automatico agganciato.
///
/// Gli script girano in un **mondo isolato** della WKWebView: vedono il DOM
/// della pagina ma non le sue variabili, e soprattutto la pagina non vede i
/// tuoi dati. È lo stesso confine che l'estensione ha su Chrome.
final class WebController: NSObject, ObservableObject {
    @Published var currentURL: URL?
    @Published var pageTitle = ""
    @Published var canGoBack = false
    @Published var canGoForward = false
    @Published var isLoading = false
    @Published var banner: Banner?
    @Published var ultimoEsito: FillResult?

    struct Banner: Identifiable, Equatable {
        let id = UUID()
        var text: String
        var tone: String        // ok | warn | err
    }

    let webView: WKWebView
    private weak var store: Store?
    private var osservazioni: [NSKeyValueObservation] = []
    private var iscrizione: AnyCancellable?
    private let mondo = WKContentWorld.defaultClient

    var host: String { currentURL?.host ?? "" }

    init(store: Store) {
        self.store = store
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()

        webView.allowsBackForwardNavigationGestures = true
        webView.navigationDelegate = self
        config.userContentController.add(self, contentWorld: mondo, name: "autofill")
        ricaricaScript()
        osserva()

        // Ogni modifica ai profili o alle impostazioni arriva subito alla
        // pagina aperta, senza doverla ricaricare.
        iscrizione = store.objectWillChange
            .debounce(for: .milliseconds(250), scheduler: RunLoop.main)
            .sink { [weak self] _ in
                DispatchQueue.main.async { self?.aggiornaStato() }
            }
    }

    // MARK: - Script iniettati

    private func sorgente(_ nome: String) -> String {
        guard let url = Bundle.main.url(forResource: nome, withExtension: "js"),
              let testo = try? String(contentsOf: url, encoding: .utf8) else {
            assertionFailure("manca \(nome).js fra le risorse del bundle")
            return ""
        }
        return testo
    }

    /// Riscrive gli script utente: lo stato prima di tutto, poi il motore.
    /// Vale per le pagine che verranno caricate da qui in avanti.
    func ricaricaScript() {
        guard let store else { return }
        let ucc = webView.configuration.userContentController
        ucc.removeAllUserScripts()

        let stato = "window.__CA_STATE = \(store.bridgeStateJSON());"
        ucc.addUserScript(WKUserScript(source: stato,
                                       injectionTime: .atDocumentStart,
                                       forMainFrameOnly: true,
                                       in: mondo))
        for nome in ["cartcore", "filler", "bridge"] {
            ucc.addUserScript(WKUserScript(source: sorgente(nome),
                                           injectionTime: .atDocumentEnd,
                                           forMainFrameOnly: true,
                                           in: mondo))
        }
    }

    /// Aggiorna lo stato nella pagina già aperta e per quelle successive.
    func aggiornaStato() {
        guard let store else { return }
        ricaricaScript()
        let js = "window.__CA_setState && window.__CA_setState(\(store.bridgeStateJSON()));"
        webView.evaluateJavaScript(js, in: nil, in: mondo) { _ in }
    }

    // MARK: - Navigazione

    func vai(a testo: String) {
        let pulito = testo.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !pulito.isEmpty else { return }
        var url: URL?
        if pulito.contains(" ") || !pulito.contains(".") {
            let q = pulito.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
            url = URL(string: "https://duckduckgo.com/?q=\(q)")
        } else if pulito.hasPrefix("http://") || pulito.hasPrefix("https://") {
            url = URL(string: pulito)
        } else {
            url = URL(string: "https://" + pulito)
        }
        guard let url else { return }
        webView.load(URLRequest(url: url))
    }

    func indietro() { webView.goBack() }
    func avanti() { webView.goForward() }
    func ricarica() { webView.reload() }

    // MARK: - Comandi al motore

    /// "Compila adesso": una passata sola, anche a pilota spento.
    func compilaAdesso(_ done: ((FillResult?) -> Void)? = nil) {
        let js = "JSON.stringify(window.__CA_fillNow ? window.__CA_fillNow() : null)"
        valuta(js, as: FillResult.self) { [weak self] esito in
            self?.ultimoEsito = esito
            if let esito {
                let n = esito.filled
                self?.mostra(n > 0
                             ? "\(n) campi compilati. Controlla e conferma tu."
                             : "Nessun campo da compilare in questa pagina.",
                             tono: n > 0 ? "ok" : "warn")
            } else {
                self?.mostra("Il motore non risponde su questa pagina.", tono: "err")
            }
            done?(esito)
        }
    }

    /// Diagnostica: cosa vede in pagina, senza toccare niente.
    func prova(_ done: @escaping (ProbeResult?) -> Void) {
        let js = "JSON.stringify(window.__CA_probe ? window.__CA_probe() : null)"
        valuta(js, as: ProbeResult.self, done)
    }

    private func valuta<T: Decodable>(_ js: String, as tipo: T.Type, _ done: @escaping (T?) -> Void) {
        webView.evaluateJavaScript(js, in: nil, in: mondo) { risultato in
            switch risultato {
            case .success(let valore):
                guard let testo = valore as? String,
                      let data = testo.data(using: .utf8),
                      let decodificato = try? JSONDecoder().decode(T.self, from: data) else {
                    done(nil)
                    return
                }
                done(decodificato)
            case .failure:
                done(nil)
            }
        }
    }

    func mostra(_ testo: String, tono: String) {
        banner = Banner(text: testo, tone: tono)
        let mio = banner?.id
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
            if self?.banner?.id == mio { self?.banner = nil }
        }
    }

    // MARK: - Osservazioni

    private func osserva() {
        osservazioni = [
            webView.observe(\.url, options: [.new]) { [weak self] w, _ in
                DispatchQueue.main.async { self?.currentURL = w.url }
            },
            webView.observe(\.title, options: [.new]) { [weak self] w, _ in
                DispatchQueue.main.async { self?.pageTitle = w.title ?? "" }
            },
            webView.observe(\.canGoBack, options: [.new]) { [weak self] w, _ in
                DispatchQueue.main.async { self?.canGoBack = w.canGoBack }
            },
            webView.observe(\.canGoForward, options: [.new]) { [weak self] w, _ in
                DispatchQueue.main.async { self?.canGoForward = w.canGoForward }
            },
            webView.observe(\.isLoading, options: [.new]) { [weak self] w, _ in
                DispatchQueue.main.async { self?.isLoading = w.isLoading }
            }
        ]
    }
}

// MARK: - Messaggi dal ponte

extension WebController: WKScriptMessageHandler {
    func userContentController(_ controller: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard let corpo = message.body as? [String: Any],
              let tipo = corpo["type"] as? String else { return }

        switch tipo {
        case "toast":
            mostra(corpo["text"] as? String ?? "", tono: corpo["tone"] as? String ?? "ok")
        case "filled":
            let n = corpo["count"] as? Int ?? 0
            ultimoEsito = FillResult(filled: n, skipped: 0, scanned: 0, fields: [])
        case "added", "log":
            break   // già raccontati dal riquadro
        default:
            break
        }
    }
}

// MARK: - Navigazione

extension WebController: WKNavigationDelegate {
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        currentURL = webView.url
        pageTitle = webView.title ?? ""
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        mostra("Pagina non caricata: \(error.localizedDescription)", tono: "err")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        guard e.code != NSURLErrorCancelled else { return }
        mostra("Pagina non caricata: \(error.localizedDescription)", tono: "err")
    }
}
