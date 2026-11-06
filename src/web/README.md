# src/web

Static pages served by the app at `/` (SAD: HTML, CSS and JavaScript pages, no build step).
Owner of the shell: Member 2. Each module owner adds their own screen.

## Adding your page

Copy this skeleton to `src/web/<page>.html`. The nav bar links to `reading.html` (Member 3),
`bookings.html` (Member 4) and `profile.html` (Member 3). `register.html` (Member 3) is
linked from the login page. Member 3's pages also load `css/users.css`.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My Page · Digital Library</title>
  <link rel="stylesheet" href="/css/app.css">
  <script src="/js/app.js"></script>
</head>
<body>
<main>
  <h1>My Page</h1>
  <ul id="list" class="grid"></ul>
</main>
<script>
  DL.requireLogin();                                   // optional: page needs a login
  DL.api("/api/bookings/me").then((data) => { ... });  // token added automatically
</script>
</body>
</html>
```

## What `js/app.js` gives you

| Function | Use |
|---|---|
| `DL.api(path, {method, body})` | Calls the API with the login token. Throws `Error(detail)` on 4xx/5xx |
| `DL.user()` | `{id, name, email, role}` of the logged-in user, or `null` |
| `DL.requireLogin()` | Sends the visitor to the login page if not logged in |
| `DL.bookCard(book, {reason})` | HTML for one book card (`<li>`); put it inside `<ul class="grid">` |
| `DL.esc(text)` | Escapes text before you put it into HTML |
| `DL.logout()` | Clears the token and goes home |

The nav bar is added to every page automatically.
