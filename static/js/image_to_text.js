document.addEventListener("DOMContentLoaded", function () {

    const form = document.getElementById("ocrForm");
    const input = document.getElementById("fileInput");

    const fileCard = document.getElementById("fileCard");
    const fileName = document.getElementById("fileName");
    const fileSize = document.getElementById("fileSize");

    const removeBtn = document.getElementById("removeFile");
    const convertBtn = document.getElementById("convertBtn");

    const loader = document.getElementById("loader");
    const progressBar = document.getElementById("progressBar");

    const resultCard = document.getElementById("resultCard");
    const resultBox = document.getElementById("ocrResult");

    const copyBtn = document.getElementById("copyBtn");
    const downloadBtn = document.getElementById("downloadBtn");

    function showFile(file) {

        fileCard.style.display = "flex";
        fileName.textContent = file.name;
        fileSize.textContent = (file.size / 1024 / 1024).toFixed(2) + " MB";

        convertBtn.disabled = false;
        convertBtn.classList.add("active");
    }

    input.addEventListener("change", function () {

        if (this.files.length > 0) {
            showFile(this.files[0]);
        }

    });

    removeBtn.addEventListener("click", function () {

        input.value = "";

        fileCard.style.display = "none";

        resultCard.style.display = "none";

        convertBtn.disabled = true;
        convertBtn.classList.remove("active");

    });

    form.dataset.customHandler = "true";

    form.addEventListener("submit", async function (e) {

        e.preventDefault();

        loader.style.display = "flex";
        progressBar.style.width = "30%";

        const formData = new FormData(form);

        try {

            const response = await fetch(form.action, {

                method: "POST",
                body: formData

            });

            if (!response.ok) {

                let serverMessage = "";

                try {
                    const errBody = await response.clone().json();
                    if (errBody && errBody.message) serverMessage = errBody.message;
                }
                catch (ignored) { /* not JSON */ }

                if (!serverMessage) {
                    serverMessage = response.status === 413
                        ? "Image is too large. Maximum upload size is 100 MB."
                        : "Server error (" + response.status + "). Please try again.";
                }

                throw new Error(serverMessage);

            }

            const data = await response.json();

            progressBar.style.width = "100%";

            setTimeout(() => {

                loader.style.display = "none";
                progressBar.style.width = "0%";

            }, 500);

            if (!data.success) {

                alert(data.message);
                return;

            }

            resultBox.value = data.text;

            resultCard.style.display = "block";

        }

        catch (err) {

            loader.style.display = "none";
            progressBar.style.width = "0%";

            alert((err && err.message) ? err.message : "OCR failed.");

            console.error(err);

        }

    });

    copyBtn.addEventListener("click", function () {

        navigator.clipboard.writeText(resultBox.value);

        copyBtn.innerHTML = '<i class="fa-solid fa-check"></i> Copied';

        setTimeout(function () {

            copyBtn.innerHTML = '<i class="fa-solid fa-copy"></i> Copy';

        }, 1500);

    });

    downloadBtn.addEventListener("click", function () {

        const blob = new Blob([resultBox.value], {

            type: "text/plain"

        });

        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = url;

        a.download = "ocr_text.txt";

        a.click();

        URL.revokeObjectURL(url);

    });

});