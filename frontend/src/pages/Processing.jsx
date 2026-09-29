import React, { useState, useEffect } from 'react';
import { Box, Grid, Paper, Typography, Button, Select, MenuItem, Card, CardContent, FormControl, InputLabel } from '@mui/material';
import { Play, RotateCcw, Info, Activity, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import { useDashboard, useDashboardAnalytics } from '../hooks/useDashboard';
import { useStartProcessing, useRecentJobs, useJob } from '../hooks/useJobs';
import ProcessingProgress from '../components/Processing/ProcessingProgress';
import RecentProcessingRuns from '../components/Processing/RecentProcessingRuns';

const Processing = () => {
  const { data: dashboardData, isLoading: dashboardLoading, error: dashboardError } = useDashboard();
  const { data: analyticsData } = useDashboardAnalytics();

  const { data: recentJobs = [], refetch: refetchJobs } = useRecentJobs();
  const startProcessingMutation = useStartProcessing();

  const [batchSize, setBatchSize] = useState(20);
  const [processingMode, setProcessingMode] = useState('Standard');
  const [activeJobId, setActiveJobId] = useState(null);
  const { data: activeJob } = useJob(activeJobId, true);

  // ---- FIX: Auto-load the latest processing job on refresh ----
  useEffect(() => {
    if (!activeJobId && recentJobs && recentJobs.length > 0) {
      const latestProcessingJob = recentJobs.find(job => job.type === 'processing');
      if (latestProcessingJob) {
        setActiveJobId(latestProcessingJob.job_id);
      }
    }
  }, [recentJobs, activeJobId]);

  const handleStartProcessing = async () => {
    try {
      const result = await startProcessingMutation.mutateAsync({ limit: batchSize });
      setActiveJobId(result.job_id);
      refetchJobs();
    } catch (error) {
      console.error("Failed to start processing:", error);
    }
  };

  const pendingCount = dashboardData?.pending || 0;
  const processedMonth = dashboardData?.processed || 0;
  const iocsMonth = analyticsData?.iocs_this_month || 0;

  const topKpiData = [
    { title: 'Pending Articles', value: pendingCount, sub: 'Ready to process', icon: Activity, color: '#8B5CF6' },
    { title: 'Processed Today', value: 0, sub: new Date().toLocaleDateString(), icon: Clock, color: '#22C55E' },
    { title: 'Processed (This Month)', value: processedMonth, sub: 'This month', icon: CheckCircle, color: '#F59E0B' },
    { title: 'Extracted IOCs (Today)', value: 0, sub: new Date().toLocaleDateString(), icon: AlertCircle, color: '#3B82F6' },
    { title: 'Extracted IOCs (This Month)', value: iocsMonth, sub: 'This month', icon: AlertCircle, color: '#EF4444' },
  ];

  if (dashboardLoading && !dashboardData) {
    return <Box sx={{ p: 3 }}>Loading...</Box>;
  }

  if (dashboardError) {
    return <Box sx={{ p: 3, color: 'red' }}>Error loading dashboard data. Please refresh.</Box>;
  }

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight="bold">Processing (Module 2)</Typography>
        <Typography variant="body2" color="text.secondary">Run AI processing to extract IOCs and threat intelligence from collected articles.</Typography>
      </Box>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        {topKpiData.map((kpi, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={2.4} key={idx} sx={{ display: 'flex' }}>
            <Paper sx={{ p: 2, width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Box sx={{ p: 0.5, borderRadius: 1, color: kpi.color }}>
                  <kpi.icon size={18} />
                </Box>
                <Typography variant="body2" color="text.secondary">{kpi.title}</Typography>
              </Box>
              <Typography variant="h5" fontWeight="bold">{kpi.value.toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary">{kpi.sub}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight="bold" sx={{ mb: 3 }}>1. Start Processing</Typography>

            <Box sx={{ bgcolor: '#EFF6FF', p: 2, borderRadius: 2, mb: 3, display: 'flex', gap: 2 }}>
              <Info color="#3B82F6" size={20} />
              <Typography variant="body2" color="#1E40AF">
                AI will process to extract IOCs, malware, threat actors, CVEs and map MITRE ATT&CK techniques from pending articles.
              </Typography>
            </Box>

            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={6}>
                <FormControl fullWidth size="small">
                  <InputLabel>Batch Size (Articles per run)</InputLabel>
                  <Select value={batchSize} onChange={(e) => setBatchSize(e.target.value)} label="Batch Size (Articles per run)">
                    <MenuItem value={10}>10</MenuItem>
                    <MenuItem value={20}>20 (Recommended)</MenuItem>
                    <MenuItem value={50}>50</MenuItem>
                    <MenuItem value={100}>100</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={6}>
                <FormControl fullWidth size="small">
                  <InputLabel>Processing Mode</InputLabel>
                  <Select value={processingMode} onChange={(e) => setProcessingMode(e.target.value)} label="Processing Mode">
                    <MenuItem value="Standard">Standard (Recommended)</MenuItem>
                    <MenuItem value="Aggressive">Aggressive (Higher GPU usage)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>

            <Box sx={{ bgcolor: '#F0FDF4', p: 2, borderRadius: 2, mb: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box>
                <Typography variant="body2" fontWeight="bold" color="#166534">Pending Articles Ready</Typography>
                <Typography variant="caption" color="#15803D">{pendingCount} articles are ready for processing</Typography>
              </Box>
            </Box>

            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                startIcon={<Play size={16} />}
                disabled={pendingCount === 0 || startProcessingMutation.isPending || activeJob?.status === 'running'}
                onClick={handleStartProcessing}
              >
                Start Processing
              </Button>
              <Button variant="outlined" startIcon={<RotateCcw size={16} />} color="inherit">Reset</Button>
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <ProcessingProgress job={activeJob} />
        </Grid>
      </Grid>

      <Box sx={{ mt: 3 }}>
        <RecentProcessingRuns jobs={recentJobs} />
      </Box>
    </Box>
  );
};

export default Processing;