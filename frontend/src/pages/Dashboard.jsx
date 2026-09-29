import React from 'react';
import { Grid, Box, Typography, Paper, CircularProgress } from '@mui/material';
import { useDashboardAnalytics } from '../hooks/useDashboard'; // uses analytics endpoint
import KpiCard from '../components/Dashboard/KpiCard';
import PipelineTrendsChart from '../components/Dashboard/PipelineTrendsChart';
import RecentActivityFeed from '../components/Dashboard/RecentActivityFeed';
import ProcessingStatusChart from '../components/Dashboard/ProcessingStatusChart';
import { FileText, FileCheck, Clock, AlertTriangle } from 'lucide-react';

const Dashboard = () => {
  const { data, isLoading } = useDashboardAnalytics();

  if (isLoading && !data) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  const metrics = data?.metrics || {};

  const kpiData = [
    { title: 'Articles Scraped', value: metrics.total_raw || 0, icon: FileText, color: '#22C55E', trend: { text: 'Total scraped', isPositive: true, percentage: 0 } },
    { title: 'Articles Processed', value: metrics.processed || 0, icon: FileCheck, color: '#8B5CF6', trend: { text: 'Processed', isPositive: true, percentage: 0 } },
    { title: 'Pending Articles', value: metrics.pending || 0, icon: Clock, color: '#F59E0B', trend: { text: 'Pending', isPositive: false, percentage: 0 } },
    { title: 'Failed Articles', value: metrics.failed || 0, icon: AlertTriangle, color: '#EF4444', trend: { text: 'Failed', isPositive: false, percentage: 0 } },
  ];

  return (
    <Box>
      <Grid container spacing={3}>
        {kpiData.map((kpi, index) => (
          <Grid item xs={12} sm={6} md={3} lg={3} key={index}>
            <KpiCard {...kpi} />
          </Grid>
        ))}

        <Grid item xs={12} lg={8}>
          <PipelineTrendsChart />
        </Grid>

        <Grid item xs={12} md={6} lg={4}>
          <ProcessingStatusChart
            total={metrics.total_raw || 0}
            processed={metrics.processed || 0}
            pending={metrics.pending || 0}
            failed={metrics.failed || 0}
          />
        </Grid>

        <Grid item xs={12} lg={8}>
          {/* Pass recent_activity from analytics data */}
          <RecentActivityFeed activities={data?.recent_activity || []} />
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;