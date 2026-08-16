
document.addEventListener("DOMContentLoaded", () => {

    const textInput = document.getElementById("textInput");

    const wordCount = document.getElementById("wordCount");
    const characterCount = document.getElementById("characterCount");
    const characterNoSpace = document.getElementById("characterNoSpace");
    const sentenceCount = document.getElementById("sentenceCount");
    const paragraphCount = document.getElementById("paragraphCount");
    const readingTime = document.getElementById("readingTime");
    const speakingTime = document.getElementById("speakingTime");

    const copyBtn = document.getElementById("copyBtn");
    const clearBtn = document.getElementById("clearBtn");
    const downloadBtn = document.getElementById("downloadBtn");
 
  
function updateStats() {

    const text = textInput.value;

    const wordTotal = text.match(/\b\S+\b/g)?.length || 0;

    const characters = text.length;

    const charactersWithoutSpaces = text.replace(/\s/g, "").length;

    const sentenceTotal = text.match(/[.!?]+/g)?.length || 0;

    const paragraphTotal =
        text.trim() === ""
            ? 0
            : text.trim().split(/\n+/).filter(p => p.trim() !== "").length;

    const readingMinutes =
        wordTotal === 0 ? 0 : Math.ceil(wordTotal / 200);

    const speakingMinutes =
        wordTotal === 0 ? 0 : Math.ceil(wordTotal / 130);

    wordCount.textContent = wordTotal;
    characterCount.textContent = characters;
    characterNoSpace.textContent = charactersWithoutSpaces;
    sentenceCount.textContent = sentenceTotal;
    paragraphCount.textContent = paragraphTotal;
    readingTime.textContent = readingMinutes + " min";
    speakingTime.textContent = speakingMinutes + " min";
}


    textInput.addEventListener("input", updateStats);

    copyBtn.addEventListener("click", () => {

        if (!textInput.value) return;

        navigator.clipboard.writeText(textInput.value);

        copyBtn.innerHTML =
            '<i class="fa-solid fa-check"></i> Copied';

        setTimeout(() => {

            copyBtn.innerHTML =
                '<i class="fa-solid fa-copy"></i> Copy';

        }, 1500);

    });

    clearBtn.addEventListener("click", () => {

        textInput.value = "";

        updateStats();

    });

    downloadBtn.addEventListener("click", () => {

        if (!textInput.value) return;

        const blob = new Blob(

            [textInput.value],

            {

                type: "text/plain"

            }

        );

        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = url;

        a.download = "text.txt";

        a.click();

        URL.revokeObjectURL(url);

    });

    updateStats();

});