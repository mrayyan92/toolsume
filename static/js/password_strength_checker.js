document.addEventListener("DOMContentLoaded", () => {

    const passwordInput = document.getElementById("passwordInput");
    const togglePassword = document.getElementById("togglePassword");

    const strengthFill = document.getElementById("strengthFill");
    const strengthText = document.getElementById("strengthText");

    const crackTime = document.getElementById("crackTime");

    const analysisList = document.getElementById("analysisList");

    // ======================
    // SHOW / HIDE PASSWORD
    // ======================

    togglePassword.addEventListener("click", () => {

        if (passwordInput.type === "password") {

            passwordInput.type = "text";

            togglePassword.innerHTML =
                '<i class="fa-solid fa-eye-slash"></i> Hide';

        }

        else {

            passwordInput.type = "password";

            togglePassword.innerHTML =
                '<i class="fa-solid fa-eye"></i> Show';

        }

    });

    // ======================
    // LIVE CHECK
    // ======================

    passwordInput.addEventListener("input", () => {

        checkPassword(passwordInput.value);

    });

    // ======================
    // PASSWORD ANALYSIS
    // ======================

    function checkPassword(password) {

        let score = 0;

        const lengthOK = password.length >= 8;
        const upperOK = /[A-Z]/.test(password);
        const lowerOK = /[a-z]/.test(password);
        const numberOK = /[0-9]/.test(password);
        const symbolOK = /[^A-Za-z0-9]/.test(password);

        if (lengthOK) score++;
        if (upperOK) score++;
        if (lowerOK) score++;
        if (numberOK) score++;
        if (symbolOK) score++;

        analysisList.innerHTML = `

            <li>${lengthOK ? "✅" : "❌"} Minimum 8 characters</li>

            <li>${upperOK ? "✅" : "❌"} Uppercase letters</li>

            <li>${lowerOK ? "✅" : "❌"} Lowercase letters</li>

            <li>${numberOK ? "✅" : "❌"} Numbers</li>

            <li>${symbolOK ? "✅" : "❌"} Special characters</li>

        `;

        switch (score) {

            case 0:
            case 1:

                strengthFill.style.width = "20%";
                strengthFill.style.background = "#ef4444";

                strengthText.textContent = "Very Weak";

                crackTime.textContent = "A few seconds";

                break;

            case 2:

                strengthFill.style.width = "40%";
                strengthFill.style.background = "#f97316";

                strengthText.textContent = "Weak";

                crackTime.textContent = "A few minutes";

                break;

            case 3:

                strengthFill.style.width = "60%";
                strengthFill.style.background = "#facc15";

                strengthText.textContent = "Medium";

                crackTime.textContent = "Several days";

                break;

            case 4:

                strengthFill.style.width = "80%";
                strengthFill.style.background = "#22c55e";

                strengthText.textContent = "Strong";

                crackTime.textContent = "Several years";

                break;

            case 5:

                strengthFill.style.width = "100%";
                strengthFill.style.background = "#16a34a";

                strengthText.textContent = "Very Strong";

                crackTime.textContent = "Hundreds of years";

                break;

        }

        if (password.length === 0) {

            strengthFill.style.width = "0%";

            strengthText.textContent = "Start typing...";

            crackTime.textContent = "Start typing a password...";
        }

    }

});