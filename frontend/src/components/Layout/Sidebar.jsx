import React, { useState } from 'react';
import { Box, Drawer, List, ListItemButton, ListItemIcon, ListItemText, Typography, IconButton } from '@mui/material';
import { LayoutDashboard, Database, Cpu, FileText, FileOutput, Share2, ChevronRight, ChevronLeft, Activity } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

const drawerWidth = 240;

const Sidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const menuItems = [
    { label: 'Dashboard', icon: LayoutDashboard, path: '/' },
    { label: 'Ingestion', icon: Database, path: '/ingestion' },
    { label: 'Processing', icon: Cpu, path: '/processing' },
    { label: 'Raw Articles', icon: FileText, path: '/raw' },
    { label: 'Processed Articles', icon: FileOutput, path: '/processed' },
    { label: 'Export', icon: Share2, path: '/export' },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: collapsed ? 64 : drawerWidth,
        flexShrink: 0,
        [`& .MuiDrawer-paper`]: {
          width: collapsed ? 64 : drawerWidth,
          boxSizing: 'border-box',
          backgroundColor: 'sidebar.bg',
          color: 'sidebar.text',
          borderRight: 'none',
          transition: 'width 0.2s',
          overflowX: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between'
        },
      }}
    >
      <Box sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ bgcolor: '#2563EB', borderRadius: 2, p: 0.5, color: 'white' }}>
            <Activity size={20} />
          </Box>
          {!collapsed && <Typography variant="h6" fontWeight="bold" sx={{ color: 'white' }}>IntelVix</Typography>}
        </Box>
      </Box>

      <List sx={{ flexGrow: 1, px: 1, py: 2 }}>
        {menuItems.map((item) => (
          <ListItemButton
            key={item.path}
            onClick={() => navigate(item.path)}
            sx={{
              borderRadius: 2,
              mb: 0.5,
              bgcolor: isActive(item.path) ? 'sidebar.active' : 'transparent',
              color: isActive(item.path) ? 'sidebar.textActive' : 'sidebar.text',
              '&:hover': { bgcolor: isActive(item.path) ? 'sidebar.active' : 'sidebar.hover' },
              justifyContent: collapsed ? 'center' : 'flex-start',
            }}
          >
            <ListItemIcon sx={{ minWidth: collapsed ? 0 : 40, color: 'inherit', mr: collapsed ? 0 : 2 }}>
              <item.icon size={20} />
            </ListItemIcon>
            {!collapsed && <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: 500 }} />}
          </ListItemButton>
        ))}
      </List>

      <Box sx={{ p: 2, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {!collapsed && (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
              <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#22C55E' }} />
              <Typography variant="caption" sx={{ color: '#94A3B8' }}>All Systems Operational</Typography>
            </Box>
            <Box sx={{ width: '100%', mb: 2 }}>
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block', color: '#64748B' }}>Version 1.0.0</Typography>
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block', color: '#64748B' }}>Environment Production</Typography>
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block', color: '#64748B' }}>Last Updated 2 mins ago</Typography>
            </Box>
          </>
        )}
        <IconButton onClick={() => setCollapsed(!collapsed)} sx={{ color: 'sidebar.text' }}>
          {collapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
        </IconButton>
      </Box>
    </Drawer>
  );
};

export default Sidebar;