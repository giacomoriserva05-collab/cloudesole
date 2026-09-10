import SwiftUI
import UIKit
import UserNotifications

/// Registra il telefono presso Apple e conserva il *token del dispositivo*:
/// l'indirizzo a cui vanno mandate le notifiche.
///
/// Serve perché il monitor sul computer possa svegliare il telefono anche ad
/// app chiusa. Il giro è questo: l'app chiede un token ad Apple, tu lo copi
/// nella configurazione del monitor, e da lì in poi è il computer a mandare
/// le notifiche passando dai server di Apple. Nessun server nostro.
final class PushRegistrar: NSObject, ObservableObject, UIApplicationDelegate {
    /// Il token in esadecimale, quello da incollare nel monitor.
    @Published var token: String?
    /// Perché la registrazione non è riuscita, quando non riesce.
    @Published var errore: String?

    private let chiave = "apnsToken"

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        token = UserDefaults.standard.string(forKey: chiave)
        // Registrarsi non chiede niente all'utente: il permesso di mostrare
        // le notifiche è un'altra cosa, e si chiede dalla scheda Monitor.
        application.registerForRemoteNotifications()
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let esadecimale = deviceToken.map { String(format: "%02x", $0) }.joined()
        UserDefaults.standard.set(esadecimale, forKey: chiave)
        DispatchQueue.main.async {
            self.token = esadecimale
            self.errore = nil
        }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        DispatchQueue.main.async {
            self.errore = error.localizedDescription
        }
    }
}
