import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  InputAdornment,
  Paper,
  Skeleton,
  Snackbar,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
} from "@mui/material";
import SearchRounded from "@mui/icons-material/SearchRounded";
import AutoAwesomeRounded from "@mui/icons-material/AutoAwesomeRounded";
import HomeRounded from "@mui/icons-material/HomeRounded";
import CloseRounded from "@mui/icons-material/CloseRounded";
import DoneAllRounded from "@mui/icons-material/DoneAllRounded";
import DeselectRounded from "@mui/icons-material/DeselectRounded";
import StarBorderRounded from "@mui/icons-material/StarBorderRounded";
import StarRounded from "@mui/icons-material/StarRounded";
import DeleteForeverRounded from "@mui/icons-material/DeleteForeverRounded";
import DeleteSweepRounded from "@mui/icons-material/DeleteSweepRounded";
import DeleteOutlineRounded from "@mui/icons-material/DeleteOutlineRounded";
import RestoreFromTrashRounded from "@mui/icons-material/RestoreFromTrashRounded";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  dismissReview,
  deleteOriginals,
  getAllDeletionIds,
  getAllReviewIds,
  getDeletionPage,
  getPhotoContext,
  getPhotoPage,
  getReviewPage,
  getStats,
  getTimelineIndex,
  getTimelineLocation,
  markReviewSample,
  queueDeletion,
  refreshRandomPhotos,
  restoreDeletion,
  setCategory,
  setStarred,
  setStarredMany,
} from "./api";
import AppNavigation from "./components/AppNavigation";
import PhotoMasonry from "./components/PhotoMasonry";
import { buildHeroCopy } from "./heroCopy";

const PhotoLightbox = lazy(() => import("./components/PhotoLightbox"));
const TimelineScrubber = lazy(() => import("./components/TimelineScrubber"));

function useColumns() {
  const xs = useMediaQuery("(max-width:520px)");
  const sm = useMediaQuery("(max-width:840px)");
  const md = useMediaQuery("(max-width:1180px)");
  const xl = useMediaQuery("(min-width:1800px)");
  if (xs) return 2;
  if (sm) return 3;
  if (md) return 4;
  if (xl) return 7;
  return 5;
}

function Hero({ items, total, onLocate, onNeedMore, hasMore, loadingMore }) {
  const photos = items;
  const [activeIndex, setActiveIndex] = useState(0);
  const [dragOffset, setDragOffset] = useState({ index: -1, x: 0, y: 0 });
  const drag = useRef({
    pointerId: null,
    index: -1,
    startX: 0,
    startY: 0,
    x: 0,
    moved: false,
  });
  const photoKey = photos.slice(0, 5).map((photo) => photo.id).join(",");
  const cardStep = 190;
  const projectedShift = dragOffset.index >= 0
    ? Math.round(-dragOffset.x / cardStep)
    : 0;
  const projectedIndex = Math.max(
    0,
    Math.min(Math.max(photos.length - 1, 0), activeIndex + projectedShift),
  );
  const residualDragX = dragOffset.index >= 0
    ? Math.max(
      -cardStep,
      Math.min(cardStep, dragOffset.x + (projectedIndex - activeIndex) * cardStep),
    )
    : 0;

  useEffect(() => {
    setActiveIndex(Math.min(2, Math.max(photos.length - 1, 0)));
    setDragOffset({ index: -1, x: 0, y: 0 });
  }, [photoKey]);

  useEffect(() => {
    if (hasMore && !loadingMore && projectedIndex >= photos.length - 12) onNeedMore();
  }, [hasMore, loadingMore, onNeedMore, photos.length, projectedIndex]);

  if (!photos.length) return null;
  const visibleIndices = [
    projectedIndex - 2,
    projectedIndex - 1,
    projectedIndex,
    projectedIndex + 1,
    projectedIndex + 2,
  ]
    .filter((index) => index >= 0 && index < photos.length);
  const visiblePhotos = visibleIndices.map((index) => photos[index]);
  const copy = buildHeroCopy(visiblePhotos, total);

  const finishDrag = (event) => {
    if (drag.current.pointerId !== event.pointerId) return;
    const shift = drag.current.moved
      ? Math.round(-drag.current.x / cardStep)
      : 0;
    setActiveIndex((current) => Math.max(0, Math.min(photos.length - 1, current + shift)));
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drag.current.pointerId = null;
    setDragOffset({ index: -1, x: 0, y: 0 });
  };

  const startDrag = (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const card = event.target.closest?.("[data-hero-index]");
    if (!card || !event.currentTarget.contains(card)) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      pointerId: event.pointerId,
      index: Number(card.dataset.heroIndex),
      startX: event.clientX,
      startY: event.clientY,
      x: 0,
      moved: false,
    };
    setDragOffset({ index: drag.current.index, x: 0, y: 0 });
  };

  const moveDrag = (event) => {
    if (drag.current.pointerId !== event.pointerId) return;
    const x = event.clientX - drag.current.startX;
    const y = Math.max(-120, Math.min(120, event.clientY - drag.current.startY));
    if (Math.abs(x) + Math.abs(y) > 7) drag.current.moved = true;
    drag.current.x = x;
    setDragOffset({ index: drag.current.index, x, y });
  };

  return (
    <Box className="hero">
      <Box className="hero__copy">
        <Chip label={copy.eyebrow} size="small" />
        <Typography variant="h1">
          {copy.title[0]}<br />{copy.title[1]}
        </Typography>
        <Typography color="text.secondary" className="hero__desc">
          {copy.description}
        </Typography>
      </Box>
      <Box
        className={`hero__photos ${dragOffset.index >= 0 ? "is-dragging" : ""}`}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
      >
        {visibleIndices.map((index) => {
          const photo = photos[index];
          const position = index - projectedIndex + (residualDragX / cardStep);
          const distance = Math.min(Math.abs(position), 2.4);
          const scale = Math.max(0.66, 1 - distance * 0.16);
          const opacity = Math.max(0.34, 1 - distance * 0.27);
          return (
          <button
            key={photo.id}
            type="button"
            className={`hero__photo-card ${index === projectedIndex ? "is-active" : ""}`}
            data-hero-index={index}
            style={{
              "--card-x": `${position * 58}%`,
              "--card-y": `${distance * 25 + dragOffset.y * 0.08}px`,
              "--card-scale": scale,
              "--card-rotate": `${position * 4.5 + dragOffset.y * 0.018}deg`,
              "--card-opacity": opacity,
              "--card-brightness": Math.max(0.72, 1 - distance * 0.11),
              zIndex: Math.round(30 - distance * 8),
            }}
            onDoubleClick={() => !drag.current.moved && onLocate(photo)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onLocate(photo);
              } else if (event.key === "ArrowLeft") {
                setActiveIndex((current) => Math.max(0, current - 1));
              } else if (event.key === "ArrowRight") {
                setActiveIndex((current) => Math.min(photos.length - 1, current + 1));
              }
            }}
            aria-label={`拖动第 ${index + 1} 张照片切换主卡；双击去时间线位置`}
          >
            <img src={photo.thumbnailUrl} alt="" draggable="false" />
          </button>
          );
        })}
        <Typography variant="caption" className="hero__gesture-hint">
          {loadingMore ? "正在接上更多随机照片…" : "左右拖动 · 松手回到最近一张 · 双击去时间线"}
        </Typography>
      </Box>
    </Box>
  );
}

function LoadingWall() {
  return (
    <Box className="loading-wall">
      {[1, 2, 3, 4, 5, 6, 7, 8].map((item) => (
        <Skeleton key={item} variant="rounded" height={item % 3 === 0 ? 320 : 230} />
      ))}
    </Box>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const mobile = useMediaQuery("(max-width:760px)");
  const columns = useColumns();
  const [view, setView] = useState("discover");
  const [category, setCategoryFilter] = useState(1);
  const [starredOnly, setStarredOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [selectionAnchor, setSelectionAnchor] = useState(null);
  const [lightboxPhoto, setLightboxPhoto] = useState(null);
  const [lightboxIndex, setLightboxIndex] = useState(-1);
  const [layoutEpoch, setLayoutEpoch] = useState(0);
  const [timelineStart, setTimelineStart] = useState(0);
  const [timelinePosition, setTimelinePosition] = useState(0);
  const [timelineDragging, setTimelineDragging] = useState(false);
  const [timelineTargetId, setTimelineTargetId] = useState(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [refreshTooFast, setRefreshTooFast] = useState(false);
  const [toast, setToast] = useState("");
  const timelineReleaseTimer = useRef(null);
  const refreshHintTimer = useRef(null);
  const refreshInFlightRef = useRef(false);
  const timelineJumpRef = useRef(null);
  const scrollPositionsRef = useRef(new Map());
  const pendingScrollRestoreRef = useRef(null);

  const handleViewChange = useCallback((nextView, { restore = true } = {}) => {
    if (!nextView || nextView === view) return;
    scrollPositionsRef.current.set(view, window.scrollY);
    if (view === "timeline" && nextView !== "timeline") {
      timelineJumpRef.current = null;
      setTimelineTargetId(null);
    }
    pendingScrollRestoreRef.current = restore
      ? { view: nextView, top: scrollPositionsRef.current.get(nextView) ?? 0 }
      : null;
    setView(nextView);
  }, [view]);

  useEffect(() => {
    let timer = null;
    const recoverLayout = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setLayoutEpoch((value) => value + 1), 160);
    };
    window.addEventListener("resize", recoverLayout, { passive: true });
    return () => {
      window.removeEventListener("resize", recoverLayout);
      window.clearTimeout(timer);
    };
  }, []);

  const statsQuery = useQuery({ queryKey: ["stats"], queryFn: getStats });
  const mode = view === "timeline" ? "timeline" : "random";
  const timelineQueryOffset = mode === "timeline" ? timelineStart : 0;
  const timelineIndexQuery = useQuery({
    queryKey: ["timeline-index", category, starredOnly],
    queryFn: () => getTimelineIndex(category, starredOnly),
    enabled: view === "timeline",
    staleTime: 5 * 60_000,
  });
  const feedQuery = useInfiniteQuery({
    queryKey: ["photos", category, mode, starredOnly, timelineQueryOffset],
    queryFn: ({ pageParam }) => getPhotoPage({ category, mode, starredOnly, pageParam }),
    initialPageParam: { offset: timelineQueryOffset, exclude: [] },
    enabled: view !== "review" && view !== "deletions",
    placeholderData: (previousData, previousQuery) => (
      previousQuery?.queryKey?.[2] === mode && previousQuery?.queryKey?.[3] === starredOnly
        ? previousData
        : undefined
    ),
    getNextPageParam: (lastPage, pages) => {
      if (!lastPage.hasMore || !lastPage.items.length) return undefined;
      const loaded = pages.flatMap((page) => page.items);
      return mode === "timeline"
        ? { offset: lastPage.offset + lastPage.items.length, exclude: [] }
        : { offset: loaded.length, exclude: loaded.slice(-800).map((photo) => photo.id) };
    },
    getPreviousPageParam: (firstPage) => {
      const firstOffset = Number(firstPage.offset) || 0;
      if (mode !== "timeline" || firstOffset <= 0) return undefined;
      const limit = Math.min(72, firstOffset);
      return { offset: firstOffset - limit, limit, exclude: [] };
    },
  });
  const reviewQuery = useInfiniteQuery({
    queryKey: ["review"],
    queryFn: ({ pageParam }) => getReviewPage({ pageParam }),
    initialPageParam: { offset: 0 },
    enabled: view === "review",
    getNextPageParam: (lastPage, pages) => {
      if (!lastPage.hasMore || !lastPage.items.length) return undefined;
      return { offset: pages.reduce((sum, page) => sum + page.items.length, 0) };
    },
  });
  const deletionQuery = useInfiniteQuery({
    queryKey: ["deletions"],
    queryFn: ({ pageParam }) => getDeletionPage({ pageParam }),
    initialPageParam: { offset: 0 },
    enabled: view === "deletions",
    getNextPageParam: (lastPage, pages) => {
      if (!lastPage.hasMore || !lastPage.items.length) return undefined;
      return { offset: pages.reduce((sum, page) => sum + page.items.length, 0) };
    },
  });

  const warmedFeedCount = feedQuery.data?.pages.reduce(
    (total, page) => total + page.items.length,
    0,
  ) || 0;
  useEffect(() => {
    if (
      (view === "review" || view === "deletions")
      || warmedFeedCount >= 216
      || !feedQuery.hasNextPage
      || feedQuery.isFetchingNextPage
    ) return undefined;
    const timer = window.setTimeout(() => feedQuery.fetchNextPage(), 0);
    return () => window.clearTimeout(timer);
  }, [
    feedQuery.fetchNextPage,
    feedQuery.hasNextPage,
    feedQuery.isFetchingNextPage,
    view,
    warmedFeedCount,
  ]);
  const lightboxContextQuery = useQuery({
    queryKey: ["photo-context", lightboxPhoto?.id, lightboxPhoto?.category, lightboxPhoto?.starredOnly],
    queryFn: () => getPhotoContext(
      lightboxPhoto.id,
      lightboxPhoto.category,
      lightboxPhoto.starredOnly,
    ),
    enabled: Boolean(lightboxPhoto?.category),
    staleTime: 5 * 60_000,
  });

  const activeQuery = view === "review"
    ? reviewQuery
    : view === "deletions"
      ? deletionQuery
      : feedQuery;
  const timelineLoadedStart = mode === "timeline"
    ? Number(feedQuery.data?.pages?.[0]?.offset ?? timelineStart)
    : 0;
  const items = useMemo(
    () => activeQuery.data?.pages.flatMap((page) => page.items) || [],
    [activeQuery.data],
  );
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return items;
    return items.filter((photo) => `${photo.name} ${photo.folder}`.toLowerCase().includes(keyword));
  }, [items, search]);
  const lightboxItems = lightboxContextQuery.data?.items
    || (lightboxPhoto ? [lightboxPhoto.photo] : []);

  useEffect(() => {
    setSelected(new Set());
    setSelectionAnchor(null);
    setLightboxPhoto(null);
    setLightboxIndex(-1);
    setTimelineDragging(false);
    setDeleteConfirmOpen(false);
    setRefreshTooFast(false);
  }, [view, category, starredOnly]);

  useEffect(() => {
    if (timelineJumpRef.current) return;
    setTimelineStart(0);
    setTimelinePosition(0);
    setTimelineTargetId(null);
  }, [category, starredOnly]);

  useEffect(() => {
    const pending = pendingScrollRestoreRef.current;
    if (!pending || pending.view !== view || activeQuery.isLoading) return undefined;
    let cancelled = false;
    let frame = 0;
    let timer = 0;
    let attempts = 0;
    const restore = () => {
      if (cancelled || pendingScrollRestoreRef.current !== pending) return;
      const maxTop = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      window.scrollTo({ top: Math.min(pending.top, maxTop), behavior: "instant" });
      if (maxTop + 2 >= pending.top || attempts >= 8) {
        pendingScrollRestoreRef.current = null;
        return;
      }
      attempts += 1;
      timer = window.setTimeout(restore, 55);
    };
    frame = window.requestAnimationFrame(() => {
      frame = window.requestAnimationFrame(restore);
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [activeQuery.isLoading, filteredItems.length, layoutEpoch, view]);

  useEffect(() => () => {
    window.clearTimeout(timelineReleaseTimer.current);
    window.clearTimeout(refreshHintTimer.current);
  }, []);

  const finishMutation = useCallback((message) => {
    setToast(message);
    setSelected(new Set());
    queryClient.invalidateQueries({ queryKey: ["review"] });
    queryClient.invalidateQueries({ queryKey: ["deletions"] });
    queryClient.invalidateQueries({ queryKey: ["photos"] });
    queryClient.invalidateQueries({ queryKey: ["timeline-index"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
  }, [queryClient]);

  const removeCachedItems = useCallback((queryKey, ids) => {
    const removed = new Set(ids);
    queryClient.setQueriesData({ queryKey }, (data) => {
      if (!data?.pages) return data;
      return {
        ...data,
        pages: data.pages.map((page) => ({
          ...page,
          items: page.items.filter((photo) => !removed.has(photo.id)),
        })),
      };
    });
  }, [queryClient]);

  const removeReviewItems = useCallback((ids) => {
    removeCachedItems(["review"], ids);
    setSelected(new Set());
    setSelectionAnchor(null);
  }, [removeCachedItems]);

  const closeLightboxIfRemoved = useCallback((ids) => {
    const activeId = lightboxItems[lightboxIndex]?.id;
    if (activeId && ids.includes(activeId)) {
      setLightboxIndex(-1);
      setLightboxPhoto(null);
    }
  }, [lightboxIndex, lightboxItems]);

  const randomFeedQueryKey = ["photos", category, "random", starredOnly, 0];

  const categoryMutation = useMutation({
    mutationFn: ({ ids, nextCategory }) => setCategory(ids, nextCategory),
    onSuccess: (_, variables) => {
      if (view === "review") removeReviewItems(variables.ids);
      closeLightboxIfRemoved(variables.ids);
      finishMutation(variables.nextCategory === 2 ? "已转入样片" : "已归入生活");
    },
    onError: (error) => setToast(error.message),
  });
  const sampleMutation = useMutation({
    mutationFn: markReviewSample,
    onSuccess: (_, ids) => {
      removeReviewItems(ids);
      closeLightboxIfRemoved(ids);
      finishMutation(`${ids.length} 张照片已转入样片`);
    },
    onError: (error) => setToast(error.message),
  });
  const dismissMutation = useMutation({
    mutationFn: dismissReview,
    onSuccess: (_, ids) => {
      removeReviewItems(ids);
      closeLightboxIfRemoved(ids);
      finishMutation(`${ids.length} 张候选已忽略`);
    },
    onError: (error) => setToast(error.message),
  });
  const selectAllMutation = useMutation({
    mutationFn: getAllReviewIds,
    onSuccess: ({ ids, truncated }) => {
      setSelected(new Set(ids));
      setSelectionAnchor(null);
      setToast(truncated ? `已选择前 ${ids.length} 张候选` : `已选择全部 ${ids.length} 张候选`);
    },
    onError: (error) => setToast(error.message),
  });
  const selectAllDeletionsMutation = useMutation({
    mutationFn: getAllDeletionIds,
    onSuccess: ({ ids, truncated }) => {
      setSelected(new Set(ids));
      setSelectionAnchor(null);
      setToast(truncated ? `已选择前 ${ids.length} 张待删除照片` : `已选择全部 ${ids.length} 张待删除照片`);
    },
    onError: (error) => setToast(error.message),
  });
  const queueDeletionMutation = useMutation({
    mutationFn: (ids) => queueDeletion(ids),
    onMutate: (ids) => {
      removeCachedItems(["photos"], ids);
      removeCachedItems(["review"], ids);
      closeLightboxIfRemoved(ids);
      setSelected(new Set());
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deletions"] });
      queryClient.invalidateQueries({ queryKey: ["timeline-index"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      setToast("已移到待删除库，原图尚未删除");
    },
    onError: (error) => {
      queryClient.invalidateQueries({ queryKey: ["photos"] });
      queryClient.invalidateQueries({ queryKey: ["review"] });
      setToast(error.message);
    },
  });
  const restoreDeletionMutation = useMutation({
    mutationFn: restoreDeletion,
    onSuccess: ({ restored }, ids) => {
      removeCachedItems(["deletions"], ids);
      finishMutation(`${restored} 张照片已恢复到抽取库`);
    },
    onError: (error) => setToast(error.message),
  });
  const deleteOriginalsMutation = useMutation({
    mutationFn: deleteOriginals,
    onSuccess: ({ deleted, deletedIds, failed }) => {
      removeCachedItems(["deletions"], deletedIds);
      setSelected((current) => {
        const next = new Set(current);
        deletedIds.forEach((id) => next.delete(id));
        return next;
      });
      setDeleteConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ["deletions"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      setToast(failed ? `已删除 ${deleted} 张原图，${failed} 张失败并保留在待删除库` : `已永久删除 ${deleted} 张原图`);
    },
    onError: (error) => {
      setDeleteConfirmOpen(false);
      setToast(error.message);
    },
  });
  const randomRefreshMutation = useMutation({
    mutationFn: () => refreshRandomPhotos(category, starredOnly),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: randomFeedQueryKey, exact: true });
    },
    onSuccess: (page) => {
      queryClient.setQueryData(randomFeedQueryKey, {
        pages: [page],
        pageParams: [{ offset: 0, exclude: [] }],
      });
      setLayoutEpoch((value) => value + 1);
    },
    onError: (error) => setToast(error.message),
    onSettled: () => {
      refreshInFlightRef.current = false;
    },
  });
  const applyStarToCachedPhotos = useCallback((ids, starred) => {
    const changedIds = new Set(Array.isArray(ids) ? ids : [ids]);
    queryClient.getQueriesData({ queryKey: ["photos"] }).forEach(([key, data]) => {
      if (!data?.pages) return;
      const hideUnstarred = Boolean(key[3]) && !starred;
      queryClient.setQueryData(key, {
        ...data,
        pages: data.pages.map((page) => ({
          ...page,
          items: page.items
            .map((photo) => (changedIds.has(photo.id) ? { ...photo, starred } : photo))
            .filter((photo) => !(hideUnstarred && changedIds.has(photo.id))),
        })),
      });
    });
    ["review", "deletions"].forEach((queryKey) => {
      queryClient.setQueriesData({ queryKey: [queryKey] }, (data) => (
        data?.pages
          ? {
            ...data,
            pages: data.pages.map((page) => ({
              ...page,
              items: page.items.map((photo) => (changedIds.has(photo.id) ? { ...photo, starred } : photo)),
            })),
          }
          : data
      ));
    });
    queryClient.setQueriesData({ queryKey: ["photo-context"] }, (data) => (
      data?.items
        ? { ...data, items: data.items.map((photo) => (changedIds.has(photo.id) ? { ...photo, starred } : photo)) }
        : data
    ));
    setLightboxPhoto((current) => (
      current && changedIds.has(current.id) ? { ...current, photo: { ...current.photo, starred } } : current
    ));
  }, [queryClient]);

  const starMutation = useMutation({
    mutationFn: ({ id, starred }) => setStarred(id, starred),
    onMutate: ({ id, starred }) => {
      const snapshots = queryClient.getQueriesData({
        predicate: (query) => ["photos", "review", "deletions", "photo-context"].includes(query.queryKey[0]),
      });
      const previousLightboxPhoto = lightboxPhoto;
      const previousLightboxIndex = lightboxIndex;
      const closedLightbox = starredOnly && !starred && lightboxItems[lightboxIndex]?.id === id;
      queryClient.cancelQueries({ queryKey: ["photos"] });
      queryClient.cancelQueries({ queryKey: ["review"] });
      queryClient.cancelQueries({ queryKey: ["deletions"] });
      queryClient.cancelQueries({ queryKey: ["photo-context"] });
      applyStarToCachedPhotos([id], starred);
      if (closedLightbox) {
        setLightboxIndex(-1);
        setLightboxPhoto(null);
      }
      return { snapshots, previousLightboxPhoto, previousLightboxIndex, closedLightbox };
    },
    onSuccess: ({ starred }) => {
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === "photos" && query.queryKey[3] === true,
        refetchType: starredOnly ? "active" : "none",
      });
      setToast(starred ? "已收藏" : "已取消收藏");
    },
    onError: (error, { id }, context) => {
      context?.snapshots?.forEach(([key, data]) => queryClient.setQueryData(key, data));
      setLightboxPhoto((current) => (
        context?.closedLightbox || current?.id === id ? context?.previousLightboxPhoto || null : current
      ));
      if (context?.closedLightbox) setLightboxIndex(context.previousLightboxIndex);
      setToast(`收藏失败：${error.message}`);
    },
  });

  const bulkStarMutation = useMutation({
    mutationFn: ({ ids, starred }) => setStarredMany(ids, starred),
    onMutate: ({ ids, starred }) => {
      const snapshots = queryClient.getQueriesData({
        predicate: (query) => ["photos", "review", "deletions", "photo-context"].includes(query.queryKey[0]),
      });
      queryClient.cancelQueries({ queryKey: ["photos"] });
      queryClient.cancelQueries({ queryKey: ["review"] });
      queryClient.cancelQueries({ queryKey: ["deletions"] });
      queryClient.cancelQueries({ queryKey: ["photo-context"] });
      applyStarToCachedPhotos(ids, starred);
      return { snapshots };
    },
    onSuccess: ({ updated, starred }) => {
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      setToast(starred ? `已收藏 ${updated} 张照片` : `已取消 ${updated} 张收藏`);
    },
    onError: (error, _variables, context) => {
      context?.snapshots?.forEach(([key, data]) => queryClient.setQueryData(key, data));
      setToast(`批量收藏失败：${error.message}`);
    },
  });

  const handleRandomRefresh = () => {
    if (refreshInFlightRef.current) {
      window.clearTimeout(refreshHintTimer.current);
      setRefreshTooFast(true);
      refreshHintTimer.current = window.setTimeout(() => setRefreshTooFast(false), 1400);
      return;
    }
    refreshInFlightRef.current = true;
    randomRefreshMutation.mutate();
  };

  const handleSelect = useCallback((index, extend, forceSelected = null) => {
    const photo = filteredItems[index];
    if (!photo) return;
    if (extend && selectionAnchor !== null) {
      const start = Math.min(selectionAnchor, index);
      const end = Math.max(selectionAnchor, index);
      setSelected(new Set(filteredItems.slice(start, end + 1).map((item) => item.id)));
      return;
    }
    setSelectionAnchor(index);
    setSelected((current) => {
      const next = new Set(current);
      if (typeof forceSelected === "boolean") {
        if (forceSelected) next.add(photo.id);
        else next.delete(photo.id);
      } else if (next.has(photo.id)) next.delete(photo.id);
      else next.add(photo.id);
      return next;
    });
  }, [filteredItems, selectionAnchor]);

  const timelineLocationMutation = useMutation({
    mutationFn: ({ photo, targetCategory, targetStarredOnly }) => (
      getTimelineLocation(photo.id, targetCategory, targetStarredOnly)
    ),
    onSuccess: ({ id, offset }, { targetCategory, targetStarredOnly }) => {
      timelineJumpRef.current = id;
      setTimelineTargetId(id);
      setCategoryFilter(targetCategory);
      setStarredOnly(targetStarredOnly);
      handleViewChange("timeline", { restore: false });
      setTimelineStart(offset);
      setTimelinePosition(offset);
      setSelected(new Set());
      setSelectionAnchor(null);
    },
    onError: (error) => setToast(`时间线定位失败：${error.message}`),
  });

  const handleJumpToTimeline = useCallback((photo) => {
    if (!photo || view === "deletions" || timelineLocationMutation.isPending) return;
    const targetCategory = view === "review" ? 1 : category;
    const targetStarredOnly = view !== "review" && starredOnly && Boolean(photo.starred);
    timelineLocationMutation.mutate({ photo, targetCategory, targetStarredOnly });
  }, [category, starredOnly, timelineLocationMutation, view]);

  const openPhoto = useCallback((photo) => {
    if (!photo) return;
    setLightboxPhoto({
      photo,
      id: photo.id,
      category: view === "deletions" ? null : view === "review" ? 1 : category,
      starredOnly: view === "review" || view === "deletions" ? false : starredOnly,
    });
    setLightboxIndex(0);
  }, [category, starredOnly, view]);

  const handleOpen = useCallback((index) => {
    openPhoto(filteredItems[index]);
  }, [filteredItems, openPhoto]);

  const handleTimelineCommit = useCallback((offset) => {
    const nextOffset = Math.max(0, Math.round(offset));
    window.clearTimeout(timelineReleaseTimer.current);
    setTimelineDragging(true);
    setTimelinePosition(nextOffset);
    setTimelineStart(nextOffset);
    const section = document.querySelector(".section-head");
    if (section) {
      window.scrollTo({ top: Math.max(0, section.getBoundingClientRect().top + window.scrollY - 18), behavior: "instant" });
    }
    timelineReleaseTimer.current = window.setTimeout(() => setTimelineDragging(false), 650);
  }, []);

  const handleTimelineVisibleIndex = useCallback((visibleIndex) => {
    if (!timelineDragging) setTimelinePosition(timelineLoadedStart + visibleIndex);
  }, [timelineDragging, timelineLoadedStart]);

  useEffect(() => {
    if (view !== "timeline" || !timelineTargetId) return undefined;
    if (!filteredItems.some((photo) => photo.id === timelineTargetId)) return undefined;
    let clearTimer = 0;
    const scrollTimer = window.setTimeout(() => {
      const tile = document.querySelector(`[data-photo-id="${timelineTargetId}"]`);
      if (!tile) return;
      tile.scrollIntoView({ block: "center", behavior: "instant" });
      timelineJumpRef.current = null;
      clearTimer = window.setTimeout(() => setTimelineTargetId(null), 1700);
    }, 90);
    return () => {
      window.clearTimeout(scrollTimer);
      window.clearTimeout(clearTimer);
    };
  }, [filteredItems, timelineTargetId, view]);

  const handleLoadPrevious = useCallback(() => {
    if (feedQuery.isFetchingPreviousPage) return Promise.resolve();
    return feedQuery.fetchPreviousPage();
  }, [feedQuery.fetchPreviousPage, feedQuery.isFetchingPreviousPage]);

  useEffect(() => {
    if (lightboxContextQuery.data && lightboxPhoto) {
      setLightboxIndex(lightboxContextQuery.data.index);
    }
  }, [lightboxContextQuery.data, lightboxPhoto]);

  const title = view === "review"
    ? "疑似样片"
    : view === "deletions"
      ? "待删除库"
      : view === "timeline"
        ? "时间线"
        : category === 2 ? "样片漫游" : "随心漫游";
  const subtitle = view === "review"
    ? "明确成人内容进入这里，确认后再跨越生活分类规则。"
    : view === "deletions"
      ? "这里的照片已退出所有瀑布流；可以恢复，也可以二次确认后永久删除原图。"
    : view === "timeline"
      ? "从最近到更早，沿着时间向回看。"
      : "每次打开，都从不同的文件夹、时间和事件里重新抽取。";

  return (
    <Box className="app-shell">
      <AppNavigation
        mobile={mobile}
        view={view}
        onChange={handleViewChange}
        reviewCount={statsQuery.data?.review || 0}
        deletionCount={statsQuery.data?.pendingDeletion || 0}
      />
      <Box component="main" className={`main-content ${view === "timeline" ? "has-timeline" : ""}`}>
        <Box className="topbar">
          <Stack direction="row" spacing={1} className="stat-pills">
            <Chip label={`${new Intl.NumberFormat("zh-CN").format(statsQuery.data?.life || 0)} 生活`} />
            <Chip label={`${new Intl.NumberFormat("zh-CN").format(statsQuery.data?.sample || 0)} 样片`} />
          </Stack>
          <TextField
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            size="small"
            placeholder="在当前结果中搜索"
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchRounded /></InputAdornment> } }}
          />
        </Box>

        {view === "discover" && !starredOnly && !activeQuery.isLoading && (
          <Hero
            items={items}
            total={statsQuery.data?.total}
            onLocate={handleJumpToTimeline}
            onNeedMore={() => !feedQuery.isFetchingNextPage && feedQuery.fetchNextPage()}
            hasMore={Boolean(feedQuery.hasNextPage)}
            loadingMore={feedQuery.isFetchingNextPage}
          />
        )}

        <Box className="section-head">
          <Box>
            <Typography variant="h2">{title}</Typography>
            <Typography color="text.secondary">{subtitle}</Typography>
          </Box>
          {view !== "review" && view !== "deletions" && (
            <Stack direction="row" spacing={1} className="section-filters">
              <ToggleButtonGroup
                exclusive
                value={category}
                onChange={(_, value) => value && setCategoryFilter(value)}
                size="small"
                aria-label="照片分类"
              >
                <ToggleButton value={1}><HomeRounded fontSize="small" />生活</ToggleButton>
                <ToggleButton value={2}><AutoAwesomeRounded fontSize="small" />样片</ToggleButton>
              </ToggleButtonGroup>
              <ToggleButton
                value="starred"
                selected={starredOnly}
                onChange={() => setStarredOnly((current) => !current)}
                size="small"
                className="starred-filter"
                aria-label={starredOnly ? "显示全部照片" : "只看收藏照片"}
              >
                {starredOnly ? <StarRounded fontSize="small" /> : <StarBorderRounded fontSize="small" />}
                收藏
              </ToggleButton>
              {view === "discover" && (
                <Box className="random-refresh-control">
                  <Button
                    color="inherit"
                    className={`random-refresh-button ${randomRefreshMutation.isPending ? "is-loading" : ""}`}
                    startIcon={<RefreshRounded fontSize="small" />}
                    onClick={handleRandomRefresh}
                    aria-label="重新抽取随机照片"
                    aria-busy={randomRefreshMutation.isPending}
                  >
                    刷新
                  </Button>
                  <Typography
                    variant="caption"
                    className={`random-refresh-hint ${refreshTooFast ? "is-visible" : ""}`}
                  >
                    刷新的太快啦……
                  </Typography>
                </Box>
              )}
            </Stack>
          )}
          {view === "review" && (
            <Button
              variant="outlined"
              className="review-select-all"
              startIcon={selectAllMutation.isPending ? <CircularProgress size={18} /> : <DoneAllRounded />}
              onClick={() => selectAllMutation.mutate()}
              disabled={selectAllMutation.isPending || sampleMutation.isPending || dismissMutation.isPending}
            >
              全选全部候选
            </Button>
          )}
          {view === "deletions" && (
            <Button
              variant="outlined"
              className="review-select-all"
              startIcon={selectAllDeletionsMutation.isPending ? <CircularProgress size={18} /> : <DoneAllRounded />}
              onClick={() => selectAllDeletionsMutation.mutate()}
              disabled={selectAllDeletionsMutation.isPending || restoreDeletionMutation.isPending || deleteOriginalsMutation.isPending}
            >
              全选待删除照片
            </Button>
          )}
        </Box>

        {activeQuery.isError && <Alert severity="error">{activeQuery.error.message}</Alert>}
        {view === "timeline" && !search && timelineIndexQuery.data?.total > 0 && (
          <Suspense fallback={null}>
            <TimelineScrubber
              index={timelineIndexQuery.data}
              offset={timelinePosition}
              onCommit={handleTimelineCommit}
            />
          </Suspense>
        )}
        {activeQuery.isLoading ? <LoadingWall /> : filteredItems.length === 0 ? (
          <Paper className="empty-state" variant="outlined">
            {view === "review" ? <DoneAllRounded /> : view === "deletions" ? <DeleteSweepRounded /> : <StarBorderRounded />}
            <Typography variant="h6">
              {view === "review"
                ? "疑似样片已处理完"
                : view === "deletions"
                  ? "待删除库是空的"
                  : starredOnly ? "这个分类还没有收藏照片" : "没有找到照片"}
            </Typography>
            <Typography color="text.secondary">
              {view === "review"
                ? "后续识别出的新候选会继续出现在这里。"
                : view === "deletions"
                  ? "瀑布流右下角的删除按钮只会先把照片移到这里，不会直接删除原图。"
                : starredOnly
                  ? "在照片右上角或放大视图里点星星，就会出现在这里。"
                  : "换一个分类或清除搜索条件再试试。"}
            </Typography>
          </Paper>
        ) : (
          <PhotoMasonry
            key={`${view}-${category}-${columns}-${layoutEpoch}-${timelineStart}`}
            items={filteredItems}
            columnCount={columns}
            selectionEnabled
            selected={selected}
            onSelect={handleSelect}
            onOpen={handleOpen}
            onStar={(id, starred) => starMutation.mutate({ id, starred })}
            onQueueDelete={view === "deletions" ? undefined : (id) => queueDeletionMutation.mutate([id])}
            onJumpTimeline={view === "deletions" ? undefined : handleJumpToTimeline}
            onLoadMore={() => !activeQuery.isFetchingNextPage && activeQuery.fetchNextPage()}
            onLoadPrevious={view === "timeline" ? handleLoadPrevious : undefined}
            loadingMore={activeQuery.isFetchingNextPage}
            loadingPrevious={view === "timeline" && feedQuery.isFetchingPreviousPage}
            hasMore={Boolean(activeQuery.hasNextPage) && !search}
            hasPrevious={view === "timeline" && Boolean(feedQuery.hasPreviousPage) && !search}
            onVisibleIndex={view === "timeline" ? handleTimelineVisibleIndex : undefined}
            focusId={timelineTargetId}
          />
        )}

        {selected.size > 0 && (
          <Paper className="selection-bar" elevation={18}>
            <Typography><strong>{selected.size}</strong> 张已选择</Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Button startIcon={<DeselectRounded />} color="inherit" onClick={() => setSelected(new Set())}>
                取消选择
              </Button>
              {view === "deletions" ? (
                <>
                  <Button
                    startIcon={<RestoreFromTrashRounded />}
                    color="inherit"
                    disabled={restoreDeletionMutation.isPending || deleteOriginalsMutation.isPending}
                    onClick={() => restoreDeletionMutation.mutate([...selected])}
                  >
                    恢复到抽取库
                  </Button>
                  <Button
                    variant="contained"
                    color="error"
                    startIcon={<DeleteForeverRounded />}
                    disabled={restoreDeletionMutation.isPending || deleteOriginalsMutation.isPending}
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    删除原图
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    startIcon={<StarRounded />}
                    color="inherit"
                    disabled={bulkStarMutation.isPending}
                    onClick={() => bulkStarMutation.mutate({ ids: [...selected], starred: true })}
                  >
                    收藏
                  </Button>
                  {view === "review" && (
                    <Button
                      startIcon={<CloseRounded />}
                      color="inherit"
                      disabled={sampleMutation.isPending || dismissMutation.isPending}
                      onClick={() => dismissMutation.mutate([...selected])}
                    >
                      归入生活
                    </Button>
                  )}
                  <Button
                    startIcon={<DeleteOutlineRounded />}
                    color="error"
                    disabled={queueDeletionMutation.isPending}
                    onClick={() => queueDeletionMutation.mutate([...selected])}
                  >
                    移到待删除库
                  </Button>
                  <Button
                    variant="contained"
                    startIcon={view === "review" || category === 1 ? <AutoAwesomeRounded /> : <HomeRounded />}
                    disabled={categoryMutation.isPending || sampleMutation.isPending || dismissMutation.isPending}
                    onClick={() => (
                      view === "review"
                        ? sampleMutation.mutate([...selected])
                        : categoryMutation.mutate({ ids: [...selected], nextCategory: category === 1 ? 2 : 1 })
                    )}
                  >
                    {view === "review" || category === 1 ? "转样片" : "归入生活"}
                  </Button>
                </>
              )}
            </Stack>
          </Paper>
        )}
      </Box>

      {lightboxIndex >= 0 && (
        <Suspense fallback={null}>
          <PhotoLightbox
            items={lightboxItems}
            index={lightboxIndex}
            onIndex={setLightboxIndex}
            loadingContext={lightboxContextQuery.isFetching}
            readOnly={view === "deletions"}
            onClose={() => {
              setLightboxIndex(-1);
              setLightboxPhoto(null);
            }}
            onCategory={(id, nextCategory) => categoryMutation.mutate({ ids: [id], nextCategory })}
            onStar={(id, starred) => starMutation.mutate({ id, starred })}
          />
        </Suspense>
      )}
      <Dialog
        open={deleteConfirmOpen}
        onClose={() => !deleteOriginalsMutation.isPending && setDeleteConfirmOpen(false)}
        aria-labelledby="delete-originals-title"
      >
        <DialogTitle id="delete-originals-title">再次确认删除原图</DialogTitle>
        <DialogContent>
          <DialogContentText>
            将永久删除选中的 {selected.size} 张原始照片。这个操作无法撤销，缩略图缓存不会作为原图保留入口。
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button
            color="inherit"
            disabled={deleteOriginalsMutation.isPending}
            onClick={() => setDeleteConfirmOpen(false)}
          >
            返回检查
          </Button>
          <Button
            color="error"
            variant="contained"
            startIcon={deleteOriginalsMutation.isPending ? <CircularProgress size={18} /> : <DeleteForeverRounded />}
            disabled={deleteOriginalsMutation.isPending || selected.size === 0}
            onClick={() => deleteOriginalsMutation.mutate([...selected])}
          >
            确认永久删除原图
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={2600}
        onClose={() => setToast("")}
        message={toast}
      />
      {(categoryMutation.isPending || sampleMutation.isPending || dismissMutation.isPending
        || starMutation.isPending || bulkStarMutation.isPending || timelineLocationMutation.isPending
        || selectAllMutation.isPending || selectAllDeletionsMutation.isPending
        || queueDeletionMutation.isPending || restoreDeletionMutation.isPending || deleteOriginalsMutation.isPending) && (
        <Box className="global-progress"><CircularProgress size={24} /></Box>
      )}
    </Box>
  );
}
