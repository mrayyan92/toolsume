
/* =========================================================
   TOOLHUB FINAL NAVBAR DROPDOWN JS
   Replace ONLY the old navbar/dropdown JavaScript with this.
   Keep the rest of script.js unchanged.
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    const navbar = document.getElementById("navbar");
    const hamburger = document.getElementById("hamburger");
    const navLinks = document.getElementById("navLinks");

    if (!navbar || !navLinks) {
        return;
    }

    /* Mobile menu */
    if (hamburger) {
        hamburger.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();

            navLinks.classList.toggle("active");
            hamburger.classList.toggle("active");
        });
    }

    /*
       IMPORTANT:
       Only target the direct trigger of each dropdown.
       This prevents submenu links from being treated as
       dropdown buttons.
    */
    const dropdowns = navbar.querySelectorAll("#navLinks > .dropdown");

    dropdowns.forEach(function (dropdown) {

        const trigger = dropdown.querySelector(":scope > a");

        if (!trigger) {
            return;
        }

        trigger.addEventListener("click", function (e) {

            if (window.innerWidth <= 992) {

                e.preventDefault();
                e.stopPropagation();

                /* Close the other dropdowns */
                dropdowns.forEach(function (other) {
                    if (other !== dropdown) {
                        other.classList.remove("open");

                        const otherTrigger =
                            other.querySelector(":scope > a");

                        if (otherTrigger) {
                            otherTrigger.setAttribute(
                                "aria-expanded",
                                "false"
                            );
                        }
                    }
                });

                /* Open/close this dropdown */
                const opening = !dropdown.classList.contains("open");

                dropdown.classList.toggle("open", opening);

                trigger.setAttribute(
                    "aria-expanded",
                    opening ? "true" : "false"
                );
            }
        });
    });

});
