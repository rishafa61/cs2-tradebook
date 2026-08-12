document.addEventListener("DOMContentLoaded", function () {
    const root = document.documentElement;
    const toggle = document.getElementById("darkModeToggle");
    const saved = localStorage.getItem("tradebook-theme");

    if (saved === "dark") {
        root.setAttribute("data-bs-theme", "dark");
        toggle.textContent = "☀️ Light Mode";
    }

    toggle.addEventListener("click", function () {
        const isDark = root.getAttribute("data-bs-theme") === "dark";
        if (isDark) {
            root.setAttribute("data-bs-theme", "light");
            toggle.textContent = "🌙 Dark Mode";
            localStorage.setItem("tradebook-theme", "light");
        } else {
            root.setAttribute("data-bs-theme", "dark");
            toggle.textContent = "☀️ Light Mode";
            localStorage.setItem("tradebook-theme", "dark");
        }
    });
});
