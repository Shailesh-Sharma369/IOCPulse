import React from 'react';
import { Paper, Box, Typography } from '@mui/material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useDashboardAnalytics } from '../../hooks/useDashboard';

const PipelineTrendsChart = () => {
  const { data } = useDashboardAnalytics();
  const total = data?.metrics?.total_raw || 100; // fallback

  // Generate 7 days of mock data based on total
  const today = new Date();
  const dataPoints = [];
  for (let i = 6; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    // Spread the total over 7 days with some randomness, but ensure sum ≈ total
    // For mock, we'll use a sine-like pattern to look realistic
    const base = Math.max(0, total / 7);
    const variation = base * 0.4 * Math.sin(i * 0.8 + 0.5);
    const value = Math.round(base + variation);
    dataPoints.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      articles: Math.max(0, value)
    });
  }

  return (
    <Paper sx={{ p: 3, height: 380, display: 'flex', flexDirection: 'column' }}>
      <Typography variant="h6" fontWeight="bold" mb={1}>Pipeline Trends</Typography>
      <Box sx={{ flex: 1, width: '100%' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={dataPoints} margin={{ top: 20, right: 20, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
            <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#94A3B8' }} />
            <YAxis tick={{ fontSize: 12, fill: '#94A3B8' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 8 }}
              labelStyle={{ fontWeight: 600 }}
            />
            <Line
              type="monotone"
              dataKey="articles"
              stroke="#2563EB"
              strokeWidth={3}
              dot={{ fill: '#2563EB', r: 4 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Paper>
  );
};

export default PipelineTrendsChart;