// Shared Booking & Borrowing UI controls (DLBS-53) inside Member 2's app shell.
// Requires /js/app.js (DL.api, DL.user, DL.esc).

window.DLBooking = (() => {
  const STATUS_LABELS = {
    reserved: "Reserved",
    borrowed: "Borrowed",
    returned: "Returned",
    cancelled: "Cancelled",
    expired: "Expired",
  };

  function statusBadgeHtml(booking) {
    const status = String(booking.status || "reserved").toLowerCase();
    const label = STATUS_LABELS[status] || status;
    const overdue = Boolean(booking.overdue || booking.is_overdue);
    const primary = `<span class="badge badge-${DL.esc(status)}">${DL.esc(label)}</span>`;
    const overdueBadge = overdue
      ? ` <span class="badge badge-overdue">Overdue</span>`
      : "";
    return primary + overdueBadge;
  }

  function formatDatesHtml(booking) {
    const parts = [];
    if (booking.reserved_at || booking.created_at) {
      parts.push(`<span>Reserved: ${DL.esc(booking.reserved_at || booking.created_at)}</span>`);
    }
    if (booking.status === "reserved" && booking.expires_at) {
      parts.push(`<span>Hold expires: ${DL.esc(booking.expires_at)}</span>`);
    }
    if (booking.borrowed_at) {
      parts.push(`<span>Borrowed: ${DL.esc(booking.borrowed_at)}</span>`);
    }
    if (booking.due_date) {
      parts.push(`<span>Due: ${DL.esc(booking.due_date)}</span>`);
    }
    if (booking.returned_at) {
      parts.push(`<span>Returned: ${DL.esc(booking.returned_at)}</span>`);
    }
    return `<div class="booking-dates">${parts.join("")}</div>`;
  }

  function handleActionError(err, errorEl) {
    if (err && err.status === 401) {
      DL.requireLogin();
      return;
    }
    if (errorEl) {
      errorEl.textContent = (err && err.message) || "Unable to complete booking action.";
    }
  }

  async function mountBookActions(container, bookId, { onUpdated } = {}) {
    if (!container) return;

    const statusMsg = document.createElement("p");
    statusMsg.className = "saved";
    statusMsg.setAttribute("role", "status");
    statusMsg.setAttribute("aria-live", "polite");

    const errorMsg = document.createElement("p");
    errorMsg.className = "error";
    errorMsg.setAttribute("role", "alert");

    const bodyEl = document.createElement("div");
    container.innerHTML = "";
    container.append(bodyEl, statusMsg, errorMsg);

    async function refresh() {
      errorMsg.textContent = "";
      const user = DL.user();
      let avail = null;
      try {
        avail = await DL.api(`/api/books/${encodeURIComponent(bookId)}/availability`);
      } catch (err) {
        handleActionError(err, errorMsg);
        return;
      }

      const availCount = Number(avail.available_copies ?? 0);
      const totalCount = Number(avail.total_copies ?? 0);
      const availBadge = availCount > 0
        ? `<span class="badge ok">Available: ${availCount} of ${totalCount} copies</span>`
        : `<span class="badge none">Currently unavailable (0 of ${totalCount} copies)</span>`;

      if (!user) {
        const nextUrl = encodeURIComponent(location.pathname + location.search);
        bodyEl.innerHTML = `
          <div>${availBadge}</div>
          <p><a href="/login.html?next=${nextUrl}">Log in</a> to reserve or borrow this book.</p>
        `;
        return;
      }

      let activeBooking = null;
      try {
        const mine = await DL.api("/api/bookings/me");
        const items = (mine && mine.items) || [];
        activeBooking = items.find(
          (b) => Number(b.book_id) === Number(bookId) && b.is_active
        ) || null;
      } catch (err) {
        if (err && err.status === 401) return DL.requireLogin();
        handleActionError(err, errorMsg);
      }

      if (activeBooking) {
        const buttons = activeBooking.status === "reserved"
          ? `
            <button type="button" class="action-btn primary" data-action="borrow"
                    data-id="${DL.esc(activeBooking.id)}">Borrow Book</button>
            <button type="button" class="action-btn danger" data-action="cancel"
                    data-id="${DL.esc(activeBooking.id)}">Cancel Reservation</button>
          `
          : `
            <button type="button" class="action-btn primary" data-action="return"
                    data-id="${DL.esc(activeBooking.id)}">Return Book</button>
          `;

        bodyEl.innerHTML = `
          <div class="booking-badges">
            ${availBadge}
            ${statusBadgeHtml(activeBooking)}
          </div>
          ${formatDatesHtml(activeBooking)}
          <div class="booking-actions">
            ${buttons}
            <a href="/bookings.html">View all My Bookings</a>
          </div>
        `;
      } else if (availCount > 0) {
        bodyEl.innerHTML = `
          <div>${availBadge}</div>
          <div class="booking-actions">
            <button type="button" class="action-btn primary" data-action="reserve">Reserve Copy</button>
            <button type="button" class="action-btn" data-action="reserve-and-borrow">Borrow Now</button>
          </div>
        `;
      } else {
        bodyEl.innerHTML = `
          <div>${availBadge}</div>
          <div class="booking-actions">
            <button type="button" class="action-btn" disabled>No Copies Available</button>
          </div>
        `;
      }

      if (typeof onUpdated === "function") onUpdated(avail);
    }

    container.addEventListener("click", async (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn || btn.disabled) return;

      const action = btn.dataset.action;
      const bookingId = btn.dataset.id;
      const allBtns = container.querySelectorAll("button.action-btn");
      allBtns.forEach((b) => { b.disabled = true; });
      errorMsg.textContent = "";
      statusMsg.textContent = "";

      try {
        if (action === "reserve") {
          await DL.api("/api/bookings", { method: "POST", body: { book_id: Number(bookId) } });
          statusMsg.textContent = "Copy reserved! Hold is valid for 2 days.";
        } else if (action === "reserve-and-borrow") {
          const created = await DL.api("/api/bookings", {
            method: "POST",
            body: { book_id: Number(bookId) },
          });
          const borrowed = await DL.api(`/api/bookings/${created.id}/borrow`, { method: "POST" });
          statusMsg.textContent = `Borrowed! Due date: ${borrowed.due_date || "in 14 days"}.`;
        } else if (action === "borrow") {
          const borrowed = await DL.api(`/api/bookings/${bookingId}/borrow`, { method: "POST" });
          statusMsg.textContent = `Book borrowed. Due date: ${borrowed.due_date}.`;
        } else if (action === "cancel") {
          await DL.api(`/api/bookings/${bookingId}`, { method: "DELETE" });
          statusMsg.textContent = "Reservation cancelled and copy restored.";
        } else if (action === "return") {
          await DL.api(`/api/bookings/${bookingId}/return`, { method: "POST" });
          statusMsg.textContent = "Book returned! Thank you.";
        }
        await refresh();
      } catch (err) {
        allBtns.forEach((b) => { b.disabled = false; });
        handleActionError(err, errorMsg);
      }
    });

    await refresh();
  }

  return {
    STATUS_LABELS,
    statusBadgeHtml,
    formatDatesHtml,
    mountBookActions,
  };
})();
