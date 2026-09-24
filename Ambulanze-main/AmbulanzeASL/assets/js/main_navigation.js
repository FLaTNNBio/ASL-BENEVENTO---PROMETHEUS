"use strict";

(() => {

    function initMainNavigation() {

        const nav118 = document.getElementById("mainNav118");
        const navPopulation = document.getElementById("mainNavPopulationHealth");
        const planner118 = document.getElementById("planner118Area");
        const populationHealth = document.getElementById("populationHealthSection");

        if (!nav118 || !navPopulation || !planner118 || !populationHealth) {
            console.error("Main navigation: elementi DOM mancanti.");
            return;
        }

        function setArea(area) {

            const show118 = area === "118";
            planner118.hidden = !show118;
            populationHealth.hidden = show118;
            nav118.classList.toggle("is-active", show118);
            navPopulation.classList.toggle("is-active", !show118);
            nav118.setAttribute("aria-selected", String(show118));
            navPopulation.setAttribute("aria-selected", String(!show118));

            if (show118) {
                history.replaceState(null, "", "#planning-118");
            } else {
                history.replaceState(null, "", "#population-health");
            }
            window.scrollTo({top: 0, behavior: "smooth",});
        }
        nav118.addEventListener("click", () => setArea("118"));
        navPopulation.addEventListener("click", () => setArea("population-health"));
        // Permette anche URL:
        // .../#population-health
        if (window.location.hash === "#population-health") {
            setArea("population-health");
        } else {
            setArea("118");
        }
    }
    document.addEventListener("DOMContentLoaded", initMainNavigation);

})();