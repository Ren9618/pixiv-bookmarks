"use strict";

(function () {
  const STORAGE_KEY = "pixiv-viewer-lang";
  const SUPPORTED = new Set(["ja", "en"]);

  const MESSAGES = {
    ja: {
      "common.loading": "読み込み中…",
      "common.close": "閉じる",
      "common.separator": " ・ ",

      "header.accountLoading": "読み込み中…",
      "header.syncStatus": "同期ステータスを開く",
      "header.checking": "確認中",
      "header.logout": "ログアウト",

      "filter.label": "フィルター",
      "filter.clear": "クリア",
      "search.placeholder": "タイトル・作者・タグを検索",
      "sort.label": "並び順",
      "sort.added": "追加が新しい順",
      "sort.created": "投稿が新しい順",
      "sort.popular": "人気順",
      "sort.title": "タイトル順",
      "account.filter": "アカウントで絞り込み",
      "account.all": "すべてのアカウント",
      "account.none": "アカウント",
      "favorite.filter": "★ お気に入り",
      "r18.show": "R-18 表示",
      "r18.hide": "R-18 非表示",
      "artist.filter": "作者で絞り込み",
      "artist.all": "すべての作者",
      "artist.id": "作者ID {id}",
      "tags.label": "タグ",

      "collection.filter": "コレクションで絞り込み",
      "collection.all": "すべてのコレクション",
      "collection.none": "コレクション",

      "tag.mode.and": "AND",
      "tag.mode.or": "OR",
      "tag.mode.andTitle": "選択したタグをすべて含む",
      "tag.mode.orTitle": "選択したタグのいずれかを含む",

      "selection.enter": "選択",
      "selection.exit": "選択を終了",
      "selection.addOne": "この作品を選択",
      "selection.removeOne": "この作品の選択を解除",
      "selection.toolbar": "選択した作品の操作",
      "selection.count": "{count}件を選択中",
      "selection.selectAllLoaded": "表示中をすべて選択",
      "selection.clearLoaded": "表示中の選択を解除",
      "selection.addToCollection": "コレクションに追加",
      "selection.removeFromCollection": "コレクションから外す",
      "selection.delete": "削除",
      "selection.deleteConfirm": "{count}件をローカルから削除します。画像・サムネイルも削除され、Pixivのブックマークは変更されません。元に戻せません。続けますか？",
      "selection.deleted": "{count}件を削除しました",
      "selection.deleteError": "削除できませんでした",
      "selection.addedToCollection": "{count}件を「{name}」に追加しました",
      "selection.addCollectionError": "コレクションに追加できませんでした",
      "selection.removedFromCollection": "{count}件を「{name}」から外しました",
      "selection.removeCollectionError": "コレクションから外せませんでした",
      "selection.required": "作品を選択してください。",
      "selection.noCollections": "先にグループ画面でコレクションを作成してください。",

      "group.open": "グループ",
      "group.title": "グループ",
      "group.tab.collections": "作品コレクション",
      "group.tab.tagSets": "タグセット",
      "group.selectionHint": "選択中の{count}件をコレクションに追加できます。",
      "group.noSelectionHint": "作品を選択すると、選択分をまとめてコレクションへ追加できます。",
      "group.collection.placeholder": "例: お気に入りイラスト",
      "group.collection.create": "作成",
      "group.collection.created": "「{name}」を作成しました",
      "group.collection.createError": "コレクションを作成できませんでした",
      "group.collection.nameRequired": "コレクション名を入力してください",
      "group.collection.empty": "コレクションはまだありません。",
      "group.collection.view": "表示",
      "group.collection.viewing": "表示中",
      "group.collection.rename": "名前変更",
      "group.collection.renamePrompt": "新しいコレクション名",
      "group.collection.renamed": "名前を変更しました",
      "group.collection.renameError": "名前を変更できませんでした",
      "group.collection.delete": "削除",
      "group.collection.deleteConfirm": "コレクション「{name}」を削除します。作品自体は削除されません。",
      "group.collection.deleted": "コレクションを削除しました",
      "group.collection.deleteError": "コレクションを削除できませんでした",
      "group.collection.addSelected": "選択中の{count}件を追加",
      "group.collection.addSelectedDone": "「{name}」に{count}件を追加しました",
      "group.collection.addSelectedError": "選択した作品を追加できませんでした",
      "group.tagBulk.title": "タグから一括追加",
      "group.tagBulk.target": "追加先",
      "group.tagBulk.mode": "一致条件",
      "group.tagBulk.tags": "追加するタグ",
      "group.tagBulk.inputPlaceholder": "タグを入力して追加",
      "group.tagBulk.addTag": "タグを追加",
      "group.tagBulk.add": "一致する作品を追加",
      "group.tagBulk.empty": "タグを1つ以上選んでください。",
      "group.tagBulk.noCollections": "コレクションを作成すると、タグからまとめて追加できます。",
      "group.tagBulk.added": "{matched}件が一致し、{added}件を追加しました",
      "group.tagBulk.error": "タグから追加できませんでした",
      "group.mode.and": "すべて含む (AND)",
      "group.mode.or": "いずれかを含む (OR)",
      "group.mode.short.and": "AND",
      "group.mode.short.or": "OR",
      "group.tagSets.current": "現在のタグ: {tags}",
      "group.tagSets.currentEmpty": "タグが選択されていません。先にタグを選ぶと、その組み合わせを保存できます。",
      "group.tagSets.placeholder": "例: 風景",
      "group.tagSets.save": "現在のタグを保存",
      "group.tagSets.saved": "タグセット「{name}」を保存しました",
      "group.tagSets.saveError": "タグセットを保存できませんでした",
      "group.tagSets.nameRequired": "セット名を入力してください",
      "group.tagSets.empty": "タグセットはまだありません。",
      "group.tagSets.apply": "適用",
      "group.tagSets.delete": "削除",
      "group.tagSets.deleteConfirm": "タグセット「{name}」を削除します。",
      "group.tagSets.deleted": "タグセットを削除しました",
      "group.tagSets.deleteError": "タグセットを削除できませんでした",
      "group.tagSets.applied": "「{name}」を適用しました",
      "group.tagSets.tags": "{count}タグ",

      "empty.noWorks": "まだ作品がありません",
      "empty.noWorksBody": "初回同期が終わると、ここにブックマークが並びます。",
      "empty.checkSync": "同期状態を確認",
      "loading.more": "読み込み中…",
      "loadMore": "もっと見る",

      "card.untitled": "作品 {id}",
      "card.video": "▶ 動画",
      "card.pages": "{count}枚",
      "card.unknownArtist": "不明な作者",
      "card.favorite": "お気に入り",

      "sync.title": "同期ステータス",
      "sync.addAccount": "＋ pixivアカウントを追加",
      "sync.addAccountLead": "この画面だけで追加できます。サーバーへのSSHは不要です。<code>code</code> は発行から数十秒で失効するため、ログイン後すぐに貼り付けてください。",
      "sync.step1": "「ログインURLを発行」を押し、表示されたリンクを開きます。",
      "sync.step2": "<strong>ログインする前に</strong> <kbd>F12</kbd>（Macは <kbd>⌘</kbd>+<kbd>⌥</kbd>+<kbd>I</kbd>）で開発者ツールを開き、<b>Network</b> タブの <b>Preserve log</b> を有効にします。",
      "sync.step3": "追加したいアカウントでログインします。白いページ、またはpixivアプリへ移動したような画面になりますが、正常です。",
      "sync.step4": "Network 一覧の <code>callback?…code=…</code> を右クリック →「Copy link address」（Firefoxは「URLをコピー」）でURLをコピーします。検索欄に <code>callback</code> と入れると絞り込めます。",
      "sync.step5": "下の欄に貼り付けて「このアカウントを追加」を押します。",
      "oauth.start": "ログインURLを発行",
      "oauth.openLogin": "pixivログインを開く",
      "oauth.field": "コールバックURL または code",
      "oauth.exchange": "このアカウントを追加",
      "oauth.paste": "クリップボードから貼り付け",
      "oauth.trouble": "うまくいかないとき: ログイン済みの状態で「pixivログインを開く」を押すと新しい <code>code</code> が発行されます。Network の記録が空の場合は、DevToolsを開いたまま再読み込みしてください。",
      "sync.scopeAll": "同期対象: 全アカウント",
      "sync.scopeSelected": "同期対象: {account}（このアカウントのみ）",
      "sync.now": "今すぐ同期",
      "sync.reindex": "再インデックス",
      "sync.full": "全件再同期",
      "sync.log": "同期ログ",

      "lightbox.viewer": "作品ビューア",
      "lightbox.hint": "左タップで戻る ・ 右タップで次へ",
      "lightbox.prev": "前へ",
      "lightbox.next": "次へ",
      "lightbox.favoriteOn": "★ お気に入り",
      "lightbox.favoriteOff": "☆ お気に入り",
      "lightbox.pixiv": "pixiv で開く",
      "lightbox.original": "原寸",
      "lightbox.download": "保存",
      "lightbox.delete": "ローカル削除",
      "lightbox.deleteConfirm": "「{title}」をローカルから削除します。画像・サムネイルも削除され、Pixivのブックマークは変更されません。元に戻せません。",
      "lightbox.deleted": "作品を削除しました",
      "lightbox.counter": "作品 {index} / {total}{plus}",
      "lightbox.pages": "{page} / {total}",

      "empty.syncingTitle": "初回同期中です",
      "empty.syncingBody": "ブックマークを取得しています。完了すると自動的に表示されます。",
      "empty.authTitle": "pixiv認証が必要です",
      "empty.authBody": "サーバーでOAuth認証を完了してから「今すぐ同期」を実行してください。",
      "empty.errorTitle": "同期でエラーが発生しました",
      "empty.errorBody": "同期ステータスを開いてログを確認してください。",
      "empty.accountTitle": "{account}の作品がありません",
      "empty.accountFallback": "選択中のアカウント",
      "empty.accountBody": "同期が完了すると表示されます。別のアカウントに切り替えることもできます。",

      "toast.lastItem": "最後の作品です",
      "toast.firstItem": "最初の作品です",

      "error.loginRequired": "ログインが必要です",
      "error.loadWorks": "作品を読み込めませんでした",
      "error.favoriteUpdate": "お気に入りを更新できませんでした",
      "error.nameExists": "同じ名前が既にあります。",
      "error.tagsRequired": "タグを選択してください。",
      "error.worksRequired": "作品を選択してください。",

      "status.idle": "同期OK",
      "status.running": "同期中",
      "status.error": "エラー",
      "status.auth_required": "要認証",
      "status.stopped": "停止",
      "status.unknownLabel": "確認中",
      "status.unknown": "状態不明",
      "status.message.idle": "同期完了: 新規 {new} 作品 / 全 {works} 作品（{accounts}）",
      "status.message.running": "{accounts}のブックマークを同期中です…",
      "status.message.error": "一部のアカウントで同期エラーが発生しました。ログを確認してください。",
      "status.message.authRequired": "pixivの認証が無効になりました。再認証してください。",
      "status.message.stopped": "停止しました",
      "status.subSelected": "{accounts} ・ {account} を表示中",
      "status.subAll": "{accounts} ・ すべて表示",
      "status.subNoAccounts": "pixiv未認証",
      "status.lastUpdated": "最終更新 {date}",
      "status.cell.lastSync": "最終同期",
      "status.cell.next": "次回",
      "status.cell.queued": "リクエスト受付済み",
      "status.cell.works": "作品数",
      "status.cell.images": "画像数",
      "status.cell.favorites": "お気に入り",
      "status.cell.new": "前回の新規",
      "status.cell.duration": "所要時間",
      "status.cell.mode": "モード",
      "status.mode.full": "全件確認",
      "status.mode.incremental": "差分",
      "status.connectionError": "接続エラー",

      "sync.nowTitle": "{target}を差分同期",
      "sync.fullTitle": "{target}を全件再同期",
      "account.allTarget": "全アカウント",
      "account.noneRegistered": "pixivアカウントが未登録です。setup_auth.py で認証してください。",
      "account.lastSync": "最終同期 {date}",
      "account.r18": "R-18 {count}",
      "account.viewing": "表示中",
      "account.view": "表示",
      "account.syncing": "同期中",
      "account.sync": "同期",
      "account.id": "作者ID {id}",

      "tag.title": "{count}作品",
      "log.empty": "ログはまだありません。",
      "log.loadError": "ログを読み込めませんでした",

      "oauth.pending": "発行済み・あと約{minutes}分",
      "oauth.confirmRegenerate": "ログインURLを発行し直すと、以前のURLで取得したcodeは使えなくなります。続けますか？",
      "oauth.generating": "発行中…",
      "oauth.generated": "ログインURLを発行しました。リンクを開き、ログインする前にDevToolsのNetworkで「Preserve log」を有効にしてください。",
      "oauth.startError": "ログインURLを発行できませんでした",
      "oauth.empty": "コールバックURLまたは code を貼り付けてください。",
      "oauth.adding": "追加中…",
      "oauth.contacting": "pixivに問い合わせています…",
      "oauth.added": "{account} を追加しました。このアカウントの初回同期をキューに入れました。",
      "oauth.addedToast": "{account} を追加しました",
      "oauth.addError": "アカウントを追加できませんでした",
      "oauth.accountFallback": "アカウント",
      "oauth.pasted": "クリップボードから貼り付けました。内容を確認して「このアカウントを追加」を押してください。",
      "oauth.clipboardError": "クリップボードを読めませんでした。欄をタップして手動で貼り付けてください。",
      "oauth.error.missing_code": "コールバックURLまたは code を貼り付けてください。",
      "oauth.error.pending_missing": "ログインURLの準備データがありません。「ログインURLを発行」からやり直してください。",
      "oauth.error.pending_corrupt": "ログインURLの準備データが壊れています。「ログインURLを発行」からやり直してください。",
      "oauth.error.code_rejected": "pixivがcodeを受け付けませんでした。codeは発行から数十秒で失効します。「ログインURLを発行」からやり直し、ログイン後すぐに貼り付けてください。",
      "oauth.error.network_error": "pixivへの通信に失敗しました。",
      "oauth.error.invalid_response": "pixivからJSON以外の応答が返りました。時間をおいてやり直してください。",
      "oauth.error.refresh_token_missing": "refresh_token を取得できませんでした。",
      "oauth.error.user_id_missing": "pixivのユーザーIDを取得できませんでした。",
      "oauth.error.store_failed": "ログインURLを保存できませんでした。",

      "sync.queued": "{mode}をキューに追加しました（{account}）",
      "sync.mode.full": "全件再同期",
      "sync.mode.normal": "同期",
      "sync.queueError": "同期を開始できませんでした",
      "sync.confirmFull": "全件を再確認します。既存ファイルはそのままに、不足分を再取得します。時間がかかることがあります。",

      "reindex.working": "処理中…",
      "reindex.done": "再インデックス完了: {works}作品",
      "reindex.error": "再インデックスに失敗しました",

      "login.pageTitle": "ログイン | {app}",
      "login.subtitle": "ブックマークビューワー",
      "login.error.invalid_password": "パスワードが違います。",
      "login.password": "パスワード",
      "login.open": "開く",
      "login.note": "Tailscale または自宅LANからのみアクセスできます。",
    },

    en: {
      "common.loading": "Loading…",
      "common.close": "Close",
      "common.separator": " · ",

      "header.accountLoading": "Loading…",
      "header.syncStatus": "Open sync status",
      "header.checking": "Checking…",
      "header.logout": "Log out",

      "filter.label": "Filters",
      "filter.clear": "Clear",
      "search.placeholder": "Search titles, artists, and tags",
      "sort.label": "Sort order",
      "sort.added": "Recently added",
      "sort.created": "Newest posts",
      "sort.popular": "Popular",
      "sort.title": "Title",
      "account.filter": "Filter by account",
      "account.all": "All accounts",
      "account.none": "Accounts",
      "favorite.filter": "★ Favorites",
      "r18.show": "Show R-18",
      "r18.hide": "Hide R-18",
      "artist.filter": "Filter by artist",
      "artist.all": "All artists",
      "artist.id": "Artist ID {id}",
      "tags.label": "Tags",

      "collection.filter": "Filter by collection",
      "collection.all": "All collections",
      "collection.none": "Collections",

      "tag.mode.and": "AND",
      "tag.mode.or": "OR",
      "tag.mode.andTitle": "Works must contain every selected tag",
      "tag.mode.orTitle": "Works can contain any selected tag",

      "selection.enter": "Select",
      "selection.exit": "Exit selection",
      "selection.addOne": "Select this work",
      "selection.removeOne": "Deselect this work",
      "selection.toolbar": "Selected artwork actions",
      "selection.count": "{count} selected",
      "selection.selectAllLoaded": "Select all shown",
      "selection.clearLoaded": "Clear shown selection",
      "selection.addToCollection": "Add to collection",
      "selection.removeFromCollection": "Remove from collection",
      "selection.delete": "Delete",
      "selection.deleteConfirm": "Delete {count} works locally? Their images and thumbnails will be removed. Your pixiv bookmarks are not changed. This cannot be undone.",
      "selection.deleted": "Deleted {count} works",
      "selection.deleteError": "Could not delete the selected works",
      "selection.addedToCollection": "Added {count} works to \"{name}\"",
      "selection.addCollectionError": "Could not add the works to the collection",
      "selection.removedFromCollection": "Removed {count} works from \"{name}\"",
      "selection.removeCollectionError": "Could not remove the works from the collection",
      "selection.required": "Select at least one work.",
      "selection.noCollections": "Create a collection in the Groups panel first.",

      "group.open": "Groups",
      "group.title": "Groups",
      "group.tab.collections": "Work collections",
      "group.tab.tagSets": "Tag sets",
      "group.selectionHint": "You can add the {count} selected works to a collection.",
      "group.noSelectionHint": "Select works first to add them to a collection in bulk.",
      "group.collection.placeholder": "e.g. Favorite illustrations",
      "group.collection.create": "Create",
      "group.collection.created": "Created \"{name}\"",
      "group.collection.createError": "Could not create the collection",
      "group.collection.nameRequired": "Enter a collection name",
      "group.collection.empty": "No collections yet.",
      "group.collection.view": "View",
      "group.collection.viewing": "Viewing",
      "group.collection.rename": "Rename",
      "group.collection.renamePrompt": "New collection name",
      "group.collection.renamed": "Collection renamed",
      "group.collection.renameError": "Could not rename the collection",
      "group.collection.delete": "Delete",
      "group.collection.deleteConfirm": "Delete the collection \"{name}\"? The works themselves are kept.",
      "group.collection.deleted": "Collection deleted",
      "group.collection.deleteError": "Could not delete the collection",
      "group.collection.addSelected": "Add {count} selected",
      "group.collection.addSelectedDone": "Added {count} works to \"{name}\"",
      "group.collection.addSelectedError": "Could not add the selected works",
      "group.tagBulk.title": "Add in bulk by tag",
      "group.tagBulk.target": "Add to",
      "group.tagBulk.mode": "Match",
      "group.tagBulk.tags": "Tags to add",
      "group.tagBulk.inputPlaceholder": "Type a tag and add it",
      "group.tagBulk.addTag": "Add tag",
      "group.tagBulk.add": "Add matching works",
      "group.tagBulk.empty": "Select at least one tag.",
      "group.tagBulk.noCollections": "Create a collection to add matching works by tag.",
      "group.tagBulk.added": "{matched} matched, {added} added",
      "group.tagBulk.error": "Could not add works by tag",
      "group.mode.and": "Match all (AND)",
      "group.mode.or": "Match any (OR)",
      "group.mode.short.and": "AND",
      "group.mode.short.or": "OR",
      "group.tagSets.current": "Current tags: {tags}",
      "group.tagSets.currentEmpty": "No tags are selected. Choose tags first to save the combination.",
      "group.tagSets.placeholder": "e.g. Scenery",
      "group.tagSets.save": "Save current tags",
      "group.tagSets.saved": "Saved tag set \"{name}\"",
      "group.tagSets.saveError": "Could not save the tag set",
      "group.tagSets.nameRequired": "Enter a tag set name",
      "group.tagSets.empty": "No tag sets yet.",
      "group.tagSets.apply": "Apply",
      "group.tagSets.delete": "Delete",
      "group.tagSets.deleteConfirm": "Delete the tag set \"{name}\"?",
      "group.tagSets.deleted": "Tag set deleted",
      "group.tagSets.deleteError": "Could not delete the tag set",
      "group.tagSets.applied": "Applied \"{name}\"",
      "group.tagSets.tags": "{count} tags",

      "empty.noWorks": "No works yet",
      "empty.noWorksBody": "Bookmarks will appear here after the first sync.",
      "empty.checkSync": "Check sync status",
      "loading.more": "Loading…",
      "loadMore": "Load more",

      "card.untitled": "Artwork {id}",
      "card.video": "▶ Video",
      "card.pages": "{count} pages",
      "card.unknownArtist": "Unknown artist",
      "card.favorite": "Favorite",

      "sync.title": "Sync status",
      "sync.addAccount": "+ Add pixiv account",
      "sync.addAccountLead": "You can add an account here. No SSH access is needed. The <code>code</code> expires within seconds, so paste it immediately after logging in.",
      "sync.step1": "Press <b>Generate login URL</b> and open the link that appears.",
      "sync.step2": "<strong>Before logging in</strong>, open developer tools with <kbd>F12</kbd> (on Mac, <kbd>⌘</kbd>+<kbd>⌥</kbd>+<kbd>I</kbd>) and enable <b>Preserve log</b> in the <b>Network</b> tab.",
      "sync.step3": "Log in with the account you want to add. A blank page or a screen that looks like it is opening the pixiv app is normal.",
      "sync.step4": "In the Network list, right-click the <code>callback?…code=…</code> request and choose <b>Copy link address</b> (Firefox: <b>Copy URL</b>). Typing <code>callback</code> in the filter box makes it easier to find.",
      "sync.step5": "Paste it into the field below and press <b>Add this account</b>.",
      "oauth.start": "Generate login URL",
      "oauth.openLogin": "Open pixiv login",
      "oauth.field": "Callback URL or code",
      "oauth.exchange": "Add this account",
      "oauth.paste": "Paste from clipboard",
      "oauth.trouble": "If it doesn't work: while logged in, press <b>Open pixiv login</b> to issue a new <code>code</code>. If the Network log is empty, reload the page with DevTools open.",
      "sync.scopeAll": "Sync target: All accounts",
      "sync.scopeSelected": "Sync target: {account} (this account only)",
      "sync.now": "Sync now",
      "sync.reindex": "Reindex",
      "sync.full": "Full resync",
      "sync.log": "Sync log",

      "lightbox.viewer": "Artwork viewer",
      "lightbox.hint": "Tap left to go back · Tap right to go forward",
      "lightbox.prev": "Previous",
      "lightbox.next": "Next",
      "lightbox.favoriteOn": "★ Favorite",
      "lightbox.favoriteOff": "☆ Favorite",
      "lightbox.pixiv": "Open on pixiv",
      "lightbox.original": "Original",
      "lightbox.download": "Save",
      "lightbox.delete": "Delete local copy",
      "lightbox.deleteConfirm": "Delete \"{title}\" locally? Its images and thumbnails will be removed. Your pixiv bookmarks are not changed. This cannot be undone.",
      "lightbox.deleted": "Work deleted",
      "lightbox.counter": "Artwork {index} / {total}{plus}",
      "lightbox.pages": "Page {page} / {total}",

      "empty.syncingTitle": "Initial sync in progress",
      "empty.syncingBody": "Fetching bookmarks. They will appear automatically when complete.",
      "empty.authTitle": "pixiv authentication required",
      "empty.authBody": "Complete OAuth authentication on the server, then run \"Sync now\".",
      "empty.errorTitle": "Sync error",
      "empty.errorBody": "Open sync status and check the log.",
      "empty.accountTitle": "No works for {account}",
      "empty.accountFallback": "the selected account",
      "empty.accountBody": "They will appear when sync completes. You can also switch to another account.",

      "toast.lastItem": "This is the last artwork.",
      "toast.firstItem": "This is the first artwork.",

      "error.loginRequired": "Login required",
      "error.loadWorks": "Could not load works",
      "error.favoriteUpdate": "Could not update favorites",
      "error.nameExists": "That name already exists.",
      "error.tagsRequired": "Select at least one tag.",
      "error.worksRequired": "Select at least one work.",

      "status.idle": "Sync OK",
      "status.running": "Syncing",
      "status.error": "Error",
      "status.auth_required": "Auth required",
      "status.stopped": "Stopped",
      "status.unknownLabel": "Checking…",
      "status.unknown": "Unknown status",
      "status.message.idle": "Sync complete: {new} new / {works} total ({accounts})",
      "status.message.running": "Syncing bookmarks for {accounts}…",
      "status.message.error": "Some accounts failed to sync. Check the log.",
      "status.message.authRequired": "pixiv authentication is no longer valid. Please re-authenticate.",
      "status.message.stopped": "Stopped",
      "status.subSelected": "{accounts} · viewing {account}",
      "status.subAll": "{accounts} · all accounts",
      "status.subNoAccounts": "pixiv not authenticated",
      "status.lastUpdated": "Last updated {date}",
      "status.cell.lastSync": "Last sync",
      "status.cell.next": "Next",
      "status.cell.queued": "Queued",
      "status.cell.works": "Works",
      "status.cell.images": "Images",
      "status.cell.favorites": "Favorites",
      "status.cell.new": "New last run",
      "status.cell.duration": "Duration",
      "status.cell.mode": "Mode",
      "status.mode.full": "Full",
      "status.mode.incremental": "Incremental",
      "status.connectionError": "Connection error",

      "sync.nowTitle": "Sync {target} (incremental)",
      "sync.fullTitle": "Full resync {target}",
      "account.allTarget": "All accounts",
      "account.noneRegistered": "No pixiv account is registered. Authenticate with setup_auth.py.",
      "account.lastSync": "Last sync {date}",
      "account.r18": "R-18 {count}",
      "account.viewing": "Viewing",
      "account.view": "View",
      "account.syncing": "Syncing",
      "account.sync": "Sync",
      "account.id": "Artist ID {id}",

      "tag.title": "{count} works",
      "log.empty": "No log entries yet.",
      "log.loadError": "Could not load the log",

      "oauth.pending": "Generated · about {minutes} min left",
      "oauth.confirmRegenerate": "Generating a new login URL invalidates codes from the previous URL. Continue?",
      "oauth.generating": "Generating…",
      "oauth.generated": "Login URL generated. Open the link and enable \"Preserve log\" in DevTools' Network tab before logging in.",
      "oauth.startError": "Could not generate a login URL",
      "oauth.empty": "Paste the callback URL or code.",
      "oauth.adding": "Adding…",
      "oauth.contacting": "Contacting pixiv…",
      "oauth.added": "Added {account}. Initial sync has been queued.",
      "oauth.addedToast": "Added {account}",
      "oauth.addError": "Could not add the account",
      "oauth.accountFallback": "account",
      "oauth.pasted": "Pasted from the clipboard. Check it and press \"Add this account\".",
      "oauth.clipboardError": "Could not read the clipboard. Tap the field and paste manually.",
      "oauth.error.missing_code": "Paste the callback URL or code.",
      "oauth.error.pending_missing": "The login URL data is missing. Start again with \"Generate login URL\".",
      "oauth.error.pending_corrupt": "The login URL data is corrupted. Start again with \"Generate login URL\".",
      "oauth.error.code_rejected": "pixiv rejected the code. Codes expire within seconds. Generate a new login URL and paste the new code immediately after logging in.",
      "oauth.error.network_error": "Could not reach pixiv.",
      "oauth.error.invalid_response": "pixiv returned an unexpected response. Try again later.",
      "oauth.error.refresh_token_missing": "Could not obtain a refresh token.",
      "oauth.error.user_id_missing": "Could not obtain the pixiv user ID.",
      "oauth.error.store_failed": "Could not save the login URL.",

      "sync.queued": "{mode} queued ({account})",
      "sync.mode.full": "Full resync",
      "sync.mode.normal": "Sync",
      "sync.queueError": "Could not start sync",
      "sync.confirmFull": "Recheck every work. Existing files are kept and missing items are downloaded again. This can take a while.",

      "reindex.working": "Working…",
      "reindex.done": "Reindex complete: {works} works",
      "reindex.error": "Reindex failed",

      "login.pageTitle": "Login | {app}",
      "login.subtitle": "Bookmark viewer",
      "login.error.invalid_password": "Incorrect password.",
      "login.password": "Password",
      "login.open": "Open",
      "login.note": "Access is limited to Tailscale or your home LAN.",
    },
  };

  function detectLanguage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (SUPPORTED.has(stored)) return stored;
    } catch (_) {
      /* localStorage can be unavailable in private modes. */
    }
    const navigatorLanguage = (navigator.language || "").toLowerCase();
    return navigatorLanguage.startsWith("ja") ? "ja" : "en";
  }

  let language = detectLanguage();

  function has(key) {
    return Object.prototype.hasOwnProperty.call(MESSAGES[language], key)
      || Object.prototype.hasOwnProperty.call(MESSAGES.en, key);
  }

  function t(key, variables) {
    const table = MESSAGES[language] || MESSAGES.en;
    let value = table[key];
    if (value === undefined) value = MESSAGES.en[key];
    if (value === undefined) value = MESSAGES.ja[key];
    if (value === undefined) return key;
    if (variables) {
      value = value.replace(/\{(\w+)\}/g, (match, name) => (
        variables[name] === undefined ? match : String(variables[name])
      ));
    }
    return value;
  }

  function formatNumber(value) {
    const number = Number(value || 0);
    return number.toLocaleString(language === "ja" ? "ja-JP" : "en-US");
  }

  function updateToggle() {
    const button = document.getElementById("langToggle");
    if (!button) return;
    button.textContent = language === "ja" ? "EN" : "日本語";
    button.setAttribute("lang", language === "ja" ? "en" : "ja");
    button.setAttribute(
      "aria-label",
      language === "ja" ? "Switch to English" : "日本語に切り替える"
    );
    button.title = language === "ja" ? "Switch to English" : "日本語に切り替える";
  }

  function apply(root = document) {
    document.documentElement.lang = language;

    root.querySelectorAll("[data-i18n]").forEach((node) => {
      const key = node.dataset.i18n;
      if (has(key)) node.textContent = t(key);
    });
    root.querySelectorAll("[data-i18n-html]").forEach((node) => {
      const key = node.dataset.i18nHtml;
      if (has(key)) node.innerHTML = t(key);
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
      const key = node.dataset.i18nPlaceholder;
      if (has(key)) node.setAttribute("placeholder", t(key));
    });
    root.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
      const key = node.dataset.i18nAriaLabel;
      if (has(key)) node.setAttribute("aria-label", t(key));
    });
    root.querySelectorAll("[data-i18n-title]").forEach((node) => {
      const key = node.dataset.i18nTitle;
      if (has(key)) node.setAttribute("title", t(key));
    });
    root.querySelectorAll("[data-i18n-error]").forEach((node) => {
      const key = "login.error." + node.dataset.i18nError;
      if (has(key)) node.textContent = t(key);
    });

    if (document.body && document.body.dataset.titleKey) {
      document.title = t(document.body.dataset.titleKey, {
        app: document.body.dataset.appName || "",
      });
    }

    updateToggle();
  }

  function setLanguage(next) {
    if (!SUPPORTED.has(next) || next === language) return;
    language = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (_) {
      /* Ignore storage failures. */
    }
    apply();
    document.dispatchEvent(
      new CustomEvent("viewer:langchange", { detail: { lang: language } })
    );
  }

  function init() {
    apply();
    const button = document.getElementById("langToggle");
    if (button) {
      button.addEventListener("click", () => {
        setLanguage(language === "ja" ? "en" : "ja");
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  // Deferred scripts run after the document is parsed, so applying here
  // avoids a flash of untranslated text before DOMContentLoaded.
  apply();

  window.ViewerI18n = {
    t,
    has,
    getLang: () => language,
    setLang: setLanguage,
    apply,
    formatNumber,
  };
})();
