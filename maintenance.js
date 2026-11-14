"use strict";
(() => {
    if (location.pathname === "/m.html") return;

    let checking = false;
    const check = async () => {
        if (checking) return;
        checking = true;
        try {
            const response = await fetch("/api/maintenance", {cache: "no-store"});
            if (!response.ok) return;
            const state = await response.json();
            if (state.active) {
                const returnPath = location.pathname + location.search + location.hash;
                location.replace("/m.html?return=" + encodeURIComponent(returnPath));
            }
        } catch (_) {
            // A brief connection failure during a restart is expected.
        } finally {
            checking = false;
        }
    };

    check();
    window.setInterval(check, 1500);
})();
