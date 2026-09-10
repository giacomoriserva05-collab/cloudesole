import SwiftUI

@main
struct CheckoutAutofillApp: App {
    @StateObject private var store: Store
    @StateObject private var web: WebController
    @StateObject private var monitor: MonitorEngine

    init() {
        let s = Store()
        let w = WebController(store: s)
        let m = MonitorEngine()

        // Toccando la notifica di un restock si arriva sul prodotto: l'app
        // apre l'indirizzo e passa alla scheda Negozio da sé.
        m.apriProdotto = { [weak s, weak w] url in
            w?.vai(a: url)
            s?.schedaSelezionata = 0
        }

        _store = StateObject(wrappedValue: s)
        _web = StateObject(wrappedValue: w)
        _monitor = StateObject(wrappedValue: m)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(web)
                .environmentObject(monitor)
        }
    }
}

struct RootView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        TabView(selection: $store.schedaSelezionata) {
            BrowserView()
                .tabItem { Label("Negozio", systemImage: "safari") }
                .tag(0)
            MonitorView()
                .tabItem { Label("Monitor", systemImage: "dot.radiowaves.left.and.right") }
                .tag(1)
            ProfilesView()
                .tabItem { Label("Profili", systemImage: "person.text.rectangle") }
                .tag(2)
            SettingsView()
                .tabItem { Label("Impostazioni", systemImage: "gearshape") }
                .tag(3)
        }
    }
}
