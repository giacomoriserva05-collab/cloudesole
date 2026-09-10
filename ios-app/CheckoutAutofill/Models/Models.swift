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
