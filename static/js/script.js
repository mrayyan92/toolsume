document.addEventListener("DOMContentLoaded", function () {

    const form = document.querySelector("form");

    if (!form) return;

    const input = document.getElementById("fileInput");
    const card = document.getElementById("fileCard");
    const name = document.getElementById("fileName");
    const size = document.getElementById("fileSize");
    const remove = document.getElementById("removeFile");
    const convertBtn = document.getElementById("convertBtn");
    const dropZone = document.getElementById("dropZone");

    const loader = document.getElementById("loader");
    const progressBar = document.getElementById("progressBar");

    // ==========================
    // FILE TOOLS ONLY
    // ==========================

    if (input) {

        function showFile(files) {

            if (!card) return;

            if (files.length > 1) {

                let totalSize = 0;

                for (const file of files) {

                    totalSize += file.size;

                }

                name.textContent = files.length + " Files Selected";

                size.textContent =
                    (totalSize / 1024 / 1024).toFixed(2) + " MB";

            }

            else {

                name.textContent = files[0].name;

                size.textContent =
                    (files[0].size / 1024 / 1024).toFixed(2) + " MB";

            }

            card.style.display = "flex";

            if (convertBtn) {

                convertBtn.disabled = false;
                convertBtn.classList.add("active");

            }

        }

        input.addEventListener("change", function () {

            if (this.files.length > 0) {

                showFile(this.files);

            }

        });

        if (remove) {

            remove.addEventListener("click", function () {

                input.value = "";

                if (card)
                    card.style.display = "none";

                if (convertBtn) {

                    convertBtn.disabled = true;
                    convertBtn.classList.remove("active");

                }

            });

        }

        if (dropZone) {

            dropZone.addEventListener("dragover", function (e) {

                e.preventDefault();

                dropZone.classList.add("drag-over");

            });

            dropZone.addEventListener("dragleave", function () {

                dropZone.classList.remove("drag-over");

            });

            dropZone.addEventListener("drop", function (e) {

                e.preventDefault();

                dropZone.classList.remove("drag-over");

                if (e.dataTransfer.files.length > 0) {

                    input.files = e.dataTransfer.files;

                    showFile(e.dataTransfer.files);

                }

            });

        }

    }

    // ==========================
    // UNIVERSAL AJAX SUBMIT
    // ==========================

    form.addEventListener("submit", async function (e) {

        if (form.dataset.customHandler === "true") return;

        e.preventDefault();

        if (input && input.files.length === 0) {

            alert("Please select a file first.");

            return;

        }

        if (loader)
            loader.style.display = "flex";

        if (progressBar)
            progressBar.style.width = "20%";

        const formData = new FormData(form);

        try {

            const response = await fetch(form.action, {

                method: "POST",

                body: formData

            });

            if (!response.ok) {

                // Surface the server's actual message instead of a generic one.
                let serverMessage = "";

                try {

                    const errBody = await response.clone().json();

                    if (errBody && errBody.message)
                        serverMessage = errBody.message;

                }
                catch (ignored) { /* response was not JSON */ }

                if (!serverMessage) {

                    if (response.status === 413)
                        serverMessage = "File is too large. Maximum upload size is 100 MB.";
                    else
                        serverMessage = "Server error (" + response.status + "). Please try again.";

                }

                throw new Error(serverMessage);

            }

            if (progressBar)
                progressBar.style.width = "70%";

            const contentType = response.headers.get("content-type");

            // ==========================
            // JSON RESPONSE
            // ==========================

            if (contentType && contentType.includes("application/json")) {

                const data = await response.json();

                if (data.success) {

    if (progressBar)
        progressBar.style.width = "100%";

    setTimeout(function () {

        if (loader)
            loader.style.display = "none";

        if (progressBar)
            progressBar.style.width = "0%";

        if (data.download_url) {

            window.location.href = data.download_url;

        }

        else if (data.message) {

            alert("QR Code Content:\n\n" + data.message);

        }

    }, 500);



                }

                else {

                    if (loader)
                        loader.style.display = "none";

                    if (progressBar)
                        progressBar.style.width = "0%";

                    alert(data.message || "Operation failed.");

                }

            }

            // ==========================
            // FILE DOWNLOAD RESPONSE
            // ==========================

            else {

                const blob = await response.blob();

                const url = window.URL.createObjectURL(blob);

                const a = document.createElement("a");

                a.href = url;

                const disposition = response.headers.get("Content-Disposition");

                let filename = "download";

                if (disposition) {

                    // Prefer RFC 5987 filename*=UTF-8''... when present.
                    const extended = disposition.match(/filename\*=UTF-8''([^;]+)/i);

                    if (extended) {

                        try {
                            filename = decodeURIComponent(extended[1]);
                        }
                        catch (ignored) {
                            filename = extended[1];
                        }

                    }
                    else {

                        const plain = disposition.match(/filename="?([^\";]+)"?/i);

                        if (plain)
                            filename = plain[1].trim();

                    }

                }

                a.download = filename;

                document.body.appendChild(a);

                a.click();

                a.remove();

                window.URL.revokeObjectURL(url);

                if (loader)
                    loader.style.display = "none";

                if (progressBar)
                    progressBar.style.width = "0%";

            }

        }

        catch (error) {

            console.error(error);

            if (loader)
                loader.style.display = "none";

            if (progressBar)
                progressBar.style.width = "0%";

            alert(
                (error && error.message)
                    ? error.message
                    : "Something went wrong. Please try again."
            );

        }

    });

});

