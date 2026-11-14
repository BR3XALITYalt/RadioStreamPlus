"use strict";

const HAMQSL_XML_URL = "https://www.hamqsl.com/solarxml.php";
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;
const RETRY_INTERVAL_MS = 5 * 60 * 1000;
const REQUEST_TIMEOUT_MS = 15 * 1000;
const MOSCOW_UTC_OFFSET_MS = 3 * 60 * 60 * 1000;

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
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

function setStatus(message, visible = true) {
    if (!statusElement) return;
    statusElement.textContent = message;
    statusElement.hidden = !visible;
}

function updateClock(selector, date) {
    const clock = document.querySelector(selector);
    if (!clock) return;

    const lines = clock.querySelectorAll("tspan");
    const dateText = `${WEEKDAYS[date.getUTCDay()]} ${date.toISOString().slice(0, 10)}`;
    const timeText = date.toISOString().slice(11, 19);

    if (lines.length >= 2) {
        lines[0].textContent = dateText;
        lines[1].textContent = timeText;
    } else {
        clock.textContent = `${dateText} ${timeText}`;
    }
}

function updateClocks() {
    const now = new Date();
    updateClock("#clock-utc .val", now);
    updateClock("#clock-msk .val", new Date(now.getTime() + MOSCOW_UTC_OFFSET_MS));
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
            throw new Error(`HTTP ${response.status} ${response.statusText}`);
        }

        const xmlText = await response.text();
        const values = parsePropagationXml(xmlText);
        displayPropagationValues(values);

        lastSuccessfulLoad = new Date().toISOString();
        setStatus("", false);
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

    updateClocks();
    window.setInterval(updateClocks, 1000);
    refreshPropagationData();
}

document.addEventListener("DOMContentLoaded", initialize, { once: true });
