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

    /// Vero quando in scheda Negozio si vede l'elenco dei negozi invece della
    /// pagina. È lo stato in cui l'app si apre.
    @Published var mostraElenco = true

    /// Vero quando in pagina c'è un modulo di accesso: è ciò che fa comparire
    /// la chiave nella barra.
    @Published var moduloAccesso = false

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

        // Niente scorrimento laterale per tornare indietro: installa
        // riconoscitori di gesti pensati per un controller di navigazione,
        // che qui non c'è. Avanti e indietro stanno nella barra in basso.
        webView.allowsBackForwardNavigationGestures = false
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
        for nome in ["cartcore", "shopify", "filler", "login", "bridge"] {
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
        // Il passaggio si fa al giro successivo del ciclo principale: cambiare
        // stato dentro la gestione di un tocco significa riorganizzare le
        // viste mentre UIKit sta ancora consegnando quel tocco.
        DispatchQueue.main.async { self.mostraElenco = false }
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

    // MARK: - Accesso ai siti

    /// Le stringhe non si incollano nel JavaScript a mano: una password con
    /// un apice o una barra rovescia romperebbe la chiamata, o peggio.
    private func letterale(_ s: String) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: [s]),
              let t = String(data: d, encoding: .utf8) else { return "\"\"" }
        return String(t.dropFirst().dropLast())
    }

    /// Guarda se la pagina ha un modulo di accesso da compilare.
    func controllaModuloAccesso() {
        let js = "JSON.stringify(window.LoginEngine ? window.LoginEngine.guarda() : null)"
        webView.evaluateJavaScript(js, in: nil, in: mondo) { [weak self] esito in
            guard case .success(let valore) = esito,
                  let testo = valore as? String,
                  let data = testo.data(using: .utf8),
                  let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                self?.moduloAccesso = false
                return
            }
            self?.moduloAccesso = (o["presente"] as? Bool) ?? false
        }
    }

    /// Compila l'accesso. La password si rilegge adesso dal portachiavi, e il
    /// telefono chiede Face ID: se rifiuti, non succede niente. Il modulo non
    /// viene inviato — "Accedi" lo premi tu.
    func accedi(con voce: SiteAccount, store: Store) {
        guard let segreto = store.password(per: voce) else {
            mostra("Accesso annullato.", tono: "warn")
            return
        }
        let js = "JSON.stringify(window.LoginEngine ? window.LoginEngine.compila("
            + letterale(voce.utente) + ", " + letterale(segreto) + ") : null)"
        webView.evaluateJavaScript(js, in: nil, in: mondo) { [weak self] esito in
            guard case .success(let valore) = esito,
                  let testo = valore as? String,
                  let data = testo.data(using: .utf8),
                  let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  (o["ok"] as? Bool) == true else {
                self?.mostra("Qui non ho trovato un modulo di accesso da compilare.", tono: "warn")
                return
            }
            self?.mostra("Credenziali inserite. Premi tu \"Accedi\".", tono: "ok")
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
        controllaModuloAccesso()
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
