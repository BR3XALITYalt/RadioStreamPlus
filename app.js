"use strict";

const HAMQSL_XML_URL = "/api/solar";
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;
// HamQSL asks XML/RSS clients not to refresh more often than hourly.
const RETRY_INTERVAL_MS = 60 * 60 * 1000;
const REQUEST_TIMEOUT_MS = 15 * 1000;
const CLOCK_SETTINGS_KEY = "uvbinfobar.clockSettings";

const COLOR_CLASSES = ["good", "fair", "poor", "undefined"];

const GEOMAG_LEVELS = [
    { label: "Inactive", color: "good" },
    { label: "Very quiet", color: "good" },
    { label: "Quiet", color: "good" },
    { label: "Unsettled", color: "fair" },
    { label: "Active", color: "fair" },
    { label: "Min. storm", color: "poor" },
    { label: "Maj. storm", color: "poor" },
    { label: "Sevr. storm", color: "poor" },
    { label: "Extr. storm", color: "poor" }
];

const PROPAGATION_COLORS = {
    Good: "good",
    Fair: "fair",
    Poor: "poor"
};

let lastSuccessfulLoad = null;
let loadedData = Object.create(null);
let statusElement;
let valueElements = [];
let clockSettings;
let browserTimeZone = "UTC";

function setStatus(message, visible = true) {
    if (!statusElement) return;
    statusElement.textContent = message;
    statusElement.hidden = !visible;
}


function detectBrowserTimeZone() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch (error) {
        console.warn("Unable to detect the browser time zone:", error);
        return "UTC";
    }
}

function getDefaultClockLabel() {
    return "LOCAL";
}

function isValidTimeZone(timeZone) {
    if (typeof timeZone !== "string" || !timeZone.trim()) return false;
    try {
        new Intl.DateTimeFormat("en-US", { timeZone: timeZone.trim() });
        return true;
    } catch (error) {
        return false;
    }
}

function loadClockSettings() {
    const defaults = {
        label: getDefaultClockLabel(),
        timeZone: browserTimeZone
    };

    try {
        const saved = JSON.parse(localStorage.getItem(CLOCK_SETTINGS_KEY) || "null");
        if (saved && typeof saved === "object") {
            const label = typeof saved.label === "string" ? saved.label.trim().slice(0, 18) : "";
            const timeZone = typeof saved.timeZone === "string" ? saved.timeZone.trim() : "";
            return {
                label: label || defaults.label,
                timeZone: isValidTimeZone(timeZone) ? timeZone : defaults.timeZone
            };
        }
    } catch (error) {
        console.warn("Clock settings could not be loaded from local storage:", error);
    }

    return defaults;
}

function saveClockSettings() {
    try {
        localStorage.setItem(CLOCK_SETTINGS_KEY, JSON.stringify(clockSettings));
    } catch (error) {
        console.warn("Clock settings could not be saved to local storage:", error);
    }
}

function getDateParts(date, timeZone) {
    const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone, weekday: "short", year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.weekday} ${values.year}-${values.month}-${values.day}`;
}

function getTimeParts(date, timeZone) {
    const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.hour}:${values.minute}:${values.second}`;
}

function getUtcOffset(date, timeZone) {
    const parts = new Intl.DateTimeFormat("en", {
        timeZone, timeZoneName: "shortOffset"
    }).formatToParts(date);
    const zone = parts.find(part => part.type === "timeZoneName")?.value || "GMT";
    return zone.replace(/^GMT/, "UTC");
}

function updateClock(selector, date, timeZone) {
    const clock = document.querySelector(selector);
    if (!clock) return;

    const lines = clock.querySelectorAll("tspan");
    if (lines.length >= 2) {
        lines[0].textContent = getDateParts(date, timeZone);
        lines[1].textContent = getTimeParts(date, timeZone);
    }
}

function updateClocks() {
    const now = new Date();
    updateClock("#clock-utc .val", now, "UTC");
    updateClock("#clock-msk .val", now, clockSettings.timeZone);

    const label = document.querySelector("#clock-local-label");
    const labelText = label?.parentElement;
    const offset = document.querySelector("#clock-local-offset");
    if (label) label.textContent = clockSettings.label;
    if (offset) offset.textContent = `(${getUtcOffset(now, clockSettings.timeZone)})`;

    // Keep longer city labels clear of the date and time on the right.
    if (labelText) {
        const length = clockSettings.label.length;
        const layout = length <= 5 ? [42, 150] : length <= 8 ? [30, 165] : length <= 12 ? [24, 180] : [18, 195];
        labelText.style.fontSize = `${layout[0]}px`;
        document.querySelectorAll("#clock-msk .val tspan").forEach(line => {
            line.setAttribute("x", String(layout[1]));
        });
    }
}

function readRequiredText(xmlDocument, selector, label) {
    const element = xmlDocument.querySelector(selector);
    const value = element?.textContent?.trim();

    if (!value) {
        throw new Error(`Missing or empty XML field: ${label}`);
    }

    return value;
}

function getNoiseFloorColor(value) {
    // HamQSL normally reports ranges such as "S2-S3". Use the worse
    // (higher) end of the range, matching the original overlay's intent.
    const match = value.match(/^S(\d+)\s*-\s*S(\d+)$/i);
    if (!match) return "undefined";

    const level = Math.max(Number(match[1]), Number(match[2]));
    if (level <= 1) return "good";
    if (level === 2) return "fair";
    return "poor";
}

function parsePropagationXml(xmlText) {
    const xmlDocument = new DOMParser().parseFromString(xmlText, "application/xml");

    if (xmlDocument.querySelector("parsererror")) {
        throw new Error("HamQSL returned invalid XML");
    }

    const propDay = readRequiredText(
        xmlDocument,
        "calculatedconditions band[name='80m-40m'][time='day']",
        "80-40m daytime conditions"
    );
    const propNight = readRequiredText(
        xmlDocument,
        "calculatedconditions band[name='80m-40m'][time='night']",
        "80-40m nighttime conditions"
    );
    const noiseFloor = readRequiredText(xmlDocument, "signalnoise", "signal noise floor");
    const solarFlux = readRequiredText(xmlDocument, "solarflux", "solar flux index");
    const kIndexText = readRequiredText(xmlDocument, "kindex", "K-index");
    const kIndex = Number.parseInt(kIndexText, 10);
    const geomag = Number.isInteger(kIndex) ? GEOMAG_LEVELS[kIndex] : undefined;

    return {
        prop_day: propDay,
        prop_day_color: PROPAGATION_COLORS[propDay] || "fair",
        prop_night: propNight,
        prop_night_color: PROPAGATION_COLORS[propNight] || "fair",
        noise_floor: noiseFloor,
        noise_floor_color: getNoiseFloorColor(noiseFloor),
        sfi: solarFlux,
        geomag: geomag?.label || "Unknown",
        geomag_color: geomag?.color || "undefined"
    };
}

function updateValueElement(element) {
    const key = element.dataset.key;
    const value = element.querySelector("tspan") || element;
    const nextValue = loadedData[key] ?? "Unknown";
    const nextColor = loadedData[`${key}_color`];

    value.textContent = nextValue;

    for (const color of COLOR_CLASSES) {
        element.classList.toggle(color, color === nextColor);
    }
}

function onValueAnimationEnd(event) {
    const element = event.currentTarget;
    if (event.target !== element) return;

    if (element.classList.contains("fade-out")) {
        updateValueElement(element);
        element.classList.remove("fade-out");
        element.getAnimations().forEach(animation => animation.cancel());
        element.classList.add("fade-in");
    } else if (element.classList.contains("fade-in")) {
        element.classList.remove("fade-in");
    }
}

function displayPropagationValues(values) {
    loadedData = values;

    for (const element of valueElements) {
        // Reduced-motion mode removes the CSS animation, so update directly.
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            updateValueElement(element);
            continue;
        }

        element.classList.remove("fade-in");
        element.classList.add("fade-out");
    }
}

async function fetchPropagationData() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
        const response = await fetch(HAMQSL_XML_URL, {
            cache: "no-store",
            signal: controller.signal
        });

        if (!response.ok) {
            let detail = `HTTP ${response.status} ${response.statusText}`;
            try {
                const payload = await response.json();
                if (payload.error) detail += `: ${payload.error}`;
            } catch (_) {
                // Preserve the HTTP status when the server did not return JSON.
            }
            throw new Error(detail);
        }

        const xmlText = await response.text();
        const values = parsePropagationXml(xmlText);
        displayPropagationValues(values);

        lastSuccessfulLoad = new Date().toISOString();
        if (response.headers.get("X-RadioStream-Cache") === "stale") {
            setStatus("* using cached propagation data; the live feed is temporarily unavailable");
        } else {
            setStatus("", false);
        }
        return true;
    } catch (error) {
        const reason = error.name === "AbortError"
            ? `request timed out after ${REQUEST_TIMEOUT_MS / 1000} seconds`
            : `${error.name}: ${error.message}`;
        const lastLoadText = lastSuccessfulLoad || "never";

        console.error("Unable to update UVB-76 propagation data:", error);
        setStatus(`* loading failed; last successful load: ${lastLoadText}\n${reason}`);
        return false;
    } finally {
        window.clearTimeout(timeout);
    }
}

async function refreshPropagationData() {
    const succeeded = await fetchPropagationData();
    const nextRefresh = succeeded ? REFRESH_INTERVAL_MS : RETRY_INTERVAL_MS;

    // Schedule only after the previous request completes, so refreshes cannot overlap.
    window.setTimeout(refreshPropagationData, nextRefresh);
}


function openClockSettings() {
    const dialog = document.querySelector("#clock-settings");
    document.querySelector("#clock-label-input").value = clockSettings.label;
    document.querySelector("#clock-timezone-input").value = clockSettings.timeZone;
    document.querySelector("#clock-settings-error").textContent = "";
    dialog.hidden = false;
    document.querySelector("#clock-label-input").focus({ preventScroll: true });
}

function closeClockSettings(restoreFocus = false) {
    const dialog = document.querySelector("#clock-settings");
    if (dialog.hidden) return;
    dialog.hidden = true;
    if (restoreFocus) document.querySelector("#clock-msk")?.focus({ preventScroll: true });
}

function applyClockSettings(event) {
    event.preventDefault();

    const label = document.querySelector("#clock-label-input").value.trim().slice(0, 18);
    const timeZone = document.querySelector("#clock-timezone-input").value.trim();
    const error = document.querySelector("#clock-settings-error");

    if (!isValidTimeZone(timeZone)) {
        error.textContent = "Enter a valid IANA time zone, such as Europe/Moscow.";
        document.querySelector("#clock-timezone-input").focus({ preventScroll: true });
        return;
    }

    clockSettings = {
        label: label || getDefaultClockLabel(),
        timeZone
    };
    saveClockSettings();
    updateClocks();
    closeClockSettings(true);
}

function initializeClockSettings() {
    browserTimeZone = detectBrowserTimeZone();
    clockSettings = loadClockSettings();

    const trigger = document.querySelector("#clock-msk");
    const dialog = document.querySelector("#clock-settings");

    trigger.addEventListener("click", event => {
        event.stopPropagation();
        if (dialog.hidden) openClockSettings();
        else closeClockSettings(true);
    });

    trigger.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (dialog.hidden) openClockSettings();
            else closeClockSettings(true);
        }
    });

    document.querySelector("#clock-settings-form").addEventListener("submit", applyClockSettings);
    document.querySelector("#cancel-clock-settings").addEventListener("click", () => closeClockSettings(true));

    document.querySelector("#use-browser-time").addEventListener("click", () => {
        document.querySelector("#clock-label-input").value = getDefaultClockLabel();
        document.querySelector("#clock-timezone-input").value = browserTimeZone;
        document.querySelector("#clock-settings-error").textContent = "";
    });

    dialog.addEventListener("click", event => event.stopPropagation());
    document.addEventListener("click", event => {
        if (!dialog.hidden && !dialog.contains(event.target) && !trigger.contains(event.target)) {
            closeClockSettings();
        }
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !dialog.hidden) closeClockSettings(true);
    });
}

function setOverlayTextLines(elementId, value, x, firstY, lineHeight) {
    const element = document.getElementById(elementId);
    if (!element || typeof value !== "string") return;

    const namespace = "http://www.w3.org/2000/svg";
    const lines = value.replace(/\r\n?/g, "\n").split("\n");
    const fragment = document.createDocumentFragment();

    lines.forEach((line, index) => {
        const span = document.createElementNS(namespace, "tspan");
        span.setAttribute("x", String(x));
        span.setAttribute("y", String(firstY + index * lineHeight));
        span.textContent = line;
        fragment.appendChild(span);
    });

    element.replaceChildren(fragment);
}

async function loadOverlayMessages() {
    try {
        const response = await fetch("/api/config", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const config = payload.config || {};

        setOverlayTextLines(
            "text9615",
            config.overlay_reload_notice,
            702.64648,
            907.37019,
            32.2666
        );
        setOverlayTextLines(
            "text11484",
            config.overlay_black_notice,
            44.925781,
            931.4984,
            26.4
        );
    } catch (error) {
        // Keep the text embedded in index.html if the local config endpoint is unavailable.
        console.warn("Unable to load saved overlay messages:", error);
    }
}

function initialize() {
    statusElement = document.querySelector("#status");
    valueElements = Array.from(document.querySelectorAll("#SVGRoot .val[data-key]"));

    if (valueElements.length === 0) {
        setStatus("* inline SVG artwork was not found. Check index.html.");
        return;
    }

    for (const element of valueElements) {
        element.addEventListener("animationend", onValueAnimationEnd);
    }

    initializeClockSettings();
    loadOverlayMessages();
    updateClocks();
    window.setInterval(updateClocks, 1000);
    refreshPropagationData();
}

document.addEventListener("DOMContentLoaded", initialize, { once: true });
