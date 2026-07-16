import React, { useEffect, useMemo, useState } from "react";
import { Button, Paper, Slider, Typography } from "@mui/material";

function monthAtOffset(months, offset) {
  if (!months?.length) return "日期未知";
  let low = 0;
  let high = months.length - 1;
  let match = months[0];
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (months[middle].offset <= offset) {
      match = months[middle];
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return match.month === "未知日期" ? match.month : match.month.replace("-", "年") + "月";
}

export default function TimelineScrubber({ index, offset, onCommit }) {
  const total = Math.max(Number(index?.total) || 0, 0);
  const max = Math.max(total - 1, 1);
  const [dragOffset, setDragOffset] = useState(offset);
  const [dragging, setDragging] = useState(false);
  const safeOffset = Math.max(0, Math.min(Number(dragOffset) || 0, max));
  const months = index?.months || [];
  const label = monthAtOffset(months, safeOffset);

  useEffect(() => {
    if (!dragging) setDragOffset(offset);
  }, [dragging, offset]);
  const marks = useMemo(() => {
    const years = new Set();
    return months.flatMap((item) => {
      const year = item.month?.slice(0, 4);
      if (!/^\d{4}$/.test(year) || years.has(year)) return [];
      years.add(year);
      return [{ value: max - Math.min(item.offset, max), label: year }];
    });
  }, [max, months]);

  const toOffset = (sliderValue) => max - Number(sliderValue);
  return (
    <Paper className="timeline-scrubber" elevation={16} aria-label="时间线日期导航">
      <Typography className="timeline-scrubber__date" variant="caption">{label}</Typography>
      <Slider
        className="timeline-scrubber__slider"
        orientation="vertical"
        min={0}
        max={max}
        value={max - safeOffset}
        marks={marks}
        disabled={total <= 1}
        valueLabelDisplay="auto"
        valueLabelFormat={(value) => monthAtOffset(months, toOffset(value))}
        getAriaValueText={(value) => monthAtOffset(months, toOffset(value))}
        onChange={(_, value) => {
          setDragging(true);
          setDragOffset(toOffset(value));
        }}
        onChangeCommitted={(_, value) => {
          const nextOffset = toOffset(value);
          setDragging(false);
          setDragOffset(nextOffset);
          onCommit(nextOffset);
        }}
      />
      <Button size="small" color="inherit" onClick={() => onCommit(0)}>最新</Button>
    </Paper>
  );
}
