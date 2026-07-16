import React, { useEffect, useMemo, useState } from "react";
import { CircularProgress, IconButton, Tooltip } from "@mui/material";
import AutoAwesomeRounded from "@mui/icons-material/AutoAwesomeRounded";
import HomeRounded from "@mui/icons-material/HomeRounded";
import StarBorderRounded from "@mui/icons-material/StarBorderRounded";
import StarRounded from "@mui/icons-material/StarRounded";
import { Lightbox } from "yet-another-react-lightbox";
import Fullscreen from "yet-another-react-lightbox/plugins/fullscreen";
import Thumbnails from "yet-another-react-lightbox/plugins/thumbnails";
import Zoom from "yet-another-react-lightbox/plugins/zoom";

export default function PhotoLightbox({ items, index, onIndex, onClose, onCategory, onStar, loadingContext, readOnly = false }) {
  const [viewportWidth, setViewportWidth] = useState(() => (
    typeof window === "undefined" ? 1280 : window.innerWidth
  ));
  useEffect(() => {
    const updateWidth = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", updateWidth, { passive: true });
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  const slides = useMemo(
    () => items.map((photo) => ({
      src: photo.originalUrl,
      thumbnail: photo.thumbnailUrl,
      alt: photo.name,
      width: photo.width || 1600,
      height: photo.height || 1200,
    })),
    [items],
  );

  const active = items[index];
  const thumbnailWidth = Math.max(56, Math.min(170, Math.floor((viewportWidth - 120) / 10) - 12));
  const actionButtons = active && !readOnly ? [
    <Tooltip title={active.starred ? "取消收藏" : "收藏"} key="star">
      <IconButton
        className={`lightbox-toolbar-action ${active.starred ? "is-starred" : ""}`}
        onClick={() => onStar(active.id, !active.starred)}
        aria-label={active.starred ? "取消收藏" : "收藏"}
      >
        {active.starred ? <StarRounded /> : <StarBorderRounded />}
      </IconButton>
    </Tooltip>,
    <Tooltip title="转为生活" key="life">
      <IconButton className="lightbox-toolbar-action" onClick={() => onCategory(active.id, 1)} aria-label="转为生活">
        <HomeRounded />
      </IconButton>
    </Tooltip>,
    <Tooltip title="转为样片" key="sample">
      <IconButton className="lightbox-toolbar-action" onClick={() => onCategory(active.id, 2)} aria-label="转为样片">
        <AutoAwesomeRounded />
      </IconButton>
    </Tooltip>,
  ] : [];
  return (
    <Lightbox
      className="photo-lightbox"
      open={index >= 0}
      close={onClose}
      index={Math.max(index, 0)}
      slides={slides}
      plugins={[Fullscreen, Thumbnails, Zoom]}
      on={{ view: ({ index: nextIndex }) => onIndex(nextIndex) }}
      animation={{
        fade: 140,
        swipe: 170,
        navigation: 160,
        easing: {
          fade: "ease-out",
          swipe: "cubic-bezier(.22,.75,.2,1)",
          navigation: "cubic-bezier(.22,.75,.2,1)",
        },
      }}
      carousel={{ preload: 1, imageFit: "contain", padding: "20px", spacing: "16px" }}
      thumbnails={{
        position: "bottom",
        width: thumbnailWidth,
        height: Math.max(42, Math.round(thumbnailWidth * 0.6)),
        border: 1,
        borderRadius: 8,
        padding: 2,
        gap: 6,
        imageFit: "cover",
        vignette: true,
        showToggle: false,
      }}
      toolbar={{ buttons: [...actionButtons, "zoom", "fullscreen", "close"] }}
      controller={{ closeOnBackdropClick: true, closeOnPullDown: true }}
      labels={{ Previous: "上一张", Next: "下一张", Close: "关闭", ZoomIn: "放大", ZoomOut: "缩小" }}
      render={{
        controls: () => loadingContext && <CircularProgress className="lightbox-context-progress" size={25} />,
      }}
    />
  );
}
