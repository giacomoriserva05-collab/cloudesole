import Foundation
import Combine

/// Lo stato dell'app: profili, impostazioni, regole per sito, interruttore.
/// Salva da sé a ogni modifica, come faceva il popup dell'estensione.
final class Store: ObservableObject {
    @Published var profiles: [Profile] { didSet { salva() } }
    @Published var activeID: String { didSet { salva() } }
    @Published var settings: Settings { didSet { cambiaCustodiaCarte(oldValue); salva() } }
    @Published var sites: [String: SiteConfig] { didSet { salva() } }
    @Published var armed = false { didSet { salva() } }

    /// I negozi della schermata iniziale. Al primo avvio ci sono quelli
    /// predefiniti; da lì in poi comanda l'utente.
    @Published var shops: [Shop] = [] { didSet { salva() } }

    /// Gli account dei siti. Qui c'è solo il nome utente: la password sta nel
    /// portachiavi, protetta dal riconoscimento del volto.
    @Published var accounts: [SiteAccount] = [] { didSet { salva() } }

    /// I target del monitor.
    @Published var targets: [MonitorTarget] = [] { didSet { salva() } }

    /// Quale scheda è in primo piano. Non si salva: serve a portare l'app sul
    /// prodotto quando si tocca una notifica di restock.
    @Published var schedaSelezionata = 0

    /// Le carte, una per profilo. Se non le ricordi restano solo qui in
    /// memoria e spariscono chiudendo l'app.
    @Published private(set) var cards: [String: Card] = [:]

    private let d = UserDefaults.standard
    private var caricamentoInCorso = true

    init() {
        // Riferimento locale: finché le proprietà non sono tutte inizializzate
        // non si può leggere `self.d`, e il compilatore ha ragione a fermarci.
        let ud = UserDefaults.standard
        let dec = JSONDecoder()
        profiles = (ud.data(forKey: "profiles").flatMap { try? dec.decode([Profile].self, from: $0) })
            ?? [Profile.principale()]
        activeID = ud.string(forKey: "activeID") ?? ""
        settings = (ud.data(forKey: "settings").flatMap { try? dec.decode(Settings.self, from: $0) })
            ?? Settings()
        sites = (ud.data(forKey: "sites").flatMap { try? dec.decode([String: SiteConfig].self, from: $0) })
            ?? [:]
        armed = ud.bool(forKey: "armed")
        shops = (ud.data(forKey: "shops").flatMap { try? dec.decode([Shop].self, from: $0) })
            ?? NegoziPredefiniti.all
        accounts = (ud.data(forKey: "accounts").flatMap { try? dec.decode([SiteAccount].self, from: $0) })
            ?? []
        targets = (ud.data(forKey: "targets").flatMap { try? dec.decode([MonitorTarget].self, from: $0) })
            ?? []

        if profiles.isEmpty { profiles = [Profile.principale()] }
        if !profiles.contains(where: { $0.id == activeID }) { activeID = profiles[0].id }
        if settings.rememberCard { caricaCarteDalPortachiavi() }
        caricamentoInCorso = false

        // I siti predefiniti arrivano una volta sola: chi ne toglie uno non
        // se lo ritrova al prossimo avvio. Chi aveva già dei target li trova
        // accanto ai suoi, senza doppioni di quelli creati a mano.
        // Dentro init i didSet non scattano: il salvataggio va chiesto.
        if ud.integer(forKey: "monitorPredefinitiVersione") < 1 {
            for voce in MonitorPredefiniti.tutti where !giaPresente(voce, in: targets) {
                targets.append(voce.target)
            }
            salva()
            ud.set(1, forKey: "monitorPredefinitiVersione")
        }

        // Versione 2: il controllo delle schede. Chi aveva già i predefiniti
        // lo riceve su quelli che lo reggono, e anche sul target che aveva
        // creato a mano sullo stesso indirizzo — è il suo Supreme, ed è lì che
        // i restock servono. Non si tocca chi l'ha già configurato da sé.
        if ud.integer(forKey: "monitorPredefinitiVersione") < 2 {
            for (id, schede) in MonitorPredefiniti.schedePerPredefinito {
                guard let voce = MonitorPredefiniti.tutti.first(where: { $0.id == id }) else { continue }
                let impronta = MonitorPredefiniti.impronta(voce.target.url)
                for i in targets.indices where targets[i].approfondisci == nil
                    && targets[i].tipo == .elenco
                    && (targets[i].preset == id || MonitorPredefiniti.impronta(targets[i].url) == impronta) {
                    MonitorPredefiniti.conApprofondimento(&targets[i], schede: schede)
                }
            }
            salva()
            ud.set(2, forKey: "monitorPredefinitiVersione")
        }
    }

    // MARK: - Profilo attivo

    var active: Profile {
        get { profiles.first { $0.id == activeID } ?? profiles[0] }
        set {
            guard let i = profiles.firstIndex(where: { $0.id == newValue.id }) else { return }
            profiles[i] = newValue
        }
    }

    func aggiungiProfilo(copiandoAttivo: Bool) {
        var p = Profile(name: copiandoAttivo ? active.name + " (copia)" : "Nuovo profilo")
        if copiandoAttivo {
            p.shipping = active.shipping
            p.billing = active.billing
            p.billingEnabled = active.billingEnabled
            if let c = cards[active.id] { setCard(c, for: p.id) }
        }
        profiles.append(p)
        activeID = p.id
    }

    func eliminaProfiloAttivo() {
        guard profiles.count > 1 else { return }
        let via = activeID
        profiles.removeAll { $0.id == via }
        cards[via] = nil
        Keychain.delete(account: via)
        activeID = profiles[0].id
    }

    // MARK: - Carte

    func card(for id: String) -> Card { cards[id] ?? Card() }

    func setCard(_ card: Card, for id: String) {
        let pulita = card.normalizzata
        cards[id] = pulita
        guard settings.rememberCard else { return }
        if let data = try? JSONEncoder().encode(pulita) {
            Keychain.save(data, account: id)
        }
    }

    func cancellaCarta(for id: String) {
        cards[id] = nil
        Keychain.delete(account: id)
    }

    private func caricaCarteDalPortachiavi() {
        let dec = JSONDecoder()
        for p in profiles {
            if let data = Keychain.load(account: p.id), let c = try? dec.decode(Card.self, from: data) {
                cards[p.id] = c
            }
        }
    }

    /// Cambiando "ricorda la carta" le carte vanno spostate tutte insieme,
    /// altrimenti ne resterebbero di orfane da una parte.
    private func cambiaCustodiaCarte(_ prima: Settings) {
        guard !caricamentoInCorso, prima.rememberCard != settings.rememberCard else { return }
        if settings.rememberCard {
            for (id, c) in cards {
                if let data = try? JSONEncoder().encode(c) { Keychain.save(data, account: id) }
            }
        } else {
            Keychain.deleteAll()
        }
    }

    // MARK: - Negozi

    func aggiungiNegozio(nome: String, indirizzo: String) {
        let n = nome.trimmingCharacters(in: .whitespaces)
        var url = indirizzo.trimmingCharacters(in: .whitespaces)
        guard !n.isEmpty, !url.isEmpty else { return }
        if !url.lowercased().hasPrefix("http") { url = "https://" + url }
        shops.append(Shop(nome: n, indirizzo: url))
    }

    func rimuoviNegozio(_ negozio: Shop) {
        shops.removeAll { $0.id == negozio.id }
    }

    func spostaNegozi(da: IndexSet, a: Int) {
        shops.move(fromOffsets: da, toOffset: a)
    }

    func ripristinaNegozi() {
        shops = NegoziPredefiniti.all
    }

    // MARK: - Monitor

    func aggiungiTarget(_ t: MonitorTarget) {
        targets.append(t)
    }

    func rimuoviTarget(_ t: MonitorTarget) {
        targets.removeAll { $0.id == t.id }
    }

    func aggiornaTarget(_ t: MonitorTarget) {
        if let i = targets.firstIndex(where: { $0.id == t.id }) { targets[i] = t }
    }

    /// Vero se quel predefinito c'è già, per nome d'origine o per indirizzo.
    func haPredefinito(_ voce: MonitorPredefiniti.Voce) -> Bool {
        giaPresente(voce, in: targets)
    }

    func aggiungiPredefinito(_ voce: MonitorPredefiniti.Voce) {
        guard !haPredefinito(voce) else { return }
        var t = voce.target
        t.id = UUID().uuidString
        targets.append(t)
    }

    private func giaPresente(_ voce: MonitorPredefiniti.Voce, in elenco: [MonitorTarget]) -> Bool {
        let impronta = MonitorPredefiniti.impronta(voce.target.url)
        return elenco.contains {
            $0.preset == voce.id || MonitorPredefiniti.impronta($0.url) == impronta
        }
    }

    // MARK: - Account dei siti

    /// L'account per l'host aperto adesso, sottodomini compresi: salvato su
    /// "endclothing.com" vale anche su "www.endclothing.com".
    func account(per host: String) -> SiteAccount? {
        guard !host.isEmpty else { return nil }
        return accounts.first { host == $0.host || host.hasSuffix("." + $0.host) || $0.host.hasSuffix("." + host) }
    }

    @discardableResult
    func salvaAccount(host: String, utente: String, password: String, nota: String = "") -> Bool {
        let h = host.trimmingCharacters(in: .whitespaces).lowercased()
            .replacingOccurrences(of: "https://", with: "")
            .replacingOccurrences(of: "http://", with: "")
            .split(separator: "/").first.map(String.init) ?? ""
        let u = utente.trimmingCharacters(in: .whitespaces)
        guard !h.isEmpty, !u.isEmpty else { return false }

        var voce = accounts.first { $0.host == h } ?? SiteAccount(host: h, utente: u)
        voce.utente = u
        voce.nota = nota

        if !password.isEmpty {
            guard KeychainAccessi.salva(password, account: voce.chiavePortachiavi) else { return false }
        }
        if let i = accounts.firstIndex(where: { $0.id == voce.id }) {
            accounts[i] = voce
        } else {
            accounts.append(voce)
        }
        return true
    }

    func rimuoviAccount(_ voce: SiteAccount) {
        KeychainAccessi.elimina(account: voce.chiavePortachiavi)
        accounts.removeAll { $0.id == voce.id }
    }

    /// Rilegge la password. È qui che il telefono chiede Face ID; se rifiuti,
    /// torna nil e non succede niente.
    func password(per voce: SiteAccount) -> String? {
        KeychainAccessi.leggi(account: voce.chiavePortachiavi,
                              motivo: "Compilare l'accesso a \(voce.host)")
    }

    // MARK: - Regole per sito

    func site(for host: String) -> SiteConfig {
        var unito = SiteConfig()
        for (chiave, cfg) in sites where host == chiave || host.hasSuffix("." + chiave) {
            if !cfg.addToCart.isEmpty { unito.addToCart = cfg.addToCart }
            if !cfg.cartUrl.isEmpty { unito.cartUrl = cfg.cartUrl }
            if !cfg.checkoutUrl.isEmpty { unito.checkoutUrl = cfg.checkoutUrl }
            unito.rules.append(contentsOf: cfg.rules)
        }
        return unito
    }

    func setSite(_ cfg: SiteConfig, for host: String) {
        guard !host.isEmpty else { return }
        if cfg.isEmpty { sites[host] = nil } else { sites[host] = cfg }
    }

    // MARK: - Stato per il motore JavaScript

    func bridgeState() -> BridgeState {
        let p = active
        return BridgeState(
            armed: armed,
            settings: settings,
            sites: sites,
            profile: ProfilePayload(
                shipping: p.shipping,
                billing: BillingPayload(enabled: p.billingEnabled, address: p.billing)
            ),
            card: settings.fillCard ? card(for: p.id) : nil
        )
    }

    func bridgeStateJSON() -> String {
        let enc = JSONEncoder()
        guard let data = try? enc.encode(bridgeState()),
              let testo = String(data: data, encoding: .utf8) else { return "null" }
        return testo
    }

    // MARK: - Salvataggio

    private func salva() {
        guard !caricamentoInCorso else { return }
        let enc = JSONEncoder()
        if let x = try? enc.encode(profiles) { d.set(x, forKey: "profiles") }
        if let x = try? enc.encode(settings) { d.set(x, forKey: "settings") }
        if let x = try? enc.encode(sites) { d.set(x, forKey: "sites") }
        if let x = try? enc.encode(shops) { d.set(x, forKey: "shops") }
        if let x = try? enc.encode(accounts) { d.set(x, forKey: "accounts") }
        if let x = try? enc.encode(targets) { d.set(x, forKey: "targets") }
        d.set(activeID, forKey: "activeID")
        d.set(armed, forKey: "armed")
    }
}
