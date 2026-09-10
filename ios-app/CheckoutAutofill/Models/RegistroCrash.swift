import Foundation

/// Prende nota dell'ultima eccezione non gestita, così al riavvio l'app può
/// dire cosa l'ha fatta cadere.
///
/// Nasce da una difficoltà concreta: i crolli si vedevano solo sul telefono, e
/// per capirli bisognava andare a pescare a mano i file di analisi in
/// Impostazioni. Ora il motivo resta scritto e si legge — e si copia — dalla
/// scheda Impostazioni.
///
/// Non sostituisce il resoconto di sistema, che resta più completo: qui c'è il
/// nome dell'eccezione, il motivo e la parte alta della pila delle chiamate,
/// che nella pratica bastano quasi sempre a capire dove guardare.
enum RegistroCrash {
    private static let chiaveTesto = "ultimoCrashTesto"
    private static let chiaveData = "ultimoCrashData"

    static func installa() {
        NSSetUncaughtExceptionHandler { eccezione in
            let pila = eccezione.callStackSymbols.prefix(14).joined(separator: "\n")
            let testo = """
            \(eccezione.name.rawValue)
            \(eccezione.reason ?? "senza motivo dichiarato")

            \(pila)
            """
            // Scrittura sincrona: fra un attimo il processo non c'è più.
            let d = UserDefaults.standard
            d.set(testo, forKey: chiaveTesto)
            d.set(Date(), forKey: chiaveData)
            d.synchronize()
        }
    }

    static var ultimo: (testo: String, quando: Date)? {
        let d = UserDefaults.standard
        guard let t = d.string(forKey: chiaveTesto),
              let q = d.object(forKey: chiaveData) as? Date else { return nil }
        return (t, q)
    }

    static func dimentica() {
        let d = UserDefaults.standard
        d.removeObject(forKey: chiaveTesto)
        d.removeObject(forKey: chiaveData)
    }
}
