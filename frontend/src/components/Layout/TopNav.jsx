import React from 'react';
import { AppBar, Toolbar, Typography, IconButton, Box, Button, InputBase, Avatar, Menu, MenuItem } from '@mui/material';
import { Search, RefreshCw, Bell, User, Menu as MenuIcon, Calendar } from 'lucide-react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import dayjs from 'dayjs';

const TopNav = ({ onRefresh }) => {
  const [anchorEl, setAnchorEl] = React.useState(null);

  return (
    <AppBar position="sticky" color="default" elevation={0} sx={{ bgcolor: '#FFFFFF', borderBottom: '1px solid #E2E8F0' }}>
      <Toolbar sx={{ minHeight: 64, justifyContent: 'space-between', px: { xs: 2, md: 4 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexGrow: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" fontWeight="bold" color="text.primary">Dashboard</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ display: { xs: 'none', md: 'block' } }}>Real-time overview of your CTI pipeline</Typography>
          </Box>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <LocalizationProvider dateAdapter={AdapterDayjs}>
            <DatePicker 
              defaultValue={dayjs('2026-08-02')} 
              slotProps={{ textField: { size: 'small', sx: { width: 130 } } }} 
            />
          </LocalizationProvider>

          <Button variant="outlined" startIcon={<RefreshCw size={16} />} onClick={onRefresh} size="small" sx={{ textTransform: 'none', color: '#475569', borderColor: '#E2E8F0' }}>
            Refresh
          </Button>
          <IconButton><Bell size={20} /></IconButton>
          <IconButton onClick={(e) => setAnchorEl(e.currentTarget)}>
             <Avatar sx={{ width: 32, height: 32, bgcolor: '#2563EB' }}><User size={16} /></Avatar>
          </IconButton>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem onClick={() => setAnchorEl(null)}>Profile</MenuItem>
            <MenuItem onClick={() => setAnchorEl(null)}>Logout</MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default TopNav;