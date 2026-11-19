/* exported selectRecentPdf, openChatAndCopyMessage, updateRowMeal, updateRowName, updateRowPhone,
   openChangeApiKeyDialog, openChangeTemplateDialog, openCustomDayDialog, openCustomMealDialog,
   openNoteModal, closeNoteModal, copyNoteFromModal, openSuperbConfigDialog, closeSettingsModal */

let pdfPath = null;
let currentData = [];
let recentPdfs = [];
let mealSelectedValues = null;
let statusSelectedValues = null;
// true quando la tabella contiene modifiche a mano o chat già aperte: ricaricare le perderebbe
let tableDirty = false;

// Pausa tra un'apertura e l'altra nell'invio in blocco (ms)
const BULK_PAUSE_MS = 800;

// ===== KIT UNICO: conferma e notifiche (al posto di alert/confirm nativi) =====
const ui = (() => {
    function toast(message, kind = "info", ms = 4500) {
        let host = document.getElementById("toastHost");
        if (!host) {
            host = document.createElement("div");
            host.id = "toastHost";
            host.setAttribute("aria-live", "polite");
            document.body.appendChild(host);
        }
        const el = document.createElement("div");
        el.className = `toast toast-${kind}`;
        el.textContent = message;
        host.appendChild(el);
        requestAnimationFrame(() => el.classList.add("show"));
        const close = () => {
            el.classList.remove("show");
            setTimeout(() => el.remove(), 220);
        };
        el.addEventListener("click", close);
        setTimeout(close, kind === "error" ? Math.max(ms, 8000) : ms);
    }

    // Ritorna Promise<boolean>. Il fuoco parte su «Annulla»; Esc = Annulla.
    function confirm({ title, message, details = [], confirmLabel = "Conferma", danger = false }) {
        return new Promise(resolve => {
            const backdrop = document.createElement("div");
            backdrop.className = "modal-backdrop open confirm-backdrop";
            const box = document.createElement("div");
            box.className = "modal";
            box.setAttribute("role", "alertdialog");
            box.setAttribute("aria-modal", "true");

            const h = document.createElement("h2");
            h.textContent = title;
            const p = document.createElement("p");
            p.className = "confirm-message";
            p.textContent = message;
            box.append(h, p);

            if (details.length) {
                const ul = document.createElement("ul");
                ul.className = "confirm-details";
                details.forEach(d => {
                    const li = document.createElement("li");
                    li.textContent = d;
                    ul.appendChild(li);
                });
                box.appendChild(ul);
            }

            const footer = document.createElement("div");
            footer.className = "modal-footer";
            const cancel = document.createElement("button");
            cancel.type = "button";
            cancel.className = "btn-modal-cancel";
            cancel.textContent = "Annulla";
            const ok = document.createElement("button");
            ok.type = "button";
            ok.className = danger ? "btn-modal-danger" : "btn-modal-confirm";
            ok.textContent = confirmLabel;
            footer.append(cancel, ok);
            box.appendChild(footer);
            backdrop.appendChild(box);
            document.body.appendChild(backdrop);

            const done = (val) => {
                document.removeEventListener("keydown", onKey, true);
                backdrop.remove();
                resolve(val);
            };
            const onKey = (e) => {
                if (e.key === "Escape") { e.preventDefault(); done(false); }
            };
            document.addEventListener("keydown", onKey, true);
            cancel.addEventListener("click", () => done(false));
            ok.addEventListener("click", () => done(true));
            cancel.focus();
        });
    }

    return { toast, confirm };
})();

// Data di oggi nel fuso del PC (toISOString usa UTC: dopo mezzanotte darebbe il giorno prima)
function localISODate(d = new Date()) {
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Variabili del template: l'elenco vero arriva dal backend (get_template_info) all'avvio.
let TEMPLATE_VARS_TEXT = "{nome}, {giorno}, {pasto}, {ospiti}, {persone}, {orario}";

function hasApi() {
    return !!(window.pywebview && window.pywebview.api);
}

// Unico punto che cambia tableDirty: lo comunica anche al backend, che lo usa
// per chiedere conferma quando si chiude la finestra.
function setTableDirty(v) {
    tableDirty = !!v;
    if (hasApi() && window.pywebview.api.set_modifiche_in_sospeso) {
        window.pywebview.api.set_modifiche_in_sospeso(tableDirty).catch(e => console.warn(e));
    }
}

// Chiamata dal backend quando si prova a chiudere la finestra con modifiche in sospeso
let closeDialogOpen = false;
window.chiediConfermaChiusura = async function () {
    if (closeDialogOpen) return;
    closeDialogOpen = true;
    try {
        try { await window.pywebview.api.ack_chiusura(); } catch (e) { console.warn(e); }
        const aperte = currentData.filter(r => r.chatOpened).length;
        const details = [];
        if (aperte) details.push(`${aperte} chat risultano aperte: alla riapertura il segno verde non ci sarà più.`);
        details.push("Le modifiche fatte a mano nella tabella non vengono salvate.");
        const ok = await ui.confirm({
            title: "Chiudere PrenotazioniCN?",
            message: "La tabella ha modifiche o chat segnate che si perdono chiudendo.",
            details,
            confirmLabel: "Chiudi senza salvare",
            danger: true,
        });
        if (ok) await window.pywebview.api.conferma_chiusura();
        else await window.pywebview.api.annulla_chiusura();
    } catch (e) {
        console.warn(e);
    } finally {
        closeDialogOpen = false;
    }
};

// Prima di sostituire la tabella: se contiene modifiche o chat aperte, chiede conferma.
async function confirmDiscardTable() {
    if (!tableDirty || !currentData || currentData.length === 0) return true;
    const aperte = currentData.filter(r => r.chatOpened).length;
    const details = [];
    if (aperte) details.push(`${aperte} chat risultano già aperte: il segno verde andrà perso.`);
    details.push("Le modifiche fatte a mano nella tabella (nomi, telefoni, pasti, giorno) andranno perse.");
    return ui.confirm({
        title: "Sostituire le prenotazioni attuali?",
        message: "Caricando nuove prenotazioni, la tabella attuale viene sostituita.",
        details,
        confirmLabel: "Sostituisci",
        danger: true,
    });
}

const btnExportHtml = document.getElementById("btnExportHtml");

const templateInput = document.getElementById("templateInput");
const btnApplyTemplate = document.getElementById("btnApplyTemplate");


function openSettingsModalForApiKey() {

    const backdrop   = document.getElementById("settingsModalBackdrop");
    const titleEl    = document.getElementById("settingsModalTitle");
    const descEl     = document.getElementById("settingsModalDesc");
    const inputEl    = document.getElementById("settingsModalInput");
    const textareaEl = document.getElementById("settingsModalTextarea");
    const confirmBtn = document.getElementById("settingsModalConfirmBtn");
    const resetRow   = document.getElementById("settingsModalResetRow");
    const resetBtn   = document.getElementById("settingsModalResetBtn");

    if (!backdrop || !titleEl || !descEl || !inputEl || !textareaEl || !confirmBtn) return;

    titleEl.textContent = "Cambia chiave ChatGPT";
    descEl.textContent  = "Inserisci la nuova chiave ChatGPT. Sarà usata subito, dalla prossima elaborazione.";

    inputEl.value = "";
    inputEl.style.display    = "block";
    textareaEl.style.display = "none";

    if (resetRow) resetRow.style.display = "none";
    if (resetBtn) resetBtn.onclick = null;
    confirmBtn.textContent = "Salva";

    confirmBtn.onclick = async () => {
        const nuova = (inputEl.value || "").trim();
        if (!nuova) {
            ui.toast("Chiave vuota: nessuna modifica applicata.", "warning");
            return;
        }

        try {
            const res = await window.pywebview.api.set_api_key(nuova);
            if (res && res.ok) {
                ui.toast(res.message || "Chiave ChatGPT salvata.", "success");
                closeSettingsModal();
                refreshStatusBar();
            } else {
                ui.toast((res && res.error) || "Chiave non salvata.", "error");
            }
        } catch (e) {
            console.error(e);
            ui.toast("Errore nel salvataggio della chiave ChatGPT.", "error");
        }
    };

    backdrop.style.display = "block";
    inputEl.focus();
}


function openSettingsModalForTemplate(corrente) {

    const backdrop   = document.getElementById("settingsModalBackdrop");
    const titleEl    = document.getElementById("settingsModalTitle");
    const descEl     = document.getElementById("settingsModalDesc");
    const inputEl    = document.getElementById("settingsModalInput");
    const textareaEl = document.getElementById("settingsModalTextarea");
    const confirmBtn = document.getElementById("settingsModalConfirmBtn");
    const resetRow   = document.getElementById("settingsModalResetRow");
    const resetBtn   = document.getElementById("settingsModalResetBtn");

    if (!backdrop || !titleEl || !descEl || !inputEl || !textareaEl || !confirmBtn) return;

    titleEl.textContent = "Cambia template predefinito";
    descEl.textContent  = "Variabili disponibili: " + TEMPLATE_VARS_TEXT +
        ". Il template viene controllato prima di salvarlo; quello precedente resta nei backup.";

    inputEl.style.display    = "none";
    textareaEl.style.display = "block";
    textareaEl.value         = corrente || "";
    confirmBtn.textContent   = "Salva";

    if (resetRow) resetRow.style.display = "block";

    if (resetBtn) {
        resetBtn.onclick = async () => {
            const ok = await ui.confirm({
                title: "Ripristinare il template di fabbrica?",
                message: "Il template predefinito attuale viene sostituito da quello di fabbrica. " +
                    "Una copia di quello attuale resta nei backup.",
                confirmLabel: "Ripristina",
                danger: true,
            });
            if (!ok) return;
            try {
                const res = await window.pywebview.api.reset_template();
                if (!res || !res.ok) {
                    ui.toast((res && res.error) || "Ripristino non riuscito.", "error");
                    return;
                }
                // rileggo dal backend ciò che è stato davvero salvato
                const tpl = await window.pywebview.api.get_template();
                textareaEl.value = tpl || "";
                if (templateInput) templateInput.value = tpl || "";
                ui.toast(res.message || "Template ripristinato.", "success");

                if (currentData && currentData.length > 0) {
                    await recalcAllAndRender();
                }
            } catch (e) {
                console.error(e);
                ui.toast("Errore durante il ripristino del template.", "error");
            }
        };
    }

    confirmBtn.onclick = async () => {
        const nuovo = (textareaEl.value || "").trim();
        try {
            const res = await window.pywebview.api.set_template(nuovo);
            if (!res || !res.ok) {
                // la finestra resta aperta: l'utente corregge senza riscrivere tutto
                ui.toast((res && res.error) || "Template non salvato.", "error");
                return;
            }
            const salvato = await window.pywebview.api.get_template();
            if (templateInput) templateInput.value = salvato || "";
            ui.toast(res.message || "Template aggiornato.", "success");
        } catch (e) {
            console.error(e);
            ui.toast("Errore durante l'aggiornamento del template predefinito.", "error");
            return;
        }

        closeSettingsModal();
        if (currentData && currentData.length > 0) {
            await recalcAllAndRender();
        }
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}

function closeSettingsModal() {
    const backdrop = document.getElementById("settingsModalBackdrop");
    if (backdrop) {
        backdrop.style.display = "none";
    }
}

if (btnApplyTemplate && templateInput) {
    btnApplyTemplate.addEventListener("click", async () => {
        const txt = templateInput.value.trim();
        try {
            // Template SOLO di sessione: non tocca template.txt
            const res = await window.pywebview.api.set_runtime_template(txt);
            if (!res || !res.ok) {
                ui.toast((res && res.error) || "Template non applicato.", "error");
                return;
            }

            if (currentData && currentData.length > 0) {
                await recalcAllAndRender();
            }
            setStatus("Template di sessione applicato alle prenotazioni (non salvato come predefinito).");
        } catch (e) {
            console.error(e);
            ui.toast("Errore durante l'aggiornamento del template di sessione.", "error");
        }
    });
}


function addRecentPdf(path) {
    if (!path) return;

    // Evita duplicati, tieni il più recente in alto
    recentPdfs = [path, ...recentPdfs.filter(p => p !== path)].slice(0, 5);
    renderRecentPdfs();
}

function renderRecentPdfs() {
    const box = document.getElementById("recentPdfsBox");
    if (!box) return;

    if (!recentPdfs.length) {
        box.innerHTML = '<div class="nav-empty">Nessun file aperto</div>';
        return;
    }

    box.innerHTML = recentPdfs.map((p, idx) => {
        const name = escapeHtml(p.split(/[/\\]/).pop());
        return `<button type="button" onclick="selectRecentPdf(${idx})" title="${escapeHtml(p)}">
            <svg class="icon-12" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            ${name}
        </button>`;
    }).join("");
}

// Seleziona un PDF dalla history
function selectRecentPdf(index) {
    const path = recentPdfs[index];
    if (!path) return;

    pdfPath = path;
    setOpenFileEnabled(true);

    const statusEl = document.getElementById("status");
    if (statusEl) {
        statusEl.textContent = "PDF selezionato: " + path.split(/[/\\]/).pop();
    }

    // Per l'elaborazione automatica, scommenta:
    // document.getElementById("btnProcess").click();
}
function escapeHtml(str) {
    // 0 è un valore vero: solo null/undefined diventano vuoto
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

// Dati che, se mancano, mettono un «?» nel messaggio al cliente
// Calcolato dal backend (_mancanti) sul template attivo: solo i dati che il template usa davvero
function missingFields(rec) {
    return Array.isArray(rec._mancanti) ? rec._mancanti : [];
}

// Ospiti come numero (accetta "2", "2 adulti"); null se non si capisce
function guestsNumber(v) {
    if (typeof v === "number" && Number.isFinite(v)) return v;
    const m = String(v ?? "").match(/\d+/);
    return m ? parseInt(m[0], 10) : null;
}

const TODAY_BADGE_TEXT = (() => {
    const days = ["Domenica","Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato"];
    const months = ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"];
    const now = new Date();
    return "Oggi: " + days[now.getDay()] + " " + now.getDate() + " " + months[now.getMonth()] + " " + now.getFullYear();
})();

// «Apri file» ha senso solo dopo aver scelto un file
function setOpenFileEnabled(on) {
    const b = document.getElementById("btnOpenLoadedFile");
    if (b) b.disabled = !on;
}

// Le righe "entrano" con un'animazione solo quando arrivano dati nuovi (non a ogni modifica)
let animateNextRender = false;

// Aggiorna un numero delle statistiche; se cambia, piccolo movimento
function setStat(el, value) {
    if (!el) return;
    const v = String(value);
    if (el.textContent === v) return;
    el.textContent = v;
    el.classList.remove("bump");
    void el.offsetWidth;   // riavvia l'animazione
    el.classList.add("bump");
}

// Statistiche, data di servizio e barra di stato calcolate sui dati finali
function updateSummary() {
    const n = currentData.length;
    const statCount = document.getElementById("statCount");
    const statGuests = document.getElementById("statGuests");
    const statChats = document.getElementById("statChats");
    setStat(statCount, n);
    if (statGuests) {
        const nums = currentData.map(r => guestsNumber(r.ospiti));
        const total = nums.reduce((s, x) => s + (x || 0), 0);
        const missing = nums.filter(x => x === null).length;
        setStat(statGuests, total);
        statGuests.title = missing ? `${missing} prenotazioni senza numero di ospiti` : "";
    }
    setStat(statChats, currentData.filter(r => r.chatOpened).length);

    const badge = document.getElementById("date-badge");
    if (badge) {
        const label = n ? (currentData[0].data_servizio_label || "") : "";
        badge.textContent = label ? "Servizio: " + label : TODAY_BADGE_TEXT;
        badge.classList.toggle("is-service", !!label);
    }

    const sbFile = document.getElementById("sbFile");
    if (sbFile && n) sbFile.textContent = n + " prenotazioni caricate";

    const btnOpenAll = document.getElementById("btnOpenAllChats");
    if (btnOpenAll) btnOpenAll.disabled = n === 0;
    if (btnExportHtml) btnExportHtml.disabled = n === 0;
}

function renderTable(data) {
    const container = document.getElementById("output");
    currentData = Array.isArray(data) ? data : [];

    // nessun dato
    if (currentData.length === 0) {
        container.innerHTML = '<div class="output-empty">Nessuna prenotazione trovata nel file.</div>';
        updateSummary();
        return;
    }

    // valori unici presenti nei dati (come Excel)
    const uniqueMeals = [...new Set(
        currentData
            .map(r => (r.pasto || "").toLowerCase())
            .filter(v => v)
    )];
    const uniqueStatus = [...new Set(
        currentData
            .map(r => (r.stato || "").toUpperCase())
            .filter(v => v)
    )];

    // box selezionati
    if (mealSelectedValues === null) {
        mealSelectedValues = [];
    } else {
        mealSelectedValues = mealSelectedValues.filter(v => uniqueMeals.includes(v));
    }

    if (statusSelectedValues === null) {
        statusSelectedValues = [];
    } else {
        statusSelectedValues = statusSelectedValues.filter(v => uniqueStatus.includes(v));
    }

    // valori da LLM/Superb/utente: sempre con escape
    const mealOptionsHtml = uniqueMeals.map(v => {
        const checked = mealSelectedValues.includes(v);
        return `
            <label class="filter-option">
                <input type="checkbox" class="chkMealFilter" value="${escapeHtml(v)}" ${checked ? "checked" : ""}>
                <span>${escapeHtml(v)}</span>
            </label>`;
    }).join("");

    const statusOptionsHtml = uniqueStatus.map(v => {
        const checked = statusSelectedValues.includes(v);
        return `
            <label class="filter-option">
                <input type="checkbox" class="chkStatusFilter" value="${escapeHtml(v)}" ${checked ? "checked" : ""}>
                <span>${escapeHtml(v)}</span>
            </label>`;
    }).join("");

// Ricava colonne dal primo record o da _colonne
    const colonneDef = (currentData[0] && currentData[0]._colonne && currentData[0]._colonne.length > 0)
        ? currentData[0]._colonne
        : Object.keys(currentData[0] || {}).filter(k =>
            !["messaggio","link_whatsapp","telefono_wa","data_servizio","data_servizio_label",
              "chatOpened","giorno","_colonne","_mancanti","pasto_personalizzato"].includes(k)
          );

    // Colonne sempre visibili alla fine
    const colonneVisibili = colonneDef.filter(c =>
        ![
            "messaggio",
            "link_whatsapp",
            "telefono_wa",
            "data_servizio",
            "data_servizio_label",
            "chatOpened",
            "_colonne",

            // nascondi note raw
            "note",
            "note_ospiti",
            "allergie",
            "pasto_personalizzato"
        ].includes(c)
    );
    // Nome, telefono e pasto sono sempre visibili e modificabili, anche se il file
    // (o Superb) non li elenca: il pasto è dedotto dall'orario e va controllabile.
    [["nome", 0], ["telefono", 1]].forEach(([c, pos]) => {
        if (!colonneVisibili.includes(c)) colonneVisibili.splice(Math.min(pos, colonneVisibili.length), 0, c);
    });
    if (!colonneVisibili.includes("pasto")) {
        const after = colonneVisibili.indexOf("orario");
        colonneVisibili.splice(after >= 0 ? after + 1 : colonneVisibili.length, 0, "pasto");
    }

    let html = `<table><thead><tr>`;
    colonneVisibili.forEach(col => {
        // i nomi delle colonne arrivano dall'LLM: escape obbligatorio
        const label = escapeHtml(col.charAt(0).toUpperCase() + col.slice(1));
        if (col === "pasto") {
            html += `<th><div class="filter-header"><span>${label}</span>
                <button type="button" class="filter-toggle${mealSelectedValues.length ? " is-active" : ""}" data-target="mealFilterBox" title="Filtra per pasto" aria-label="Filtra per pasto"><svg viewBox="0 0 24 24"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg></button></div>
                <div class="filter-box" id="mealFilterBox">${mealOptionsHtml || "<em>—</em>"}</div></th>`;
        } else if (col === "stato") {
            html += `<th><div class="filter-header"><span>${label}</span>
                <button type="button" class="filter-toggle${statusSelectedValues.length ? " is-active" : ""}" data-target="statusFilterBox" title="Filtra per stato" aria-label="Filtra per stato"><svg viewBox="0 0 24 24"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg></button></div>
                <div class="filter-box" id="statusFilterBox">${statusOptionsHtml || "<em>—</em>"}</div></th>`;
        } else {
            html += `<th>${label}</th>`;
        }
    });
    html += `<th>Note</th><th>WhatsApp</th></tr></thead><tbody>`;

    currentData.forEach((r, index) => {
            const hasNote = ["note", "note_ospiti", "allergie"].some(k => r[k] && String(r[k]).trim());

            html += animateNextRender ? `<tr class="row-in" style="animation-delay:${Math.min(index, 14) * 22}ms">` : `<tr>`;
            colonneVisibili.forEach(col => {
                const val = r[col] ?? "";
                const valStr = escapeHtml(String(val));

                if (col === "nome") {
                    html += `<td><input type="text" value="${valStr}"
                        onchange="updateRowName(${index}, this.value)" class="td-input"></td>`;
                } else if (col === "telefono") {
                    html += `<td><input type="text" value="${escapeHtml(r.telefono || valStr)}" placeholder="aggiungi numero"
                        onchange="updateRowPhone(${index}, this.value)" class="td-input"></td>`;
                } else if (col === "pasto") {
                    const pasto = String(val);
                    const standard = ["pranzo", "cena", "aperitivo"];
                    // esperienza personalizzata: compare come voce propria, non come «auto»
                    const custom = pasto && !standard.includes(pasto)
                        ? `<option value="${valStr}" selected>${valStr}</option>` : "";
                    const missing = !pasto ? " td-missing" : "";
                    const mealKey = !pasto ? "nessuno" : (standard.includes(pasto) ? pasto : "custom");
                    html += `<td><select onchange="updateRowMeal(${index}, this.value)" class="td-select${missing}" data-pasto="${mealKey}"
                        title="${pasto ? "" : "Pasto non riconosciuto dall'orario: sceglilo qui."}">
                        <option value="" ${pasto ? "" : "selected"}>auto</option>
                        ${standard.map(s => `<option value="${s}" ${pasto === s ? "selected" : ""}>${s}</option>`).join("")}
                        ${custom}
                        </select></td>`;
                } else if (col === "stato") {
                    const validBadges = ["C","N","A","S","PS"];
                    const statoUp = valStr.toUpperCase();
                    const badgeClass = validBadges.includes(statoUp) ? `badge badge-${statoUp}` : "badge badge-default";
                    html += `<td><span class="${badgeClass}">${valStr || "—"}</span></td>`;
                } else {
                    html += `<td>${valStr}</td>`;
                }
            });

            html += `<td>${hasNote ? `<button type="button" class="btn-note" onclick="openNoteModal(${index})">Vedi note</button>` : ""}</td>`;
            if (r.telefono_wa) {
                html += `<td><button id="btnChat_${index}" type="button"
                    class="btn-chat ${r.chatOpened ? "btn-chat-sent" : ""}"
                    title="${r.chatOpened ? "Chat già aperta in questa sessione" : "Apre WhatsApp con il messaggio già scritto"}"
                    onclick="openChatAndCopyMessage(${index}, event)">${r.chatOpened ? "Aperta" : "Apri chat"}</button></td>`;
            } else {
                html += `<td><button id="btnChat_${index}" type="button" class="btn-chat" disabled
                    title="Manca il numero di telefono: inseriscilo nella colonna Telefono">Senza numero</button></td>`;
            }
            html += `</tr>`;
        });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
    animateNextRender = false;

    updateSummary();
    const dotFile = document.getElementById("dotFile");
    if (dotFile) dotFile.classList.add("green");
    container.querySelectorAll(".filter-toggle").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const targetId = btn.dataset.target;
            const box = document.getElementById(targetId);
            if (!box) return;

            const isOpen = box.classList.contains("open");

            // chiudo eventuali altri box aperti
            document.querySelectorAll(".filter-box.open")
                .forEach(b => b.classList.remove("open"));

            if (!isOpen) {
                box.classList.add("open");
            }
        });
    });

    // chiudi i box cliccando fuori (un solo listener globale)
    ensureFilterBoxGlobalClickListener();

    // aggancio i filtri (come in Excel: multi-selezione)
    document.querySelectorAll(".chkMealFilter").forEach(chk => {
        chk.addEventListener("change", () => {
            mealSelectedValues = Array.from(
                document.querySelectorAll(".chkMealFilter:checked")
            ).map(c => c.value.toLowerCase());
            applyTableFilters();
        });
    });

    document.querySelectorAll(".chkStatusFilter").forEach(chk => {
        chk.addEventListener("change", () => {
            statusSelectedValues = Array.from(
                document.querySelectorAll(".chkStatusFilter:checked")
            ).map(c => c.value.toUpperCase());
            applyTableFilters();
        });
    });


    // applico subito eventuali filtri già impostati
    applyTableFilters();

    // abilita bottoni che dipendono dai dati
    const btnOpenAll = document.getElementById("btnOpenAllChats");
    if (btnOpenAll) btnOpenAll.disabled = false;
}



async function openChatAndCopyMessage(index, event) {
    if (event) event.preventDefault();
    if (!currentData || !currentData[index]) return;

    const btn = document.getElementById(`btnChat_${index}`);
    if (btn && btn.dataset.busy === "1") return;
    if (btn) btn.dataset.busy = "1";

    try {
        const rec = currentData[index];
        if (!rec.telefono_wa) {
            ui.toast("Manca il numero di telefono: nessuna chat aperta.", "warning");
            return;
        }
        const mancanti = missingFields(rec);
        if (mancanti.length) {
            const ok = await ui.confirm({
                title: "Messaggio incompleto",
                message: `Per ${rec.nome || "questa prenotazione"} manca: ${mancanti.join(", ")}. ` +
                    "Nel messaggio al cliente comparirebbe «?». Correggi la riga in tabella oppure apri comunque.",
                details: [rec.messaggio || ""],
                confirmLabel: "Apri comunque",
                danger: true,
            });
            if (!ok) return;
        }

        // 1) app WhatsApp Desktop; se non c'è, link wa.me nel browser
        let opened = false;
        let how = "";
        if (hasApi()) {
            try {
                const res = await window.pywebview.api.apri_whatsapp_app(rec.telefono_wa, rec.messaggio || "");
                opened = !!(res && res.ok);
                if (!opened) how = res && res.reason === "not_installed" ? "not_installed" : "error";
            } catch (e) {
                console.error(e);
                how = "error";
            }
        }
        if (!opened && rec.link_whatsapp && rec.link_whatsapp !== "#") {
            const w = window.open(rec.link_whatsapp, "_blank");
            opened = !!w;
            if (opened && how === "not_installed") {
                ui.toast("WhatsApp Desktop non è installato: chat aperta nel browser (WhatsApp Web).", "info");
            }
        }

        if (!opened) {
            ui.toast(`Chat con ${rec.nome || "il cliente"} NON aperta: WhatsApp non risponde. La riga non è segnata come aperta.`, "error");
            return;
        }

        // 2) copia del messaggio, come promemoria (non blocca)
        if (rec.messaggio && navigator.clipboard) {
            navigator.clipboard.writeText(rec.messaggio).catch(() => {});
        }

        rec.chatOpened = true;
        setTableDirty(true);
        if (btn) {
            btn.classList.add("btn-chat-sent");
            btn.textContent = "Aperta";
        }
        updateSummary();

    } finally {
        if (btn) btn.dataset.busy = "0";
    }
}


const btnLoad = document.getElementById("btnLoad");
if (btnLoad) {
    btnLoad.onclick = async () => {
        let res = "";
        try {
            res = await window.pywebview.api.scegli_file();
        } catch (e) {
            console.error(e);
            ui.toast("Impossibile aprire la finestra di scelta del file.", "error");
            return;
        }
        if (res && res !== "") {
            pdfPath = res;
            const fileName = res.split(/[/\\]/).pop();
            document.getElementById("status").textContent = "File selezionato: " + fileName;

            const sbFile = document.getElementById("sbFile");
            const dotFile = document.getElementById("dotFile");
            if (sbFile) sbFile.textContent = "File: " + fileName;
            if (dotFile) dotFile.classList.add("green");

            addRecentPdf(res);
            setOpenFileEnabled(true);
        } else {
            document.getElementById("status").textContent = "Operazione annullata";
        }
    };
}

const btnProcess = document.getElementById("btnProcess");
if (btnProcess) {
    btnProcess.onclick = async () => {
        if (!pdfPath) {
            ui.toast("Seleziona prima un file con «Carica file».", "warning");
            return;
        }
        if (btnProcess.dataset.busy === "1") return;   // niente doppia elaborazione (costa)
        if (!(await confirmDiscardTable())) return;

        // Il giorno passato al backend è SOLO quello del select "daySelect"
        const sel = document.getElementById("daySelect").value;
        const selectedDay = sel || null;

        btnProcess.dataset.busy = "1";
        btnProcess.disabled = true;
        const prevData = currentData;
        setStatus("Elaborazione in corso…");
        showOutputState("loading", "Lettura del file e riconoscimento delle prenotazioni in corso…");

        try {
            const result = await window.pywebview.api.processa_pdf(pdfPath, selectedDay);
            setTableDirty(false);
            animateNextRender = true;
            renderTable(result);
            setStatus(result && result.length
                ? `Elaborazione completata: ${result.length} prenotazioni.`
                : "Elaborazione completata: nel file non ci sono prenotazioni.");
        } catch (err) {
            console.warn(err);
            const msg = friendlyError(err);
            setStatus("Elaborazione non riuscita.");
            // la tabella precedente non va persa per un errore
            if (prevData && prevData.length) {
                renderTable(prevData);
                ui.toast(msg + " La tabella precedente è rimasta invariata.", "error");
            } else {
                showOutputState("error", msg);
            }
        } finally {
            btnProcess.dataset.busy = "0";
            btnProcess.disabled = false;
        }
    };
}

// Messaggio d'errore leggibile da un'eccezione arrivata da Python
function friendlyError(err) {
    let raw = (err && err.message) ? err.message : String(err);
    if (raw.includes("invalid_api_key") || raw.includes("Incorrect API key")) {
        return "Chiave ChatGPT non valida. Aggiornala da Impostazioni → Cambia chiave ChatGPT.";
    }
    if (/APIConnectionError|Connection error|getaddrinfo|ConnectError/i.test(raw)) {
        return "Impossibile contattare ChatGPT: controlla la connessione a internet e riprova.";
    }
    if (/insufficient_quota|RateLimit/i.test(raw)) {
        return "ChatGPT ha rifiutato la richiesta (credito esaurito o troppe richieste). Riprova più tardi.";
    }
    return raw.replace(/^Error:\s*/, "");
}

// Stati della tabella: loading / error / empty
function showOutputState(kind, message) {
    const out = document.getElementById("output");
    if (!out) return;
    out.innerHTML = "";
    const div = document.createElement("div");
    div.className = `output-empty output-${kind}`;
    if (kind === "loading") {
        const sp = document.createElement("span");
        sp.className = "spinner";
        div.appendChild(sp);
    }
    const t = document.createElement("span");
    t.textContent = message;
    div.appendChild(t);
    out.appendChild(div);
}


if (btnExportHtml) {
    btnExportHtml.onclick = async () => {
        const statusEl = document.getElementById("status");

        if (!currentData || currentData.length === 0) {
            statusEl.textContent = "Non ci sono prenotazioni da esportare";
            return;
        }

        try {
            // Passiamo TUTTE le modifiche fatte lato GUI al backend
            const payload = JSON.stringify(currentData);
            const msg = await window.pywebview.api.esporta_html(payload);
            statusEl.textContent = msg || "HTML esportato/aperto nel browser";
        } catch (err) {
            console.error(err);
            ui.toast("Errore durante l'esportazione dell'HTML: " + friendlyError(err), "error");
        }
    };
}

// Dopo una modifica il messaggio cambia: la riga torna «da aprire».
async function updateRowMeal(index, newPasto) {
    if (!currentData || !currentData[index]) return;
    const rec = currentData[index];
    rec.chatOpened = false;
    setTableDirty(true);
    const standard = ["pranzo", "cena", "aperitivo"];
    if (standard.includes(newPasto) || !newPasto) {
        // scelta standard o «auto»: l'esperienza personalizzata di questa riga non vale più
        delete rec.pasto_personalizzato;
        rec.pasto = newPasto || null;
    }
    await recalcAllAndRender();
}

async function updateRowName(index, newName) {
    if (!currentData || !currentData[index]) return;
    const rec = currentData[index];
    rec.chatOpened = false;
    setTableDirty(true);
    rec.nome = newName || "";
    await recalcAllAndRender();
}

async function updateRowPhone(index, newPhone) {
    if (!currentData || !currentData[index]) return;
    const rec = currentData[index];
    rec.chatOpened = false;
    setTableDirty(true);
    // La normalizzazione (+39 ai cellulari senza prefisso, 00 → +) è fatta SOLO dal backend
    rec.telefono = (newPhone || "").trim();
    rec.telefono_wa = "";
    await recalcAllAndRender();
}

function closeAllFilterBoxes() {
    document.querySelectorAll(".filter-box.open")
        .forEach(b => b.classList.remove("open"));
}

let filterBoxClickListenerInitialized = false;

function ensureFilterBoxGlobalClickListener() {
    if (filterBoxClickListenerInitialized) return;
    filterBoxClickListenerInitialized = true;

    document.addEventListener("click", () => {
        document.querySelectorAll(".filter-box.open")
            .forEach(b => b.classList.remove("open"));
    });
}

function applyTableFilters() {
    const table = document.querySelector("#output table");
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    // Trova indici colonne dinamicamente dall’header
    const ths = Array.from(table.querySelectorAll("thead th"));
    let pastoIdx = -1;
    let statoIdx = -1;
    ths.forEach((th, i) => {
        const span = th.querySelector("span");
        const text = (span ? span.textContent : th.textContent).trim().toLowerCase();
        if (text === "pasto") pastoIdx = i;
        if (text === "stato") statoIdx = i;
    });

    const rows = tbody.querySelectorAll("tr");
    const mealActive = mealSelectedValues;
    const statusActive = statusSelectedValues;

    rows.forEach(row => {
        let visible = true;

        // Con un filtro attivo, le righe SENZA valore sono escluse: altrimenti
        // «Apri tutte le chat» con filtro «cena» includerebbe anche le righe senza pasto.
        if (pastoIdx >= 0 && mealActive && mealActive.length > 0) {
            const pastoCell = row.children[pastoIdx];
            const select = pastoCell ? pastoCell.querySelector("select") : null;
            const pastoVal = (select?.value || "").trim().toLowerCase();
            if (!mealActive.includes(pastoVal)) visible = false;
        }

        if (statoIdx >= 0 && statusActive && statusActive.length > 0) {
            const statoCell = row.children[statoIdx];
            const statoVal = (statoCell?.textContent || "").trim().toUpperCase();
            if (!statusActive.includes(statoVal)) visible = false;
        }

        row.style.display = visible ? "" : "none";
    });

    // icona del filtro accesa quando il filtro è attivo
    const mealBtn = table.querySelector('[data-target="mealFilterBox"]');
    const statusBtn = table.querySelector('[data-target="statusFilterBox"]');
    if (mealBtn) mealBtn.classList.toggle("is-active", !!(mealActive && mealActive.length));
    if (statusBtn) statusBtn.classList.toggle("is-active", !!(statusActive && statusActive.length));
}

function setStatus(message) {
    const statusEl = document.getElementById("status");
    if (statusEl) {
        statusEl.textContent = message;
    }
}

// Toggle per il menu "Impostazioni"
(function initTopMenus() {
    const buttons = document.querySelectorAll('.top-menu-toggle');
    if (!buttons.length) return;

    buttons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();

            const targetId = btn.dataset.target;
            const box = document.getElementById(targetId);
            if (!box) return;

            const isOpen = box.classList.contains("open");

            closeAllFilterBoxes();

            if (!isOpen) {
                box.classList.add("open");
            }
        });
    });
})();

// Inizializza il template in textarea leggendo il file template.txt lato backend
async function initTemplateFromBackend() {
    if (!templateInput) return;
    if (!window.pywebview || !window.pywebview.api) return;

    try {
        const tpl = await window.pywebview.api.get_template();
        if (tpl) {
            templateInput.value = tpl;
        }
    } catch (e) {
        console.error("Impossibile leggere il template dal backend:", e);
    }
}

// Barra in basso: stato vero dal backend (prima i testi erano fissi nell'HTML)
async function refreshStatusBar() {
    if (!hasApi()) return;
    try {
        const st = await window.pywebview.api.get_stato_app();
        const dotApi = document.getElementById("dotApi");
        const sbApi = document.getElementById("sbApi");
        if (sbApi) {
            sbApi.textContent = !st.api_key ? "Chiave ChatGPT non configurata"
                : st.api_key_cifrata ? "Chiave ChatGPT configurata (cifrata)" : "Chiave ChatGPT configurata";
        }
        const sbBar = document.getElementById("statusbar");
        if (sbBar && st.cartella_dati) sbBar.title = "Dati e configurazione in: " + st.cartella_dati;
        if (dotApi) {
            dotApi.classList.toggle("green", !!st.api_key);
            dotApi.classList.toggle("red", !st.api_key);
        }
        // LICENZA DISATTIVATA: gli elementi non sono più in index.html, quindi qui non succede nulla
        const sbLicense = document.getElementById("sbLicense");
        const expLabel = document.getElementById("license-expires-label");
        if (st.license_expires) {
            const [y, m, d] = st.license_expires.split("-");
            const it = d && m && y ? `${d}/${m}/${y}` : st.license_expires;
            if (sbLicense) sbLicense.textContent = "Licenza attiva fino al " + it;
            if (expLabel) expLabel.textContent = "Licenza fino al " + it;
        }
        if (st.config_warning && !refreshStatusBar.warned) {
            refreshStatusBar.warned = true;
            ui.toast(st.config_warning, "error", 15000);
        }
    } catch (e) {
        console.error("Stato app non disponibile:", e);
    }
}

async function initTemplateInfo() {
    try {
        const info = await window.pywebview.api.get_template_info();
        if (info && Array.isArray(info.fields) && info.fields.length) {
            TEMPLATE_VARS_TEXT = info.fields.map(f => "{" + f + "}").join(", ");
        }
    } catch (e) {
        console.error(e);
    }
    const help = document.getElementById("templateVarsHelp");
    if (help) help.textContent = TEMPLATE_VARS_TEXT;
}

let appInitDone = false;
function initApp() {
    if (appInitDone || !hasApi()) return;
    appInitDone = true;
    initTemplateFromBackend();
    initTemplateInfo();
    initSuperbBar();
    refreshStatusBar();
}

// Evento specifico di pywebview: viene emesso quando l'API JS è pronta
window.addEventListener("pywebviewready", initApp);
// Se l'API era già pronta prima di questo script
window.addEventListener("DOMContentLoaded", initApp);
document.addEventListener("DOMContentLoaded", () => updateSummary());
//ricalcola messaggi
async function recalcAllAndRender() {
    if (!currentData || currentData.length === 0) {
        renderTable(currentData || []);
        return;
    }

    if (!window.pywebview || !window.pywebview.api) {
        // fallback: se apri l'HTML nel browser senza app desktop
        console.warn("pywebview non disponibile: niente ricalcolo backend.");
        renderTable(currentData);
        return;
    }

    try {
        const payload = JSON.stringify(currentData);
        const enriched = await window.pywebview.api.ricalcola_messaggi(payload);
        if (Array.isArray(enriched) && enriched.length === currentData.length) {
            currentData = enriched;
        } else {
            throw new Error("Risposta del ricalcolo incompleta.");
        }
        renderTable(currentData);
    } catch (e) {
        console.error("Errore nel ricalcolo dei messaggi:", e);
        // I messaggi visibili NON corrispondono più alle modifiche: si blocca l'invio finché non si corregge
        currentData.forEach(r => { r.messaggio = ""; r.link_whatsapp = "#"; r.telefono_wa = ""; });
        renderTable(currentData);
        ui.toast("Messaggi non ricalcolati: " + friendlyError(e) +
            " Per sicurezza le chat sono disattivate finché il problema non è risolto.", "error", 12000);
        setStatus("Messaggi non aggiornati: chat disattivate.");
    }
}

async function openChangeApiKeyDialog() {
    if (!hasApi()) {
        ui.toast("Funzione disponibile solo nell'app desktop.", "warning");
        return;
    }
    openSettingsModalForApiKey();
}

async function openChangeTemplateDialog() {
    if (!hasApi()) {
        ui.toast("Funzione disponibile solo nell'app desktop.", "warning");
        return;
    }

    try {
        const corrente = await window.pywebview.api.get_template();
        openSettingsModalForTemplate(corrente || "");
    } catch (e) {
        console.error(e);
        setStatus("Impossibile leggere il template corrente dal backend.");
    }
}

function openCustomDayDialog() {
    if (!currentData || currentData.length === 0) {
        setStatus("Nessuna prenotazione da aggiornare.");
        return;
    }

    const backdrop = document.getElementById("settingsModalBackdrop");
    const titleEl = document.getElementById("settingsModalTitle");
    const descEl = document.getElementById("settingsModalDesc");
    const inputEl = document.getElementById("settingsModalInput");
    const textareaEl = document.getElementById("settingsModalTextarea");
    const confirmBtn = document.getElementById("settingsModalConfirmBtn");
    const resetRow = document.getElementById("settingsModalResetRow");
    const resetBtn = document.getElementById("settingsModalResetBtn");

    if (!backdrop || !titleEl || !descEl || !inputEl || !textareaEl || !confirmBtn) return;

    if (resetRow) resetRow.style.display = "none";
    if (resetBtn) resetBtn.onclick = null;

    // Modal in modalità "giorno personalizzato"
    titleEl.textContent = "Giorno personalizzato";
    descEl.textContent = "Imposta un giorno/descrizione da usare per tutte le prenotazioni (solo per questa sessione).";

    inputEl.style.display = "none";
    textareaEl.style.display = "block";
    textareaEl.value = "";

    textareaEl.placeholder = "es. domani, sabato 24, Natale";
    confirmBtn.textContent = "Applica a tutte";
    confirmBtn.onclick = async () => {
        const val = (textareaEl.value || "").trim();
        if (!val) {
            ui.toast("Scrivi il giorno da usare nei messaggi.", "warning");
            return;
        }

        currentData.forEach(rec => {
            rec.giorno = val;
        });
        setTableDirty(true);
        closeSettingsModal();
        await recalcAllAndRender();
        setStatus(`Giorno impostato a "${val}" per tutte le prenotazioni.`);
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}
function openNoteModal(index) {
    if (!currentData || !currentData[index]) return;

    // Le colonne note_ospiti e allergie sono nascoste in tabella: qui devono comparire
    const rec = currentData[index];
    const parts = [];
    if (rec.note) parts.push(String(rec.note));
    if (rec.note_ospiti) parts.push("Note degli ospiti: " + rec.note_ospiti);
    if (rec.allergie) parts.push("Allergie: " + rec.allergie);
    const note = parts.join("\n");
    const backdrop = document.getElementById("noteModalBackdrop");
    const textArea = document.getElementById("noteModalText");

    if (!backdrop || !textArea) return;

    textArea.value = note;
    backdrop.style.display = "block";
}

function closeNoteModal() {
    const backdrop = document.getElementById("noteModalBackdrop");
    if (backdrop) {
        backdrop.style.display = "none";
    }
}

function copyNoteFromModal() {
    const textArea = document.getElementById("noteModalText");
    if (!textArea) return;

    const raw = textArea.value || "";
    let extracted = raw;

    const t = raw.toLowerCase();

    if (t.includes("note degli ospiti:")) {
        extracted = raw.split(/note degli ospiti:/i)[1].trim();
    }
    else if (t.includes("note interne:")) {
        extracted = raw.split(/note interne:/i)[1].trim();
    }

    if (t.includes("note degli ospiti:") && t.includes("note interne:")) {
        const parts = raw.split(/\n/).map(s => s.trim());
        const ospitiLine = parts.find(p => p.toLowerCase().startsWith("note degli ospiti:"));
        if (ospitiLine) {
            extracted = ospitiLine.split(/note degli ospiti:/i)[1].trim();
        }
    }

    navigator.clipboard.writeText(extracted)
        .then(() => ui.toast("Note copiate negli appunti.", "success", 2500))
        .catch(() => ui.toast("Impossibile copiare negli appunti.", "error"));
    closeNoteModal();
}

function openCustomMealDialog() {
    if (!currentData || currentData.length === 0) {
        setStatus("Nessuna prenotazione da aggiornare.");
        return;
    }

    const backdrop = document.getElementById("settingsModalBackdrop");
    const titleEl = document.getElementById("settingsModalTitle");
    const descEl = document.getElementById("settingsModalDesc");
    const inputEl = document.getElementById("settingsModalInput");
    const textareaEl = document.getElementById("settingsModalTextarea");
    const confirmBtn = document.getElementById("settingsModalConfirmBtn");
    const resetRow = document.getElementById("settingsModalResetRow");
    const resetBtn = document.getElementById("settingsModalResetBtn");

    if (!backdrop || !titleEl || !descEl || !inputEl || !textareaEl || !confirmBtn) return;

    // 🔴 niente reset in questo modal
    if (resetRow) resetRow.style.display = "none";
    if (resetBtn) resetBtn.onclick = null;

    // Modal in modalità "esperienza personalizzata"
    titleEl.textContent = "Esperienza personalizzata";
    descEl.textContent = "Imposta il tipo di esperienza (es. pranzo, cena, aperitivo...) per tutte le prenotazioni (solo per questa sessione).";

    inputEl.style.display = "none";
    textareaEl.style.display = "block";
    textareaEl.value = "";

    textareaEl.placeholder = "es. brunch, degustazione";
    confirmBtn.textContent = "Applica a tutte";
    confirmBtn.onclick = async () => {
        const val = (textareaEl.value || "").trim();
        if (!val) {
            ui.toast("Scrivi l'esperienza da usare nei messaggi.", "warning");
            return;
        }

        // pasto_personalizzato vince sul riconoscimento automatico (prima veniva ignorato)
        currentData.forEach(rec => {
            rec.pasto_personalizzato = val;
        });
        setTableDirty(true);
        closeSettingsModal();
        await recalcAllAndRender();
        setStatus(`Esperienza impostata a "${val}" per tutte le prenotazioni.`);
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}
// ===== APRI TUTTE LE CHAT =====
(function() {
    const btn = document.getElementById("btnOpenAllChats");
    if (!btn) return;

    btn.addEventListener("click", async () => {
        if (!currentData || currentData.length === 0) return;
        if (btn.dataset.busy === "1") return;
        btn.dataset.busy = "1";
        btn.disabled = true;

        try {

            // solo le righe visibili (non filtrate)
            const visibleRows = Array.from(
                document.querySelectorAll("#output tbody tr")
            ).filter(tr => tr.style.display !== "none");

            const indices = visibleRows.map(tr => {
                const chatBtn = tr.querySelector("[id^='btnChat_']");
                if (!chatBtn) return null;
                return parseInt(chatBtn.id.replace("btnChat_", ""), 10);
            }).filter(i => i !== null && !isNaN(i));

            if (indices.length === 0) {
                ui.toast("Nessuna prenotazione visibile da aprire (controlla i filtri).", "warning");
                return;
            }
            if (!hasApi()) {
                ui.toast("Invio in blocco disponibile solo nell'app desktop.", "warning");
                return;
            }

            const incomplete = indices.filter(i => currentData[i] && currentData[i].telefono_wa &&
                !currentData[i].chatOpened && missingFields(currentData[i]).length);
            const daAprire = indices.filter(i => currentData[i] && currentData[i].telefono_wa &&
                !currentData[i].chatOpened && !missingFields(currentData[i]).length);
            const giaAperte = indices.filter(i => currentData[i] && currentData[i].chatOpened).length;
            const senzaNumero = indices.filter(i => currentData[i] && !currentData[i].telefono_wa).length;

            if (daAprire.length === 0) {
                ui.toast(incomplete.length
                    ? "Le chat rimaste hanno dati mancanti (pasto, ospiti o orario): correggile in tabella e aprile una per una."
                    : "Tutte le chat visibili sono già aperte o senza numero.", "info");
                return;
            }

            const nomi = daAprire.map(i => {
                const r = currentData[i];
                return `${r.nome || "(senza nome)"} — +${r.telefono_wa}`;
            });
            const details = nomi.slice(0, 8);
            if (nomi.length > 8) details.push(`…e altre ${nomi.length - 8}`);
            const esclusi = [];
            if (giaAperte) esclusi.push(`${giaAperte} già aperte`);
            if (senzaNumero) esclusi.push(`${senzaNumero} senza numero`);
            if (incomplete.length) esclusi.push(`${incomplete.length} con pasto, ospiti o orario mancanti (aprile una per una dopo averle corrette)`);

            const conferma = await ui.confirm({
                title: `Aprire ${daAprire.length} chat WhatsApp?`,
                message: `Si aprirà una chat alla volta, con il messaggio già scritto, per le prenotazioni visibili in tabella. ` +
                    `L'invio lo fai tu in WhatsApp.` +
                    (esclusi.length ? ` Escluse: ${esclusi.join(", ")}.` : ""),
                details,
                confirmLabel: `Apri ${daAprire.length} chat`,
            });
            if (!conferma) return;

            let aperte = 0;
            let fallite = 0;
            let interrotto = "";

            for (let i = 0; i < daAprire.length; i++) {
                const idx = daAprire[i];
                const rec = currentData[idx];
                setStatus(`Apertura chat in corso (${i + 1}/${daAprire.length})…`);

                let res = null;
                try {
                    res = await window.pywebview.api.apri_whatsapp_app(rec.telefono_wa, rec.messaggio || "");
                } catch (e) {
                    console.error(e);
                    res = { ok: false, error: String(e) };
                }

                if (res && res.ok) {
                    rec.chatOpened = true;
                    setTableDirty(true);
                    aperte++;
                    const chatBtn = document.getElementById(`btnChat_${idx}`);
                    if (chatBtn) {
                        chatBtn.classList.add("btn-chat-sent");
                        chatBtn.textContent = "Aperta";
                    }
                    updateSummary();
                } else if (res && res.reason === "not_installed") {
                    // problema di sistema: inutile continuare (né aprire N schede nel browser)
                    interrotto = "WhatsApp Desktop non è installato su questo PC. Usa «Apri chat» riga per riga (si apre WhatsApp Web).";
                    break;
                } else {
                    fallite++;
                }

                if (i < daAprire.length - 1) {
                    await new Promise(r => setTimeout(r, BULK_PAUSE_MS));
                }
            }

            // riepilogo sul risultato finale
            const parts = [`${aperte} chat aperte`];
            if (fallite) parts.push(`${fallite} non riuscite (restano da aprire)`);
            const restanti = daAprire.length - aperte - fallite;
            if (interrotto) parts.push(`invio interrotto, ${restanti} restano da aprire`);
            setStatus(parts.join(", ") + ".");
            if (interrotto) ui.toast(interrotto, "error", 12000);
            else if (fallite) ui.toast(parts.join(", ") + ".", "warning", 8000);
            else ui.toast(`${aperte} chat aperte.`, "success");
        } finally {
            btn.dataset.busy = "0";
            btn.disabled = !(currentData && currentData.length);
        }
    });
})();
const btnOpenLoadedFile = document.getElementById("btnOpenLoadedFile");

if (btnOpenLoadedFile) {
    btnOpenLoadedFile.addEventListener("click", async () => {
        try {
            const res = await window.pywebview.api.apri_file_caricato();

            if (!res?.ok) {
                setStatus(res?.error || "Impossibile aprire il file.");
            }
        } catch (e) {
            console.error(e);
            setStatus("Errore apertura file.");
        }
    });
}

// ===== SUPERB =====

async function initSuperbBar() {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
        const cfg = await window.pywebview.api.get_superb_config();
        if (cfg && cfg.has_session) {
            const bar = document.getElementById("superb-bar");
            if (bar) bar.style.display = "flex";
            const dateInput = document.getElementById("superbDateInput");
            if (dateInput && !dateInput.value) {
                dateInput.value = localISODate();
            }
        }
    } catch (e) {
        console.error("Errore init Superb:", e);
    }
}

(function() {
    const btn = document.getElementById("btnProcessSuperb");
    if (!btn) return;

    btn.addEventListener("click", async () => {
        if (btn.dataset.busy === "1") return;

        const dateInput  = document.getElementById("superbDateInput");
        const statusEl   = document.getElementById("superbStatus");
        const dateStr    = dateInput ? dateInput.value : "";

        if (!dateStr) {
            if (statusEl) statusEl.textContent = "Seleziona una data.";
            return;
        }

        if (!(await confirmDiscardTable())) return;

        btn.dataset.busy = "1";
        btn.disabled = true;
        if (statusEl) statusEl.textContent = "Scaricamento in corso…";
        const prevData = currentData;
        showOutputState("loading", "Scaricamento delle prenotazioni da Superb…");

        try {
            const sel = document.getElementById("daySelect");
            const giorno = sel ? (sel.value || null) : null;

            const result = await window.pywebview.api.processa_superb(dateStr, giorno);
            setTableDirty(false);
            animateNextRender = true;
            renderTable(result);
            setStatus(result.length ? "Prenotazioni Superb caricate." : "Superb: nessuna prenotazione per la data scelta.");
            if (statusEl) statusEl.textContent = `${result.length} prenotazioni`;
        } catch (err) {
            console.warn(err);
            const msg = friendlyError(err);
            if (statusEl) statusEl.textContent = "Errore";
            setStatus("Scaricamento da Superb non riuscito.");
            if (prevData && prevData.length) {
                renderTable(prevData);
                ui.toast(msg + " La tabella precedente è rimasta invariata.", "error");
            } else {
                showOutputState("error", msg);
            }
        } finally {
            btn.dataset.busy = "0";
            btn.disabled = false;
        }
    });
})();

function openSuperbConfigDialog() {
    const backdrop   = document.getElementById("settingsModalBackdrop");
    const titleEl    = document.getElementById("settingsModalTitle");
    const descEl     = document.getElementById("settingsModalDesc");
    const inputEl    = document.getElementById("settingsModalInput");
    const textareaEl = document.getElementById("settingsModalTextarea");
    const confirmBtn = document.getElementById("settingsModalConfirmBtn");
    const resetRow   = document.getElementById("settingsModalResetRow");
    const resetBtn   = document.getElementById("settingsModalResetBtn");

    if (!backdrop || !confirmBtn) return;

    if (resetRow) resetRow.style.display = "none";
    if (resetBtn) resetBtn.onclick = null;

    titleEl.textContent = "Configura Superb";
    descEl.textContent  = "Incolla il valore del cookie 'koa:sess' dalla pagina Superb (DevTools → Application → Cookies).";

    inputEl.style.display    = "none";
    textareaEl.style.display = "block";
    textareaEl.placeholder   = "koa:sess cookie...\n\n(opzionale) ID ristorante sulla seconda riga";
    textareaEl.value         = "";

    confirmBtn.textContent = "Salva";
    confirmBtn.onclick = async () => {
        const raw   = (textareaEl.value || "").trim();
        const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
        const session       = lines[0] || "";
        const restaurant_id = lines[1] || "";

        if (!session) {
            ui.toast("Cookie vuoto: nessuna modifica applicata.", "warning");
            return;
        }

        try {
            const res = await window.pywebview.api.set_superb_session(session, restaurant_id);
            if (res && res.ok) {
                ui.toast("Sessione Superb salvata.", "success");
                closeSettingsModal();
                // mostra la barra Superb
                const bar = document.getElementById("superb-bar");
                if (bar) bar.style.display = "flex";
                const dateInput = document.getElementById("superbDateInput");
                if (dateInput && !dateInput.value) {
                    dateInput.value = localISODate();
                }
            } else {
                ui.toast(res?.error || "Errore nel salvataggio.", "error");
            }
        } catch (e) {
            console.error(e);
            ui.toast("Errore durante il salvataggio della sessione Superb.", "error");
        }
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}

