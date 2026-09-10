import Foundation
import Security

/// Portachiavi: è qui che finiscono i dati della carta quando scegli di
/// ricordarli. Nell'estensione Chrome finivano in chiaro su disco; su iOS
/// c'è di meglio, e costa poche righe.
enum Keychain {
    private static let service = "com.giacomoriserva.checkoutautofill.cards"

    static func save(_ data: Data, account: String) {
        delete(account: account)
        let item: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data,
            // Leggibile solo a telefono sbloccato e solo su questo dispositivo:
            // non finisce nei backup né su un altro telefono.
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        SecItemAdd(item as CFDictionary, nil)
    }

    static func load(account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess else { return nil }
        return out as? Data
    }

    static func delete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }

    static func deleteAll() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service
        ]
        SecItemDelete(query as CFDictionary)
    }
}

/// Le password dei siti. Stanno in un servizio a parte rispetto alle carte, e
/// soprattutto sono protette dal riconoscimento: per rileggerle il telefono
/// chiede Face ID o il codice. È il sistema a farlo, non l'app.
enum KeychainAccessi {
    private static let service = "com.giacomoriserva.checkoutautofill.accounts"

    static func salva(_ segreto: String, account: String) -> Bool {
        elimina(account: account)
        guard let dati = segreto.data(using: .utf8) else { return false }

        // .userPresence: nessuna rilettura senza che tu ci sia.
        guard let controllo = SecAccessControlCreateWithFlags(
            nil,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            .userPresence,
            nil
        ) else { return false }

        let item: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: dati,
            kSecAttrAccessControl as String: controllo
        ]
        return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }

    /// Legge la password. Qui il sistema mostra Face ID: se rifiuti, torna nil.
    static func leggi(account: String, motivo: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecUseOperationPrompt as String: motivo
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess,
              let dati = out as? Data else { return nil }
        return String(data: dati, encoding: .utf8)
    }

    static func elimina(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
