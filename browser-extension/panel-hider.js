"use strict";

(() => {
    const targets = [
        {buttonId: "id-readme-hide", panelId: "id-readme"},
        {buttonId: "id-control-hide", panelId: "id-control"}
    ];
    const clicked = new Set();

    function isVisible(element) {
        if (!element || !element.isConnected) return false;
        const style = window.getComputedStyle(element);
        return style.display !== "none"
            && style.visibility !== "hidden"
            && element.getClientRects().length > 0;
    }

    function hidePanels() {
        for (const target of targets) {
            if (clicked.has(target.buttonId)) continue;

            const button = document.getElementById(target.buttonId);
            const panel = document.getElementById(target.panelId);
            if (!button || !panel || !isVisible(button) || !isVisible(panel)) continue;
            if (!(button instanceof HTMLButtonElement)) continue;
            if (!button.classList.contains("class-vis-button")) continue;

            const handler = button.getAttribute("onclick") || "";
            if (!handler.includes(`toggle_panel('${target.panelId}')`)) continue;

            clicked.add(target.buttonId);
            button.click();
        }
    }

    if (document.documentElement) {
        hidePanels();
        const observer = new MutationObserver(hidePanels);
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class", "style", "aria-hidden"],
            childList: true,
            subtree: true
        });
    }
})();
