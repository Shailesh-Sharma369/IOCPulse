import React from 'react';
import { Paper, Box, Typography, IconButton } from '@mui/material';
import { Info } from 'lucide-react';

const KpiCard = ({ title, value, icon: Icon, trend, color }) => {
  return (
    <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ p: 1, borderRadius: 2, bgcolor: `${color}15`, color: color, display: 'flex' }}>
            <Icon size={20} />
          </Box>
          <Typography variant="body2" color="text.secondary">{title}</Typography>
        </Box>
        <IconButton size="small"><Info size={16} /></IconButton>
      </Box>
      
      <Typography variant="h4" fontWeight="bold" sx={{ mb: 0.5 }}>{value.toLocaleString()}</Typography>
      
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="caption" color="text.secondary">{trend.text}</Typography>
        <Typography variant="caption" sx={{ color: trend.isPositive ? 'status.success' : 'status.failed' }}>
          {trend.isPositive ? '↑' : '↓'} {trend.percentage}%
        </Typography>
        <Typography variant="caption" color="text.secondary">vs yesterday</Typography>
      </Box>
    </Paper>
  );
};

export default KpiCard;