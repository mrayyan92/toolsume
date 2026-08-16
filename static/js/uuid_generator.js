document.addEventListener("DOMContentLoaded", () => {

    const generateBtn = document.getElementById("generateBtn");
    const copyAllBtn = document.getElementById("copyAllBtn");
    const downloadBtn = document.getElementById("downloadBtn");

    const uuidCount = document.getElementById("uuidCount");

    const uuidContainer = document.getElementById("uuidContainer");

    const template = document.getElementById("uuidTemplate");

    // ==========================
    // Generate UUIDs
    // ==========================

    generateBtn.addEventListener("click", generateUUIDs);

    function generateUUIDs() {

        uuidContainer.innerHTML = "";

        const count = parseInt(uuidCount.value);

        for (let i = 0; i < count; i++) {

            const uuid = crypto.randomUUID
                ? crypto.randomUUID()
                : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                });

            const clone = template.content.cloneNode(true);

            const input = clone.querySelector(".uuid-output");

            const button = clone.querySelector(".copy-single");

            input.value = uuid;

            button.addEventListener("click", () => {

                navigator.clipboard.writeText(uuid);

                button.innerHTML =
                    '<i class="fa-solid fa-check"></i> Copied';

                setTimeout(() => {

                    button.innerHTML =
                        '<i class="fa-solid fa-copy"></i> Copy';

                }, 1500);

            });

            uuidContainer.appendChild(clone);

        }

    }

    // ==========================
    // Copy All
    // ==========================

    copyAllBtn.addEventListener("click", () => {

        const uuids = [];

        document.querySelectorAll(".uuid-output").forEach(input => {

            uuids.push(input.value);

        });

        if (uuids.length === 0) return;

        navigator.clipboard.writeText(uuids.join("\n"));

        copyAllBtn.innerHTML =
            '<i class="fa-solid fa-check"></i> Copied';

        setTimeout(() => {

            copyAllBtn.innerHTML =
                '<i class="fa-solid fa-copy"></i> Copy All';

        }, 1500);

    });

    // ==========================
    // Download TXT
    // ==========================

    downloadBtn.addEventListener("click", () => {

        const uuids = [];

        document.querySelectorAll(".uuid-output").forEach(input => {

            uuids.push(input.value);

        });

        if (uuids.length === 0) return;

        const blob = new Blob(

            [uuids.join("\n")],

            {

                type: "text/plain"

            }

        );

        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = url;

        a.download = "uuids.txt";

        a.click();

        URL.revokeObjectURL(url);

    });

    // Generate one UUID when page loads

    generateUUIDs();

});