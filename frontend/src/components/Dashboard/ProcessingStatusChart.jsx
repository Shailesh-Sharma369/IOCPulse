import React from 'react';
import { Paper, Box, Typography } from '@mui/material';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const ProcessingStatusChart = ({ total, processed, pending, failed }) => {
  // We only show slices if they are greater than 0
  const data = [
    { name: 'Processed', value: processed || 0, color: '#22C55E' },
    { name: 'Pending', value: pending || 0, color: '#F59E0B' },
    { name: 'Failed', value: failed || 0, color: '#EF4444' },
  ].filter(item => item.value > 0);

  // If there is absolutely no data
  if (data.length === 0) {
    return (
      <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
        <Typography variant="h6" fontWeight="bold" mb={1}>Processing Status Distribution</Typography>
        <Typography variant="body2" color="text.secondary">No articles available yet.</Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <Box sx={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="h6" fontWeight="bold">Processing Status Distribution</Typography>
      </Box>
      <Box sx={{ position: 'relative', width: '100%', height: 200, display: 'flex', justifyContent: 'center' }}>
        <Box sx={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', zIndex: 1 }}>
          <Typography variant="h4" fontWeight="bold">{total || 0}</Typography>
          <Typography variant="body2" color="text.secondary">Total</Typography>
        </Box>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2} dataKey="value">
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} stroke="#ffffff" strokeWidth={2} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </Box>
      <Box sx={{ width: '100%', mt: 2, display: 'flex', justifyContent: 'center', gap: 3 }}>
        {data.map((entry) => (
          <Box key={entry.name} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: entry.color }} />
            <Typography variant="caption" color="text.secondary">{entry.name}</Typography>
            <Typography variant="caption" fontWeight="bold">{entry.value}</Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
};

export default ProcessingStatusChart;