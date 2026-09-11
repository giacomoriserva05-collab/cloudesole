import Foundation

/// I dati di una persona. I nomi dei campi combaciano con le chiavi che il
/// motore JavaScript si aspetta: cambiarli qui vuol dire cambiarli anche in
/// `filler.js`.
struct Address: Codable, Equatable {
    var firstName = ""
    var lastName = ""
    var email = ""
    var phone = ""
    var company = ""
    var address1 = ""
    var houseNumber = ""
    var address2 = ""
    var postalCode = ""
    var city = ""
    var province = ""
    var country = "IT"
    var fiscalCode = ""
    var birthDate = ""
    var size = ""            // taglia da scegliere sulla scheda prodotto

    var isEmpty: Bool {
        firstName.isEmpty && email.isEmpty && address1.isEmpty
    }
}

struct Profile: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var name: String = "Nuovo profilo"
    var shipping = Address()
    var billing = Address()
    var billingEnabled = false

    static func principale() -> Profile {
        Profile(name: "Principale")
    }
}

struct Card: Codable, Equatable {
    var number = ""
    var name = ""
    var expMonth = ""
    var expYear = ""
    var cvc = ""

    var isEmpty: Bool {
        number.isEmpty && name.isEmpty && expMonth.isEmpty && expYear.isEmpty && cvc.isEmpty
    }

    /// Come viene salvata e mandata al motore: cifre e niente spazi.
    var normalizzata: Card {
        var c = self
        c.number = number.filter(\.isNumber)
        c.name = name.trimmingCharacters(in: .whitespaces)
        c.expMonth = expMonth.trimmingCharacters(in: .whitespaces)
        c.expYear = expYear.trimmingCharacters(in: .whitespaces)
        c.cvc = cvc.filter(\.isNumber)
        return c
    }
}

struct Settings: Codable, Equatable {
    var fillCard = false          // compila anche i campi carta
    var rememberCard = false      // salva la carta nel portachiavi del telefono
    var overwrite = false         // sovrascrive i campi già compilati
    var splitHouseNumber = false  // il sito ha un campo civico separato
    var highlight = true          // bordo colorato sui campi toccati
    var autoFillCheckout = true   // a pilota acceso, compila arrivato al checkout
    var cartWait = 1500           // ms fra il clic e il cambio pagina
    var afterAdd = "checkout"     // dopo l'aggiunta apre "checkout" o "cart"
    var shopifyFast = true        // su Shopify va per richieste dirette
    /// Con cosa il monitor si presenta ai siti. Un contatto vero è la cortesia
    /// minima: se dai fastidio, il sito ha come scriverti invece che bloccarti.
    var userAgent = "CloudeSole/1.0 (monitor personale di disponibilita')"
}

struct FieldRule: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var selector = ""
    var key = ""
}

struct SiteConfig: Codable, Equatable {
    var addToCart = ""
    var cartUrl = ""
    var checkoutUrl = ""
    var rules: [FieldRule] = []

    var isEmpty: Bool {
        addToCart.isEmpty && cartUrl.isEmpty && checkoutUrl.isEmpty && rules.isEmpty
    }
}

/// Una voce di elenco: `id` è il valore, `nome` è quello che si legge.
/// Serve una struttura e non una tupla, perché ForEach vuole un key path e
/// in Swift i key path sugli elementi di una tupla non esistono.
struct Voce: Identifiable, Hashable {
    let id: String
    let nome: String
}

/// Le chiavi che una regola per sito può assegnare a un campo. Stesso elenco
/// del menu a tendina dell'estensione.
enum FieldKey {
    static let all: [Voce] = [
        Voce(id: "firstName", nome: "Nome"),
        Voce(id: "lastName", nome: "Cognome"),
        Voce(id: "fullName", nome: "Nome e cognome"),
        Voce(id: "email", nome: "Email"),
        Voce(id: "emailConfirm", nome: "Conferma email"),
        Voce(id: "phone", nome: "Telefono"),
        Voce(id: "company", nome: "Azienda"),
        Voce(id: "address1", nome: "Indirizzo"),
        Voce(id: "address2", nome: "Interno / scala"),
        Voce(id: "houseNumber", nome: "Civico"),
        Voce(id: "postalCode", nome: "CAP"),
        Voce(id: "city", nome: "Città"),
        Voce(id: "province", nome: "Provincia"),
        Voce(id: "country", nome: "Paese"),
        Voce(id: "fiscalCode", nome: "Codice fiscale"),
        Voce(id: "birthDate", nome: "Data di nascita"),
        Voce(id: "cardNumber", nome: "Numero carta"),
        Voce(id: "cardName", nome: "Titolare carta"),
        Voce(id: "cardExp", nome: "Scadenza"),
        Voce(id: "cardExpMonth", nome: "Mese scadenza"),
        Voce(id: "cardExpYear", nome: "Anno scadenza"),
        Voce(id: "cardCvc", nome: "CVC")
    ]

    static func label(_ key: String) -> String {
        all.first { $0.id == key }?.nome ?? key
    }
}

/// I paesi del menu a tendina dell'indirizzo.
enum Paesi {
    static let all: [Voce] = [
        Voce(id: "IT", nome: "Italia"), Voce(id: "FR", nome: "Francia"),
        Voce(id: "DE", nome: "Germania"), Voce(id: "ES", nome: "Spagna"),
        Voce(id: "GB", nome: "Regno Unito"), Voce(id: "US", nome: "Stati Uniti"),
        Voce(id: "CH", nome: "Svizzera"), Voce(id: "AT", nome: "Austria"),
        Voce(id: "BE", nome: "Belgio"), Voce(id: "NL", nome: "Paesi Bassi"),
        Voce(id: "PT", nome: "Portogallo"), Voce(id: "IE", nome: "Irlanda"),
        Voce(id: "SE", nome: "Svezia"), Voce(id: "DK", nome: "Danimarca"),
        Voce(id: "PL", nome: "Polonia"), Voce(id: "GR", nome: "Grecia")
    ]
}

// MARK: - Quello che viene passato al motore JavaScript

/// L'indirizzo di fatturazione arriva al motore come i campi dell'indirizzo
/// più il flag `enabled`, esattamente com'era nell'estensione.
struct BillingPayload: Encodable {
    var enabled: Bool
    var address: Address

    private enum Keys: String, CodingKey { case enabled }

    func encode(to encoder: Encoder) throws {
        try address.encode(to: encoder)
        var c = encoder.container(keyedBy: Keys.self)
        try c.encode(enabled, forKey: .enabled)
    }
}

struct ProfilePayload: Encodable {
    var shipping: Address
    var billing: BillingPayload
}

struct BridgeState: Encodable {
    var armed: Bool
    var settings: Settings
    var sites: [String: SiteConfig]
    var profile: ProfilePayload
    var card: Card?
}

// MARK: - Quello che il motore restituisce

struct FilledField: Decodable, Identifiable {
    var key = ""
    var section = ""
    var value = ""
    var label = ""
    var ok = true
    var id: String { key + section + label }
}

struct FillResult: Decodable {
    var filled = 0
    var skipped = 0
    var scanned = 0
    var fields: [FilledField] = []
}

struct ProbeButton: Decodable, Identifiable {
    var testo = ""
    var attivo = false
    var id: String { testo }
}

struct ProbeSizes: Decodable {
    var tipo = ""
    var voci: [String] = []
}

struct ProbeResult: Decodable {
    var url = ""
    var carrelloOChckout = false
    var indirizzoProdotto = false
    var pulsanti: [ProbeButton] = []
    var taglie: ProbeSizes?
    var carrello = ""
    var checkout = ""
    var campiCompilabili = 0
    var campi: [FilledField] = []
}

// MARK: - Negozi salvati

/// Un riquadro nella schermata iniziale: tocchi e si apre il negozio.
struct Shop: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var nome: String
    var indirizzo: String

    /// Le iniziali per il riquadro: "Foot Locker" diventa "FL".
    var sigla: String {
        let parole = nome.split(separator: " ").prefix(2)
        let lettere = parole.compactMap { $0.first }.map(String.init)
        return lettere.joined().uppercased()
    }

    /// Tinta ricavata dal nome. Non si usa `hashValue`: in Swift cambia a
    /// ogni avvio, e i colori ballerebbero da una volta all'altra.
    var tinta: Double {
        var somma = 0
        for u in nome.unicodeScalars { somma = (somma &* 31 &+ Int(u.value)) % 360 }
        return Double(somma) / 360.0
    }
}

/// Quelli che ci sono al primo avvio. Si aggiungono, si tolgono, si cambiano.
enum NegoziPredefiniti {
    static let all: [Shop] = [
        Shop(nome: "Supreme", indirizzo: "https://eu.supreme.com"),
        Shop(nome: "Nike", indirizzo: "https://www.nike.com/it/"),
        Shop(nome: "SNKRS", indirizzo: "https://www.nike.com/it/launch"),
        Shop(nome: "Slam Jam", indirizzo: "https://www.slamjam.com/it_IT/"),
        Shop(nome: "Foot Locker", indirizzo: "https://www.footlocker.it"),
        Shop(nome: "JD Sports", indirizzo: "https://www.jdsports.it"),
        Shop(nome: "Snipes", indirizzo: "https://www.snipes.it"),
        Shop(nome: "AW LAB", indirizzo: "https://www.awlab.com/it_it/"),
        Shop(nome: "END.", indirizzo: "https://www.endclothing.com/it"),
        Shop(nome: "Zalando", indirizzo: "https://www.zalando.it"),
        Shop(nome: "GameLife", indirizzo: "https://www.gamelife.it"),
        Shop(nome: "Size?", indirizzo: "https://www.size.co.uk")
    ]
}

// MARK: - Account dei siti

/// Le credenziali di accesso a un negozio. **La password non è in questa
/// struttura**: qui c'è solo il nome utente, e sta in UserDefaults con tutto
/// il resto. La password vive nel portachiavi, sotto Face ID, e si rilegge
/// solo al momento di scriverla nel modulo.
struct SiteAccount: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var host: String          // "www.endclothing.com"
    var utente: String        // email o nome utente
    var nota: String = ""

    /// La chiave con cui la password è archiviata nel portachiavi.
    var chiavePortachiavi: String { "account:" + id }
}

// MARK: - Monitor

/// Un target del monitor. Stessi campi del monitor desktop, ridotti ai due
/// tipi Shopify: sono quelli che coprono la maggior parte dei drop e che si
/// possono interrogare senza inventarsi selettori.
struct MonitorTarget: Codable, Identifiable, Equatable {
    enum Tipo: String, Codable, CaseIterable {
        case prodotto = "shopify_product"
        case collezione = "shopify_collection"
        case pagina = "html"
        case json = "json"
        case elenco = "links"

        var descrizione: String {
            switch self {
            case .prodotto: return "Prodotto Shopify"
            case .collezione: return "Collezione Shopify"
            case .pagina: return "Pagina qualsiasi (marcatori)"
            case .json: return "Risposta JSON (percorsi)"
            case .elenco: return "Elenco di prodotti (link)"
            }
        }

        /// I due Shopify sanno da soli dove guardare; gli altri no.
        var vaConfigurato: Bool { self != .prodotto && self != .collezione }
    }

    var id: String = UUID().uuidString
    var nome: String
    var tipo: Tipo = .prodotto
    var url: String
    var intervallo: Double = 20        // secondi fra un controllo e il successivo
    var taglie: String = ""            // "42, 42.5, M" — vuoto vuol dire tutte
    var attivo: Bool = true

    // --- tipo "pagina": si guarda cosa c'è scritto nel testo della pagina ---
    /// Frasi che dicono "c'è", una per riga.
    var marcatoriDisponibile: String = ""
    /// Frasi che dicono "non c'è". Hanno la precedenza: il pulsante "aggiungi
    /// al carrello" resta spesso nel codice anche a prodotto esaurito.
    var marcatoriEsaurito: String = ""
    /// Trattare i marcatori come espressioni regolari invece che come testo.
    var regex: Bool = false

    // --- tipo "json": percorsi puntati dentro la risposta, es. "data.items" ---
    var percorsoElenco: String = ""
    var percorsoDisponibile: String = ""
    var percorsoChiave: String = "id"
    var percorsoTitolo: String = "title"
    var percorsoUrl: String = ""

    // --- tipo "elenco": si pescano i link dei prodotti da una pagina ---
    /// Espressione regolare che riconosce una voce. Il primo gruppo fra
    /// parentesi è il valore tenuto: di norma l'identificatore del prodotto.
    var schema: String = "/products/([A-Za-z0-9._-]{2,90})"
    /// Anteposto al valore per ricostruire l'indirizzo completo.
    var base: String = ""
    /// Parole che la voce deve contenere, separate da virgola. Vuoto: tutte.
    var soloSe: String = ""
    /// Parole che la escludono.
    var tranneSe: String = ""

    /// Il predefinito da cui nasce, se nasce da uno. Opzionale apposta:
    /// i target salvati prima che esistesse si leggono lo stesso.
    var preset: String?

    // --- tipo "elenco", approfondimento: si aprono le schede dei prodotti ---
    //
    // Opzionali per la stessa ragione di `preset`: un campo nuovo non
    // opzionale renderebbe illeggibili i target salvati da una versione
    // precedente, e il decodificatore li butterebbe via tutti insieme.
    // Da fuori si usano le proprietà qui sotto, che hanno un valore sempre.
    var approfondisci: Bool?
    var schedaDisponibile: String?
    var schedaEsaurito: String?
    var schedaRiconosciuta: String?
    var schedePerGiro: Int?
    var schedaRegex: Bool?

    /// Aprire le schede dei prodotti per sapere se si possono comprare. È
    /// ciò che permette di accorgersi dei restock su un elenco di link.
    var approfondisce: Bool {
        get { approfondisci ?? false }
        set { approfondisci = newValue }
    }
    /// Frasi che dicono "si può comprare", una per riga.
    var marcatoriSchedaDisponibile: String {
        get { schedaDisponibile ?? "" }
        set { schedaDisponibile = newValue }
    }
    /// Frasi che dicono "esaurito". Hanno la precedenza.
    var marcatoriSchedaEsaurito: String {
        get { schedaEsaurito ?? "" }
        set { schedaEsaurito = newValue }
    }
    /// Se non è vuoto, una scheda che non contiene nessuna di queste frasi
    /// non viene giudicata: è una verifica anti-bot o una pagina d'errore,
    /// non il prodotto. Senza, una pagina così varrebbe "esaurito", e alla
    /// successiva pagina buona scatterebbe un falso restock.
    var marcatoriSchedaRiconosciuta: String {
        get { schedaRiconosciuta ?? "" }
        set { schedaRiconosciuta = newValue }
    }
    var schedeOgniGiro: Int {
        get { schedePerGiro ?? 5 }
        set { schedePerGiro = newValue }
    }
    var marcatoriSchedaRegex: Bool {
        get { schedaRegex ?? false }
        set { schedaRegex = newValue }
    }

    var elencoSchedaDisponibile: [String] { Self.righe(marcatoriSchedaDisponibile) }
    var elencoSchedaEsaurito: [String] { Self.righe(marcatoriSchedaEsaurito) }
    var elencoSchedaRiconosciuta: [String] { Self.righe(marcatoriSchedaRiconosciuta) }

    var elencoSoloSe: [String] { Self.parole(soloSe) }
    var elencoTranneSe: [String] { Self.parole(tranneSe) }

    private static func parole(_ s: String) -> [String] {
        s.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces).lowercased() }
            .filter { !$0.isEmpty }
    }

    var elencoMarcatoriDisponibile: [String] { Self.righe(marcatoriDisponibile) }
    var elencoMarcatoriEsaurito: [String] { Self.righe(marcatoriEsaurito) }

    private static func righe(_ s: String) -> [String] {
        s.split(whereSeparator: { $0.isNewline })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    /// Le taglie scritte a mano, ripulite. Vuoto = nessun filtro.
    var elencoTaglie: [String] {
        taglie.split(whereSeparator: { $0 == "," || $0 == " " })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }
}

/// I siti che il monitor conosce già: si aggiungono con un tocco.
///
/// Ognuno è stato provato interrogando davvero il sito, l'11/09/2026, con lo
/// stesso User-Agent dell'app. Sono gli stessi del monitor sul computer, e ne
/// ereditano la regola: se un sito cambia impaginazione, il predefinito va
/// ricontrollato.
///
/// Per "EU" si intende il negozio italiano: Nike non ha un negozio europeo
/// unico, ne ha uno per paese. Per cambiarlo basta sostituire `/it/` con un
/// altro codice (`/fr/`, `/de/`) nell'indirizzo, nello schema e nell'inizio.
enum MonitorPredefiniti {
    struct Voce: Identifiable {
        let id: String
        let sito: String
        let spiegazione: String
        let target: MonitorTarget
    }

    static let tutti: [Voce] = [
        Voce(id: "supreme-eu",
             sito: "Supreme",
             spiegazione: "Ogni prodotto nuovo nello shop europeo. Supreme chiude gli "
                + "endpoint JSON, quindi si leggono i link della collezione completa: "
                + "216 prodotti alla prova.",
             target: elenco(id: "supreme-eu",
                            nome: "Supreme EU",
                            url: "https://eu.supreme.com/collections/all",
                            schema: "/products/([A-Za-z0-9._-]{2,90})",
                            base: "https://eu.supreme.com/products/",
                            ogni: 30,
                            // Provato su 24 schede: 20 disponibili e 4 esaurite,
                            // tutte riconosciute. Con 216 prodotti, dieci a giro
                            // coprono il catalogo in una decina di minuti.
                            schede: 10)),

        Voce(id: "travis-apertura",
             sito: "Travis Scott",
             spiegazione: "Fra un drop e l'altro lo shop è chiuso da una password. Questo "
                + "avvisa nel momento in cui la toglie, cioè quando il drop comincia.",
             target: pagina(id: "travis-apertura",
                            nome: "Travis Scott · apertura shop",
                            url: "https://shop.travisscott.com/",
                            // Il modulo della password c'è solo a shop chiuso.
                            esaurito: "storefront_password",
                            // E questo c'è in ogni pagina di un negozio Shopify,
                            // aperto o chiuso: se manca non è lo shop che
                            // risponde (una verifica anti-bot, un errore), e
                            // un falso "aperto" è peggio di nessun avviso.
                            disponibile: "Shopify.shop",
                            ogni: 30)),

        Voce(id: "travis-nuovi",
             sito: "Travis Scott",
             spiegazione: "A shop aperto, ogni prodotto che compare. A shop chiuso non "
                + "trova niente, ed è normale: ci pensa l'avviso d'apertura.",
             target: elenco(id: "travis-nuovi",
                            nome: "Travis Scott · nuovi prodotti",
                            url: "https://shop.travisscott.com/collections/all",
                            schema: "/products/([a-z0-9][a-z0-9-]{2,60})",
                            base: "https://shop.travisscott.com/products/",
                            ogni: 60,
                            schede: 5)),

        Voce(id: "nike-novita",
             sito: "Nike",
             spiegazione: "La pagina Novità di nike.com: le uscite normali, senza "
                + "estrazione, dove chi arriva prima compra davvero.",
             target: elenco(id: "nike-novita",
                            nome: "Nike EU · novità",
                            url: "https://www.nike.com/it/w/nuovo-3n82y",
                            schema: "/it/t/([A-Za-z0-9-]{4,90}/[A-Z0-9-]{4,20})",
                            base: "https://www.nike.com/it/t/",
                            // Pagine da un mega: più spesso non serve e dà nell'occhio.
                            ogni: 180)),

        Voce(id: "snkrs-disponibili",
             sito: "SNKRS",
             spiegazione: "Il lancio passa da \"in arrivo\" ad \"acquistabile\". "
                + "In Europa molti lanci SNKRS sono estrazioni: l'avviso ti dice che la "
                + "finestra si è aperta.",
             target: elenco(id: "snkrs-disponibili",
                            nome: "SNKRS EU · appena disponibili",
                            url: "https://www.nike.com/it/launch/in-stock",
                            schema: "/it/launch/t/([a-z0-9-]{4,90})",
                            base: "https://www.nike.com/it/launch/t/",
                            ogni: 90,
                            // Disponibilità per taglia nella scheda: provata su
                            // cinque lanci reali.
                            schede: 4)),

        Voce(id: "snkrs-lanci",
             sito: "SNKRS",
             spiegazione: "Un lancio messo in calendario che prima non c'era: giorni di "
                + "margine per organizzarsi.",
             target: elenco(id: "snkrs-lanci",
                            nome: "SNKRS EU · lanci annunciati",
                            url: "https://www.nike.com/it/launch/upcoming",
                            schema: "/it/launch/t/([a-z0-9-]{4,90})",
                            base: "https://www.nike.com/it/launch/t/",
                            // Il calendario cambia poche volte al giorno.
                            ogni: 300))
    ]

    /// `schede` a zero vuol dire che le schede non si aprono: su Nike.com e
    /// sui lanci in calendario la pagina non dice niente di utile — per i
    /// secondi dice "disponibile" per taglie che non sono ancora in vendita.
    private static func elenco(id: String, nome: String, url: String,
                               schema: String, base: String, ogni: Double,
                               schede: Int = 0) -> MonitorTarget {
        var t = MonitorTarget(nome: nome, url: url)
        t.tipo = .elenco
        t.schema = schema
        t.base = base
        t.intervallo = ogni
        t.preset = id
        if schede > 0 { conApprofondimento(&t, schede: schede) }
        return t
    }

    /// Il controllo delle schede come lo fa il monitor sul computer, con il
    /// marcatore di Shopify e di Nike.
    static func conApprofondimento(_ t: inout MonitorTarget, schede: Int) {
        t.approfondisce = true
        t.marcatoriSchedaDisponibile = MarcatoriScheda.disponibile
        t.marcatoriSchedaRiconosciuta = MarcatoriScheda.riconosciuta
        t.marcatoriSchedaRegex = true
        t.schedeOgniGiro = schede
    }

    /// I predefiniti che aprono le schede, e quante per giro.
    static let schedePerPredefinito: [String: Int] = [
        "supreme-eu": 10, "travis-nuovi": 5, "snkrs-disponibili": 4
    ]

    private static func pagina(id: String, nome: String, url: String,
                               esaurito: String, disponibile: String,
                               ogni: Double) -> MonitorTarget {
        var t = MonitorTarget(nome: nome, url: url)
        t.tipo = .pagina
        t.marcatoriEsaurito = esaurito
        t.marcatoriDisponibile = disponibile
        t.intervallo = ogni
        t.preset = id
        return t
    }

    /// Dominio e percorso, senza sottodominio: `us.supreme.com/collections/all`
    /// e `eu.supreme.com/collections/all` sono la stessa cosa, perché il primo
    /// rimanda al secondo. Serve a non aggiungere un doppione di un target che
    /// hai già creato a mano.
    static func impronta(_ indirizzo: String) -> String {
        guard let u = URL(string: indirizzo.trimmingCharacters(in: .whitespaces)),
              let host = u.host?.lowercased() else { return indirizzo.lowercased() }
        let pezzi = host.split(separator: ".")
        let dominio = pezzi.suffix(2).joined(separator: ".")
        var percorso = u.path.lowercased()
        while percorso.hasSuffix("/") { percorso.removeLast() }
        return dominio + percorso
    }
}

/// Il campo "available" che Shopify e Nike incorporano nella scheda. La barra
/// rovescia è facoltativa: su Nike quel JSON sta dentro una stringa, e le
/// virgolette arrivano sfuggite.
enum MarcatoriScheda {
    static let disponibile = "\\\\?\"available\\\\?\"\\s*:\\s*true"
    /// Presente sia a prodotto disponibile sia esaurito: se manca, la pagina
    /// non è la scheda del prodotto.
    static let riconosciuta = "\\\\?\"available\\\\?\"\\s*:"
}

/// Un articolo visto durante un controllo.
struct MonitorItem: Equatable {
    var chiave: String       // id variante: stabile fra un giro e l'altro
    var titolo: String
    var disponibile: Bool
    var url: String
    var prezzo: String?
    /// Falso quando "disponibile" vuol dire solo "presente in elenco": un
    /// link trovato in una pagina non dice se il prodotto si può comprare.
    var verificato: Bool = true
}

/// Cos'è cambiato fra due controlli. Le stesse due categorie del desktop.
struct MonitorEvento: Identifiable, Equatable {
    enum Genere: String { case restock, nuovo }

    var id: String = UUID().uuidString
    var quando: Date = Date()
    var bersaglio: String
    var titolo: String
    var url: String
    var genere: Genere

    var etichetta: String {
        genere == .restock ? "RESTOCK" : "NUOVO"
    }
}

/// Una riga del registro, quello che si legge a schermo mentre gira.
struct MonitorRiga: Identifiable, Equatable {
    enum Livello: String { case info, avviso, errore, successo }

    var id: String = UUID().uuidString
    var quando: Date = Date()
    var bersaglio: String
    var testo: String
    var livello: Livello = .info
}
