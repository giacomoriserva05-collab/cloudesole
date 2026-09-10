import Foundation
import UserNotifications

/// Il monitor, dentro l'app. Fa quello che fa quello desktop — interroga gli
/// endpoint pubblici a intervalli e confronta con l'ultimo giro — con un
/// limite che viene da iOS e non dal codice:
///
/// **gira mentre l'app è aperta.** Uscendo, il sistema la sospende in pochi
/// secondi. Non è aggirabile: nessuna app può interrogare un sito ogni venti
/// secondi in sottofondo. Per la sorveglianza continua resta il monitor sul
/// computer, che di ore ne fa ventiquattro.
final class MonitorEngine: NSObject, ObservableObject {
    @Published private(set) var inCorso = false
    @Published private(set) var righe: [MonitorRiga] = []
    @Published private(set) var eventi: [MonitorEvento] = []
    @Published private(set) var ultimoControllo: [String: Date] = [:]
    @Published var permessoNotifiche: UNAuthorizationStatus = .notDetermined

    /// Chiamata quando si tocca una notifica: porta l'app sul prodotto.
    var apriProdotto: ((String) -> Void)?

    private var compiti: [String: Task<Void, Never>] = [:]
    /// chiave articolo -> era disponibile al giro precedente
    private var visti: [String: Bool] = [:]
    private let chiaveStato = "monitorVisti"

    override init() {
        super.init()
        if let d = UserDefaults.standard.dictionary(forKey: chiaveStato) as? [String: Bool] {
            visti = d
        }
        UNUserNotificationCenter.current().delegate = self
        aggiornaPermesso()
    }

    // MARK: - Permessi

    func aggiornaPermesso() {
        UNUserNotificationCenter.current().getNotificationSettings { s in
            DispatchQueue.main.async { self.permessoNotifiche = s.authorizationStatus }
        }
    }

    func chiediPermesso() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in
            self.aggiornaPermesso()
        }
    }

    // MARK: - Avvio e arresto

    func avvia(_ bersagli: [MonitorTarget], userAgent: String) {
        ferma()
        let attivi = bersagli.filter { $0.attivo && !$0.url.isEmpty }
        guard !attivi.isEmpty else {
            scrivi("Generale", "Nessun target attivo.", .avviso)
            return
        }
        inCorso = true
        scrivi("Generale", "Monitor avviato su \(attivi.count) target.", .successo)

        // Un compito per target, come sul desktop: ognuno col suo intervallo.
        for t in attivi {
            compiti[t.id] = Task { [weak self] in
                await self?.ciclo(t, userAgent: userAgent)
            }
        }
    }

    func ferma() {
        for (_, c) in compiti { c.cancel() }
        compiti.removeAll()
        if inCorso { scrivi("Generale", "Monitor fermo.", .info) }
        inCorso = false
    }

    /// Dimentica lo stato: il prossimo giro riparte da zero e tutto risulta
    /// "nuovo". Serve quando si cambia target e i vecchi articoli confondono.
    func azzeraStato() {
        visti.removeAll()
        UserDefaults.standard.removeObject(forKey: chiaveStato)
        scrivi("Generale", "Stato azzerato.", .info)
    }

    func svuotaRegistro() {
        righe.removeAll()
    }

    // MARK: - Il giro

    private func ciclo(_ t: MonitorTarget, userAgent: String) async {
        while !Task.isCancelled {
            await unGiro(t, userAgent: userAgent)
            // Un pizzico di casualità come sul desktop: interrogare a cadenza
            // esatta è il modo più rapido per farsi notare.
            let jitter = Double.random(in: 0...(max(1, t.intervallo) * 0.15))
            try? await Task.sleep(nanoseconds: UInt64((max(3, t.intervallo) + jitter) * 1_000_000_000))
        }
    }

    private func unGiro(_ t: MonitorTarget, userAgent: String) async {
        do {
            let articoli = try await interroga(t, userAgent: userAgent)
            await MainActor.run {
                ultimoControllo[t.id] = Date()
                confronta(t, articoli)
            }
        } catch is CancellationError {
            return
        } catch {
            await MainActor.run {
                scrivi(t.nome, "Errore: \(error.localizedDescription)", .errore)
            }
        }
    }

    /// Confronta col giro precedente. Due categorie, le stesse del desktop:
    /// *restock* quando un articolo torna disponibile, *nuovo* quando compare
    /// per la prima volta già disponibile.
    private func confronta(_ t: MonitorTarget, _ articoli: [MonitorItem]) {
        var disponibili = 0
        var novita: [MonitorEvento] = []

        for a in articoli where !a.chiave.isEmpty {
            if a.disponibile { disponibili += 1 }
            let chiave = t.id + ":" + a.chiave
            let prima = visti[chiave]
            visti[chiave] = a.disponibile

            guard a.disponibile else { continue }
            if prima == nil {
                novita.append(MonitorEvento(bersaglio: t.nome, titolo: a.titolo, url: a.url, genere: .nuovo))
            } else if prima == false {
                novita.append(MonitorEvento(bersaglio: t.nome, titolo: a.titolo, url: a.url, genere: .restock))
            }
        }

        UserDefaults.standard.set(visti, forKey: chiaveStato)
        scrivi(t.nome, "\(articoli.count) articoli, \(disponibili) disponibili.", .info)

        for e in novita {
            eventi.insert(e, at: 0)
            scrivi(t.nome, "[\(e.etichetta)] \(e.titolo)", .successo)
            avvisa(e)
        }
        if eventi.count > 200 { eventi = Array(eventi.prefix(200)) }
    }

    // MARK: - Interrogazione

    private func interroga(_ t: MonitorTarget, userAgent: String) async throws -> [MonitorItem] {
        let indirizzo = try endpoint(t)
        guard let url = URL(string: indirizzo) else {
            throw NSError(domain: "monitor", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Indirizzo non valido."])
        }
        var richiesta = URLRequest(url: url)
        richiesta.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        richiesta.setValue("application/json", forHTTPHeaderField: "Accept")
        richiesta.timeoutInterval = 15
        richiesta.cachePolicy = .reloadIgnoringLocalCacheData

        let (dati, risposta) = try await URLSession.shared.data(for: richiesta)
        if let http = risposta as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw NSError(domain: "monitor", code: http.statusCode,
                          userInfo: [NSLocalizedDescriptionKey: "Il sito ha risposto \(http.statusCode)."])
        }

        switch t.tipo {
        case .prodotto: return try leggiProdotto(t, dati)
        case .collezione: return try leggiCollezione(t, dati)
        }
    }

    /// Dall'indirizzo della pagina si ricava quello dell'endpoint JSON.
    private func endpoint(_ t: MonitorTarget) throws -> String {
        var s = t.url.trimmingCharacters(in: .whitespaces)
        if let taglio = s.firstIndex(of: "?") { s = String(s[s.startIndex..<taglio]) }
        while s.hasSuffix("/") { s.removeLast() }
        if s.hasSuffix(".js") || s.hasSuffix(".json") { return s }
        switch t.tipo {
        case .prodotto: return s + ".js"
        case .collezione: return s + "/products.json?limit=250"
        }
    }

    private func origine(_ s: String) -> String {
        guard let u = URL(string: s), let host = u.host else { return "" }
        return "\(u.scheme ?? "https")://\(host)"
    }

    private func leggiProdotto(_ t: MonitorTarget, _ dati: Data) throws -> [MonitorItem] {
        guard let o = try JSONSerialization.jsonObject(with: dati) as? [String: Any],
              let varianti = o["variants"] as? [[String: Any]] else {
            throw NSError(domain: "monitor", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "Risposta senza l'elenco delle varianti."])
        }
        let titolo = (o["title"] as? String) ?? t.nome
        let handle = (o["handle"] as? String) ?? ""
        let pagina = handle.isEmpty ? t.url : origine(t.url) + "/products/" + handle
        return varianti.compactMap { variante(t, $0, prodotto: titolo, pagina: pagina) }
    }

    private func leggiCollezione(_ t: MonitorTarget, _ dati: Data) throws -> [MonitorItem] {
        guard let o = try JSONSerialization.jsonObject(with: dati) as? [String: Any],
              let prodotti = o["products"] as? [[String: Any]] else {
            throw NSError(domain: "monitor", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "Risposta senza l'elenco dei prodotti."])
        }
        var out: [MonitorItem] = []
        for p in prodotti {
            let titolo = (p["title"] as? String) ?? "?"
            let handle = (p["handle"] as? String) ?? ""
            let pagina = origine(t.url) + "/products/" + handle
            for v in (p["variants"] as? [[String: Any]]) ?? [] {
                if let i = variante(t, v, prodotto: titolo, pagina: pagina) { out.append(i) }
            }
        }
        return out
    }

    private func variante(_ t: MonitorTarget, _ v: [String: Any],
                          prodotto: String, pagina: String) -> MonitorItem? {
        let nomeVariante = (v["public_title"] as? String)
            ?? (v["title"] as? String)
            ?? "default"
        guard passaFiltro(nomeVariante, t) else { return nil }

        let id = v["id"].map { "\($0)" } ?? ""
        let disponibile = (v["available"] as? Bool) ?? false
        let url = id.isEmpty ? pagina : pagina + "?variant=" + id
        return MonitorItem(chiave: id, titolo: "\(prodotto) — \(nomeVariante)",
                           disponibile: disponibile, url: url, prezzo: v["price"] as? String)
    }

    /// Filtro sulle taglie, con gli stessi alias del pilota: `M` accetta
    /// *Medium*, `42,5` accetta `42.5`.
    private func passaFiltro(_ nome: String, _ t: MonitorTarget) -> Bool {
        let volute = t.elencoTaglie
        guard !volute.isEmpty else { return true }
        let n = Taglie.canonica(nome)
        return volute.contains { Taglie.canonica($0) == n }
    }

    // MARK: - Notifiche

    private func avvisa(_ e: MonitorEvento) {
        let c = UNMutableNotificationContent()
        c.title = e.genere == .restock ? "Restock: \(e.bersaglio)" : "Nuovo: \(e.bersaglio)"
        c.body = e.titolo
        c.sound = .default
        // L'indirizzo viaggia con la notifica: toccandola l'app sa dove andare.
        c.userInfo = ["url": e.url]

        let richiesta = UNNotificationRequest(identifier: e.id, content: c, trigger: nil)
        UNUserNotificationCenter.current().add(richiesta)
    }

    // MARK: - Registro

    private func scrivi(_ bersaglio: String, _ testo: String, _ livello: MonitorRiga.Livello) {
        righe.insert(MonitorRiga(bersaglio: bersaglio, testo: testo, livello: livello), at: 0)
        if righe.count > 300 { righe = Array(righe.prefix(300)) }
    }
}

// MARK: - Notifiche toccate

extension MonitorEngine: UNUserNotificationCenterDelegate {
    /// Toccando la notifica si apre il prodotto restockato, senza passare
    /// dall'elenco né dalla barra d'indirizzo.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let url = response.notification.request.content.userInfo["url"] as? String {
            DispatchQueue.main.async { self.apriProdotto?(url) }
        }
        completionHandler()
    }

    /// Serve anche ad app aperta: senza, la notifica non comparirebbe.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .list])
    }
}

/// Le taglie ridotte a una forma sola, come fa `cartcore.js`: `M` e *Medium*
/// devono combaciare, e `42,5` con `42.5`.
enum Taglie {
    private static let alias: [String: [String]] = [
        "xxs": ["xxs", "2xs", "xxsmall"],
        "xs": ["xs", "xsmall", "extrasmall"],
        "s": ["s", "small", "piccola"],
        "m": ["m", "medium", "med", "media"],
        "l": ["l", "large", "grande"],
        "xl": ["xl", "xlarge", "extralarge"],
        "xxl": ["xxl", "2xl", "xxlarge"],
        "xxxl": ["xxxl", "3xl", "xxxlarge"],
        "os": ["os", "onesize", "tagliaunica", "unica", "tu"]
    ]

    static func canonica(_ grezzo: String) -> String {
        var t = grezzo.lowercased()
            .replacingOccurrences(of: ",", with: ".")
            .folding(options: .diacriticInsensitive, locale: .current)
        for parola in ["eu", "it", "uk", "us", "eur", "taglia", "size", "misura"] {
            t = t.replacingOccurrences(of: parola, with: " ")
        }
        let compatto = t.components(separatedBy: CharacterSet.alphanumerics.inverted.subtracting(CharacterSet(charactersIn: ".")))
            .joined()
            .trimmingCharacters(in: CharacterSet(charactersIn: " ."))
        if compatto.isEmpty { return grezzo.lowercased() }
        if Double(compatto) != nil {
            return compatto.hasSuffix(".0") ? String(compatto.dropLast(2)) : compatto
        }
        for (chiave, forme) in alias where forme.contains(compatto) { return chiave }
        return compatto
    }
}
