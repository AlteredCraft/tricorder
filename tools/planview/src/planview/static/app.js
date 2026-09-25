// Live reload: poll the file stamp and reload when planning docs change.
(() => {
  const live = document.getElementById("live");
  let stamp = document.body.dataset.stamp;
  const tick = async () => {
    try {
      const res = await fetch("/api/stamp", { cache: "no-store" });
      const next = await res.text();
      live.classList.remove("off");
      if (stamp && next !== stamp) {
        sessionStorage.setItem("planview-scroll", String(window.scrollY));
        location.reload();
        return;
      }
      stamp = next;
    } catch (_) {
      live.classList.add("off");
    }
    setTimeout(tick, 1500);
  };
  const y = sessionStorage.getItem("planview-scroll");
  if (y !== null && !location.hash) {
    sessionStorage.removeItem("planview-scroll");
    window.scrollTo(0, Number(y));
  }
  setTimeout(tick, 1500);
})();
