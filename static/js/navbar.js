/* TOOLHUB FINAL MOBILE NAVBAR */
(function () {
    "use strict";

    function initToolHubNavbar() {
        const navbar = document.getElementById("navbar");
        const hamburger = document.getElementById("hamburger");
        const navLinks = document.getElementById("navLinks");
        if (!navbar || !hamburger || !navLinks) return;
        if (navbar.dataset.finalNavReady === "1") return;
        navbar.dataset.finalNavReady = "1";

        const dropdowns = Array.from(
            navbar.querySelectorAll("#navLinks > .nav-item.dropdown")
        );

        function setSubmenu(dropdown, open) {
            const menu = dropdown.querySelector(":scope > .mega-menu");
            const trigger = dropdown.querySelector(":scope > a");
            dropdown.classList.toggle("open", open);

            if (trigger) {
                trigger.setAttribute("aria-expanded", open ? "true" : "false");
            }

            if (menu && window.innerWidth <= 992) {
                menu.style.display = open ? "flex" : "none";
                menu.style.visibility = open ? "visible" : "hidden";
                menu.style.opacity = open ? "1" : "0";
                menu.style.position = "static";
                menu.style.width = "100%";
                menu.style.height = "auto";
                menu.style.maxHeight = "none";
                menu.style.overflow = "visible";
            }
        }

        function closeDropdowns(except) {
            dropdowns.forEach(function (dropdown) {
                if (dropdown !== except) setSubmenu(dropdown, false);
            });
        }

        function closeMobileMenu() {
            navLinks.classList.remove("active");
            hamburger.classList.remove("active");
            hamburger.setAttribute("aria-expanded", "false");
            dropdowns.forEach(function (dropdown) {
                setSubmenu(dropdown, false);
            });
        }

        hamburger.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();

            const open = !navLinks.classList.contains("active");
            navLinks.classList.toggle("active", open);
            hamburger.classList.toggle("active", open);
            hamburger.setAttribute("aria-expanded", open ? "true" : "false");

            if (!open) closeDropdowns(null);
        });

        dropdowns.forEach(function (dropdown) {
            const trigger = dropdown.querySelector(":scope > a");
            if (!trigger) return;

            trigger.addEventListener("click", function (event) {
                if (window.innerWidth > 992) return;
                event.preventDefault();
                event.stopPropagation();

                const open = !dropdown.classList.contains("open");
                closeDropdowns(dropdown);
                setSubmenu(dropdown, open);

                navLinks.classList.add("active");
                hamburger.classList.add("active");
                hamburger.setAttribute("aria-expanded", "true");
            });
        });

        navLinks.querySelectorAll("a").forEach(function (link) {
            if (link.classList.contains("dropdown-trigger")) return;
            link.addEventListener("click", function () {
                if (window.innerWidth <= 992) closeMobileMenu();
            });
        });

        document.addEventListener("click", function (event) {
            if (!navbar.contains(event.target)) closeMobileMenu();
        });

        window.addEventListener("resize", function () {
            if (window.innerWidth > 992) {
                navLinks.classList.remove("active");
                hamburger.classList.remove("active");
                hamburger.setAttribute("aria-expanded", "false");
                dropdowns.forEach(function (dropdown) {
                    const menu = dropdown.querySelector(":scope > .mega-menu");
                    dropdown.classList.remove("open");
                    if (menu) {
                        menu.style.display = "";
                        menu.style.visibility = "";
                        menu.style.opacity = "";
                        menu.style.position = "";
                        menu.style.width = "";
                        menu.style.height = "";
                        menu.style.maxHeight = "";
                        menu.style.overflow = "";
                    }
                });
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initToolHubNavbar);
    } else {
        initToolHubNavbar();
    }
})();
