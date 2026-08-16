/* =========================================================
   TOOLHUB — MOBILE NAVIGATION FIX
   Replace/append this to your static/js/script.js if needed.
========================================================= */

(function () {
    "use strict";

    function initMobileNavbar() {

        const navbar = document.getElementById("navbar");
        const hamburger = document.getElementById("hamburger");
        const navLinks = document.getElementById("navLinks");

        if (!navbar || !hamburger || !navLinks) return;

        if (hamburger.dataset.mobileNavReady === "true") return;
        hamburger.dataset.mobileNavReady = "true";

        hamburger.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();

            const open = navLinks.classList.toggle("active");

            navbar.classList.toggle("mobile-open", open);
            hamburger.classList.toggle("active", open);
            hamburger.setAttribute("aria-expanded", String(open));
        });

        const dropdowns = navbar.querySelectorAll("#navLinks > .dropdown");

        dropdowns.forEach(function (dropdown) {

            const trigger = dropdown.querySelector(":scope > a");

            if (!trigger) return;

            trigger.addEventListener("click", function (event) {

                if (window.innerWidth <= 992) {

                    event.preventDefault();
                    event.stopPropagation();

                    dropdowns.forEach(function (item) {
                        if (item !== dropdown) {
                            item.classList.remove("open");
                        }
                    });

                    dropdown.classList.toggle("open");
                }
            });
        });

        navLinks.querySelectorAll("a").forEach(function (link) {

            if (link.parentElement.classList.contains("dropdown")) return;

            link.addEventListener("click", function () {
                if (window.innerWidth <= 992) {
                    navLinks.classList.remove("active");
                    navbar.classList.remove("mobile-open");
                    hamburger.classList.remove("active");
                    hamburger.setAttribute("aria-expanded", "false");
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initMobileNavbar);
    } else {
        initMobileNavbar();
    }

})();
