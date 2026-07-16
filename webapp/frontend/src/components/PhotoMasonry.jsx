import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import { Box, Checkbox, Chip, CircularProgress, IconButton, Typography } from "@mui/material";
import CheckCircleRounded from "@mui/icons-material/CheckCircleRounded";
import RadioButtonUncheckedRounded from "@mui/icons-material/RadioButtonUncheckedRounded";
import StarBorderRounded from "@mui/icons-material/StarBorderRounded";
import StarRounded from "@mui/icons-material/StarRounded";
import DeleteOutlineRounded from "@mui/icons-material/DeleteOutlineRounded";
import CalendarMonthRounded from "@mui/icons-material/CalendarMonthRounded";
import { VirtuosoMasonry } from "@virtuoso.dev/masonry";

const PhotoCard = memo(function PhotoCard({ photo, index, context }) {
  const selected = context.selected.has(photo.id);
  const timelineTarget = context.focusId === photo.id;
  const ratio = photo.width && photo.height ? photo.width / photo.height : 1.25;
  const height = Math.round(Math.min(390, Math.max(190, 268 / ratio)));

  return (
    <Box
      className={`photo-tile ${selected ? "is-selected" : ""} ${timelineTarget ? "is-timeline-target" : ""}`}
      data-photo-index={index}
      data-photo-id={photo.id}
      sx={{ mb: 1.25 }}
    >
      <button
        className="photo-tile__button"
        onPointerDown={(event) => context.onSelectionStart(index, event)}
        onClick={(event) => context.onTileClick(index, event)}
        onDoubleClick={(event) => context.onTileDoubleClick(index, event)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            context.onTileDoubleClick(index, event);
          } else if (event.key === " ") {
            event.preventDefault();
            context.onSelect(index, event.shiftKey);
          }
        }}
        aria-label={`单击选择 ${photo.name}，双击查看原图`}
      >
        <img
          src={photo.thumbnailUrl}
          alt={photo.name}
          loading="lazy"
          decoding="async"
          draggable="false"
          style={{ height }}
        />
        <span className="photo-tile__shade" />
        <span className="photo-tile__meta">
          <Typography variant="caption" className="photo-tile__date">
            {(photo.date || "日期未知").slice(0, 10)}
          </Typography>
          <Typography variant="body2" noWrap>{photo.name}</Typography>
        </span>
      </button>
      <IconButton
        className={`photo-tile__star ${photo.starred ? "is-starred" : ""}`}
        onClick={(event) => {
          event.stopPropagation();
          context.onStar(photo.id, !photo.starred);
        }}
        aria-label={photo.starred ? `取消收藏 ${photo.name}` : `收藏 ${photo.name}`}
        title={photo.starred ? "取消收藏" : "收藏"}
        size="small"
      >
        {photo.starred ? <StarRounded /> : <StarBorderRounded />}
      </IconButton>
      {context.onQueueDelete && (
        <IconButton
          className="photo-tile__delete"
          onClick={(event) => {
            event.stopPropagation();
            context.onQueueDelete(photo.id);
          }}
          aria-label={`移到待删除库 ${photo.name}`}
          title="移到待删除库"
          size="small"
        >
          <DeleteOutlineRounded />
        </IconButton>
      )}
      {context.onJumpTimeline && (
        <IconButton
          className="photo-tile__timeline"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            context.onJumpTimeline(photo);
          }}
          aria-label={`在时间线中定位 ${photo.name}`}
          title="去时间线中的位置"
          size="small"
        >
          <CalendarMonthRounded />
        </IconButton>
      )}
      {context.selectionEnabled && (
        <Checkbox
          className="photo-tile__check"
          checked={selected}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => context.onSelect(index, event.nativeEvent.shiftKey)}
          icon={<RadioButtonUncheckedRounded />}
          checkedIcon={<CheckCircleRounded />}
          inputProps={{ "aria-label": `选择 ${photo.name}` }}
        />
      )}
      {!!photo.reasons?.length && (
        <Chip className="photo-tile__reason" size="small" label={photo.reasons[0].replace("visual:", "")} />
      )}
    </Box>
  );
});

function ItemContent({ data, index, context }) {
  return <PhotoCard photo={data} index={index} context={context} />;
}

export default function PhotoMasonry({
  items,
  columnCount,
  selectionEnabled = true,
  selected,
  onSelect,
  onOpen,
  onStar,
  onQueueDelete,
  onJumpTimeline,
  onLoadMore,
  onLoadPrevious,
  loadingMore,
  loadingPrevious,
  hasMore,
  hasPrevious,
  onVisibleIndex,
  focusId,
}) {
  const sentinelRef = useRef(null);
  const topSentinelRef = useRef(null);
  const masonryRootRef = useRef(null);
  const lastVisibleIndexRef = useRef(-1);
  const loadingPreviousRef = useRef(false);
  const selectionGestureRef = useRef(null);
  const wheelTimersRef = useRef([]);
  const suppressClickRef = useRef(false);
  const [selecting, setSelecting] = useState(false);

  const paintPhotoAtPoint = useCallback((clientX, clientY) => {
    const gesture = selectionGestureRef.current;
    if (!gesture?.active) return;
    const tile = document.elementFromPoint(clientX, clientY)?.closest?.("[data-photo-index]");
    if (!tile || !masonryRootRef.current?.contains(tile)) return;
    const nextIndex = Number(tile.dataset.photoIndex);
    if (!Number.isFinite(nextIndex) || gesture.lastIndex === nextIndex) return;
    gesture.lastIndex = nextIndex;
    onSelect(nextIndex, false, gesture.selecting);
  }, [onSelect]);

  const applyGestureStart = useCallback(() => {
    const gesture = selectionGestureRef.current;
    if (!gesture?.active || gesture.appliedStart) return;
    gesture.appliedStart = true;
    gesture.lastIndex = gesture.startIndex;
    onSelect(gesture.startIndex, false, gesture.selecting);
  }, [onSelect]);

  const handleSelectionStart = useCallback((index, event) => {
    if (!selectionEnabled || event.pointerType !== "mouse" || event.button !== 0) return;
    const photo = items[index];
    if (!photo) return;
    selectionGestureRef.current = {
      active: true,
      pointerId: event.pointerId,
      startIndex: index,
      startX: event.clientX,
      startY: event.clientY,
      clientX: event.clientX,
      clientY: event.clientY,
      selecting: !selected.has(photo.id),
      appliedStart: false,
      lastIndex: -1,
      moved: false,
    };
  }, [items, selected, selectionEnabled]);

  const handleTileClick = useCallback((index, event) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      event.preventDefault();
      return;
    }
    if (event.detail > 1) return;
    onSelect(index, event.shiftKey);
  }, [onSelect]);

  const handleTileDoubleClick = useCallback((index, event) => {
    suppressClickRef.current = false;
    event.preventDefault();
    onOpen(index);
  }, [onOpen]);

  useEffect(() => {
    const finishSelection = () => {
      const gesture = selectionGestureRef.current;
      if (!gesture?.active) return;
      if (gesture.moved) suppressClickRef.current = true;
      gesture.active = false;
      selectionGestureRef.current = null;
      setSelecting(false);
      wheelTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      wheelTimersRef.current = [];
    };
    const moveSelection = (event) => {
      const gesture = selectionGestureRef.current;
      if (!gesture?.active || event.pointerId !== gesture.pointerId) return;
      gesture.clientX = event.clientX;
      gesture.clientY = event.clientY;
      if (Math.abs(event.clientX - gesture.startX) + Math.abs(event.clientY - gesture.startY) <= 6) return;
      gesture.moved = true;
      setSelecting(true);
      applyGestureStart();
      paintPhotoAtPoint(event.clientX, event.clientY);
    };
    const wheelSelection = () => {
      const gesture = selectionGestureRef.current;
      if (!gesture?.active) return;
      gesture.moved = true;
      setSelecting(true);
      applyGestureStart();
      const sample = () => {
        const current = selectionGestureRef.current;
        if (current?.active) paintPhotoAtPoint(current.clientX, current.clientY);
      };
      window.requestAnimationFrame(sample);
      wheelTimersRef.current.push(window.setTimeout(sample, 45), window.setTimeout(sample, 110));
    };
    window.addEventListener("pointermove", moveSelection, { passive: true });
    window.addEventListener("pointerup", finishSelection, { passive: true });
    window.addEventListener("pointercancel", finishSelection, { passive: true });
    window.addEventListener("blur", finishSelection);
    window.addEventListener("wheel", wheelSelection, { passive: true });
    return () => {
      window.removeEventListener("pointermove", moveSelection);
      window.removeEventListener("pointerup", finishSelection);
      window.removeEventListener("pointercancel", finishSelection);
      window.removeEventListener("blur", finishSelection);
      window.removeEventListener("wheel", wheelSelection);
      wheelTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    };
  }, [applyGestureStart, paintPhotoAtPoint]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return undefined;
    const observer = new IntersectionObserver(
      (entries) => entries[0]?.isIntersecting && onLoadMore(),
      { rootMargin: "2600px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, onLoadMore]);

  useEffect(() => {
    const sentinel = topSentinelRef.current;
    if (!sentinel || !hasPrevious || !onLoadPrevious) return undefined;

    const restoreAnchorAfterPrepend = async () => {
      if (loadingPreviousRef.current || loadingPrevious) return;
      const cards = Array.from(masonryRootRef.current?.querySelectorAll("[data-photo-id]") || []);
      const visibleCards = cards
        .map((card) => ({ card, rect: card.getBoundingClientRect() }))
        .filter(({ rect }) => rect.bottom > 80 && rect.top < window.innerHeight)
        .sort((a, b) => Math.abs(a.rect.top - 96) - Math.abs(b.rect.top - 96));
      const anchor = visibleCards[0];
      const anchorId = anchor?.card.dataset.photoId;
      const anchorTop = anchor?.rect.top;
      const oldHeight = document.documentElement.scrollHeight;
      const oldScrollY = window.scrollY;

      loadingPreviousRef.current = true;
      try {
        await onLoadPrevious();
        await new Promise((resolve) => {
          window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
        });
        const anchoredCard = anchorId
          ? masonryRootRef.current?.querySelector(`[data-photo-id="${anchorId}"]`)
          : null;
        if (anchoredCard && Number.isFinite(anchorTop)) {
          window.scrollBy({
            top: anchoredCard.getBoundingClientRect().top - anchorTop,
            behavior: "instant",
          });
        } else {
          const addedHeight = document.documentElement.scrollHeight - oldHeight;
          if (addedHeight > 0) {
            window.scrollTo({ top: oldScrollY + addedHeight, behavior: "instant" });
          }
        }
      } catch {
        // React Query keeps the request error available to the page-level error state.
      } finally {
        loadingPreviousRef.current = false;
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) restoreAnchorAfterPrepend();
      },
      { rootMargin: "900px 0px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasPrevious, loadingPrevious, onLoadPrevious]);

  useEffect(() => {
    if (!onVisibleIndex) return undefined;
    let frame = 0;
    const syncVisibleIndex = () => {
      frame = 0;
      const cards = masonryRootRef.current?.querySelectorAll("[data-photo-index]") || [];
      let firstVisible = Number.POSITIVE_INFINITY;
      cards.forEach((card) => {
        const rect = card.getBoundingClientRect();
        if (rect.bottom > 90 && rect.top < window.innerHeight) {
          firstVisible = Math.min(firstVisible, Number(card.dataset.photoIndex));
        }
      });
      if (Number.isFinite(firstVisible) && firstVisible !== lastVisibleIndexRef.current) {
        lastVisibleIndexRef.current = firstVisible;
        onVisibleIndex(firstVisible);
      }
    };
    const scheduleSync = () => {
      if (!frame) frame = window.requestAnimationFrame(syncVisibleIndex);
    };
    scheduleSync();
    window.addEventListener("scroll", scheduleSync, { passive: true });
    window.addEventListener("resize", scheduleSync, { passive: true });
    return () => {
      window.removeEventListener("scroll", scheduleSync);
      window.removeEventListener("resize", scheduleSync);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [items, onVisibleIndex]);

  return (
    <>
      <Box
        ref={topSentinelRef}
        className={`load-sentinel load-sentinel--top ${loadingPrevious ? "is-loading" : ""}`}
      >
        {loadingPrevious && <CircularProgress size={18} />}
      </Box>
      <Box ref={masonryRootRef} className={`photo-masonry-root ${selecting ? "is-selecting" : ""}`}>
        <VirtuosoMasonry
          key={`photos-${columnCount}`}
          data={items}
          columnCount={columnCount}
          useWindowScroll
          initialItemCount={Math.min(items.length, 24)}
          ItemContent={ItemContent}
          context={{
            selectionEnabled,
            selected,
            onSelect,
            onOpen,
            onStar,
            onQueueDelete,
            onJumpTimeline,
            onSelectionStart: handleSelectionStart,
            onTileClick: handleTileClick,
            onTileDoubleClick: handleTileDoubleClick,
            focusId,
          }}
          className="photo-masonry"
        />
      </Box>
      <Box ref={sentinelRef} className="load-sentinel">
        {loadingMore && <CircularProgress size={26} />}
        {!hasMore && items.length > 0 && <Typography variant="caption">已经走到这段回忆的尽头</Typography>}
      </Box>
    </>
  );
}
