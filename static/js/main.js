// Bookmarkd - main.js
// Shared interactive behaviour across pages

// -- HAMBURGER MENU (mobile nav) --
function toggleNav() {
    const navLinks = document.querySelector('.nav-links');
    if (navLinks) {
        navLinks.classList.toggle('nav-open');
    }
}

// -- SERVICE WORKER REGISTRATION --
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then((reg) => console.log('Service worker registered:', reg.scope))
            .catch((err) => console.log('Service worker registration failed:', err));
    });
}

// -- CLOSE MOBILE NAV WHEN CLICKING A LINK --
document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('.nav-links a');
    navLinks.forEach((link) => {
        link.addEventListener('click', () => {
            const nav = document.querySelector('.nav-links');
            if (nav) nav.classList.remove('nav-open');
        });
    });
});