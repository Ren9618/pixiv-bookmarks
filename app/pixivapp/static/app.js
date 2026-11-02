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

const dateFormatter = new Intl.DateTimeFormat("ja-JP", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

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
    throw new Error("ログインが必要です");
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
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

function updateAccountOptions(accounts) {
  state.accounts = accounts;
  const previous = state.account;
  if (state.account && !accounts.some((account) => String(account.id) === state.account)) {
    state.account = "";
    localStorage.removeItem("pixiv-viewer-account");
  }

  const signature = accounts
    .map((account) => `${account.id}|${account.name}|${account.account}|${account.works}|${account.works_safe}`)
    .join(";");
  if (accountSelect.dataset.signature !== signature) {
    accountSelect.innerHTML = "";
    const all = document.createElement("option");
    all.value = "";
    all.textContent = accounts.length ? "すべてのアカウント" : "アカウント";
    accountSelect.appendChild(all);
    accounts.forEach((account) => {
      const option = document.createElement("option");
      option.value = String(account.id);
      const count = Number(account.works || 0);
      option.textContent = `${accountLabel(account, true)} (${count.toLocaleString()})`;
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
    line.textContent = `${accountLabel(selected, true)} ・ ${Number(selected.works || 0).toLocaleString()}作品`;
    return;
  }
  if (!accounts.length) {
    line.textContent = status.auth_required ? "pixiv認証待ち" : "—";
    return;
  }
  if (accounts.length === 1) {
    line.textContent = `${accountLabel(accounts[0], true)} ・ ${Number(accounts[0].works || 0).toLocaleString()}作品`;
  } else {
    line.textContent = `全${accounts.length}アカウント ・ ${(status.counts?.works || 0).toLocaleString()}作品`;
  }
}

function updateSyncScope() {
  const scope = el("syncScope");
  const selected = currentAccount();
  if (selected) {
    scope.textContent = `同期対象: ${accountLabel(selected, true)}（このアカウントのみ）`;
  } else {
    scope.textContent = "同期対象: 全アカウント";
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
  if (total < 60) return `${total}秒`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${minutes}分${rest}秒` : `${minutes}分`;
}

function updateResultCount() {
  resultCount.textContent = state.total
    ? `${state.total.toLocaleString()}作品`
    : "";
}

function updateFilterUI() {
  favoriteFilter.classList.toggle("active", state.favorites);
  r18Filter.classList.toggle("active", state.r18);
  favoriteFilter.setAttribute("aria-pressed", String(state.favorites));
  r18Filter.setAttribute("aria-pressed", String(state.r18));
  r18Filter.textContent = state.r18 ? "R-18 非表示" : "R-18 表示";
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
      showToast(error.message || "作品を読み込めませんでした");
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
    card.setAttribute("aria-label", item.title || `作品 ${item.id}`);

    const thumb = document.createElement("div");
    thumb.className = "card-thumb";

    const image = document.createElement("img");
    image.loading = "lazy";
    image.decoding = "async";
    image.src = item.thumb_url;
    image.alt = item.title || `作品 ${item.id}`;
    thumb.appendChild(image);

    const shade = document.createElement("div");
    shade.className = "card-shade";
    thumb.appendChild(shade);

    const badgeParts = [];
    if (item.is_video) badgeParts.push("▶ 動画");
    if (item.page_count > 1) badgeParts.push(`${item.page_count}枚`);
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
    title.textContent = item.title || `作品 ${item.id}`;
    info.appendChild(title);

    const artist = document.createElement("div");
    artist.className = "card-artist";
    artist.textContent = item.artist_name || "不明な作者";
    info.appendChild(artist);
    thumb.appendChild(info);

    const favorite = document.createElement("button");
    favorite.type = "button";
    favorite.className = "card-fav";
    favorite.dataset.favId = String(item.id);
    favorite.textContent = item.favorited ? "★" : "☆";
    favorite.classList.toggle("active", item.favorited);
    favorite.setAttribute("aria-label", "お気に入り");
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
    title.textContent = "初回同期中です";
    body.textContent = "ブックマークを取得しています。完了すると自動的に表示されます。";
  } else if (status.state === "auth_required") {
    title.textContent = "pixiv認証が必要です";
    body.textContent = "サーバーでOAuth認証を完了してから「今すぐ同期」を実行してください。";
  } else if (status.state === "error") {
    title.textContent = "同期でエラーが発生しました";
    body.textContent = "同期ステータスを開いてログを確認してください。";
  } else if (state.account) {
    const account = currentAccount();
    title.textContent = `${accountLabel(account, true) || "選択中のアカウント"}の作品がありません`;
    body.textContent = "同期が完了すると表示されます。別のアカウントに切り替えることもできます。";
  } else {
    title.textContent = "まだ作品がありません";
    body.textContent = "初回同期が終わると、ここにブックマークが並びます。";
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
    showToast(error.message || "お気に入りを更新できませんでした");
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
    lbFavorite.textContent = item.favorited ? "★ お気に入り" : "☆ お気に入り";
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

  el("lbTitle").textContent = item.title || `作品 ${item.id}`;
  el("lbArtist").textContent = [
    item.artist_name || "不明な作者",
    item.artist_account ? `@${item.artist_account}` : "",
    item.x_restrict === 2 ? "R-18G" : item.x_restrict === 1 ? "R-18" : "",
  ].filter(Boolean).join(" ・ ");

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
    lbImage.alt = item.title || `作品 ${item.id}`;
  }

  const counterParts = [
    `作品 ${state.lb.index + 1} / ${state.items.length}${state.done ? "" : "+"}`,
  ];
  if (item.pages.length > 1) {
    counterParts.push(`${state.lb.page + 1} / ${item.pages.length}`);
  }
  el("lbCounter").textContent = counterParts.join(" ・ ");

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
  favorite.textContent = item.favorited ? "★ お気に入り" : "☆ お気に入り";
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
  showToast("最後の作品です");
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
  showToast("最初の作品です");
}

function statusLabel(status) {
  return {
    idle: "同期OK",
    running: "同期中",
    error: "エラー",
    auth_required: "要認証",
    stopped: "停止",
  }[status] || "確認中";
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
    empty.textContent = "pixivアカウントが未登録です。setup_auth.py で認証してください。";
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
      `${works.toLocaleString()}作品`,
      `最終同期 ${formatEpoch(account.last_sync_ts)}`,
    ];
    if (works > safe) parts.push(`R-18 ${(works - safe).toLocaleString()}`);
    meta.textContent = parts.join(" ・ ");
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
    view.textContent = selected ? "表示中" : "表示";
    view.disabled = selected;
    actions.appendChild(view);

    const sync = document.createElement("button");
    sync.type = "button";
    sync.className = "account-action primary";
    sync.dataset.syncAccount = String(account.id);
    sync.textContent = running ? "同期中" : "同期";
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
  heading.textContent = statusLabel(status.state) + " — " + (status.message || "状態不明");
  const sub = document.createElement("p");
  const selected = currentAccount();
  const accountText = accounts.length
    ? `${accounts.length}アカウント${selected ? ` ・ ${accountLabel(selected, true)} を表示中` : " ・ すべて表示"}`
    : "pixiv未認証";
  sub.textContent = `${accountText} ・ 最終更新 ${formatDate(status.updated_at)}`;
  hero.append(heading, sub);
  detail.appendChild(hero);

  const cells = document.createElement("div");
  cells.className = "status-grid";
  cells.append(
    statusCell("最終同期", formatDate(status.finished_at)),
    statusCell("次回", status.sync_queued ? "リクエスト受付済み" : formatDate(status.next_run)),
    statusCell("作品数", (status.counts?.works || 0).toLocaleString()),
    statusCell("画像数", (status.counts?.images || 0).toLocaleString()),
    statusCell("お気に入り", (status.counts?.favorites || 0).toLocaleString()),
    statusCell("前回の新規", status.last_new_works === null || status.last_new_works === undefined ? "—" : `${status.last_new_works}作品`),
    statusCell("所要時間", formatDuration(status.last_duration_sec)),
    statusCell("モード", status.full_sync ? "全件確認" : "差分"),
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
    const targetLabel = selected ? accountLabel(selected, true) : "全アカウント";
    el("syncNow").title = `${targetLabel}を差分同期`;
    el("fullSync").title = `${targetLabel}を全件再同期`;

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
    el("syncLabel").textContent = "接続エラー";
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
      if (entry.count) button.title = `${entry.count}作品`;
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
    artistSelect.innerHTML = '<option value="">すべての作者</option>';
    data.artists.forEach((artist) => {
      const option = document.createElement("option");
      option.value = String(artist.id);
      option.textContent = `${artist.name} (${artist.count})`;
      artistSelect.appendChild(option);
    });
    if (selected && !data.artists.some((artist) => String(artist.id) === selected)) {
      const option = document.createElement("option");
      option.value = selected;
      option.textContent = `作者ID ${selected}`;
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
    log.textContent = data.lines.length ? data.lines.join("\n") : "ログはまだありません。";
    log.scrollTop = log.scrollHeight;
  } catch (error) {
    el("logTail").textContent = error.message || "ログを読み込めませんでした";
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
  info.textContent = `発行済み・あと約${minutes}分`;
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
    !confirm(
      "ログインURLを発行し直すと、以前のURLで取得したcodeは使えなくなります。続けますか？"
    )
  ) {
    return;
  }

  const button = el("oauthStart");
  button.disabled = true;
  button.textContent = "発行中…";
  try {
    const data = await api("/api/accounts/oauth/start", { method: "POST" });
    renderOAuthPending({ pending: true, ...data });
    setOAuthStatus(
      "ログインURLを発行しました。リンクを開き、ログインする前にDevToolsのNetworkで「Preserve log」を有効にしてください。",
      "ok"
    );
  } catch (error) {
    setOAuthStatus(error.message || "ログインURLを発行できませんでした", "error");
  } finally {
    button.disabled = false;
    button.textContent = "ログインURLを発行";
  }
}

async function exchangeOAuth() {
  const field = el("oauthCode");
  const raw = field.value.trim();
  if (!raw) {
    setOAuthStatus("コールバックURLまたは code を貼り付けてください。", "error");
    field.focus();
    return;
  }

  const button = el("oauthExchange");
  button.disabled = true;
  button.textContent = "追加中…";
  setOAuthStatus("pixivに問い合わせています…");
  try {
    const data = await api("/api/accounts/oauth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: raw }),
    });
    const account = data.account || {};
    const label = accountLabel(account, true) || "アカウント";
    field.value = "";
    renderOAuthPending(null);
    setOAuthStatus(
      `${label} を追加しました。このアカウントの初回同期をキューに入れました。`,
      "ok"
    );
    showToast(`${label} を追加しました`);
    await refreshStatus();
  } catch (error) {
    setOAuthStatus(error.message || "アカウントを追加できませんでした", "error");
  } finally {
    button.disabled = false;
    button.textContent = "このアカウントを追加";
  }
}

async function pasteOAuthCode() {
  const field = el("oauthCode");
  try {
    const text = await navigator.clipboard.readText();
    if (!text || !text.trim()) throw new Error("empty clipboard");
    field.value = text.trim();
    field.focus();
    setOAuthStatus(
      "クリップボードから貼り付けました。内容を確認して「このアカウントを追加」を押してください。",
      "ok"
    );
  } catch (_) {
    setOAuthStatus(
      "クリップボードを読めませんでした。欄をタップして手動で貼り付けてください。",
      "error"
    );
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
  const label = target ? accountLabel(account, true) || `ID ${target}` : "全アカウント";

  try {
    await api("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showToast(`${full ? "全件再同期" : "同期"}をキューに追加しました（${label}）`);
    refreshStatus();
  } catch (error) {
    showToast(error.message || "同期を開始できませんでした");
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
    if (!confirm("全件を再確認します。既存ファイルはそのままに、不足分を再取得します。時間がかかることがあります。")) {
      return;
    }
    queueSync(true);
  });

  el("reindexNow").addEventListener("click", async () => {
    const button = el("reindexNow");
    button.disabled = true;
    button.textContent = "処理中…";
    try {
      const result = await api("/api/reindex", { method: "POST" });
      showToast(`再インデックス完了: ${result.works}作品`);
      await Promise.all([loadTags(), loadArtists(), refreshStatus()]);
      resetAndLoad();
    } catch (error) {
      showToast(error.message || "再インデックスに失敗しました");
    } finally {
      button.disabled = false;
      button.textContent = "再インデックス";
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

async function init() {
  state.r18 = localStorage.getItem("pixiv-viewer-r18") === "1";
  state.account = localStorage.getItem("pixiv-viewer-account") || "";
  updateFilterUI();
  bindEvents();

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
