# Peripherals Map

Every peripheral the SDK runtime runs, and what serves whose needs: radios and the host, the USB drivers that recognise sticks, the Docker services, the in-process capabilities, and a few integrations as examples of consumers. An arrow points from a provider to the peripheral whose need it serves. Click any peripheral to see what it needs, what it provides, and what runs it. How to use them: [Peripherals](../device-integration/peripherals.md).

<iframe id="permap"
        src="../peripherals-map.html"
        title="MajorDom — interactive peripherals map"
        loading="lazy"
        style="width:100%;height:85vh;border:1px solid var(--md-default-fg-color--lightest);border-radius:.35rem"></iframe>

[Open full-screen ↗](peripherals-map.html){target=_blank}

<script>
// Bridge Material's light/dark toggle into the same-origin iframe (which themes off [data-theme]).
(function () {
  var f = document.getElementById("permap");
  if (!f) return;
  function scheme() {
    return document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "light";
  }
  function sync() {
    try {
      var d = f.contentDocument;
      if (d && d.documentElement) d.documentElement.dataset.theme = scheme();
    } catch (e) {/* cross-origin or not ready — ignore */}
  }
  f.addEventListener("load", sync);
  new MutationObserver(sync).observe(document.body, {
    attributes: true, attributeFilter: ["data-md-color-scheme"],
  });
})();
</script>
