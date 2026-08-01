# Module Map

An interactive map of the whole Hub — the Hub itself, the integration SDK, and the
Matter / Zigbee / HomeKit integrations — laid out concentrically (`Coordinator` at the centre,
I/O at the rim) and grouped by domain. Click any entity to focus it: everything else mutes, its
inputs and outputs light up, and the panel lists what it implements / consumes / is implemented
by, the methods callers invoke, its output delegates and its injected dependencies. Search
entities, or click a domain's `⤢` label to isolate it.

<iframe id="modmap"
        src="../module-map.html"
        title="MajorDom Hub — interactive module map"
        loading="lazy"
        style="width:100%;height:85vh;border:1px solid var(--md-default-fg-color--lightest);border-radius:.35rem"></iframe>

[Open full-screen ↗](../module-map.html){target=_blank}

<script>
// Bridge Material's light/dark toggle into the same-origin iframe (which themes off [data-theme]).
(function () {
  var f = document.getElementById("modmap");
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
