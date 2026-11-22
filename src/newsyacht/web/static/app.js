const pendingPosts = new WeakSet();

const updatePost = async (url, row, button) => {
  if (pendingPosts.has(row)) return;
  pendingPosts.add(row);
  const hadFocus = button && document.activeElement === button;
  row.querySelector(".post-action-error")?.remove();

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "X-Newsyacht-Fragment": "post" },
    });
    if (!response.ok)
      throw new Error(`Failed to update post (${response.status})`);

    const template = document.createElement("template");
    template.innerHTML = await response.text();
    const newRow = template.content.querySelector(".post");
    if (!newRow || newRow.dataset.postId !== row.dataset.postId) {
      throw new Error("Missing updated post");
    }

    const filter = row.parentElement?.dataset.readFilter;
    const isRead = newRow.classList.contains("is-read");
    if ((filter === "unread" && isRead) || (filter === "read" && !isRead)) {
      const neighbor = row.nextElementSibling ?? row.previousElementSibling;
      row.remove();
      if (hadFocus) neighbor?.querySelector(".post-title a")?.focus();
      return;
    }

    const buttonIndex = Array.from(row.querySelectorAll("button")).indexOf(
      button,
    );
    row.replaceWith(newRow);
    if (hadFocus) newRow.querySelectorAll("button")[buttonIndex]?.focus();
  } catch (error) {
    console.error(error);
    const message = document.createElement("span");
    message.className = "post-action-error";
    message.setAttribute("role", "status");
    message.textContent = " Could not confirm the update. Refresh to check.";
    row.querySelector(".post-meta").append(message);
  } finally {
    pendingPosts.delete(row);
  }
};

document.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-async-post]");
  const row = form?.closest(".post");
  if (!row) return;
  event.preventDefault();
  void updatePost(form.action, row, event.submitter);
});

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-mark-read-url]");
  if (!link || event.defaultPrevented || event.button !== 0) return;
  const row = link.closest(".post");
  if (row) void updatePost(link.dataset.markReadUrl, row);
});

// Fallback links still work without JS: the next batch becomes a full page.
document.addEventListener("click", async (event) => {
  const more = event.target.closest("a[data-show-more]");
  if (
    !more ||
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    event.shiftKey
  )
    return;
  event.preventDefault();
  if (more.dataset.pending === "1") return;
  more.dataset.pending = "1";
  more.textContent = "Loading…";
  try {
    const response = await fetch(more.href, {
      credentials: "same-origin",
      headers: { "X-Newsyacht-Fragment": "posts" },
    });
    if (!response.ok)
      throw new Error(`Failed to load posts (${response.status})`);
    const template = document.createElement("template");
    template.innerHTML = await response.text();
    if (!more.isConnected) return;
    const list = document.getElementById("post-list");
    if (!list) throw new Error("Missing post list");
    const existing = new Set(
      [...list.querySelectorAll(".post")].map((row) => row.dataset.postId),
    );
    for (const row of template.content.querySelectorAll(".post")) {
      if (!existing.has(row.dataset.postId)) {
        list.append(row);
        existing.add(row.dataset.postId);
      }
    }
    const next = response.headers.get("X-Newsyacht-Next");
    if (next) {
      more.href = next;
      more.textContent = "Show more";
    } else {
      more.remove();
    }
  } catch (error) {
    console.error(error);
    more.textContent = "Retry loading posts";
  } finally {
    more.dataset.pending = "0";
  }
});

let activeNavigation = null;

const navigate = async (url, pushHistory) => {
  activeNavigation?.abort();
  const controller = new AbortController();
  activeNavigation = controller;
  try {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { "X-Newsyacht-Fragment": "page" },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Navigation failed (${response.status})`);
    const template = document.createElement("template");
    template.innerHTML = await response.text();
    if (controller !== activeNavigation) return;
    const newMain = template.content.querySelector("#main-content");
    const oldMain = document.getElementById("main-content");
    if (!oldMain || !newMain) throw new Error("Missing page content");
    const tagScroll = oldMain.querySelector(".tag-navigation")?.scrollLeft;
    oldMain.replaceWith(newMain);
    const tagBar = newMain.querySelector(".tag-navigation");
    if (tagBar && tagScroll !== undefined) tagBar.scrollLeft = tagScroll;
    if (pushHistory) {
      history.pushState({}, "", url);
      newMain.querySelector("h2")?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
  } catch (error) {
    if (error.name === "AbortError") return;
    console.error(error);
    window.location.assign(url);
  } finally {
    if (activeNavigation === controller) activeNavigation = null;
  }
};

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-nav]");
  if (
    !link ||
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    event.shiftKey
  )
    return;
  event.preventDefault();
  void navigate(link.href, true);
});

window.addEventListener("popstate", () => {
  if (document.getElementById("main-content")) {
    void navigate(window.location.href, false);
  }
});
