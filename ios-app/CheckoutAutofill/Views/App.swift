import SwiftUI

@main
struct CheckoutAutofillApp: App {
    @StateObject private var store: Store
    @StateObject private var web: WebController

    init() {
        let s = Store()
        _store = StateObject(wrappedValue: s)
        _web = StateObject(wrappedValue: WebController(store: s))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(web)
        }
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            BrowserView()
                .tabItem { Label("Negozio", systemImage: "safari") }
            ProfilesView()
                .tabItem { Label("Profili", systemImage: "person.text.rectangle") }
            SettingsView()
                .tabItem { Label("Impostazioni", systemImage: "gearshape") }
        }
    }
}
