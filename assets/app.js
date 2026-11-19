let pdfPath = null;
let currentData = [];
let recentPdfs = [];
let mealSelectedValues = null;
let statusSelectedValues = null;

const btnExportHtml = document.getElementById("btnExportHtml");

const templateInput = document.getElementById("templateInput");
const btnApplyTemplate = document.getElementById("btnApplyTemplate");
const templateBox = document.getElementById("templateBox");

let settingsModalMode = null;

function openSettingsModalForApiKey() {
    settingsModalMode = "apiKey";

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
    descEl.textContent  = "Inserisci la nuova chiave ChatGPT. Verrà usata dal prossimo riavvio.";

    inputEl.value = "";
    inputEl.style.display    = "block";
    textareaEl.style.display = "none";

    // 👉 qui il bottone reset NON si vede e non fa nulla
    if (resetRow) resetRow.style.display = "none";
    if (resetBtn) resetBtn.onclick = null;

    confirmBtn.onclick = async () => {
        const nuova = (inputEl.value || "").trim();
        if (!nuova) {
            setStatus("Chiave vuota: nessuna modifica applicata.");
            closeSettingsModal();
            return;
        }

        try {
            const msg = await window.pywebview.api.set_api_key(nuova);
            setStatus(msg || "Chiave ChatGPT salvata.");
        } catch (e) {
            console.error(e);
            setStatus("Errore nel salvataggio della chiave ChatGPT.");
        }
        closeSettingsModal();
    };

    backdrop.style.display = "block";
    inputEl.focus();
}


function openSettingsModalForTemplate(corrente) {
    settingsModalMode = "template";

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
    descEl.textContent  = "Puoi usare queste variabili: {nome}, {giorno}, {pasto}, {ospiti}, {orario}";

    inputEl.style.display    = "none";
    textareaEl.style.display = "block";
    textareaEl.value         = corrente || "";

    // 👉 QUI SI VEDE IL BOTTONE
    if (resetRow) resetRow.style.display = "block";

    if (resetBtn) {
        resetBtn.onclick = async () => {
            try {
                const msg = await window.pywebview.api.reset_template();
                setStatus(msg || "Template ripristinato.");

                // ricarico template di default nel modal e nel box runtime
                const tpl = await window.pywebview.api.get_template();
                if (textareaEl)   textareaEl.value   = tpl || "";
                if (templateInput) templateInput.value = tpl || "";

                if (currentData && currentData.length > 0) {
                    await recalcAllAndRender();
                }
            } catch (e) {
                console.error(e);
                setStatus("Errore durante il ripristino del template.");
            }
        };
    }

    confirmBtn.onclick = async () => {
        const nuovo = (textareaEl.value || "").trim();
        if (!nuovo) {
            setStatus("Template vuoto: nessuna modifica applicata.");
            closeSettingsModal();
            return;
        }

        try {
            const msg = await window.pywebview.api.set_template(nuovo);
            setStatus(msg || "Template aggiornato.");
        } catch (e) {
            console.error(e);
            setStatus("Errore durante l'aggiornamento del template predefinito.");
            closeSettingsModal();
            return;
        }

        if (templateInput) {
            templateInput.value = nuovo;
        }

        if (currentData && currentData.length > 0) {
            await recalcAllAndRender();
        }

        closeSettingsModal();
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}

function closeSettingsModal() {
    const backdrop = document.getElementById("settingsModalBackdrop");
    if (backdrop) {
        backdrop.style.display = "none";
    }
    settingsModalMode = null;
}

if (btnApplyTemplate && templateInput) {
    btnApplyTemplate.addEventListener("click", async () => {
        const statusEl = document.getElementById("status");
        const txt = templateInput.value.trim();
        if (!txt) {
            statusEl.textContent = "Il template non può essere vuoto";
            return;
        }

        try {
            // 👉 Template SOLO di sessione: non tocca template.txt
            await window.pywebview.api.set_runtime_template(txt);

            if (currentData && currentData.length > 0) {
                await recalcAllAndRender();
            }

            statusEl.textContent = "Template di sessione aggiornato e applicato alle prenotazioni";
        } catch (e) {
            console.error(e);
            statusEl.textContent = "Errore durante l'aggiornamento del template di sessione.";
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
        box.innerHTML = "";
        return;
    }

    box.innerHTML = recentPdfs.map((p, idx) => {
        const name = escapeHtml(p.split(/[/\\]/).pop());
        return `<button type="button" onclick="selectRecentPdf(${idx})" title="${escapeHtml(p)}">
            <svg viewBox="0 0 24 24" style="width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2;flex-shrink:0"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            ${name}
        </button>`;
    }).join("");
}

// Seleziona un PDF dalla history
function selectRecentPdf(index) {
    const path = recentPdfs[index];
    if (!path) return;

    pdfPath = path;

    const statusEl = document.getElementById("status");
    if (statusEl) {
        statusEl.textContent = "PDF selezionato: " + path.split(/[/\\]/).pop();
    }

    // Per l'elaborazione automatica, scommenta:
    // document.getElementById("btnProcess").click();
}
function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
function renderTable(data) {
    const container = document.getElementById("output");
    currentData = Array.isArray(data) ? data : [];

    // nessun dato
    if (!Array.isArray(currentData) || currentData.length === 0) {
        container.textContent = "Nessuna prenotazione trovata.";

        const countEl = document.getElementById("totalCount");
        const dataLabelEl = document.getElementById("dataServizioLabel");
        if (countEl) countEl.textContent = "Prenotazioni: 0";
        if (dataLabelEl) dataLabelEl.textContent = "";

        const btnOpenAll = document.getElementById("btnOpenAllChats");
        if (btnOpenAll) btnOpenAll.disabled = true;
        return;
    }

    const countEl = document.getElementById("totalCount");
    const dataLabelEl = document.getElementById("dataServizioLabel");

    if (countEl) {
        countEl.textContent = "Prenotazioni: " + currentData.length;
    }
    if (dataLabelEl) {
        const label = (currentData[0] && currentData[0].data_servizio_label) || "";
        dataLabelEl.textContent = label || "";
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

    const mealOptionsHtml = uniqueMeals.map(v => {
        const checked = mealSelectedValues.includes(v);
        return `
            <label class="filter-option">
                <input type="checkbox" class="chkMealFilter" value="${v}" ${checked ? "checked" : ""}>
                <span>${v}</span>
            </label>`;
    }).join("");

    const statusOptionsHtml = uniqueStatus.map(v => {
        const checked = statusSelectedValues.includes(v);
        return `
            <label class="filter-option">
                <input type="checkbox" class="chkStatusFilter" value="${v}" ${checked ? "checked" : ""}>
                <span>${v}</span>
            </label>`;
    }).join("");

// Ricava colonne dal primo record o da _colonne
    const colonneDef = (currentData[0] && currentData[0]._colonne && currentData[0]._colonne.length > 0)
        ? currentData[0]._colonne
        : Object.keys(currentData[0] || {}).filter(k =>
            !["messaggio","link_whatsapp","telefono_wa","data_servizio","data_servizio_label",
              "chatOpened","giorno","_colonne"].includes(k)
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
            "allergie"
        ].includes(c)
    );

    let html = `<table><thead><tr>`;
    colonneVisibili.forEach(col => {
        const label = col.charAt(0).toUpperCase() + col.slice(1);
        if (col === "pasto") {
            html += `<th><div class="filter-header"><span>${label}</span>
                <button type="button" class="filter-toggle" data-target="mealFilterBox">▼</button></div>
                <div class="filter-box" id="mealFilterBox">${mealOptionsHtml || "<em>—</em>"}</div></th>`;
        } else if (col === "stato") {
            html += `<th><div class="filter-header"><span>${label}</span>
                <button type="button" class="filter-toggle" data-target="statusFilterBox">▼</button></div>
                <div class="filter-box" id="statusFilterBox">${statusOptionsHtml || "<em>—</em>"}</div></th>`;
        } else {
            html += `<th>${label}</th>`;
        }
    });
    html += `<th>Note</th><th>WhatsApp</th></tr></thead><tbody>`;

    currentData.forEach((r, index) => {
            const noteRaw = r.note ?? "";
            const hasNote = !!(noteRaw && String(noteRaw).trim());

            html += `<tr>`;
            colonneVisibili.forEach(col => {
                const val = r[col] ?? "";
                const valStr = escapeHtml(String(val));

                if (col === "nome") {
                    html += `<td><input type="text" value="${valStr}"
                        onchange="updateRowName(${index}, this.value)" class="td-input"></td>`;
                } else if (col === "telefono") {
                    html += `<td><input type="text" value="${escapeHtml(r.telefono_wa || valStr)}"
                        onchange="updateRowPhone(${index}, this.value)" class="td-input"></td>`;
                } else if (col === "pasto") {
                    const pasto = valStr;
                    html += `<td><select onchange="updateRowMeal(${index}, this.value)" class="td-select">
                        <option value="" ${pasto ? "" : "selected"}>auto</option>
                        <option value="pranzo" ${pasto==="pranzo"?"selected":""}>pranzo</option>
                        <option value="cena" ${pasto==="cena"?"selected":""}>cena</option>
                        <option value="aperitivo" ${pasto==="aperitivo"?"selected":""}>aperitivo</option>
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
            html += `<td><button id="btnChat_${index}" type="button"
                class="btn-chat ${r.chatOpened ? "btn-chat-sent" : ""}"
                onclick="openChatAndCopyMessage(${index}, event)">Apri chat</button></td>`;
            html += `</tr>`;
        });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;

    // aggiorna stat cards
    const statCount = document.getElementById("statCount");
    const statGuests = document.getElementById("statGuests");
    if (statCount) statCount.textContent = currentData.length;
    if (statGuests) {
        statGuests.textContent = currentData.reduce(
            (s, r) => s + Number(r.ospiti || 0),
            0
        );
    }
    // aggiorna status bar file
    const sbFile = document.getElementById("sbFile");
    const dotFile = document.getElementById("dotFile");
    if (sbFile) sbFile.textContent = currentData.length + " prenotazioni caricate";
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

        // 1) apro PRIMA WhatsApp
        if (window.pywebview && window.pywebview.api && rec.telefono_wa) {
            try {
                const res = await window.pywebview.api.apri_whatsapp_app(
                    rec.telefono_wa,
                    rec.messaggio || ""
                );

                if (!res?.ok && rec.link_whatsapp) {
                    window.open(rec.link_whatsapp, "_blank");
                }
            } catch (e) {
                if (rec.link_whatsapp) {
                    window.open(rec.link_whatsapp, "_blank");
                }
            }
        } else if (rec.link_whatsapp) {
            window.open(rec.link_whatsapp, "_blank");
        }

        // 2) copio DOPO, senza bloccare l'apertura
        if (rec.messaggio) {
            navigator.clipboard.writeText(rec.messaggio).catch(() => {});
        }

        rec.chatOpened = true;
        const statChats = document.getElementById("statChats");
        if (statChats) statChats.textContent = currentData.filter(r => r.chatOpened).length;
        if (btn) btn.classList.add("btn-chat-sent");

    } finally {
        if (btn) btn.dataset.busy = "0";
    }
}


const btnLoad = document.getElementById("btnLoad");
if (btnLoad) {
    btnLoad.onclick = async () => {
        const res = await window.pywebview.api.scegli_file();
        if (res && res !== "") {
            pdfPath = res;
            const fileName = res.split(/[/\\]/).pop();
            document.getElementById("status").textContent = "File selezionato: " + fileName;

            const sbFile = document.getElementById("sbFile");
            const dotFile = document.getElementById("dotFile");
            if (sbFile) sbFile.textContent = "File: " + fileName;
            if (dotFile) dotFile.classList.add("green");

            addRecentPdf(res);
        } else {
            document.getElementById("status").textContent = "Operazione annullata";
        }
    };
}

const btnProcess = document.getElementById("btnProcess");
if (btnProcess) {
    btnProcess.onclick = async () => {
        if (!pdfPath) {
            document.getElementById("status").textContent = "Seleziona prima un file";
            return;
        }

        // Ora il giorno passato al backend è SOLO quello del select "daySelect"
        const sel = document.getElementById("daySelect").value;
        const selectedDay = sel || null;

        document.getElementById("status").textContent = "Elaborazione in corso...";
        document.getElementById("output").innerHTML = '<div id="output-empty" style="padding:40px;text-align:center;color:#4b5563;font-size:13px;">In elaborazione...</div>';

        try {
            const result = await window.pywebview.api.processa_pdf(pdfPath, selectedDay);
            document.getElementById("status").textContent = "Elaborazione completata";
            renderTable(result);

            if (btnExportHtml) {
                btnExportHtml.disabled = false;
            }
            const btnOpenAll = document.getElementById("btnOpenAllChats");
            if (btnOpenAll) btnOpenAll.disabled = false;

        } catch (err) {
            console.error(err);
            const raw = (err && err.toString) ? err.toString() : String(err);
            let msg = raw;
            if (raw.includes("invalid_api_key") || raw.includes("Incorrect API key")) {
                msg = "Chiave ChatGPT non valida. Aggiornarla dalle impostazioni.";
            }
            document.getElementById("status").textContent = msg;
            document.getElementById("output").textContent = msg;
        }
    };
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
            statusEl.textContent = "Errore durante l'esportazione dell'HTML";
        }
    };
}

async function updateRowMeal(index, newPasto) {
    if (!currentData || !currentData[index]) return;
    currentData[index].chatOpened = false;
    const rec = currentData[index];

    rec.pasto = newPasto || null;
    await recalcAllAndRender();
}

async function updateRowName(index, newName) {
    if (!currentData || !currentData[index]) return;
    currentData[index].chatOpened = false;
    const rec = currentData[index];

    rec.nome = newName || "";
    await recalcAllAndRender();
}

function normalizePhoneInput(raw) {
    if (!raw) return "";
    const digits = raw.replace(/\D/g, "");
    if (!digits) return "";

    if (digits.length === 10 && digits.startsWith("3")) {
        return "39" + digits;
    }
    return digits;
}

async function updateRowPhone(index, newPhone) {
    if (!currentData || !currentData[index]) return;
    currentData[index].chatOpened = false;
    const rec = currentData[index];

    const norm = normalizePhoneInput(newPhone);

    rec.telefono = norm ? ("+" + norm) : "";
    rec.telefono_wa = norm;

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

        if (pastoIdx >= 0 && mealActive && mealActive.length > 0) {
            const pastoCell = row.children[pastoIdx];
            const select = pastoCell ? pastoCell.querySelector("select") : null;
            const pastoVal = (select?.value || "").trim().toLowerCase();
            if (pastoVal && !mealActive.includes(pastoVal)) visible = false;
        }

        if (statoIdx >= 0 && statusActive && statusActive.length > 0) {
            const statoCell = row.children[statoIdx];
            const statoVal = (statoCell?.textContent || "").trim().toUpperCase();
            if (statoVal && !statusActive.includes(statoVal)) visible = false;
        }

        row.style.display = visible ? "" : "none";
    });
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

// Evento specifico di pywebview: viene emesso quando l'API JS è pronta
window.addEventListener('pywebviewready', function() {
    initTemplateFromBackend();
    initSuperbBar();
});

// Fallback: se apri l'HTML nel browser senza pywebview, non esplode
window.addEventListener('DOMContentLoaded', function () {
    if (window.pywebview && window.pywebview.api) {
        initTemplateFromBackend();
    }
});
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
        currentData = Array.isArray(enriched) ? enriched : currentData;
        renderTable(currentData);
    } catch (e) {
        console.error("Errore nel ricalcolo dei messaggi:", e);
        setStatus("Errore nel ricalcolo dei messaggi WhatsApp.");
        renderTable(currentData);
    }
}

async function openChangeApiKeyDialog() {
    if (!window.pywebview || !window.pywebview.api) {
        alert("Funzione disponibile solo nell'app desktop.");
        return;
    }
    openSettingsModalForApiKey();
}

async function openChangeTemplateDialog() {
    if (!window.pywebview || !window.pywebview.api) {
        alert("Funzione disponibile solo nell'app desktop.");
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

    confirmBtn.onclick = async () => {
        const val = (textareaEl.value || "").trim();
        if (!val) {
            setStatus("Inserisci un valore per il giorno personalizzato.");
            closeSettingsModal();
            return;
        }

        currentData.forEach(rec => {
            rec.giorno = val;
        });

        await recalcAllAndRender();
        setStatus(`Giorno impostato a "${val}" per tutte le prenotazioni.`);
        closeSettingsModal();
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}
function openNoteModal(index) {
    if (!currentData || !currentData[index]) return;

    const note = currentData[index].note || "";
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

    navigator.clipboard.writeText(extracted).then(() => {
        console.log("Note copiate:", extracted);
    });
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

    confirmBtn.onclick = async () => {
        const val = (textareaEl.value || "").trim();
        if (!val) {
            setStatus("Inserisci un valore per l'esperienza.");
            closeSettingsModal();
            return;
        }

        currentData.forEach(rec => {
            rec.pasto = val;
        });

        await recalcAllAndRender();
        setStatus(`Esperienza impostata a "${val}" per tutte le prenotazioni.`);
        closeSettingsModal();
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
                setStatus("Nessuna prenotazione visibile da aprire.");
                return;
            }

            const conferma = confirm(
                `Stai per aprire ${indices.length} chat WhatsApp.\n` +
                `I messaggi verranno copiati automaticamente.\n\nContinuare?`
            );
            if (!conferma) return;

            setStatus(`Apertura chat in corso (0/${indices.length})...`);

            for (let i = 0; i < indices.length; i++) {
                const idx = indices[i];
                const rec = currentData[idx];
                if (!rec || !rec.link_whatsapp) continue;

                // copia messaggio
                if (rec.messaggio) {
                    try {
                        await navigator.clipboard.writeText(rec.messaggio);
                    } catch(e) {}
                }

                // apri via app nativa
                if (window.pywebview && window.pywebview.api && rec.telefono_wa) {
                    try {
                        await window.pywebview.api.apri_whatsapp_app(
                            rec.telefono_wa,
                            rec.messaggio || ""
                        );
                    } catch(e) {
                        if (rec.link_whatsapp) window.open(rec.link_whatsapp, "_blank");
                    }
                } else if (rec.link_whatsapp) {
                    window.open(rec.link_whatsapp, "_blank");
                }

                // marca come aperta
                rec.chatOpened = true;
                const chatBtn = document.getElementById(`btnChat_${idx}`);
                if (chatBtn) {
                    chatBtn.classList.add("btn-chat-sent");
                }

                setStatus(`Apertura chat in corso (${i+1}/${indices.length})...`);

                // pausa tra una chat e l'altra per non sovraccaricare il browser
                if (i < indices.length - 1) {
                    await new Promise(r => setTimeout(r, 800));
                }
            }

            setStatus(`✅ ${indices.length} chat aperte.`);
            const statChats = document.getElementById("statChats");
            if (statChats) statChats.textContent = currentData.filter(r => r.chatOpened).length;
                } finally {
                    btn.dataset.busy = "0";
                    btn.disabled = false;
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
                dateInput.value = new Date().toISOString().slice(0, 10);
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

        btn.dataset.busy = "1";
        btn.disabled = true;
        if (statusEl) statusEl.textContent = "Scaricamento in corso...";
        document.getElementById("output").innerHTML =
            '<div id="output-empty" style="padding:40px;text-align:center;color:#4b5563;font-size:13px;">Scaricamento da Superb...</div>';

        try {
            const sel = document.getElementById("daySelect");
            const giorno = sel ? (sel.value || null) : null;

            const result = await window.pywebview.api.processa_superb(dateStr, giorno);
            setStatus("Prenotazioni Superb caricate");
            if (statusEl) statusEl.textContent = `${result.length} prenotazioni`;
            renderTable(result);
            if (btnExportHtml) btnExportHtml.disabled = false;
        } catch (err) {
            console.error(err);
            const msg = err && err.toString ? err.toString() : String(err);
            if (statusEl) statusEl.textContent = "Errore";
            setStatus(msg);
            document.getElementById("output").textContent = msg;
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
            setStatus("Cookie vuoto: nessuna modifica applicata.");
            closeSettingsModal();
            return;
        }

        try {
            const res = await window.pywebview.api.set_superb_session(session, restaurant_id);
            if (res && res.ok) {
                setStatus("Sessione Superb salvata.");
                // mostra la barra Superb
                const bar = document.getElementById("superb-bar");
                if (bar) bar.style.display = "flex";
                const dateInput = document.getElementById("superbDateInput");
                if (dateInput && !dateInput.value) {
                    dateInput.value = new Date().toISOString().slice(0, 10);
                }
            } else {
                setStatus(res?.error || "Errore nel salvataggio.");
            }
        } catch (e) {
            console.error(e);
            setStatus("Errore durante il salvataggio della sessione Superb.");
        }
        closeSettingsModal();
    };

    backdrop.style.display = "block";
    textareaEl.focus();
}

