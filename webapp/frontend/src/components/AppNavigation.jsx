import React from "react";
import {
  Badge,
  BottomNavigation,
  BottomNavigationAction,
  Box,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from "@mui/material";
import ExploreRounded from "@mui/icons-material/ExploreRounded";
import CalendarMonthRounded from "@mui/icons-material/CalendarMonthRounded";
import ShieldRounded from "@mui/icons-material/ShieldRounded";
import DeleteSweepRounded from "@mui/icons-material/DeleteSweepRounded";

const navItems = [
  { id: "discover", label: "漫游", icon: ExploreRounded },
  { id: "timeline", label: "时间", icon: CalendarMonthRounded },
  { id: "review", label: "疑似样片", icon: ShieldRounded },
  { id: "deletions", label: "待删除库", icon: DeleteSweepRounded },
];

function NavIcon({ id, Icon, reviewCount, deletionCount }) {
  const count = id === "review" ? reviewCount : id === "deletions" ? deletionCount : 0;
  return count > 0 ? <Badge color="primary" badgeContent={count}><Icon /></Badge> : <Icon />;
}

function Brand() {
  return (
    <Box className="brand">
      <span className="brand__mark"><i /><i /><i /></span>
      <Box>
        <Typography className="brand__name">MOMENTS</Typography>
        <Typography className="brand__sub">LOCAL PHOTO ARCHIVE</Typography>
      </Box>
    </Box>
  );
}

export default function AppNavigation({
  mobile,
  view,
  onChange,
  reviewCount = 0,
  deletionCount = 0,
}) {
  if (mobile) {
    return (
      <Paper className="mobile-nav" elevation={14}>
        <BottomNavigation value={view} onChange={(_, value) => onChange(value)}>
          {navItems.map(({ id, label, icon: Icon }) => (
            <BottomNavigationAction
              key={id}
              value={id}
              label={label}
              icon={<NavIcon id={id} Icon={Icon} reviewCount={reviewCount} deletionCount={deletionCount} />}
            />
          ))}
        </BottomNavigation>
      </Paper>
    );
  }

  return (
    <Drawer variant="permanent" className="side-drawer" PaperProps={{ className: "side-drawer__paper" }}>
      <Brand />
      <List className="side-nav">
        {navItems.map(({ id, label, icon: Icon }) => (
          <ListItemButton key={id} selected={view === id} onClick={() => onChange(id)}>
            <ListItemIcon>
              <NavIcon id={id} Icon={Icon} reviewCount={reviewCount} deletionCount={deletionCount} />
            </ListItemIcon>
            <ListItemText primary={label} />
          </ListItemButton>
        ))}
      </List>
      <Box className="side-drawer__footer">
        <Typography variant="caption">数据留在本机</Typography>
        <span className="local-dot" />
      </Box>
    </Drawer>
  );
}
