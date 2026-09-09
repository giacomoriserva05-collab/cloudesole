"""Prova automatica dell'interfaccia grafica.

Apre la finestra vera, ci inietta eventi come se arrivassero dal monitor e
verifica che tabelle, registro e salvataggio reagiscano correttamente. Alla fine
chiude tutto da sola: non serve cliccare nulla.

Uso:  .venv\\Scripts\\python.exe guitest.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from restock import config, gui as gui_module, presets
from restock.gui import App, PresetDialog, SettingsDialog, TargetDialog

failures: list[str] = []

# I messagebox sono modali: senza qualcuno che clicchi, il test resterebbe
# appeso per sempre. Li sostituiamo con stub che registrano la chiamata.
popups: list[tuple[str, str, str]] = []


class FakeMessagebox:
    @staticmethod
    def showerror(title: str, message: str, **_kw) -> str:
        popups.append(("error", title, message))
        return "ok"

    @staticmethod
    def showwarning(title: str, message: str, **_kw) -> str:
        popups.append(("warning", title, message))
        return "ok"

    @staticmethod
    def showinfo(title: str, message: str, **_kw) -> str:
        popups.append(("info", title, message))
        return "ok"

    @staticmethod
    def askyesno(title: str, message: str, **_kw) -> bool:
        popups.append(("askyesno", title, message))
        return True


gui_module.messagebox = FakeMessagebox


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="restock-gui-"))
    config_path = tmpdir / "config.yaml"

    config.save_raw(
        config_path,
        {
            "defaults": {"interval": 20, "user_agent": "RestockMonitor/1.0 (test)", "notify": ["console"]},
            "notifiers": {"console": {"enabled": True}, "desktop": {"enabled": False}},
            "targets": [
                {
                    "name": "Store A",
                    "type": "shopify_product",
                    "url": "https://esempio.test/products/x",
                    "interval": 20,
                    "notify": ["console"],
                }
            ],
        },
    )

    app = App(config_path)
    app.update()

    # --- 1. La tabella riflette la configurazione caricata.
    rows = app.tree.get_children()
    check(rows == ("Store A",), f"riga attesa 'Store A', trovate {rows}")
    check(app.tree.set("Store A", "tipo") == "Prodotto Shopify", "etichetta del tipo errata")

    # --- 2. Aggiunta di un target e salvataggio su disco.
    app.targets.append(
        {
            "name": "Store B",
            "type": "html",
            "url": "https://esempio.test/p",
            "interval": 30,
            "notify": ["console"],
            "options": {"out_of_stock_when": ["Esaurito"]},
        }
    )
    check(app._persist() is True, "il salvataggio di una config valida doveva riuscire")
    app._refresh_targets()
    app.update()
    check(len(app.tree.get_children()) == 2, "la tabella doveva mostrare 2 target")

    reloaded = config.load(config_path)
    check(len(reloaded.targets) == 2, "il file salvato doveva contenere 2 target")
    check(reloaded.targets[1].options["out_of_stock_when"] == ["Esaurito"], "opzioni html non persistite")

    # --- 3. Una config non valida viene rifiutata e il file resta intatto.
    app.targets.append({"name": "Rotto", "type": "inesistente", "url": "https://x.test"})
    popups.clear()
    check(app._persist() is False, "una config non valida non doveva essere salvata")
    check(
        any(kind == "error" and "type" in message for kind, _title, message in popups),
        f"doveva comparire un errore che spiega il problema, popup: {popups}",
    )
    check(len(config.load(config_path).targets) == 2, "il file su disco e' stato sporcato da una config non valida")
    app.targets.pop()
    check(not config_path.with_suffix(".validate.tmp").exists(), "il file temporaneo di validazione non e' stato rimosso")

    # --- 4. Eventi di polling: stato, contatori, colori.
    app._handle_event(("poll", "Store A", True, 5, 2, ""))
    app.update()
    check(app.tree.set("Store A", "stato") == "attivo", "stato 'attivo' non applicato")
    check(app.tree.set("Store A", "articoli") == "5", "conteggio articoli errato")
    check(app.tree.set("Store A", "disponibili") == "2", "conteggio disponibili errato")
    check(app.tree.item("Store A", "tags") == ("attivo",), "tag di stato errato")

    app._handle_event(("poll", "Store A", False, 0, 0, "404 - URL o tipo errato"))
    app.update()
    check(app.tree.set("Store A", "stato") == "404 - URL o tipo errato", "dettaglio errore non mostrato")
    check(app.tree.item("Store A", "tags") == ("errore",), "tag di errore non applicato")

    app._handle_event(("disabled", "Store A", "robots.txt vieta l'accesso"))
    app.update()
    check("robots" in app.tree.set("Store A", "stato"), "blocco robots.txt non mostrato in tabella")

    # --- 5. Un restock finisce fra gli avvisi, con link cliccabile.
    app._handle_event(("change", "Store A", "restock", "Sneaker X - 43", "129.00", "https://esempio.test/p?variant=2"))
    app.update()
    alerts = app.alerts.get_children()
    check(len(alerts) == 1, "l'avviso non e' comparso nella tabella Avvisi")
    check(app.alerts.set(alerts[0], "articolo") == "Sneaker X - 43", "articolo errato nell'avviso")
    check(app.alert_urls[alerts[0]] == "https://esempio.test/p?variant=2", "link dell'avviso non memorizzato")
    check(app.alert_count == 1, "contatore avvisi non incrementato")
    check(
        "(1)" in app.nav_buttons["avvisi"].cget("text"),
        f"il contatore avvisi nella barra laterale non e' aggiornato: "
        f"{app.nav_buttons['avvisi'].cget('text')!r}",
    )

    # --- 6. Registri separati: una scheda per target, piu' quella generale.
    check(
        set(app.log_panels) == {"", "Store A", "Store B"},
        f"schede del registro sbagliate: {sorted(app.log_panels)}",
    )
    check(app.log_notebook.index("end") == 3, "il numero di schede non corrisponde ai target")

    def panel_text(name: str) -> str:
        return app.log_panels[name].text.get("1.0", "end")

    # L'avviso del punto 5 doveva finire nella scheda di Store A, non altrove.
    check("Sneaker X - 43" in panel_text("Store A"), "il restock non e' finito nel registro del suo target")
    check("Sneaker X - 43" not in panel_text(""), "il restock non doveva comparire nella scheda Generale")
    check("Sneaker X - 43" not in panel_text("Store B"), "il restock e' finito nel registro di un altro target")

    app._handle_event(("log", logging.INFO, "riga di A", "Store A"))
    app._handle_event(("log", logging.INFO, "riga di B", "Store B"))
    app._handle_event(("log", logging.WARNING, "riga generale", None))
    app.update()

    check("riga di A" in panel_text("Store A") and "riga di B" not in panel_text("Store A"), "A contaminato")
    check("riga di B" in panel_text("Store B") and "riga di A" not in panel_text("Store B"), "B contaminato")
    check("riga generale" in panel_text(""), "il messaggio generale non e' arrivato")
    check("riga di A" not in panel_text(""), "una riga di target e' finita in Generale")

    # Il prefisso "[Nome]" dei log del monitor smista nella scheda giusta e viene tolto.
    logging.getLogger("restock.prova").info("[Store B] messaggio con prefisso")
    app._pump()
    app.update()
    text_b = panel_text("Store B")
    check("messaggio con prefisso" in text_b, "il log con prefisso non e' stato smistato")
    check("[Store B]" not in text_b, "il prefisso ridondante doveva essere rimosso")
    check("messaggio con prefisso" not in panel_text(""), "il log con prefisso e' finito anche in Generale")

    # Tetto di righe applicato per scheda.
    for index in range(600):
        app._log_line(logging.INFO, f"riga {index}", target="Store A")
    app.update()
    lines_a = int(app.log_panels["Store A"].text.index("end-1c").split(".")[0])
    check(lines_a <= 501, f"il registro di Store A doveva restare limitato, trovate {lines_a} righe")
    check(int(app.log_panels["Store B"].text.index("end-1c").split(".")[0]) < 20, "riempita la scheda sbagliata")

    # Svuotare agisce solo sulla scheda in primo piano.
    app.log_notebook.select(app.log_panels["Store A"])
    app.update()
    app._clear_log()
    app.update()
    check(panel_text("Store A").strip() == "", "la scheda in primo piano non e' stata svuotata")
    check("riga di B" in panel_text("Store B"), "svuotare ha toccato anche le altre schede")

    # Selezionare un target porta in primo piano il suo registro.
    app.tree.selection_set("Store B")
    app.update()
    check(app.log_notebook.select() == str(app.log_panels["Store B"]), "la selezione non apre il registro del target")

    # Rinominando un target la sua scheda segue il nuovo nome.
    app.targets[1]["name"] = "Store B rinominato"
    check(app._persist() is True, "la rinomina doveva essere salvabile")
    app._refresh_targets()
    app.update()
    check(
        set(app.log_panels) == {"", "Store A", "Store B rinominato"},
        f"le schede non seguono la rinomina: {sorted(app.log_panels)}",
    )

    # Rimuovendo un target sparisce anche il suo registro.
    app.targets.pop()
    check(app._persist() is True, "la rimozione doveva essere salvabile")
    app._refresh_targets()
    app.update()
    check(set(app.log_panels) == {"", "Store A"}, f"scheda non rimossa: {sorted(app.log_panels)}")
    check(app.log_notebook.index("end") == 2, "il numero di schede non e' sceso")

    # --- 7. Le finestre di dialogo si aprono e si chiudono senza errori.
    dialog = TargetDialog(app, app.targets[0], {"Store A", "Store B"})
    app.update()
    check(dialog.var_name.get() == "Store A", "il dialogo non ha caricato il target")
    for label in ("Collezione Shopify", "API JSON", "Pagina HTML", "Elenco di link", "Prodotto Shopify"):
        dialog.var_type.set(label)
        dialog._on_type_change()
        app.update()
    dialog.destroy()
    app.update()

    settings = SettingsDialog(app, app.raw)
    app.update()
    check(settings.var_ua.get() == "RestockMonitor/1.0 (test)", "impostazioni non caricate")
    settings.destroy()
    app.update()

    # --- 8. Preset: la scheda di ogni sito si apre e l'inserimento funziona.
    dialog = PresetDialog(app)
    app.update()
    keys = [p.key for p in presets.PRESETS]
    check(bool(keys), "nessun preset definito")

    for key in keys:
        preset = presets.get(key)
        dialog.tree.selection_set(key)
        dialog._show_detail()
        app.update()
        shown = dialog.detail.get("1.0", "end")
        check(preset.name in shown, f"la scheda di '{key}' non mostra il nome")
        check(preset.target["url"] in shown, f"la scheda di '{key}' non mostra l'indirizzo")
        if preset.caveat:
            check("Cosa NON fa" in shown, f"la scheda di '{key}' non dichiara i limiti")

    dialog.tree.selection_set(keys[0])
    dialog._add()
    check(dialog.result == [keys[0]], f"preset scelto non restituito: {dialog.result}")
    app.update()

    before = len(app.targets)
    for key in keys:
        app.targets.append(presets.instantiate(presets.get(key), {str(t.get("name")) for t in app.targets}))
    check(app._persist() is True, "i preset dovevano produrre una configurazione valida")
    app._refresh_targets()
    app.update()
    check(len(app.tree.get_children()) == before + len(keys), "i preset non compaiono in tabella")

    saved = config.load(config_path)
    check(len(saved.targets) == before + len(keys), "i preset non sono stati salvati su disco")
    names = [t.name for t in saved.targets]
    check(len(names) == len(set(names)), f"nomi duplicati fra i preset salvati: {names}")

    # --- 8b. Il riquadro dell'accertamento della disponibilita'.
    travis = next(t for t in app.targets if t.get("type") == "links" and t.get("detail"))
    dialog = TargetDialog(app, travis, set())
    app.update()
    check(dialog.var_detail_on.get() is True, "il riquadro non risulta attivo per un preset che lo usa")
    check(
        dialog.text_detail_in.get("1.0", "end").strip() == "\n".join(travis["detail"]["in_stock_when"]),
        "i marcatori dell'accertamento non sono stati caricati",
    )
    check(dialog.var_detail_max.get() == str(travis["detail"]["max_checks"]), "max_checks non caricato")

    dialog.var_detail_max.set("7")
    dialog._save()
    app.update()
    salvato = dialog.result
    check(salvato is not None, "il salvataggio del target con accertamento e' fallito")
    check(salvato["detail"]["max_checks"] == 7, f"max_checks non salvato: {salvato.get('detail')}")
    check(salvato["detail"]["regex"] is True, "il flag regex non e' stato conservato")

    # Attivare l'accertamento senza marcatori dev'essere rifiutato.
    senza = {k: v for k, v in travis.items() if k != "detail"}
    dialog = TargetDialog(app, senza, set())
    app.update()
    dialog.var_detail_on.set(True)
    popups.clear()
    dialog._save()
    app.update()
    check(dialog.result is None, "un accertamento senza marcatori non doveva essere accettato")
    check(
        any("arcatori" in title or "arcatori" in msg for _k, title, msg in popups),
        f"doveva spiegare che mancano i marcatori: {popups}",
    )
    dialog.destroy()
    app.update()

    # --- 9. Attivazione dei singoli target.
    names = [str(t.get("name")) for t in app.targets]
    initial = {name: bool(t.get("enabled", True)) for name, t in zip(names, app.targets)}
    check(any(initial.values()), "almeno un target deve nascere attivo")

    # I preset con un segnaposto da modificare nascono spenti di proposito:
    # cosi' non generano errori finche' non li personalizzi.
    off_by_design = [p for p in presets.PRESETS if p.target.get("enabled") is False]
    check(bool(off_by_design), "il preset da personalizzare dovrebbe nascere spento")
    for preset in off_by_design:
        check(bool(preset.needs_edit), f"{preset.key}: nasce spento ma non dice cosa modificare")
        check(
            app.tree.set(preset.target["name"], "attivo") == "No",
            f"{preset.key}: doveva risultare spento in tabella",
        )

    check(
        app.tree.set(names[0], "attivo") == ("Sì" if initial[names[0]] else "No"),
        "la colonna Attivo non riflette lo stato",
    )

    # Disattivare uno solo, senza toccare gli altri.
    app.tree.selection_set(names[0])
    app._toggle_target()
    app.update()
    check(app.targets[0].get("enabled") is False, "il target non e' stato disattivato")
    check(app.tree.set(names[0], "attivo") == "No", "la colonna Attivo non si e' aggiornata")
    check(app.tree.item(names[0], "tags") == ("disattivato",), "riga non marcata come disattivata")
    check(
        all(bool(t.get("enabled", True)) == initial[n] for n, t in list(zip(names, app.targets))[1:]),
        "il comando ha alterato lo stato di altri target",
    )
    check(config.load(config_path).targets[0].enabled is False, "lo spegnimento non e' stato salvato")

    # Riattivare.
    app._toggle_target()
    app.update()
    check(app.targets[0].get("enabled") is True, "il target non e' stato riattivato")

    # Solo questo: ne resta attivo uno.
    target_solo = names[2]
    app.tree.selection_set(target_solo)
    app._only_this()
    app.update()
    active = [str(t.get("name")) for t in app.targets if t.get("enabled", True)]
    check(active == [target_solo], f"'Solo questo' doveva lasciarne uno: {active}")
    check(f"1 attivi su {len(app.targets)}" in app.status.get(), f"barra di stato: {app.status.get()!r}")

    saved_active = [t.name for t in config.load(config_path).targets if t.enabled]
    check(saved_active == [target_solo], f"stato non persistito: {saved_active}")

    # Avviare con un solo target attivo non deve lamentarsi.
    popups.clear()
    settings_now = config.load(config_path)
    check(
        len([t for t in settings_now.targets if t.enabled]) == 1,
        "doveva restare un solo target attivo",
    )

    # Tutti spenti: l'avvio viene rifiutato con un messaggio, non parte a vuoto.
    for target in app.targets:
        target["enabled"] = False
    app._persist()
    app._refresh_targets()
    app.update()
    popups.clear()
    app._start()
    app.update()
    check(app.thread is None, "il monitor non doveva partire senza target attivi")
    check(
        any("attivo" in title.lower() for _kind, title, _msg in popups),
        f"doveva avvisare che non c'e' nulla di attivo: {popups}",
    )

    # Attiva tutti.
    app._enable_all()
    app.update()
    check(all(t.get("enabled", True) for t in app.targets), "'Attiva tutti' non ha riacceso tutto")
    check(
        f"{len(app.targets)} attivi su {len(app.targets)}" in app.status.get(),
        f"barra di stato: {app.status.get()!r}",
    )

    # Il dialogo di modifica espone e conserva lo stato.
    app.targets[0]["enabled"] = False
    dialog = TargetDialog(app, app.targets[0], set(names))
    app.update()
    check(dialog.var_enabled.get() is False, "il dialogo non mostra il target come spento")
    dialog.destroy()
    app.update()

    # --- 10. Chiusura pulita.
    app._on_stopped()
    app.update()
    check(str(app.btn_start["state"]) == "normal", "il pulsante Avvia doveva tornare attivo")
    app.destroy()

    print("=" * 60)
    if failures:
        print(f"{len(failures)} CONTROLLI FALLITI:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Interfaccia grafica: tutti i controlli superati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
