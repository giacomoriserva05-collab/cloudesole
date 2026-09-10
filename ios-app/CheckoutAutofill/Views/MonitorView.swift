import SwiftUI
import UserNotifications

/// Il monitor dentro l'app: target, avvio, registro dal vivo e avvisi.
/// Toccando un avviso si apre il prodotto, senza cercarlo.
struct MonitorView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var monitor: MonitorEngine
    @EnvironmentObject var web: WebController
    @EnvironmentObject var push: PushRegistrar
    @State private var mostraNuovo = false
    @State private var copiato = false
    @State private var daModificare: MonitorTarget?

    var body: some View {
        NavigationStack {
            List {
                sezioneComandi
                sezioneTelefono
                sezioneAvvisi
                sezioneTarget
                sezioneRegistro
            }
            .navigationTitle("Monitor")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { mostraNuovo = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $mostraNuovo) {
                TargetView(target: MonitorTarget(nome: "", url: ""), nuovo: true)
                    .environmentObject(store)
            }
            .sheet(item: $daModificare) { t in
                TargetView(target: t, nuovo: false).environmentObject(store)
            }
            .onAppear { monitor.aggiornaPermesso() }
        }
    }

    // MARK: - Comandi

    private var sezioneComandi: some View {
        Section {
            Button {
                if monitor.inCorso {
                    monitor.ferma()
                } else {
                    monitor.avvia(store.targets, userAgent: store.settings.userAgent)
                }
            } label: {
                Label(monitor.inCorso ? "Ferma il monitor" : "Avvia il monitor",
                      systemImage: monitor.inCorso ? "stop.circle.fill" : "play.circle.fill")
                    .foregroundStyle(monitor.inCorso ? Color.red : Color.green)
                    .font(.body.weight(.semibold))
            }
            .disabled(store.targets.filter { $0.attivo }.isEmpty)

            if monitor.permessoNotifiche != .authorized {
                Button {
                    monitor.chiediPermesso()
                } label: {
                    Label("Consenti le notifiche", systemImage: "bell.badge")
                }
            }
        } footer: {
            Text(piedeComandi)
        }
    }

    private var piedeComandi: String {
        if monitor.permessoNotifiche != .authorized {
            return "Senza il consenso alle notifiche il monitor gira lo stesso, "
                 + "ma gli avvisi li vedi solo qui dentro."
        }
        return "Il monitor gira mentre l'app è aperta: uscendo, iOS la sospende "
             + "in pochi secondi e nessuna app può interrogare un sito ogni venti "
             + "secondi in sottofondo. Per la sorveglianza continua resta il "
             + "monitor sul computer."
    }

    // MARK: - Notifiche ad app chiusa

    /// Il token è l'indirizzo del telefono per le notifiche. Copiandolo nella
    /// configurazione del monitor sul computer, quello può svegliarti anche
    /// con l'app chiusa — cosa che l'app da sola non può fare.
    private var sezioneTelefono: some View {
        Section {
            if let t = push.token {
                Button {
                    UIPasteboard.general.string = t
                    copiato = true
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(copiato ? "Copiato" : "Copia il codice del telefono")
                                .foregroundStyle(copiato ? Color.green : Color.accentColor)
                            Text(t).font(.caption2.monospaced())
                                .foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                        }
                        Spacer()
                        Image(systemName: copiato ? "checkmark" : "doc.on.doc")
                            .foregroundStyle(.secondary)
                    }
                }
            } else if let e = push.errore {
                Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            } else {
                Label("Registrazione in corso…", systemImage: "antenna.radiowaves.left.and.right")
                    .foregroundStyle(.secondary)
            }
        } header: {
            Text("Notifiche ad app chiusa")
        } footer: {
            Text("Incolla questo codice nella configurazione del monitor sul computer, "
                 + "alla voce dei dispositivi. Da lì in poi è il computer ad avvisarti, "
                 + "anche con l'app chiusa e ovunque tu sia — a patto che il computer "
                 + "sia acceso e il monitor in funzione.")
        }
    }

    // MARK: - Avvisi

    private var sezioneAvvisi: some View {
        Section("Avvisi") {
            if monitor.eventi.isEmpty {
                Text("Nessun restock finora.").foregroundStyle(.secondary)
            } else {
                ForEach(monitor.eventi.prefix(20)) { e in
                    Button {
                        web.vai(a: e.url)
                        store.schedaSelezionata = 0
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 6) {
                                Text(e.etichetta)
                                    .font(.caption2.weight(.bold))
                                    .padding(.horizontal, 6).padding(.vertical, 2)
                                    .background(e.genere == .restock ? Color.green : Color.blue,
                                                in: Capsule())
                                    .foregroundStyle(.white)
                                Text(e.bersaglio).font(.caption).foregroundStyle(.secondary)
                                Spacer()
                                Text(e.quando, style: .time).font(.caption2).foregroundStyle(.secondary)
                            }
                            Text(e.titolo).font(.callout).foregroundStyle(.primary)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Target

    private var sezioneTarget: some View {
        Section("Target") {
            if store.targets.isEmpty {
                Text("Nessun target. Aggiungine uno col più in alto.")
                    .foregroundStyle(.secondary)
            }
            ForEach(store.targets) { t in
                Button { daModificare = t } label: { rigaTarget(t) }
            }
            .onDelete { indici in
                for i in indici { store.rimuoviTarget(store.targets[i]) }
            }
        }
    }

    private func rigaTarget(_ t: MonitorTarget) -> some View {
        HStack(spacing: 10) {
            Circle()
                .fill(t.attivo ? (monitor.inCorso ? Color.green : Color.orange) : Color.secondary.opacity(0.4))
                .frame(width: 9, height: 9)
            VStack(alignment: .leading, spacing: 2) {
                Text(t.nome.isEmpty ? t.url : t.nome)
                    .font(.callout).foregroundStyle(.primary).lineLimit(1)
                Text(dettaglio(t)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            if let quando = monitor.ultimoControllo[t.id] {
                Text(quando, style: .time).font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    private func dettaglio(_ t: MonitorTarget) -> String {
        var parti = [t.tipo.descrizione, "ogni \(Int(t.intervallo))s"]
        if !t.elencoTaglie.isEmpty { parti.append("taglie " + t.elencoTaglie.joined(separator: ", ")) }
        return parti.joined(separator: " · ")
    }

    // MARK: - Registro

    private var sezioneRegistro: some View {
        Section {
            if monitor.righe.isEmpty {
                Text("Il registro è vuoto.").foregroundStyle(.secondary)
            }
            ForEach(monitor.righe.prefix(40)) { r in
                HStack(alignment: .top, spacing: 8) {
                    Text(r.quando, style: .time)
                        .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(r.bersaglio).font(.caption2).foregroundStyle(.secondary)
                        Text(r.testo).font(.caption).foregroundStyle(colore(r.livello))
                    }
                }
            }
        } header: {
            HStack {
                Text("Registro")
                Spacer()
                Button("Svuota") { monitor.svuotaRegistro() }.font(.caption)
                Button("Azzera stato") { monitor.azzeraStato() }.font(.caption)
            }
        } footer: {
            Text("Azzerando lo stato il prossimo giro considera tutto nuovo: "
                 + "serve dopo aver cambiato i target.")
        }
    }

    private func colore(_ l: MonitorRiga.Livello) -> Color {
        switch l {
        case .errore: return .red
        case .avviso: return .orange
        case .successo: return .green
        case .info: return .primary
        }
    }
}

/// Il modulo di un target: gli stessi campi del monitor desktop.
struct TargetView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var chiudi

    @State var target: MonitorTarget
    let nuovo: Bool

    private var valido: Bool {
        !target.url.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var aiutoIndirizzo: String {
        switch target.tipo {
        case .prodotto:
            return "L'indirizzo della scheda prodotto, quello con /products/ dentro. "
                 + "L'endpoint JSON lo ricava l'app."
        case .collezione:
            return "L'indirizzo della collezione, quello con /collections/ dentro."
        case .pagina:
            return "L'indirizzo della pagina, qualunque negozio sia. Viene letta com'è, "
                 + "compresa la parte dopo il punto interrogativo."
        case .json:
            return "L'indirizzo che risponde in JSON: l'endpoint del negozio, non la pagina."
        case .elenco:
            return "L'indirizzo dell'elenco: una collezione, la pagina dei lanci, una mappa "
                 + "del sito. Serve dove la disponibilità non si legge ma i prodotti sì."
        }
    }

    /// Il tipo che funziona ovunque: si dice all'app cosa cercare nel testo.
    private var sezionePagina: some View {
        Section {
            VStack(alignment: .leading, spacing: 4) {
                Text("Se c'è, la pagina dice").font(.caption).foregroundStyle(.secondary)
                TextEditor(text: $target.marcatoriDisponibile)
                    .frame(height: 62)
                    .font(.callout.monospaced())
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Se è esaurito, dice").font(.caption).foregroundStyle(.secondary)
                TextEditor(text: $target.marcatoriEsaurito)
                    .frame(height: 62)
                    .font(.callout.monospaced())
            }
            Toggle("Espressioni regolari", isOn: $target.regex)
        } header: {
            Text("Marcatori")
        } footer: {
            Text("Una frase per riga, per esempio «Aggiungi al carrello» sopra e "
                 + "«Esaurito» sotto. **L'esaurito vince sempre**: il pulsante d'acquisto "
                 + "resta quasi sempre nel codice della pagina anche quando non si può "
                 + "comprare, quindi da solo non basta a dire che c'è.")
        }
    }

    /// Pesca i link dei prodotti da una pagina d'elenco.
    private var sezioneElenco: some View {
        Section {
            TextField("Schema dei link", text: $target.schema)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .font(.callout.monospaced())
            TextField("Inizio dell'indirizzo", text: $target.base)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Solo se contiene (facoltativo)", text: $target.soloSe)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Tranne se contiene (facoltativo)", text: $target.tranneSe)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
        } header: {
            Text("Link")
        } footer: {
            Text("Lo schema è un'espressione regolare: il pezzo fra parentesi è quello "
                 + "tenuto. Quello predefinito prende gli identificatori dei prodotti "
                 + "Shopify. **Qui ogni voce vale come disponibile**: il segnale è la "
                 + "comparsa di un prodotto che prima non c'era, non il ritorno in stock.")
        }
    }

    /// Per gli endpoint che rispondono in JSON ma non sono Shopify.
    private var sezioneJson: some View {
        Section {
            TextField("Percorso dell'elenco (es. data.items)", text: $target.percorsoElenco)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Percorso della disponibilità", text: $target.percorsoDisponibile)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Percorso della chiave", text: $target.percorsoChiave)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Percorso del titolo", text: $target.percorsoTitolo)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Percorso dell'indirizzo (facoltativo)", text: $target.percorsoUrl)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
        } header: {
            Text("Percorsi")
        } footer: {
            Text("Percorsi puntati dentro la risposta, come sul monitor del computer: "
                 + "`a.b.0.c`. Lascia vuoto l'elenco se la risposta è già una lista.")
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Nome", text: $target.nome)
                    Picker("Tipo", selection: $target.tipo) {
                        ForEach(MonitorTarget.Tipo.allCases, id: \.self) { t in
                            Text(t.descrizione).tag(t)
                        }
                    }
                    TextField("Indirizzo", text: $target.url)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                } footer: {
                    Text(aiutoIndirizzo)
                }

                if target.tipo == .pagina { sezionePagina }
                if target.tipo == .json { sezioneJson }
                if target.tipo == .elenco { sezioneElenco }

                Section {
                    Stepper("Ogni \(Int(target.intervallo)) secondi",
                            value: $target.intervallo, in: 5...600, step: 5)
                    TextField("Taglie (vuoto = tutte)", text: $target.taglie)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                    Toggle("Attivo", isOn: $target.attivo)
                } footer: {
                    Text("Le taglie si scrivono separate da virgola: 42, 42.5, M. "
                         + "Valgono gli stessi alias del pilota, quindi M accetta Medium.")
                }
            }
            .navigationTitle(nuovo ? "Nuovo target" : "Target")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Annulla") { chiudi() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Salva") {
                        if target.nome.trimmingCharacters(in: .whitespaces).isEmpty {
                            target.nome = URL(string: target.url)?.host ?? "Target"
                        }
                        if nuovo { store.aggiungiTarget(target) } else { store.aggiornaTarget(target) }
                        chiudi()
                    }
                    .disabled(!valido)
                }
            }
        }
    }
}
