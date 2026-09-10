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
    /// I nomi già letti, per non richiedere due volte la stessa pagina.
    private let cacheNomi = CacheNomi()

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
            let novita = await MainActor.run { () -> [MonitorEvento] in
                ultimoControllo[t.id] = Date()
                return confronta(t, articoli)
            }
            guard !novita.isEmpty else { return }
            // Il nome vero si legge adesso, prima di suonare: una notifica
            // che dice "04cqa7voxxsqvang" non serve a nessuno.
            let conNome = await conNomiLeggibili(novita, userAgent: userAgent)
            await MainActor.run { annuncia(t, conNome) }
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
    @discardableResult
    private func confronta(_ t: MonitorTarget, _ articoli: [MonitorItem]) -> [MonitorEvento] {
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
        return novita
    }

    /// Mette gli avvisi in elenco e li fa suonare. È un passo separato dal
    /// confronto perché fra i due c'è un'attesa: quella che serve a leggere
    /// il nome dei prodotti.
    @MainActor
    private func annuncia(_ t: MonitorTarget, _ novita: [MonitorEvento]) {
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
        let accetta = (t.tipo == .pagina || t.tipo == .elenco)
            ? "text/html,application/xhtml+xml" : "application/json"
        richiesta.setValue(accetta, forHTTPHeaderField: "Accept")
        richiesta.timeoutInterval = 15
        richiesta.cachePolicy = .reloadIgnoringLocalCacheData

        let (dati, risposta) = try await URLSession.shared.data(for: richiesta)
        if let http = risposta as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw NSError(domain: "monitor", code: http.statusCode,
                          userInfo: [NSLocalizedDescriptionKey: "Il sito ha risposto \(http.statusCode)."])
        }

        // Il sito può averci spostati altrove — us.supreme.com risponde da
        // eu.supreme.com — e i link relativi vanno letti a partire da dove
        // siamo finiti davvero, non da dove volevamo andare.
        let effettivo = (risposta.url ?? url).absoluteString

        switch t.tipo {
        case .prodotto: return try leggiProdotto(t, dati, effettivo)
        case .collezione: return try leggiCollezione(t, dati, effettivo)
        case .pagina: return try leggiPagina(t, dati)
        case .json: return try leggiJson(t, dati)
        case .elenco: return try leggiElenco(t, dati, effettivo)
        }
    }

    /// Dall'indirizzo della pagina si ricava quello dell'endpoint JSON.
    private func endpoint(_ t: MonitorTarget) throws -> String {
        var s = t.url.trimmingCharacters(in: .whitespaces)
        if let taglio = s.firstIndex(of: "?") { s = String(s[s.startIndex..<taglio]) }
        while s.hasSuffix("/") { s.removeLast() }
        // Per pagina e json l'indirizzo è già quello giusto: lo si interroga
        // com'è, compresa la stringa di ricerca, che spesso conta.
        if t.tipo == .pagina || t.tipo == .json || t.tipo == .elenco {
            return t.url.trimmingCharacters(in: .whitespaces)
        }
        if s.hasSuffix(".js") || s.hasSuffix(".json") { return s }
        switch t.tipo {
        case .prodotto: return s + ".js"
        case .collezione: return s + "/products.json?limit=250"
        default: return s
        }
    }

    private func origine(_ s: String) -> String {
        guard let u = URL(string: s), let host = u.host else { return "" }
        return "\(u.scheme ?? "https")://\(host)"
    }

    private func leggiProdotto(_ t: MonitorTarget, _ dati: Data, _ effettivo: String) throws -> [MonitorItem] {
        guard let o = try JSONSerialization.jsonObject(with: dati) as? [String: Any],
              let varianti = o["variants"] as? [[String: Any]] else {
            throw NSError(domain: "monitor", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "Risposta senza l'elenco delle varianti."])
        }
        let titolo = (o["title"] as? String) ?? t.nome
        let handle = (o["handle"] as? String) ?? ""
        let pagina = handle.isEmpty ? t.url : origine(effettivo) + "/products/" + handle
        return varianti.compactMap { variante(t, $0, prodotto: titolo, pagina: pagina) }
    }

    private func leggiCollezione(_ t: MonitorTarget, _ dati: Data, _ effettivo: String) throws -> [MonitorItem] {
        guard let o = try JSONSerialization.jsonObject(with: dati) as? [String: Any],
              let prodotti = o["products"] as? [[String: Any]] else {
            throw NSError(domain: "monitor", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "Risposta senza l'elenco dei prodotti."])
        }
        var out: [MonitorItem] = []
        for p in prodotti {
            let titolo = (p["title"] as? String) ?? "?"
            let handle = (p["handle"] as? String) ?? ""
            let pagina = origine(effettivo) + "/products/" + handle
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

    // MARK: - Pagina qualsiasi, per marcatori

    /// Decide leggendo cosa c'è scritto nella pagina. **L'esaurito ha la
    /// precedenza**: se la pagina dichiara che il prodotto non c'è, quello
    /// vince su ogni indizio contrario. È la stessa regola del desktop, e
    /// nasce dal fatto che il pulsante d'acquisto resta quasi sempre nel
    /// codice anche quando non si può comprare.
    private func leggiPagina(_ t: MonitorTarget, _ dati: Data) throws -> [MonitorItem] {
        let dentro = t.elencoMarcatoriDisponibile
        let fuori = t.elencoMarcatoriEsaurito
        guard !dentro.isEmpty || !fuori.isEmpty else {
            throw NSError(domain: "monitor", code: 4, userInfo: [NSLocalizedDescriptionKey:
                "Per una pagina serve almeno un marcatore, di disponibile o di esaurito."])
        }
        let corpo = String(data: dati, encoding: .utf8)
            ?? String(decoding: dati, as: UTF8.self)

        var disponibile: Bool
        if !fuori.isEmpty, trovato(fuori, in: corpo, regex: t.regex) {
            disponibile = false
        } else if !dentro.isEmpty {
            disponibile = trovato(dentro, in: corpo, regex: t.regex)
        } else {
            // Solo marcatori di esaurito, e nessuno trovato: si assume ci sia.
            disponibile = true
        }

        return [MonitorItem(chiave: "pagina", titolo: t.nome,
                            disponibile: disponibile, url: t.url, prezzo: nil)]
    }

    private func trovato(_ marcatori: [String], in corpo: String, regex: Bool) -> Bool {
        for m in marcatori {
            if regex {
                if let r = try? NSRegularExpression(pattern: m, options: [.caseInsensitive, .dotMatchesLineSeparators]) {
                    let campo = NSRange(corpo.startIndex..., in: corpo)
                    if r.firstMatch(in: corpo, range: campo) != nil { return true }
                }
            } else if corpo.range(of: m, options: .caseInsensitive) != nil {
                return true
            }
        }
        return false
    }

    // MARK: - Elenco di prodotti

    /// Pesca dalla pagina i link dei prodotti. Qui **ogni voce trovata conta
    /// come disponibile**: il segnale utile non è il passaggio da esaurito a
    /// disponibile, ma la *comparsa* di una voce che prima non c'era.
    ///
    /// Serve dove la disponibilità non è leggibile ma l'elenco sì — Supreme è
    /// il caso da manuale: chiude gli endpoint JSON con un 403 e non scrive
    /// nulla sullo stock nel codice della pagina, ma i link dei prodotti nella
    /// collezione ci sono tutti.
    private func leggiElenco(_ t: MonitorTarget, _ dati: Data, _ effettivo: String) throws -> [MonitorItem] {
        let schema = t.schema.trimmingCharacters(in: .whitespaces)
        guard !schema.isEmpty else {
            throw NSError(domain: "monitor", code: 7, userInfo: [NSLocalizedDescriptionKey:
                "Per un elenco serve lo schema che riconosce i link."])
        }
        guard let regola = try? NSRegularExpression(pattern: schema, options: [.caseInsensitive]) else {
            throw NSError(domain: "monitor", code: 8, userInfo: [NSLocalizedDescriptionKey:
                "Lo schema non è un'espressione regolare valida."])
        }
        let corpo = String(data: dati, encoding: .utf8) ?? String(decoding: dati, as: UTF8.self)
        let campo = NSRange(corpo.startIndex..., in: corpo)

        let soloSe = t.elencoSoloSe
        let tranneSe = t.elencoTranneSe
        var viste = Set<String>()
        var out: [MonitorItem] = []

        for m in regola.matches(in: corpo, range: campo) {
            // Col gruppo fra parentesi si tiene quello; senza, tutto il pezzo.
            let quale = m.numberOfRanges > 1 ? 1 : 0
            guard let r = Range(m.range(at: quale), in: corpo) else { continue }
            let valore = String(corpo[r]).trimmingCharacters(in: .whitespaces)
            guard !valore.isEmpty, !viste.contains(valore) else { continue }

            let minuscolo = valore.lowercased()
            if !soloSe.isEmpty && !soloSe.contains(where: { minuscolo.contains($0) }) { continue }
            if tranneSe.contains(where: { minuscolo.contains($0) }) { continue }

            let intero = Range(m.range(at: 0), in: corpo).map { String(corpo[$0]) } ?? valore
            guard let indirizzo = componiIndirizzo(valore: valore, intero: intero,
                                                   base: t.base, pagina: effettivo) else { continue }

            viste.insert(valore)
            out.append(MonitorItem(chiave: valore, titolo: valore,
                                   disponibile: true, url: indirizzo, prezzo: nil))
            if out.count >= 3000 { break }   // pagine enormi: si mette un tetto
        }
        return out
    }

    /// Da un pezzo di link a un indirizzo che si può davvero aprire.
    ///
    /// Qui si nascondeva un errore che rendeva inutile ogni avviso: lo schema
    /// di serie cattura fra parentesi il solo codice del prodotto, e il codice
    /// veniva incollato all'origine del sito senza il percorso in mezzo. Ne
    /// usciva `https://eu.supreme.com04cqa7voxxsqvang`, che il telefono non sa
    /// nemmeno dove cercare: toccando la notifica compariva la barra rossa.
    ///
    /// Adesso, se il pezzo fra parentesi non è un percorso, si riprende il
    /// pezzo intero — che il percorso ce l'ha — e lo si risolve rispetto alla
    /// pagina da cui è stato letto, come farebbe un browser con un link.
    private func componiIndirizzo(valore: String, intero: String,
                                  base: String, pagina: String) -> String? {
        let grezzo: String
        if !base.isEmpty {
            // Con un inizio scritto a mano comanda quello, con una barra sola.
            if valore.hasPrefix("http") {
                grezzo = valore
            } else {
                let b = base.hasSuffix("/") ? String(base.dropLast()) : base
                grezzo = b + (valore.hasPrefix("/") ? valore : "/" + valore)
            }
        } else if valore.hasPrefix("http") || valore.hasPrefix("/") {
            grezzo = valore
        } else {
            grezzo = intero
        }

        guard let u = URL(string: grezzo, relativeTo: URL(string: pagina)),
              let schema = u.scheme?.lowercased(), schema == "http" || schema == "https",
              let host = u.host, host.contains(".") else { return nil }
        return u.absoluteURL.absoluteString
    }

    // MARK: - Dal codice al nome

    /// Sostituisce i codici con i nomi veri, leggendoli dalla pagina.
    ///
    /// Certi negozi non hanno un nome leggibile nell'indirizzo: da Supreme un
    /// prodotto si chiama `04cqa7voxxsqvang`, e un avviso che dice così non
    /// dice niente. Il nome sta nella pagina, e la pagina la si aprirà comunque
    /// un istante dopo: tanto vale leggerla adesso.
    ///
    /// Costa una richiesta per articolo *nuovo*, non per giro. E solo quando il
    /// titolo è un codice: dove il negozio il nome ce l'ha, non si chiede
    /// niente a nessuno.
    private func conNomiLeggibili(_ novita: [MonitorEvento], userAgent: String) async -> [MonitorEvento] {
        var out = novita
        // Un tetto: a un lancio possono comparire cinquanta articoli insieme,
        // e cinquanta richieste in fila sarebbero peggio del problema.
        let quanti = min(out.count, 8)
        await withTaskGroup(of: (Int, String?).self) { gruppo in
            for i in 0..<quanti where sembraUnCodice(out[i].titolo) {
                let indirizzo = out[i].url
                gruppo.addTask { [weak self] in
                    // Il doppio opzionale di `self?.` va appiattito subito:
                    // al gruppo serve un String?, non un String??.
                    let nome = await self?.nomeDallaPagina(indirizzo, userAgent: userAgent)
                    return (i, nome ?? nil)
                }
            }
            for await (i, nome) in gruppo {
                if let nome, !nome.isEmpty { out[i].titolo = nome }
            }
        }
        return out
    }

    /// Un titolo senza spazi non è un titolo: è l'identificativo interno del
    /// negozio.
    private func sembraUnCodice(_ titolo: String) -> Bool {
        !titolo.contains(" ")
    }

    private func nomeDallaPagina(_ indirizzo: String, userAgent: String) async -> String? {
        if let gia = await cacheNomi.nome(indirizzo) { return gia }
        guard let url = URL(string: indirizzo) else { return nil }
        var r = URLRequest(url: url)
        r.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        r.setValue("text/html,application/xhtml+xml", forHTTPHeaderField: "Accept")
        r.timeoutInterval = 8
        guard let (dati, _) = try? await URLSession.shared.data(for: r) else { return nil }

        // Il titolo sta in testa: non serve leggere mezzo megabyte di pagina.
        let corpo = String(decoding: dati.prefix(300_000), as: UTF8.self)
        let grezzo = primoGruppo(SchemiTitolo.og, corpo)
            ?? primoGruppo(SchemiTitolo.ogRovescio, corpo)
            ?? primoGruppo(SchemiTitolo.titolo, corpo)
        guard let grezzo else { return nil }

        let pulito = ripulisci(grezzo, host: url.host ?? "")
        guard !pulito.isEmpty else { return nil }
        await cacheNomi.metti(pulito, indirizzo)
        return pulito
    }

    private func primoGruppo(_ schema: String, _ testo: String) -> String? {
        guard let r = try? NSRegularExpression(pattern: schema,
                                               options: [.caseInsensitive, .dotMatchesLineSeparators]),
              let m = r.firstMatch(in: testo, range: NSRange(testo.startIndex..., in: testo)),
              m.numberOfRanges > 1,
              let g = Range(m.range(at: 1), in: testo) else { return nil }
        return String(testo[g])
    }

    /// Il titolo di una pagina è scritto per un browser, non per un avviso:
    /// va a capo, ha le entità HTML e finisce col nome del negozio. Quello lo
    /// sai già — l'avviso dice da quale target arriva.
    private func ripulisci(_ grezzo: String, host: String) -> String {
        var s = grezzo.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        for (entita, carattere) in Entita.tabella {
            s = s.replacingOccurrences(of: entita, with: carattere)
        }

        let marchio = (host.hasPrefix("www.") ? String(host.dropFirst(4)) : host)
            .split(separator: ".").first.map(String.init)?.lowercased() ?? ""
        // Più code di seguito: "Money S Logo New Era® - Shop - Supreme".
        for _ in 0..<3 {
            var tagliato = false
            for separatore in [" - ", " | ", " – ", " — ", " · "] {
                guard let r = s.range(of: separatore, options: .backwards) else { continue }
                let coda = s[r.upperBound...].trimmingCharacters(in: .whitespaces).lowercased()
                if coda == "shop" || coda == "home" || (!marchio.isEmpty && coda == marchio) {
                    s = String(s[..<r.lowerBound])
                    tagliato = true
                }
            }
            if !tagliato { break }
        }
        return s.trimmingCharacters(in: .whitespaces)
    }

    // MARK: - JSON qualsiasi, per percorsi

    private func leggiJson(_ t: MonitorTarget, _ dati: Data) throws -> [MonitorItem] {
        guard !t.percorsoDisponibile.isEmpty else {
            throw NSError(domain: "monitor", code: 5, userInfo: [NSLocalizedDescriptionKey:
                "Per una risposta JSON serve il percorso del campo di disponibilità."])
        }
        let radice = try JSONSerialization.jsonObject(with: dati)
        let grezzi = scava(radice, t.percorsoElenco)

        var elenco: [Any] = []
        if let a = grezzi as? [Any] { elenco = a }
        else if let d = grezzi as? [String: Any] { elenco = [d] }
        else {
            throw NSError(domain: "monitor", code: 6, userInfo: [NSLocalizedDescriptionKey:
                "Il percorso \"\(t.percorsoElenco)\" non porta a un elenco."])
        }

        var out: [MonitorItem] = []
        for (i, grezzo) in elenco.enumerated() {
            let titolo = testo(scava(grezzo, t.percorsoTitolo)) ?? "articolo-\(i)"
            guard passaFiltro(titolo, t) else { continue }
            let chiave = testo(scava(grezzo, t.percorsoChiave)) ?? "\(i)"
            let indirizzo = t.percorsoUrl.isEmpty ? t.url : (testo(scava(grezzo, t.percorsoUrl)) ?? t.url)
            out.append(MonitorItem(chiave: chiave, titolo: titolo,
                                   disponibile: vero(scava(grezzo, t.percorsoDisponibile)),
                                   url: indirizzo, prezzo: nil))
        }
        return out
    }

    /// Naviga il JSON con un percorso puntato, `a.b.0.c`, come fa il desktop.
    private func scava(_ dato: Any, _ percorso: String) -> Any? {
        guard !percorso.isEmpty else { return dato }
        var corrente: Any? = dato
        for pezzo in percorso.split(separator: ".") {
            if let array = corrente as? [Any] {
                guard let i = Int(pezzo), i >= 0, i < array.count else { return nil }
                corrente = array[i]
            } else if let dizionario = corrente as? [String: Any] {
                corrente = dizionario[String(pezzo)]
            } else {
                return nil
            }
            if corrente == nil { return nil }
        }
        return corrente
    }

    private func testo(_ v: Any?) -> String? {
        switch v {
        case let s as String: return s
        case let n as NSNumber: return n.stringValue
        case .none: return nil
        default: return String(describing: v!)
        }
    }

    private func vero(_ v: Any?) -> Bool {
        switch v {
        case let b as Bool: return b
        case let n as NSNumber: return n.boolValue
        case let s as String: return ["true", "1", "si", "yes", "instock", "available"]
            .contains(s.lowercased())
        default: return false
        }
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

/// Gli schemi che pescano il titolo dal codice della pagina.
private enum SchemiTitolo {
    static let og = "<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']"
    static let ogRovescio = "<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:title[\"']"
    static let titolo = "<title[^>]*>(.*?)</title>"
}

/// Le entità HTML che capitano davvero in un nome di prodotto.
private enum Entita {
    static let tabella: [(String, String)] = [
        ("&amp;", "&"), ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
        ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "),
        ("&reg;", "®"), ("&#174;", "®"), ("&trade;", "™"),
        ("&#8217;", "'"), ("&rsquo;", "'")
    ]
}

/// Il piccolo archivio dei nomi risolti. È un attore perché ci si scrive da
/// più richieste contemporanee.
private actor CacheNomi {
    private var mappa: [String: String] = [:]

    func nome(_ url: String) -> String? { mappa[url] }

    func metti(_ nome: String, _ url: String) {
        if mappa.count > 500 { mappa.removeAll() }
        mappa[url] = nome
    }
}
