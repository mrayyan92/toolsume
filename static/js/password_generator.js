document.addEventListener("DOMContentLoaded", () => {

    const output = document.getElementById("passwordOutput");

    const generateBtn = document.getElementById("generateBtn");

    const copyBtn = document.getElementById("copyBtn");

    const lengthSlider = document.getElementById("length");

    const lengthValue = document.getElementById("lengthValue");

    const uppercase = document.getElementById("uppercase");

    const lowercase = document.getElementById("lowercase");

    const numbers = document.getElementById("numbers");

    const symbols = document.getElementById("symbols");

    const strengthFill = document.getElementById("strengthFill");

    const strengthText = document.getElementById("strengthText");



    const upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

    const lower = "abcdefghijklmnopqrstuvwxyz";

    const nums = "0123456789";

    const sym = "!@#$%^&*()_-+=<>?/{}[]";



    lengthSlider.addEventListener("input", () => {

        lengthValue.textContent = lengthSlider.value;

    });



    function secureRandom(max) {
        const array = new Uint32Array(1);
        crypto.getRandomValues(array);
        return array[0] % max;
    }

    function generatePassword() {

        let chars = "";

        if (uppercase.checked)
            chars += upper;

        if (lowercase.checked)
            chars += lower;

        if (numbers.checked)
            chars += nums;

        if (symbols.checked)
            chars += sym;

        if (chars.length === 0) {
            alert("Please select at least one character type.");
            return;
        }

        let password = "";

        for (let i = 0; i < lengthSlider.value; i++) {
            password += chars.charAt(secureRandom(chars.length));
        }



        output.value = password;



        updateStrength(password);

    }



    function updateStrength(password) {

        let score = 0;



        if (password.length >= 8)

            score++;



        if (password.length >= 12)

            score++;



        if (/[A-Z]/.test(password))

            score++;



        if (/[a-z]/.test(password))

            score++;



        if (/[0-9]/.test(password))

            score++;



        if (/[^A-Za-z0-9]/.test(password))

            score++;



        if (score <= 2) {

            strengthFill.style.width = "30%";

            strengthFill.style.background = "#ef4444";

            strengthText.textContent = "Weak";

        }

        else if (score <= 4) {

            strengthFill.style.width = "65%";

            strengthFill.style.background = "#f59e0b";

            strengthText.textContent = "Medium";

        }

        else {

            strengthFill.style.width = "100%";

            strengthFill.style.background = "#22c55e";

            strengthText.textContent = "Strong";

        }

    }



    generateBtn.addEventListener("click", generatePassword);



    copyBtn.addEventListener("click", () => {

        if (!output.value)

            return;



        navigator.clipboard.writeText(output.value);



        copyBtn.innerHTML =

            '<i class="fa-solid fa-check"></i> Copied';



        setTimeout(() => {

            copyBtn.innerHTML =

                '<i class="fa-solid fa-copy"></i> Copy';

        }, 1500);

    });



    generatePassword();

});