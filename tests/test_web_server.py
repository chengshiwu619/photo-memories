import http.client
import json
import threading

from config import CATEGORY_LIFE, CATEGORY_SAMPLE
from db_manager import Database


def _insert_photo(conn, tmp_path, photo_id, category=CATEGORY_LIFE, date_taken=None):
    date_taken = date_taken or "2026-07-16T12:00:00"
    folder = tmp_path / "Photos" / f"Set-{photo_id}"
    folder.mkdir(parents=True, exist_ok=True)
    original = folder / f"photo-{photo_id}.jpg"
    thumbnail = tmp_path / "thumbs" / f"{photo_id}.jpg"
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"original-image")
    thumbnail.write_bytes(b"thumbnail-image")
    conn.execute(
        """
        INSERT INTO files
            (id, file_path, file_name, folder_path, folder_name, file_mtime, is_image)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (photo_id, str(original), original.name, str(folder), folder.name, date_taken),
    )
    conn.execute(
        "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, 'manual')",
        (str(folder), category),
    )
    conn.execute(
        """
        INSERT INTO photo_metadata
            (file_id, thumbnail_path, width, height, date_taken, category)
        VALUES (?, ?, 1200, 800, ?, ?)
        """,
        (photo_id, str(thumbnail), date_taken, category),
    )
    return original, thumbnail


def _start_server(tmp_path):
    from webapp.server import create_server

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    with db.connect() as conn:
        _insert_photo(conn, tmp_path, 1)
        conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (1, 'sunset', 'siglip')")
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Moments</h1>", encoding="utf-8")
    server = create_server(port=0, db=db, static_dir=static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return db, server, thread


def _request(server, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json", "Content-Length": str(len(body))}
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    return response.status, response.getheaders(), raw


def test_web_server_serves_local_app_api_and_thumbnail(tmp_path):
    _, server, thread = _start_server(tmp_path)
    try:
        status, _, body = _request(server, "GET", "/")
        assert status == 200
        assert b"Moments" in body

        status, _, body = _request(server, "GET", "/api/photos?category=life&limit=10")
        payload = json.loads(body)
        assert status == 200
        assert payload["hot"] is True
        assert payload["offset"] == 0
        assert [item["id"] for item in payload["items"]] == [1]
        assert "file_path" not in payload["items"][0]
        assert payload["items"][0]["thumbnailUrl"] == "/media/thumbnail/1"
        assert payload["items"][0]["starred"] is False
        assert payload["items"][0]["tags"] == ["sunset"]

        status, _, body = _request(
            server,
            "POST",
            "/api/photos/refresh",
            {"category": "life", "starred": False, "limit": 72},
        )
        refreshed = json.loads(body)
        assert status == 200
        assert refreshed["hot"] is True
        assert refreshed["offset"] == 0
        assert [item["id"] for item in refreshed["items"]] == [1]

        status, _, body = _request(server, "GET", "/api/timeline-index?category=life")
        timeline = json.loads(body)
        assert status == 200
        assert timeline == {
            "months": [{"month": "2026-07", "count": 1, "offset": 0}],
            "total": 1,
            "hot": True,
        }

        status, headers, body = _request(server, "GET", "/media/thumbnail/1")
        assert status == 200
        assert dict(headers)["Cache-Control"] == "private, max-age=86400"
        assert dict(headers)["X-Photo-Source"] == "thumbnail"
        assert body == b"thumbnail-image"

        status, headers, body = _request(server, "GET", "/media/original/1")
        assert status == 200
        assert dict(headers)["X-Photo-Source"] == "original"
        assert body == b"original-image"

        (tmp_path / "Photos" / "Set-1" / "photo-1.jpg").unlink()
        status, _, _ = _request(server, "GET", "/media/original/1")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_category_action_uses_confirmed_sample_override(tmp_path):
    from business.classifier.category_rules import CONFIRMED_SAMPLE_SOURCE, CONFIRMED_SAMPLE_TAG

    db, server, thread = _start_server(tmp_path)
    try:
        status, _, body = _request(
            server,
            "POST",
            "/api/category",
            {"ids": [1], "category": CATEGORY_SAMPLE},
        )
        assert status == 200
        assert json.loads(body)["updated"] == 1
        with db.connect() as conn:
            row = conn.execute("SELECT category FROM photo_metadata WHERE file_id = 1").fetchone()
            marker = conn.execute(
                "SELECT 1 FROM photo_tags WHERE file_id = 1 AND tag = ? AND source = ?",
                (CONFIRMED_SAMPLE_TAG, CONFIRMED_SAMPLE_SOURCE),
            ).fetchone()
        assert row["category"] == CATEGORY_SAMPLE
        assert marker is not None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_deletion_queue_hides_restores_and_only_deletes_after_confirmation(tmp_path):
    db, server, thread = _start_server(tmp_path)
    original = tmp_path / "Photos" / "Set-1" / "photo-1.jpg"
    thumbnail = tmp_path / "thumbs" / "1.jpg"
    try:
        with db.connect() as conn:
            conn.executemany(
                "INSERT INTO photo_tags (file_id, tag, source) VALUES (1, ?, 'siglip')",
                [("nude",), ("nipples",)],
            )
        status, _, body = _request(server, "POST", "/api/deletions/queue", {"ids": [1]})
        assert status == 200
        assert json.loads(body)["queued"] == 1

        status, _, body = _request(server, "GET", "/api/photos?category=life&limit=10")
        assert status == 200
        assert json.loads(body)["items"] == []

        status, _, body = _request(server, "GET", "/api/review")
        assert status == 200
        assert json.loads(body)["items"] == []

        status, _, body = _request(server, "GET", "/api/deletions")
        assert status == 200
        assert [item["id"] for item in json.loads(body)["items"]] == [1]

        status, _, body = _request(server, "GET", "/api/stats")
        assert status == 200
        assert json.loads(body)["pendingDeletion"] == 1

        status, _, body = _request(server, "POST", "/api/deletions/restore", {"ids": [1]})
        assert status == 200
        assert json.loads(body)["restored"] == 1
        status, _, body = _request(server, "GET", "/api/photos?category=life&limit=10")
        assert [item["id"] for item in json.loads(body)["items"]] == [1]

        _request(server, "POST", "/api/deletions/queue", {"ids": [1]})
        status, _, _ = _request(
            server,
            "POST",
            "/api/deletions/delete-originals",
            {"ids": [1]},
        )
        assert status == 400
        assert original.is_file()

        status, _, body = _request(
            server,
            "POST",
            "/api/deletions/delete-originals",
            {"ids": [1], "confirmation": "DELETE_ORIGINALS"},
        )
        result = json.loads(body)
        assert status == 200
        assert result["deleted"] == 1
        assert result["failed"] == 0
        assert not original.exists()
        assert thumbnail.is_file()
        with db.connect() as conn:
            row = conn.execute("SELECT path_status, path_error FROM files WHERE id = 1").fetchone()
        assert row["path_status"] == "missing"
        assert row["path_error"] == "deleted_by_user"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_ids_selects_all_candidates_and_updates_after_batch_action(tmp_path):
    db, server, thread = _start_server(tmp_path)
    try:
        with db.connect() as conn:
            conn.executemany(
                "INSERT INTO photo_tags (file_id, tag, source) VALUES (1, ?, 'siglip')",
                [("nude",), ("nipples",)],
            )

        status, _, body = _request(server, "GET", "/api/review/ids")
        payload = json.loads(body)
        assert status == 200
        assert payload["ids"] == [1]
        assert payload["count"] == 1
        assert payload["truncated"] is False

        status, _, body = _request(server, "POST", "/api/review/sample", {"ids": payload["ids"]})
        assert status == 200
        assert json.loads(body)["updated"] == 1

        status, _, body = _request(server, "GET", "/api/review/ids")
        assert status == 200
        assert json.loads(body)["ids"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_star_action_and_starred_category_filter(tmp_path):
    _, server, thread = _start_server(tmp_path)
    try:
        status, _, body = _request(server, "POST", "/api/star", {"id": 1, "starred": True})
        assert status == 200
        assert json.loads(body) == {"id": 1, "starred": True}

        status, _, body = _request(
            server,
            "GET",
            "/api/photos?category=life&starred=1&limit=10",
        )
        payload = json.loads(body)
        assert status == 200
        assert [item["id"] for item in payload["items"]] == [1]
        assert payload["items"][0]["starred"] is True

        status, _, body = _request(
            server,
            "POST",
            "/api/category",
            {"ids": [1], "category": CATEGORY_SAMPLE},
        )
        assert status == 200
        assert json.loads(body)["updated"] == 1
        status, _, body = _request(
            server,
            "GET",
            "/api/photos?category=sample&starred=1&limit=10",
        )
        payload = json.loads(body)
        assert [item["id"] for item in payload["items"]] == [1]
        assert payload["items"][0]["starred"] is True

        status, _, _ = _request(server, "POST", "/api/star", {"id": 1, "starred": False})
        assert status == 200
        status, _, body = _request(
            server,
            "GET",
            "/api/photos?category=sample&starred=1&limit=10",
        )
        assert status == 200
        assert json.loads(body)["items"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_batch_star_action_updates_all_existing_photos(tmp_path):
    db, server, thread = _start_server(tmp_path)
    try:
        with db.connect() as conn:
            _insert_photo(conn, tmp_path, 2)
            _insert_photo(conn, tmp_path, 3)
        status, _, body = _request(
            server,
            "POST",
            "/api/star",
            {"ids": [1, 2, 3], "starred": True},
        )
        payload = json.loads(body)
        assert status == 200
        assert payload["ids"] == [1, 2, 3]
        assert payload["updated"] == 3
        assert payload["starred"] is True
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT file_id, is_starred FROM photo_metadata WHERE file_id IN (1, 2, 3) ORDER BY file_id"
            ).fetchall()
        assert [(row["file_id"], row["is_starred"]) for row in rows] == [(1, 1), (2, 1), (3, 1)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_photo_context_is_centered_on_clicked_photo_in_timeline_order(tmp_path):
    db, server, thread = _start_server(tmp_path)
    try:
        with db.connect() as conn:
            conn.execute("UPDATE files SET file_mtime = ? WHERE id = 1", ("2026-07-01T12:00:00",))
            conn.execute("UPDATE photo_metadata SET date_taken = ? WHERE file_id = 1", ("2026-07-01T12:00:00",))
            for photo_id in range(2, 8):
                _insert_photo(
                    conn,
                    tmp_path,
                    photo_id,
                    date_taken=f"2026-07-{photo_id:02d}T12:00:00",
                )

        status, _, body = _request(
            server,
            "GET",
            "/api/photo-context?id=4&category=life&before=2&after=2",
        )
        payload = json.loads(body)

        assert status == 200
        assert [item["id"] for item in payload["items"]] == [6, 5, 4, 3, 2]
        assert payload["index"] == 2
        assert payload["items"][payload["index"]]["id"] == 4
        assert payload["beforeCount"] == 2
        assert payload["afterCount"] == 2

        with db.connect() as conn:
            conn.execute("UPDATE photo_metadata SET is_starred = 1 WHERE file_id IN (2, 4, 6)")
        status, _, body = _request(
            server,
            "GET",
            "/api/photo-context?id=4&category=life&starred=1&before=2&after=2",
        )
        starred_payload = json.loads(body)
        assert status == 200
        assert [item["id"] for item in starred_payload["items"]] == [6, 4, 2]
        assert starred_payload["items"][starred_payload["index"]]["id"] == 4

        status, _, body = _request(
            server,
            "GET",
            "/api/timeline-location?id=4&category=life",
        )
        location = json.loads(body)
        assert status == 200
        assert location["id"] == 4
        assert location["offset"] == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_main_uses_web_as_the_only_ui_entry():
    source = open("main.py", encoding="utf-8").read()
    launcher = open("启动GPU相册.bat", encoding="utf-8").read()

    assert 'default="web"' in source
    assert 'choices=["web", "setup"]' in source
    assert "from webapp import run_web" in source
    assert "ui.app" not in source
    assert "PyQt6" not in source
    assert "main.py web" in launcher


def test_web_masonry_rebuilds_layout_when_responsive_column_count_changes():
    masonry = open("webapp/frontend/src/components/PhotoMasonry.jsx", encoding="utf-8").read()
    styles = open("webapp/frontend/src/styles.css", encoding="utf-8").read()

    assert 'key={`photos-${columnCount}`}' in masonry
    assert "content-visibility" not in styles


def test_web_feed_keeps_warming_after_hot_start_buffer():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()
    api = open("webapp/frontend/src/api.js", encoding="utf-8").read()
    masonry = open("webapp/frontend/src/components/PhotoMasonry.jsx", encoding="utf-8").read()

    assert "warmedFeedCount >= 216" in app
    assert "feedQuery.fetchNextPage()" in app
    assert "String(pageParam?.limit || 72)" in api
    assert "slice(0, 36)" in api
    assert 'rootMargin: "2600px 0px"' in masonry


def test_category_switch_keeps_scroll_position_and_previous_layout_until_ready():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()

    assert "placeholderData: (previousData, previousQuery)" in app
    assert "previousQuery?.queryKey?.[2] === mode" in app
    assert "previousQuery?.queryKey?.[3] === starredOnly" in app
    assert 'window.scrollTo({ top: 0, behavior: "instant" });\n  }, [view]);' not in app
    assert "scrollPositionsRef.current.set(view, window.scrollY)" in app
    assert "pendingScrollRestoreRef.current" in app
    assert 'onChange={handleViewChange}' in app


def test_view_scroll_memory_restores_discover_and_timeline_independently():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()

    assert "const scrollPositionsRef = useRef(new Map())" in app
    assert "scrollPositionsRef.current.get(nextView) ?? 0" in app
    assert "document.documentElement.scrollHeight - window.innerHeight" in app
    assert "Math.min(pending.top, maxTop)" in app
    assert "attempts >= 8" in app
    assert 'handleViewChange("timeline", { restore: false })' in app
    assert "setTimelineStart(0)" in app
    assert '}, [category, starredOnly]);' in app


def test_hero_deck_scales_continuously_and_keeps_side_cards_ready():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()
    styles = open("webapp/frontend/src/styles.css", encoding="utf-8").read()

    assert "projectedIndex - 2" in app
    assert "projectedIndex + 2" in app
    assert "activeIndex + projectedShift" in app
    assert "index - projectedIndex + (residualDragX / cardStep)" in app
    assert '"--card-scale": scale' in app
    assert "Math.round(-drag.current.x / cardStep)" in app
    assert "onPointerMove={moveDrag}" in app
    assert "projectedIndex >= photos.length - 12" in app
    assert "photos.length - 12" in app
    assert "scale(var(--card-scale))" in styles
    assert ".hero__photos.is-dragging .hero__photo-card" in styles
    assert "hero__photo-card--" not in app


def test_web_deletion_queue_is_two_stage_and_optimistically_removes_tiles():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()
    api = open("webapp/frontend/src/api.js", encoding="utf-8").read()
    navigation = open("webapp/frontend/src/components/AppNavigation.jsx", encoding="utf-8").read()
    masonry = open("webapp/frontend/src/components/PhotoMasonry.jsx", encoding="utf-8").read()

    assert 'id: "deletions", label: "待删除库"' in navigation
    assert 'className="photo-tile__delete"' in masonry
    assert "context.onQueueDelete(photo.id)" in masonry
    assert 'post("/api/deletions/queue", { ids })' in api
    assert 'confirmation: "DELETE_ORIGINALS"' in api
    assert 'removeCachedItems(["photos"], ids)' in app
    assert 'removeCachedItems(["review"], ids)' in app
    assert "再次确认删除原图" in app
    assert "确认永久删除原图" in app
    assert "restoreDeletionMutation.mutate([...selected])" in app


def test_random_refresh_replaces_the_hot_page_and_only_warns_when_busy():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()
    api = open("webapp/frontend/src/api.js", encoding="utf-8").read()
    styles = open("webapp/frontend/src/styles.css", encoding="utf-8").read()

    assert 'post("/api/photos/refresh"' in api
    assert "preloadPageThumbnails(payload)" in api
    assert "refreshInFlightRef.current" in app
    assert "queryClient.cancelQueries({ queryKey: randomFeedQueryKey, exact: true })" in app
    assert "queryClient.setQueryData(randomFeedQueryKey" in app
    assert "刷新的太快啦……" in app
    assert 'view === "discover"' in app
    assert ".random-refresh-hint.is-visible" in styles


def test_star_toggle_is_optimistic_and_rolls_back_on_write_failure():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()

    assert "applyStarToCachedPhotos" in app
    assert "onMutate: ({ id, starred })" in app
    assert "onMutate: async ({ id, starred })" not in app
    assert '["review", "deletions"].forEach' in app
    assert "previousLightboxPhoto" in app
    assert "context?.snapshots?.forEach" in app
    assert "收藏失败：" in app


def test_lightbox_keeps_original_and_thumbnail_requests_separate():
    lightbox = open("webapp/frontend/src/components/PhotoLightbox.jsx", encoding="utf-8").read()
    styles = open("webapp/frontend/src/styles.css", encoding="utf-8").read()

    assert 'className="photo-lightbox"' in lightbox
    assert "navigation: 160" in lightbox
    assert "src: photo.originalUrl" in lightbox
    assert "thumbnail: photo.thumbnailUrl" in lightbox
    assert 'preload: 1' in lightbox
    assert 'spacing: "16px"' in lightbox
    assert "Math.floor((viewportWidth - 120) / 10)" in lightbox
    assert 'toolbar={{ buttons: [...actionButtons, "zoom", "fullscreen", "close"] }}' in lightbox
    assert "lightbox-category" not in lightbox
    assert 'spacing: "-100%"' not in lightbox
    assert ".photo-lightbox .yarl__slide_current + .yarl__slide" not in styles
    assert ".photo-lightbox .yarl__slide {" in styles
    assert "transition: opacity 70ms linear" in styles
    assert ".photo-lightbox .yarl__slide_current {" in styles
    assert "transition-delay: 32ms" in styles


def test_timeline_scrubber_seeks_hot_cache_and_tracks_visible_photo():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()
    api = open("webapp/frontend/src/api.js", encoding="utf-8").read()
    scrubber = open("webapp/frontend/src/components/TimelineScrubber.jsx", encoding="utf-8").read()
    masonry = open("webapp/frontend/src/components/PhotoMasonry.jsx", encoding="utf-8").read()

    assert "/api/timeline-index" in api
    assert 'orientation="vertical"' in scrubber
    assert "onChangeCommitted" in scrubber
    assert 'valueLabelDisplay="auto"' in scrubber
    assert "setDragOffset(toOffset(value))" in scrubber
    assert "getPreviousPageParam" in app
    assert "firstOffset - limit" in app
    assert "lastPage.offset + lastPage.items.length" in app
    assert "setTimelineStart(nextOffset)" in app
    assert "onVisibleIndex={view === \"timeline\"" in app
    assert "fetchPreviousPage()" in app
    assert "data-photo-index={index}" in masonry
    assert "data-photo-id={photo.id}" in masonry
    assert "restoreAnchorAfterPrepend" in masonry


def test_masonry_supports_drag_wheel_selection_double_click_and_timeline_jump():
    app = open("webapp/frontend/src/App.jsx", encoding="utf-8").read()
    api = open("webapp/frontend/src/api.js", encoding="utf-8").read()
    masonry = open("webapp/frontend/src/components/PhotoMasonry.jsx", encoding="utf-8").read()

    assert 'onPointerDown={(event) => context.onSelectionStart(index, event)}' in masonry
    assert 'window.addEventListener("wheel", wheelSelection, { passive: true })' in masonry
    assert "paintPhotoAtPoint" in masonry
    assert "forceSelected" in app
    assert "onDoubleClick={(event) => context.onTileDoubleClick(index, event)}" in masonry
    assert "context.onJumpTimeline(photo)" in masonry
    assert "/api/timeline-location" in api
    assert 'handleViewChange("timeline", { restore: false })' in app
    assert "setTimelineStart(offset)" in app
    assert "setStarredMany(ids, starred)" in app
    assert "queueDeletionMutation.mutate([...selected])" in app
    assert "categoryMutation.mutate({ ids: [...selected]" in app
    assert "双击去时间线" in app
