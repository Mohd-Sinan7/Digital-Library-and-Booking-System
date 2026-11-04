// App shell shared by every page (DLBS-23): login token, API helper, nav bar, book card.
// Use it from a page with:  <script src="/js/app.js"></script>  then call DL.* functions.

const DL = (() => {
  const TOKEN = "dl_token";
  const USER = "dl_user";

  function read(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  function write(key, value) {
    try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); }
    catch { /* storage blocked: the user simply stays logged out */ }
  }

  function user() {
    try { return JSON.parse(read(USER)); } catch { return null; }
  }

  // Calls the REST API. Adds the bearer token, parses JSON and throws Error(detail) on failure.
  async function api(path, { method = "GET", body } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const token = read(TOKEN);
    if (token) headers.Authorization = "Bearer " + token;
    const res = await fetch(path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 401 && token) logout(false);  // expired token
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      const d = data && data.detail;
      const msg = Array.isArray(d) ? d.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join("; ") : d;
      const err = new Error(msg || `Request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function login(email, password) {
    const data = await api("/api/auth/login", { method: "POST", body: { email, password } });
    write(TOKEN, data.access_token);
    write(USER, JSON.stringify(data.user));
    return data.user;
  }

  function logout(redirect = true) {
    write(TOKEN, null);
    write(USER, null);
    if (redirect) location.href = "/";
  }

  // Navigation bar from SAD 4.5. Admin only for admins; Log in or Log out.
  function renderNav() {
    const u = user();
    const links = [
      ["/", "Home"], ["/catalog.html", "Catalog"], ["/reading.html", "My Reading"],
      ["/bookings.html", "My Bookings"], ["/profile.html", "Profile"],
    ];
    if (u && u.role === "admin") links.push(["/admin.html", "Admin"]);
    const here = location.pathname === "/index.html" ? "/" : location.pathname;
    const items = links.map(([href, text]) =>
      `<li><a href="${href}"${href === here ? ' aria-current="page"' : ""}>${text}</a></li>`);
    items.push(u
      ? `<li><span class="muted">${esc(u.name)}</span> <button type="button" id="logout">Log out</button></li>`
      : `<li><a href="/login.html">Log in</a></li>`);
    const nav = document.createElement("nav");
    nav.className = "nav";
    nav.setAttribute("aria-label", "Main");
    nav.innerHTML = `<ul><li><a class="brand" href="/">Digital Library</a></li>${items.join("")}</ul>`;
    document.body.prepend(nav);
    const btn = nav.querySelector("#logout");
    if (btn) btn.addEventListener("click", () => logout());
  }

  // Escape text before putting it into HTML.
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // Reusable book card (SAD 4.5): cover, title, author, then either an availability badge
  // or a recommendation reason. Works with catalog books and recommendation items.
  function bookCard(book, { reason } = {}) {
    const id = book.id ?? book.book_id;
    const cover = book.cover_url
      ? `<img src="${esc(book.cover_url)}" alt="Cover of ${esc(book.title)}" loading="lazy">`
      : "";
    let extra = "";
    if (reason) {
      extra = `<p class="reason">${esc(reason)}</p>`;
    } else if (book.available_copies !== undefined) {
      extra = book.available_copies > 0
        ? `<span class="badge ok">Available: ${book.available_copies} of ${book.total_copies}</span>`
        : `<span class="badge none">Not available</span>`;
    }
    return `<li><article class="card">${cover}
      <h3><a href="/book.html?id=${encodeURIComponent(id)}">${esc(book.title)}</a></h3>
      <p class="author">${esc(book.author)}</p>${extra}</article></li>`;
  }

  // Redirects to the login page when nobody is logged in. Returns the user otherwise.
  function requireLogin() {
    const u = user();
    if (!u) location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
    return u;
  }

  document.addEventListener("DOMContentLoaded", renderNav);
  return { api, login, logout, user, esc, bookCard, requireLogin };
})();
