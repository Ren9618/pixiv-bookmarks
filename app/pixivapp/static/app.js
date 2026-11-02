"use strict";

const el = (id) => document.getElementById(id);
const state = {
  q: "",
  tag: "",
  artist: "",
  favorites: false,
  r18: false,
  sort: "added_desc",
  offset: 0,
  limit: 60,
  total: 0,
  items: [],
  loading: false,
  done: false,
  status: null,
  accounts: [],
  account: "",
  lb: null,
};

const grid = el("grid");
const sentinel = el("sentinel");
const searchInput = el("searchInput");
const sortSelect = el("sortSelect");
const accountSelect = el("accountSelect");
const artistSelect = el("artistSelect");
const favoriteFilter = el("favoriteFilter");
const r18Filter = el("r18Filter");
const resultCount = el("resultCount");
const emptyBox = el("empty");
const syncPanel = el("syncPanel");
const lightbox = el("lightbox");
const lbImage = el("lbImage");
const lbVideo = el("lbVideo");
const lbStage = el("lbStage");
const lbHint = el("lbHint");

const I18n = window.ViewerI18n;
const t = (key, variables) => I18n.t(key, variables);
const currentLanguage = () => I18n.getLang();
const isJapanese = () => currentLanguage() === "ja";
const separator = () => t("common.separator");
const formatNumber = (value) => I18n.formatNumber(value);

function countLabel(value, singular, plural, japaneseUnit) {
  const number = Number(value || 0);
  if (isJapanese()) return `${formatNumber(number)}${japaneseUnit}`;
  return `${formatNumber(number)} ${number === 1 ? singular : plural}`;
}

const workCount = (value) => countLabel(value, "work", "works", "作品");
const accountCount = (value) => countLabel(value, "account", "accounts", "アカウント");

function createDateFormatter() {
  return new Intl.DateTimeFormat(isJapanese() ? "ja-JP" : "en-US", {
    month: isJapanese() ? "numeric" : "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

let dateFormatter = createDateFormatter();

let toastTimer = null;
let hintTimer = null;
let lbPointer = null;
let requestSeq = 0;

function showToast(message) {
  const toast = el("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 3200);
}

async function api(url, options = {}) {
  const opts = { credentials: "same-origin", ...options };
  opts.headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  const response = await fetch(url, opts);
  if (response.status === 401) {
    const next = encodeURIComponent(location.pathname + location.search);
    location.href = `/login?next=${next}`;
    throw new Error(t("error.loginRequired"));
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    let code = response.headers.get("X-Error-Code") || "";
    try {
      const body = await response.json();
      if (body && body.detail) {
        detail = typeof body.detail === "string"
          ? body.detail
          : (body.detail.message || JSON.stringify(body.detail));
      }
      if (body && body.code) code = body.code;
    } catch (_) {
      /* ignore */
    }
    const error = new Error(detail);
    error.code = code;
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateFormatter.format(date);
}

function formatEpoch(seconds) {
  const value = Number(seconds);
  if (!value) return "—";
  return dateFormatter.format(new Date(value * 1000));
}

function accountLabel(account, compact = false) {
  if (!account) return "";
  const name = account.name || account.account || `ID ${account.id}`;
  if (!account.account) return name;
  return compact ? `${name} @${account.account}` : `${name} (@${account.account})`;
}

function statusAccounts(status) {
  if (Array.isArray(status?.accounts)) return status.accounts;
  return status?.account ? [status.account] : [];
}

function currentAccount() {
  return state.accounts.find((account) => String(account.id) === state.account) || null;
}

function updateAccountOptions(accounts, force = false) {
  state.accounts = accounts;
  const previous = state.account;
  if (state.account && !accounts.some((account) => String(account.id) === state.account)) {
    state.account = "";
    localStorage.removeItem("pixiv-viewer-account");
  }

  const signature = accounts
    .map((account) => `${account.id}|${account.name}|${account.account}|${account.works}|${account.works_safe}`)
    .join(";");
  if (force || accountSelect.dataset.signature !== signature) {
    accountSelect.innerHTML = "";
    const all = document.createElement("option");
    all.value = "";
    all.textContent = accounts.length ? t("account.all") : t("account.none");
    accountSelect.appendChild(all);
    accounts.forEach((account) => {
      const option = document.createElement("option");
      option.value = String(account.id);
      const count = Number(account.works || 0);
      option.textContent = `${accountLabel(account, true)} (${formatNumber(count)})`;
      accountSelect.appendChild(option);
    });
    accountSelect.dataset.signature = signature;
  }
  accountSelect.value = state.account;
  return previous !== state.account;
}

function updateAccountLine(status, accounts) {
  const line = el("accountLine");
  const selected = currentAccount();
  if (selected) {
    line.textContent = `${accountLabel(selected, true)}${separator()}${workCount(selected.works)}`;
    return;
  }
  if (!accounts.length) {
    line.textContent = status.auth_required ? t("status.subNoAccounts") : "—";
    return;
  }
  if (accounts.length === 1) {
    line.textContent = `${accountLabel(accounts[0], true)}${separator()}${workCount(accounts[0].works)}`;
  } else {
    line.textContent = `${accountCount(accounts.length)}${separator()}${workCount(status.counts?.works)}`;
  }
}

function updateSyncScope() {
  const scope = el("syncScope");
  const selected = currentAccount();
  if (selected) {
    scope.textContent = t("sync.scopeSelected", {
      account: accountLabel(selected, true),
    });
  } else {
    scope.textContent = t("sync.scopeAll");
  }
  scope.classList.toggle("active", Boolean(selected));
}

function setAccount(value) {
  const next = state.accounts.some((account) => String(account.id) === String(value))
    ? String(value)
    : "";
  accountSelect.value = next;
  if (next === state.account) return;

  state.account = next;
  if (next) localStorage.setItem("pixiv-viewer-account", next);
  else localStorage.removeItem("pixiv-viewer-account");

  refreshStatus();
  loadTags();
  loadArtists();
  resetAndLoad();
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.round(Number(seconds)));
  if (isJapanese()) {
    if (total < 60) return `${total}秒`;
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return rest ? `${minutes}分${rest}秒` : `${minutes}分`;
  }
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

function updateResultCount() {
  resultCount.textContent = state.total ? workCount(state.total) : "";
}

function updateFilterUI() {
  favoriteFilter.classList.toggle("active", state.favorites);
  r18Filter.classList.toggle("active", state.r18);
  favoriteFilter.setAttribute("aria-pressed", String(state.favorites));
  r18Filter.setAttribute("aria-pressed", String(state.r18));
  r18Filter.textContent = state.r18 ? t("r18.hide") : t("r18.show");
}

function resetAndLoad() {
  requestSeq += 1;
  state.offset = 0;
  state.items = [];
  state.done = false;
  state.loading = false;
  grid.innerHTML = "";
  emptyBox.classList.add("hidden");
  updateResultCount();
  loadItems(requestSeq);
}

function queryParams() {
  const params = new URLSearchParams({
    q: state.q,
    tag: state.tag,
    favorites: state.favorites ? "1" : "0",
    r18: state.r18 ? "1" : "0",
    sort: state.sort,
    offset: String(state.offset),
    limit: String(state.limit),
  });
  if (state.artist) params.set("artist", state.artist);
  if (state.account) params.set("account", state.account);
  return params;
}

async function loadItems(seq = requestSeq) {
  if (state.loading || state.done) return;
  state.loading = true;
  el("loadingMore").classList.remove("hidden");
  el("loadMore").classList.add("hidden");

  try {
    const data = await api(`/api/items?${queryParams().toString()}`);
    if (seq !== requestSeq) return;
    state.total = data.total;
    const startIndex = state.items.length;
    if (data.items.length) {
      state.items.push(...data.items);
      renderCards(data.items, startIndex);
    }
    state.offset += data.items.length;
    state.done = state.offset >= data.total || data.items.length === 0;
    updateResultCount();
    toggleEmpty();
  } catch (error) {
    if (seq === requestSeq) {
      showToast(error.message || t("error.loadWorks"));
    }
  } finally {
    if (seq === requestSeq) {
      state.loading = false;
      el("loadingMore").classList.add("hidden");
      const showMore = !state.done && state.items.length > 0;
      el("loadMore").classList.toggle("hidden", !showMore);
      toggleEmpty();
    }
  }
}

function cardBadge(text, className = "card-badge") {
  const badge = document.createElement("span");
  badge.className = className;
  badge.textContent = text;
  return badge;
}

function renderCards(items, startIndex) {
  const fragment = document.createDocumentFragment();

  items.forEach((item, offset) => {
    const card = document.createElement("article");
    card.className = "card";
    card.tabIndex = 0;
    card.dataset.index = String(startIndex + offset);
    const fallbackTitle = t("card.untitled", { id: item.id });
    card.setAttribute("aria-label", item.title || fallbackTitle);

    const thumb = document.createElement("div");
    thumb.className = "card-thumb";

    const image = document.createElement("img");
    image.loading = "lazy";
    image.decoding = "async";
    image.src = item.thumb_url;
    image.alt = item.title || fallbackTitle;
    thumb.appendChild(image);

    const shade = document.createElement("div");
    shade.className = "card-shade";
    thumb.appendChild(shade);

    const badgeParts = [];
    if (item.is_video) badgeParts.push(t("card.video"));
    if (item.page_count > 1) {
      badgeParts.push(t("card.pages", { count: formatNumber(item.page_count) }));
    }
    if (badgeParts.length) {
      thumb.appendChild(cardBadge(badgeParts.join(" / ")));
    }

    if (item.x_restrict > 0) {
      card.classList.add("has-r18");
      thumb.appendChild(
        cardBadge(item.x_restrict === 2 ? "R-18G" : "R-18", "card-badge r18")
      );
    }

    const info = document.createElement("div");
    info.className = "card-info";

    const title = document.createElement("div");
    title.className = "card-title";
    title.textContent = item.title || fallbackTitle;
    info.appendChild(title);

    const artist = document.createElement("div");
    artist.className = "card-artist";
    artist.textContent = item.artist_name || t("card.unknownArtist");
    info.appendChild(artist);
    thumb.appendChild(info);

    const favorite = document.createElement("button");
    favorite.type = "button";
    favorite.className = "card-fav";
    favorite.dataset.favId = String(item.id);
    favorite.textContent = item.favorited ? "★" : "☆";
    favorite.classList.toggle("active", item.favorited);
    favorite.setAttribute("aria-label", t("card.favorite"));
    favorite.setAttribute("aria-pressed", String(item.favorited));
    thumb.appendChild(favorite);

    card.appendChild(thumb);
    fragment.appendChild(card);
  });

  grid.appendChild(fragment);
}

function toggleEmpty() {
  if (state.loading) return;
  const isEmpty = state.done && state.items.length === 0;
  emptyBox.classList.toggle("hidden", !isEmpty);
  if (!isEmpty) return;

  const status = state.status || {};
  const title = el("emptyTitle");
  const body = el("emptyBody");
  if (status.state === "running") {
    title.textContent = t("empty.syncingTitle");
    body.textContent = t("empty.syncingBody");
  } else if (status.state === "auth_required") {
    title.textContent = t("empty.authTitle");
    body.textContent = t("empty.authBody");
  } else if (status.state === "error") {
    title.textContent = t("empty.errorTitle");
    body.textContent = t("empty.errorBody");
  } else if (state.account) {
    const account = currentAccount();
    title.textContent = t("empty.accountTitle", {
      account: accountLabel(account, true) || t("empty.accountFallback"),
    });
    body.textContent = t("empty.accountBody");
  } else {
    title.textContent = t("empty.noWorks");
    body.textContent = t("empty.noWorksBody");
  }
}

async function toggleFavorite(item, button) {
  if (button) button.disabled = true;
  const desired = !item.favorited;
  try {
    const result = await api(`/api/favorite/${item.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ favorited: desired }),
    });
    item.favorited = Boolean(result.favorited);
    updateFavoriteUI(item);
    if (state.favorites && !item.favorited) {
      resetAndLoad();
    }
  } catch (error) {
    showToast(error.message || t("error.favoriteUpdate"));
  } finally {
    if (button) button.disabled = false;
  }
}

function updateFavoriteUI(item) {
  document
    .querySelectorAll(`.card-fav[data-fav-id="${item.id}"]`)
    .forEach((button) => {
      button.textContent = item.favorited ? "★" : "☆";
      button.classList.toggle("active", item.favorited);
      button.setAttribute("aria-pressed", String(item.favorited));
    });

  const lbFavorite = el("lbFavorite");
  if (state.lb && currentItem() && currentItem().id === item.id) {
    lbFavorite.textContent = item.favorited
      ? t("lightbox.favoriteOn")
      : t("lightbox.favoriteOff");
    lbFavorite.classList.toggle("active", item.favorited);
    lbFavorite.setAttribute("aria-pressed", String(item.favorited));
  }
}

function currentItem() {
  if (!state.lb) return null;
  return state.items[state.lb.index] || null;
}

function currentPage() {
  const item = currentItem();
  if (!item) return null;
  return item.pages[state.lb.page] || item.pages[0] || null;
}

function openLightbox(index) {
  if (!state.items[index]) return;
  state.lb = { index, page: 0 };
  lightbox.classList.remove("hidden");
  document.body.classList.add("lb-open");
  renderLightbox();
  clearTimeout(hintTimer);
  lbHint.classList.remove("hidden");
  hintTimer = setTimeout(() => lbHint.classList.add("hidden"), 3200);
}

function closeLightbox() {
  lightbox.classList.add("hidden");
  document.body.classList.remove("lb-open");
  lbVideo.pause();
  lbVideo.removeAttribute("src");
  lbImage.removeAttribute("src");
  state.lb = null;
  clearTimeout(hintTimer);
}

function renderLightbox() {
  const item = currentItem();
  if (!item) {
    closeLightbox();
    return;
  }
  if (state.lb.page >= item.pages.length) state.lb.page = 0;
  const page = currentPage();
  if (!page) {
    closeLightbox();
    return;
  }

  el("lbTitle").textContent = item.title || t("card.untitled", { id: item.id });
  el("lbArtist").textContent = [
    item.artist_name || t("card.unknownArtist"),
    item.artist_account ? `@${item.artist_account}` : "",
    item.x_restrict === 2 ? "R-18G" : item.x_restrict === 1 ? "R-18" : "",
  ].filter(Boolean).join(separator());

  if (page.is_video) {
    lbImage.hidden = true;
    lbVideo.hidden = false;
    lbVideo.src = page.media_url;
    lbVideo.poster = page.thumb_url;
    lbVideo.muted = true;
    lbVideo.play().catch(() => {});
  } else {
    lbVideo.pause();
    lbVideo.hidden = true;
    lbVideo.removeAttribute("src");
    lbImage.hidden = false;
    lbImage.src = page.media_url;
    lbImage.alt = item.title || t("card.untitled", { id: item.id });
  }

  const counterParts = [
    t("lightbox.counter", {
      index: formatNumber(state.lb.index + 1),
      total: formatNumber(state.items.length),
      plus: state.done ? "" : "+",
    }),
  ];
  if (item.pages.length > 1) {
    counterParts.push(t("lightbox.pages", {
      page: formatNumber(state.lb.page + 1),
      total: formatNumber(item.pages.length),
    }));
  }
  el("lbCounter").textContent = counterParts.join(separator());

  const dots = el("lbDots");
  dots.innerHTML = "";
  if (item.pages.length > 1) {
    item.pages.forEach((_, index) => {
      const dot = document.createElement("span");
      dot.className = "lb-dot" + (index === state.lb.page ? " active" : "");
      dots.appendChild(dot);
    });
  }

  const favorite = el("lbFavorite");
  favorite.textContent = item.favorited
    ? t("lightbox.favoriteOn")
    : t("lightbox.favoriteOff");
  favorite.classList.toggle("active", item.favorited);
  favorite.setAttribute("aria-pressed", String(item.favorited));

  el("lbPixiv").href = item.pixiv_url;
  el("lbOriginal").href = page.media_url;
  el("lbDownload").href = `${page.media_url}?download=1`;
}

async function nextItem() {
  const item = currentItem();
  if (!item) return;
  if (state.lb.page + 1 < item.pages.length) {
    state.lb.page += 1;
    renderLightbox();
    return;
  }
  if (state.lb.index + 1 < state.items.length) {
    state.lb.index += 1;
    state.lb.page = 0;
    renderLightbox();
    return;
  }
  if (!state.done) {
    await loadItems();
    if (state.lb.index + 1 < state.items.length) {
      state.lb.index += 1;
      state.lb.page = 0;
      renderLightbox();
      return;
    }
  }
  showToast(t("toast.lastItem"));
}

function previousItem() {
  const item = currentItem();
  if (!item) return;
  if (state.lb.page > 0) {
    state.lb.page -= 1;
    renderLightbox();
    return;
  }
  if (state.lb.index > 0) {
    state.lb.index -= 1;
    state.lb.page = Math.max(0, state.items[state.lb.index].pages.length - 1);
    renderLightbox();
    return;
  }
  showToast(t("toast.firstItem"));
}

function statusLabel(status) {
  const key = `status.${status}`;
  return I18n.has(key) ? t(key) : t("status.unknownLabel");
}

function statusMessage(status) {
  const accounts = statusAccounts(status);
  const syncedAccounts = Number(status.sync_account_count || 0) || accounts.length;
  switch (status.state) {
    case "idle":
      return t("status.message.idle", {
        new: formatNumber(status.last_new_works || 0),
        works: formatNumber(status.counts?.works || 0),
        accounts: accountCount(syncedAccounts),
      });
    case "running":
      return t("status.message.running", {
        accounts: accountCount(syncedAccounts || 1),
      });
    case "error":
      return t("status.message.error");
    case "auth_required":
      return t("status.message.authRequired");
    case "stopped":
      return t("status.message.stopped");
    default:
      return status.message || t("status.unknown");
  }
}

function oauthErrorText(error, fallbackKey) {
  if (error && error.code) {
    const key = `oauth.error.${error.code}`;
    if (I18n.has(key)) return t(key);
  }
  return error?.message || t(fallbackKey);
}

function statusCell(label, value) {
  const cell = document.createElement("div");
  cell.className = "status-cell";
  const name = document.createElement("span");
  name.textContent = label;
  const content = document.createElement("strong");
  content.textContent = value;
  cell.append(name, content);
  return cell;
}

function renderAccounts(status) {
  const container = el("syncAccounts");
  container.innerHTML = "";
  const accounts = statusAccounts(status);

  if (!accounts.length) {
    const empty = document.createElement("p");
    empty.className = "account-empty";
    empty.textContent = t("account.noneRegistered");
    container.appendChild(empty);
    return;
  }

  const running = status.state === "running";
  accounts.forEach((account) => {
    const card = document.createElement("div");
    card.className = "account-card" + (String(account.id) === state.account ? " active" : "");

    const info = document.createElement("div");
    info.className = "account-info";

    const name = document.createElement("div");
    name.className = "account-name";
    name.textContent = accountLabel(account);
    info.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "account-meta";
    const works = Number(account.works || 0);
    const safe = Number(account.works_safe || 0);
    const parts = [
      workCount(works),
      t("account.lastSync", { date: formatEpoch(account.last_sync_ts) }),
    ];
    if (works > safe) {
      parts.push(t("account.r18", { count: formatNumber(works - safe) }));
    }
    meta.textContent = parts.join(separator());
    info.appendChild(meta);

    if (account.last_error) {
      const error = document.createElement("p");
      error.className = "account-error";
      const text = String(account.last_error);
      error.textContent = text.length > 500 ? `${text.slice(0, 500)}…` : text;
      info.appendChild(error);
    }

    const actions = document.createElement("div");
    actions.className = "account-actions";

    const selected = String(account.id) === state.account;
    const view = document.createElement("button");
    view.type = "button";
    view.className = "account-action";
    view.dataset.viewAccount = String(account.id);
    view.textContent = selected ? t("account.viewing") : t("account.view");
    view.disabled = selected;
    actions.appendChild(view);

    const sync = document.createElement("button");
    sync.type = "button";
    sync.className = "account-action primary";
    sync.dataset.syncAccount = String(account.id);
    sync.textContent = running ? t("account.syncing") : t("account.sync");
    sync.disabled = running;
    actions.appendChild(sync);

    card.append(info, actions);
    container.appendChild(card);
  });
}

function renderSyncDetail(status) {
  const detail = el("syncDetail");
  detail.innerHTML = "";
  const accounts = statusAccounts(status);

  const hero = document.createElement("div");
  hero.className = `status-hero ${status.state || ""}`;
  const heading = document.createElement("strong");
  heading.textContent = statusLabel(status.state) + " — " + statusMessage(status);
  const sub = document.createElement("p");
  const selected = currentAccount();
  const accountText = accounts.length
    ? (selected
      ? t("status.subSelected", {
        accounts: accountCount(accounts.length),
        account: accountLabel(selected, true),
      })
      : t("status.subAll", { accounts: accountCount(accounts.length) }))
    : t("status.subNoAccounts");
  sub.textContent = `${accountText}${separator()}${t("status.lastUpdated", {
    date: formatDate(status.updated_at),
  })}`;
  hero.append(heading, sub);
  detail.appendChild(hero);

  const cells = document.createElement("div");
  cells.className = "status-grid";
  cells.append(
    statusCell(t("status.cell.lastSync"), formatDate(status.finished_at)),
    statusCell(t("status.cell.next"), status.sync_queued
      ? t("status.cell.queued")
      : formatDate(status.next_run)),
    statusCell(t("status.cell.works"), formatNumber(status.counts?.works)),
    statusCell(t("status.cell.images"), formatNumber(status.counts?.images)),
    statusCell(t("status.cell.favorites"), formatNumber(status.counts?.favorites)),
    statusCell(t("status.cell.new"),
      status.last_new_works === null || status.last_new_works === undefined
        ? "—"
        : workCount(status.last_new_works)),
    statusCell(t("status.cell.duration"), formatDuration(status.last_duration_sec)),
    statusCell(t("status.cell.mode"),
      status.full_sync ? t("status.mode.full") : t("status.mode.incremental")),
  );
  detail.appendChild(cells);

  if (status.last_error) {
    const error = document.createElement("pre");
    error.className = "status-error";
    error.textContent = status.last_error;
    detail.appendChild(error);
  }

  renderAccounts(status);
}

async function refreshStatus() {
  try {
    const status = await api("/api/status");
    state.status = status;
    const pill = el("syncPill");
    pill.className = `sync-pill state-${status.state || "unknown"}`;
    el("syncLabel").textContent = statusLabel(status.state);

    const accounts = statusAccounts(status);
    const selectionChanged = updateAccountOptions(accounts);
    updateAccountLine(status, accounts);
    updateSyncScope();

    const selected = currentAccount();
    const targetLabel = selected ? accountLabel(selected, true) : t("account.allTarget");
    el("syncNow").title = t("sync.nowTitle", { target: targetLabel });
    el("fullSync").title = t("sync.fullTitle", { target: targetLabel });

    if (selectionChanged) {
      loadTags();
      loadArtists();
      resetAndLoad();
    }
    if (!syncPanel.classList.contains("hidden")) {
      renderSyncDetail(status);
    }
    toggleEmpty();
  } catch (error) {
    el("syncLabel").textContent = t("status.connectionError");
    el("syncPill").className = "sync-pill state-error";
  }
}

async function loadTags() {
  try {
    const params = new URLSearchParams({
      r18: state.r18 ? "1" : "0",
      limit: "60",
    });
    if (state.account) params.set("account", state.account);
    const data = await api(`/api/tags?${params.toString()}`);
    const bar = el("tagBar");
    bar.innerHTML = "";
    if (state.tag && !data.tags.some((entry) => entry.tag === state.tag)) {
      data.tags.unshift({ tag: state.tag, count: 0 });
    }
    data.tags.forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tag-chip" + (entry.tag === state.tag ? " active" : "");
      button.dataset.tag = entry.tag;
      button.textContent = `#${entry.tag}`;
      if (entry.count) button.title = workCount(entry.count);
      bar.appendChild(button);
    });
  } catch (error) {
    console.error(error);
  }
}

async function loadArtists() {
  try {
    const params = new URLSearchParams({
      r18: state.r18 ? "1" : "0",
      limit: "100",
    });
    if (state.account) params.set("account", state.account);
    const data = await api(`/api/artists?${params.toString()}`);
    const selected = state.artist;
    artistSelect.innerHTML = "";
    const all = document.createElement("option");
    all.value = "";
    all.textContent = t("artist.all");
    artistSelect.appendChild(all);
    data.artists.forEach((artist) => {
      const option = document.createElement("option");
      option.value = String(artist.id);
      option.textContent = `${artist.name} (${formatNumber(artist.count)})`;
      artistSelect.appendChild(option);
    });
    if (selected && !data.artists.some((artist) => String(artist.id) === selected)) {
      const option = document.createElement("option");
      option.value = selected;
      option.textContent = t("artist.id", { id: selected });
      artistSelect.appendChild(option);
    }
    artistSelect.value = selected;
  } catch (error) {
    console.error(error);
  }
}

async function loadLog() {
  try {
    const data = await api("/api/log?lines=140");
    const log = el("logTail");
    log.textContent = data.lines.length ? data.lines.join("\n") : t("log.empty");
    log.scrollTop = log.scrollHeight;
  } catch (error) {
    el("logTail").textContent = error.message || t("log.loadError");
  }
}

function setOAuthStatus(message, kind = "") {
  const node = el("oauthStatus");
  node.textContent = message || "";
  node.classList.toggle("ok", kind === "ok");
  node.classList.toggle("error", kind === "error");
}

function renderOAuthPending(data) {
  const link = el("oauthLogin");
  const info = el("oauthPending");
  if (!data || !data.pending || !data.login_url) {
    link.classList.add("hidden");
    link.removeAttribute("href");
    info.textContent = "";
    return;
  }
  link.href = data.login_url;
  link.classList.remove("hidden");
  const minutes = Math.max(1, Math.ceil(Number(data.expires_in || 0) / 60));
  info.textContent = t("oauth.pending", { minutes: formatNumber(minutes) });
}

async function loadOAuthPending() {
  try {
    renderOAuthPending(await api("/api/accounts/oauth/pending"));
  } catch (_) {
    renderOAuthPending(null);
  }
}

async function startOAuth() {
  if (
    !el("oauthLogin").classList.contains("hidden") &&
    !confirm(t("oauth.confirmRegenerate"))
  ) {
    return;
  }

  const button = el("oauthStart");
  button.disabled = true;
  button.textContent = t("oauth.generating");
  try {
    const data = await api("/api/accounts/oauth/start", { method: "POST" });
    renderOAuthPending({ pending: true, ...data });
    setOAuthStatus(t("oauth.generated"), "ok");
  } catch (error) {
    setOAuthStatus(oauthErrorText(error, "oauth.startError"), "error");
  } finally {
    button.disabled = false;
    button.textContent = t("oauth.start");
  }
}

async function exchangeOAuth() {
  const field = el("oauthCode");
  const raw = field.value.trim();
  if (!raw) {
    setOAuthStatus(t("oauth.empty"), "error");
    field.focus();
    return;
  }

  const button = el("oauthExchange");
  button.disabled = true;
  button.textContent = t("oauth.adding");
  setOAuthStatus(t("oauth.contacting"));
  try {
    const data = await api("/api/accounts/oauth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: raw }),
    });
    const account = data.account || {};
    const label = accountLabel(account, true) || t("oauth.accountFallback");
    field.value = "";
    renderOAuthPending(null);
    setOAuthStatus(t("oauth.added", { account: label }), "ok");
    showToast(t("oauth.addedToast", { account: label }));
    await refreshStatus();
  } catch (error) {
    setOAuthStatus(oauthErrorText(error, "oauth.addError"), "error");
  } finally {
    button.disabled = false;
    button.textContent = t("oauth.exchange");
  }
}

async function pasteOAuthCode() {
  const field = el("oauthCode");
  try {
    const text = await navigator.clipboard.readText();
    if (!text || !text.trim()) throw new Error("empty clipboard");
    field.value = text.trim();
    field.focus();
    setOAuthStatus(t("oauth.pasted"), "ok");
  } catch (_) {
    setOAuthStatus(t("oauth.clipboardError"), "error");
  }
}

function openSyncPanel() {
  syncPanel.classList.remove("hidden");
  document.body.classList.add("lb-open");
  renderSyncDetail(state.status || {});
  refreshStatus();
  loadLog();
  if (el("addAccount").open) loadOAuthPending();
}

function closeSyncPanel() {
  syncPanel.classList.add("hidden");
  if (!state.lb) document.body.classList.remove("lb-open");
}

async function queueSync(full, accountId = undefined) {
  const target = accountId === undefined
    ? (state.account ? Number(state.account) : null)
    : accountId;
  const payload = { mode: full ? "full" : "normal" };
  if (target) payload.account_id = target;

  const account = target
    ? state.accounts.find((entry) => Number(entry.id) === target)
    : null;
  const label = target
    ? accountLabel(account, true) || `ID ${target}`
    : t("account.allTarget");

  try {
    await api("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showToast(t("sync.queued", {
      mode: full ? t("sync.mode.full") : t("sync.mode.normal"),
      account: label,
    }));
    refreshStatus();
  } catch (error) {
    showToast(error.message || t("sync.queueError"));
  }
}

function bindEvents() {
  searchInput.addEventListener(
    "input",
    debounce(() => {
      state.q = searchInput.value.trim();
      resetAndLoad();
    }, 300)
  );
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      state.q = searchInput.value.trim();
      resetAndLoad();
    }
    if (event.key === "Escape") {
      searchInput.value = "";
      state.q = "";
      resetAndLoad();
    }
  });

  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    resetAndLoad();
  });

  artistSelect.addEventListener("change", () => {
    state.artist = artistSelect.value;
    resetAndLoad();
  });

  accountSelect.addEventListener("change", () => {
    setAccount(accountSelect.value);
  });

  favoriteFilter.addEventListener("click", () => {
    state.favorites = !state.favorites;
    updateFilterUI();
    resetAndLoad();
  });

  r18Filter.addEventListener("click", () => {
    state.r18 = !state.r18;
    localStorage.setItem("pixiv-viewer-r18", state.r18 ? "1" : "0");
    updateFilterUI();
    loadTags();
    loadArtists();
    resetAndLoad();
  });

  el("clearFilters").addEventListener("click", () => {
    state.q = "";
    state.tag = "";
    state.artist = "";
    state.favorites = false;
    state.r18 = false;
    localStorage.setItem("pixiv-viewer-r18", "0");
    searchInput.value = "";
    artistSelect.value = "";
    updateFilterUI();
    loadTags();
    loadArtists();
    resetAndLoad();
  });

  el("tagBar").addEventListener("click", (event) => {
    const chip = event.target.closest(".tag-chip");
    if (!chip) return;
    state.tag = state.tag === chip.dataset.tag ? "" : chip.dataset.tag;
    loadTags();
    resetAndLoad();
  });

  grid.addEventListener("click", (event) => {
    const favorite = event.target.closest(".card-fav");
    if (favorite) {
      const card = favorite.closest(".card");
      const item = state.items[Number(card?.dataset.index)];
      if (item) toggleFavorite(item, favorite);
      return;
    }
    const card = event.target.closest(".card");
    if (card) openLightbox(Number(card.dataset.index));
  });

  grid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("button")) return;
    const card = event.target.closest(".card");
    if (card) {
      event.preventDefault();
      openLightbox(Number(card.dataset.index));
    }
  });

  el("loadMore").addEventListener("click", loadItems);
  el("emptySync").addEventListener("click", openSyncPanel);
  el("syncPill").addEventListener("click", openSyncPanel);
  document.querySelectorAll("[data-close-sync]").forEach((button) => {
    button.addEventListener("click", closeSyncPanel);
  });

  el("syncAccounts").addEventListener("click", (event) => {
    const view = event.target.closest("[data-view-account]");
    if (view) {
      setAccount(view.dataset.viewAccount);
      closeSyncPanel();
      return;
    }
    const sync = event.target.closest("[data-sync-account]");
    if (sync) {
      queueSync(false, Number(sync.dataset.syncAccount));
    }
  });

  el("oauthStart").addEventListener("click", startOAuth);
  el("oauthExchange").addEventListener("click", exchangeOAuth);
  el("oauthPaste").addEventListener("click", pasteOAuthCode);
  el("oauthCode").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      exchangeOAuth();
    }
  });
  el("addAccount").addEventListener("toggle", () => {
    if (el("addAccount").open) loadOAuthPending();
  });
  if (!navigator.clipboard || !navigator.clipboard.readText) {
    el("oauthPaste").classList.add("hidden");
  } else {
    el("oauthPaste").classList.remove("hidden");
  }

  el("syncNow").addEventListener("click", () => {
    queueSync(false);
  });

  el("fullSync").addEventListener("click", () => {
    if (!confirm(t("sync.confirmFull"))) {
      return;
    }
    queueSync(true);
  });

  el("reindexNow").addEventListener("click", async () => {
    const button = el("reindexNow");
    button.disabled = true;
    button.textContent = t("reindex.working");
    try {
      const result = await api("/api/reindex", { method: "POST" });
      showToast(t("reindex.done", { works: formatNumber(result.works) }));
      await Promise.all([loadTags(), loadArtists(), refreshStatus()]);
      resetAndLoad();
    } catch (error) {
      showToast(error.message || t("reindex.error"));
    } finally {
      button.disabled = false;
      button.textContent = t("sync.reindex");
    }
  });

  el("lbClose").addEventListener("click", closeLightbox);
  el("lbNext").addEventListener("click", nextItem);
  el("lbPrev").addEventListener("click", previousItem);
  el("lbFavorite").addEventListener("click", () => {
    const item = currentItem();
    if (item) toggleFavorite(item, el("lbFavorite"));
  });

  lbStage.addEventListener("pointerdown", (event) => {
    if (event.target.closest("video")) return;
    lbPointer = {
      x: event.clientX,
      y: event.clientY,
      time: Date.now(),
      moved: false,
    };
  });

  lbStage.addEventListener("pointermove", (event) => {
    if (!lbPointer) return;
    if (Math.hypot(event.clientX - lbPointer.x, event.clientY - lbPointer.y) > 12) {
      lbPointer.moved = true;
    }
  });

  lbStage.addEventListener("pointerup", (event) => {
    if (!lbPointer) return;
    const pointer = lbPointer;
    lbPointer = null;
    if (event.target.closest("video")) return;

    const dx = event.clientX - pointer.x;
    const dy = event.clientY - pointer.y;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy)) {
      if (dx < 0) nextItem();
      else previousItem();
      return;
    }
    if (dy > 90 && Math.abs(dy) > Math.abs(dx)) {
      closeLightbox();
      return;
    }
    if (!pointer.moved && Date.now() - pointer.time < 700) {
      // Tap zones: the left 40% goes back, the rest advances.  This keeps
      // the old "tap to next" behaviour in the centre while making the
      // left side a predictable back gesture on phones.
      const rect = lbStage.getBoundingClientRect();
      const ratio = rect.width
        ? (event.clientX - rect.left) / rect.width
        : 0.5;
      if (ratio < 0.4) previousItem();
      else nextItem();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (lightbox.classList.contains("hidden")) return;
    if (event.key === "Escape") closeLightbox();
    else if (event.key === "ArrowRight") nextItem();
    else if (event.key === "ArrowLeft") previousItem();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshStatus();
  });
}

function updateLanguage() {
  dateFormatter = createDateFormatter();
  updateFilterUI();
  updateAccountOptions(state.accounts, true);
  if (state.status) {
    updateAccountLine(state.status, state.accounts);
    el("syncLabel").textContent = statusLabel(state.status.state);
    const selected = currentAccount();
    const targetLabel = selected ? accountLabel(selected, true) : t("account.allTarget");
    el("syncNow").title = t("sync.nowTitle", { target: targetLabel });
    el("fullSync").title = t("sync.fullTitle", { target: targetLabel });
  }
  updateSyncScope();
  updateResultCount();
  if (state.items.length) {
    grid.innerHTML = "";
    renderCards(state.items, 0);
  }
  loadTags();
  loadArtists();
  if (!syncPanel.classList.contains("hidden")) {
    renderSyncDetail(state.status || {});
    if (el("addAccount").open) loadOAuthPending();
  }
  if (!lightbox.classList.contains("hidden")) renderLightbox();
  toggleEmpty();
  setOAuthStatus("");
}

async function init() {
  state.r18 = localStorage.getItem("pixiv-viewer-r18") === "1";
  state.account = localStorage.getItem("pixiv-viewer-account") || "";
  updateFilterUI();
  bindEvents();
  document.addEventListener("viewer:langchange", updateLanguage);

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadItems();
      },
      { rootMargin: "700px 0px" }
    );
    observer.observe(sentinel);
  } else {
    el("loadMore").classList.remove("hidden");
  }

  await refreshStatus();
  loadTags();
  loadArtists();
  resetAndLoad();
  setInterval(refreshStatus, 10000);
}

init();
