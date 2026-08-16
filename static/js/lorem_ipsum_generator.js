document.addEventListener("DOMContentLoaded", () => {

    const generateBtn = document.getElementById("generateBtn");
    const copyBtn = document.getElementById("copyBtn");
    const downloadBtn = document.getElementById("downloadBtn");

    const output = document.getElementById("output");

    const type = document.getElementById("type");
    const count = document.getElementById("count");

    const startLorem = document.getElementById("startLorem");

    const lorem = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua Ut enim ad minim veniam quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur Excepteur sint occaecat cupidatat non proident sunt in culpa qui officia deserunt mollit anim id est laborum";

    const words = lorem.split(" ");

    generateBtn.addEventListener("click", generateText);

    function randomWord() {

        return words[Math.floor(Math.random() * words.length)];

    }

    function generateSentence() {

        let length = Math.floor(Math.random() * 12) + 8;

        let sentence = [];

        for (let i = 0; i < length; i++) {

            sentence.push(randomWord());

        }

        let result = sentence.join(" ");

        result = result.charAt(0).toUpperCase() + result.slice(1);

        return result + ".";

    }

    function generateParagraph() {

        let paragraph = [];

        let sentenceCount = Math.floor(Math.random() * 4) + 4;

        for (let i = 0; i < sentenceCount; i++) {

            paragraph.push(generateSentence());

        }

        return paragraph.join(" ");

    }

    function generateText() {

        let result = "";

        let qty = parseInt(count.value);

        if (qty < 1) qty = 1;

        if (qty > 100) qty = 100;

        if (type.value === "words") {

            let arr = [];

            for (let i = 0; i < qty; i++) {

                arr.push(randomWord());

            }

            result = arr.join(" ");

        }

        else if (type.value === "sentences") {

            let arr = [];

            for (let i = 0; i < qty; i++) {

                arr.push(generateSentence());

            }

            result = arr.join(" ");

        }

        else {

            let arr = [];

            for (let i = 0; i < qty; i++) {

                arr.push(generateParagraph());

            }

            result = arr.join("\n\n");

        }

        if (startLorem.checked) {

            result = "Lorem ipsum " + result;

        }

        output.value = result;

    }

    copyBtn.addEventListener("click", () => {

        if (!output.value) return;

        navigator.clipboard.writeText(output.value);

        copyBtn.innerHTML =
            '<i class="fa-solid fa-check"></i> Copied';

        setTimeout(() => {

            copyBtn.innerHTML =
                '<i class="fa-solid fa-copy"></i> Copy';

        }, 1500);

    });

    downloadBtn.addEventListener("click", () => {

        if (!output.value) return;

        const blob = new Blob([output.value], {

            type: "text/plain"

        });

        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = url;

        a.download = "lorem-ipsum.txt";

        a.click();

        URL.revokeObjectURL(url);

    });

    generateText();

});