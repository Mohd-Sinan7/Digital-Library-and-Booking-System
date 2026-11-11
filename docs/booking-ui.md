# Booking UI (`src/web/`) — DLBS-53

**Story:** DLBS-53 — Booking UI  
**Owner:** Marreddy Rushieswar Reddy (Member 4)

## Screens & Files Added Inside Member 2's App Shell

Built directly on top of Member 2's shell (`/css/app.css`, `/js/app.js`, and navigation links in `src/web/js/app.js`):

| File | Purpose |
|---|---|
| `src/web/book.html` | Book detail view showing metadata, real-time copy availability, and **Reserve Copy** / **Borrow Now** / **Cancel** / **Return** controls via `DLBooking.mountBookActions`. |
| `src/web/bookings.html` | Authenticated **My Bookings** page displaying active booking summary (`X / 5`), status filter, status badges (`Reserved`, `Borrowed`, `Overdue`, `Returned`, `Cancelled`, `Expired`), key dates, and **Borrow**, **Cancel**, **Return** buttons. |
| `src/web/js/booking-actions.js` | Reusable client helper (`DLBooking`) handling booking API actions, status badge rendering, date formatting, and XSS escaping via `DL.esc`. |
| `src/web/css/bookings.css` | Accessible badge contrast styling, responsive detail layout, and WCAG-compliant button target sizes. |

## API Endpoints Used

| Action | Method & Path | Handling in UI |
|---|---|---|
| Load book details & copies | `GET /api/books/{id}`, `GET /api/books/{id}/availability` | Displays live `available_copies / total_copies` count and disables booking when `0`. |
| List member bookings | `GET /api/bookings/me` | Lists newest-first bookings with status badges, hold expiry, due date, and `overdue` indicator. |
| Reserve copy | `POST /api/bookings` | Creates reservation; reloads availability and buttons immediately. |
| Borrow reservation / Borrow now | `POST /api/bookings/{id}/borrow` | Transitions reservation to `borrowed` and displays 14-day `due_date`. |
| Return borrowed book | `POST /api/bookings/{id}/return` | Transitions to `returned` and restores available copy count. |
| Cancel reservation | `DELETE /api/bookings/{id}` | Cancels active reservation and restores copy count. |
