document.addEventListener("DOMContentLoaded", () => {
  const sidebarToggle = document.querySelector('[data-lte-toggle="sidebar"]');
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", (e) => {
      e.preventDefault();
      document.body.classList.toggle("sidebar-collapse");
    });
  }

  const treeviewLinks = document.querySelectorAll('[data-lte-toggle="treeview"]');
  treeviewLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const item = e.target.closest(".nav-item");
      if (item) item.classList.toggle("menu-open");
    });
  });
});