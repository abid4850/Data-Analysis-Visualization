// ==========================
//  Theme Toggle Script
// ==========================

// Load saved theme on page load
document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("theme");

    if (savedTheme === "dark") {
        document.body.classList.add("dark-mode");
    }

    const toggleBtn = document.getElementById("darkToggle");

    toggleBtn.addEventListener("click", () => {
        document.body.classList.toggle("dark-mode");

        // Save current mode
        const mode = document.body.classList.contains("dark-mode") ? "dark" : "light";
        localStorage.setItem("theme", mode);
    });
});
