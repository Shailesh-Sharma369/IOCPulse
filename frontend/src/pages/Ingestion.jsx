import React, { useState, useEffect } from 'react';
import { Box, Grid, Paper, Typography, TextField, Button, InputAdornment, Checkbox, FormControlLabel, MenuItem, Select, Divider, Chip, Snackbar, Alert } from '@mui/material';
import { Search, Play, RotateCcw, Globe, FileText, Timer, CheckCircle, AlertTriangle } from 'lucide-react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import dayjs from 'dayjs';
import { useSources, useStartIngestion, useRecentJobs, useJob } from '../hooks/useJobs';
import { useQueryClient } from '@tanstack/react-query';
import IngestionProgress from '../components/Ingestion/IngestionProgress';
import RecentRunsTable from '../components/Ingestion/RecentRunsTable';

const Ingestion = () => {
  const { data: sourcesData = [] } = useSources();
  const { data: recentJobs = [], refetch: refetchJobs } = useRecentJobs();
  const startIngestionMutation = useStartIngestion();
  const queryClient = useQueryClient();

  // ---- Load from localStorage ----
  const loadState = (key, defaultValue) => {
    try {
      const saved = localStorage.getItem(`ingestion_${key}`);
      if (saved !== null) return JSON.parse(saved);
    } catch (e) {}
    return defaultValue;
  };

  const [selectedSources, setSelectedSources] = useState(() => loadState('selectedSources', []));
  const [dateRange, setDateRange] = useState(() => {
    const saved = loadState('dateRange', null);
    if (saved && Array.isArray(saved) && saved.length === 2) {
      return [dayjs(saved[0]), dayjs(saved[1])];
    }
    return [dayjs().subtract(7, 'day'), dayjs()];
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [activeJobId, setActiveJobId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });

  const { data: activeJob } = useJob(activeJobId, true);

  // ---- Save to localStorage whenever state changes ----
  useEffect(() => {
    localStorage.setItem('ingestion_selectedSources', JSON.stringify(selectedSources));
  }, [selectedSources]);

  useEffect(() => {
    if (dateRange && dateRange[0] && dateRange[1]) {
      localStorage.setItem('ingestion_dateRange', JSON.stringify([dateRange[0].toISOString(), dateRange[1].toISOString()]));
    }
  }, [dateRange]);

  // ---- Auto-resume latest job on refresh ----
  useEffect(() => {
    if (!activeJobId && recentJobs && recentJobs.length > 0) {
      setActiveJobId(recentJobs[0].job_id);
    }
  }, [recentJobs, activeJobId]);

  const handleJobComplete = (job) => {
    if (job.status === 'completed') {
      setSnackbar({
        open: true,
        message: `✅ Ingestion Completed Successfully. ${job.result || 0} new articles collected. Duration: ${Math.floor((new Date(job.updated_at) - new Date(job.created_at)) / 1000)} seconds.`,
        severity: 'success'
      });
      queryClient.invalidateQueries({ queryKey: ['dashboardMetrics'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardAnalytics'] });
      queryClient.invalidateQueries({ queryKey: ['rawArticles'] });
      refetchJobs();
    } else if (job.status === 'failed') {
      setSnackbar({
        open: true,
        message: `❌ Ingestion Failed: ${job.error || 'Unknown error'}`,
        severity: 'error'
      });
      refetchJobs();
    }
  };

  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };

  const handleSelectAll = (event) => {
    if (event.target.checked) {
      setSelectedSources(sourcesData.map(s => s.id));
    } else {
      setSelectedSources([]);
    }
  };

  const handleToggleSource = (id) => {
    setSelectedSources(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    );
  };

  const handleStartIngestion = async () => {
    if (selectedSources.length === 0) return;
    const sourceNames = sourcesData.filter(s => selectedSources.includes(s.id)).map(s => s.name);

    try {
      const result = await startIngestionMutation.mutateAsync({
        sources: sourceNames,
        start_date: dateRange[0].toISOString(),
        end_date: dateRange[1].toISOString()
      });
      setActiveJobId(result.job_id);
      setLogs([]);
    } catch (error) {
      console.error("Failed to start ingestion:", error);
      setSnackbar({
        open: true,
        message: `Failed to start ingestion: ${error.message || 'Unknown error'}`,
        severity: 'error'
      });
    }
  };

  const kpiData = [
    { title: 'Configured Sources', value: sourcesData.length, sub: `${sourcesData.filter(s => s.is_user).length} user • ${sourcesData.filter(s => !s.is_user).length} built-in`, icon: Globe, color: '#3B82F6' },
    { title: 'Last Run Articles', value: recentJobs.length > 0 && recentJobs[0].status === 'completed' ? recentJobs[0].result || 0 : 0, sub: 'From latest run', icon: FileText, color: '#22C55E' },
    { title: 'Last Run Duration', value: recentJobs.length > 0 && recentJobs[0].status === 'completed' ? `${Math.floor((new Date(recentJobs[0].updated_at) - new Date(recentJobs[0].created_at)) / 1000)}s` : '-', sub: 'Latest run', icon: Timer, color: '#F59E0B' },
    { title: 'Successful Sources', value: recentJobs.length > 0 && recentJobs[0].status === 'completed' ? '18 / 18' : '-', sub: 'Last run', icon: CheckCircle, color: '#22C55E' },
    { title: 'Failed Sources', value: recentJobs.length > 0 && recentJobs[0].status === 'failed' ? '2' : '0', sub: 'Last run', icon: AlertTriangle, color: '#EF4444' },
  ];

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight="bold">Ingestion (Module 1)</Typography>
        <Typography variant="body2" color="text.secondary">Configure sources and run the scraping pipeline to collect threat intelligence articles.</Typography>
      </Box>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        {kpiData.map((kpi, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={2.4} key={idx} sx={{ display: 'flex' }}>
            <Paper sx={{ p: 2, width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Box sx={{ p: 0.5, borderRadius: 1, color: kpi.color }}>
                  <kpi.icon size={18} />
                </Box>
                <Typography variant="body2" color="text.secondary">{kpi.title}</Typography>
              </Box>
              <Typography variant="h5" fontWeight="bold">{kpi.value}</Typography>
              <Typography variant="caption" color="text.secondary">{kpi.sub}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight="bold" sx={{ mb: 3 }}>1. Configure Ingestion</Typography>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Select Sources</Typography>
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <TextField
                size="small"
                placeholder="Search sources..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                InputProps={{ startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment> }}
                sx={{ flexGrow: 1 }}
              />
              <Select size="small" defaultValue="All" sx={{ minWidth: 120 }}>
                <MenuItem value="All">All Categories</MenuItem>
              </Select>
            </Box>

            <Box sx={{ maxHeight: 300, overflowY: 'auto', mb: 3 }}>
              <FormControlLabel
                control={<Checkbox checked={selectedSources.length === sourcesData.length && sourcesData.length > 0} onChange={handleSelectAll} />}
                label={<Typography variant="body2" fontWeight="bold">Select All Active Sources ({sourcesData.length})</Typography>}
              />
              {sourcesData.filter(s => s.name.toLowerCase().includes(searchQuery.toLowerCase())).map((source) => (
                <Box key={source.id} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 0.5, pl: 3 }}>
                  <FormControlLabel
                    control={<Checkbox checked={selectedSources.includes(source.id)} onChange={() => handleToggleSource(source.id)} />}
                    label={<Typography variant="body2">{source.name}</Typography>}
                  />
                  <Chip label={source.category} size="small" variant="outlined" sx={{ fontSize: '0.65rem', height: 20, borderRadius: 1, color: 'primary.main', borderColor: 'primary.light' }} />
                </Box>
              ))}
            </Box>

            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={6}>
                <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Date Range</Typography>
                <LocalizationProvider dateAdapter={AdapterDayjs}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <DatePicker value={dateRange[0]} onChange={(val) => setDateRange([val, dateRange[1]])} slotProps={{ textField: { size: 'small', fullWidth: true, placeholder: 'Start' } }} />
                    <DatePicker value={dateRange[1]} onChange={(val) => setDateRange([dateRange[0], val])} slotProps={{ textField: { size: 'small', fullWidth: true, placeholder: 'End' } }} />
                  </Box>
                </LocalizationProvider>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Scraping Depth</Typography>
                <Select size="small" fullWidth defaultValue="Standard">
                  <MenuItem value="Standard">Standard (Recommended)</MenuItem>
                  <MenuItem value="Deep">Deep (Slower)</MenuItem>
                  <MenuItem value="Shallow">Shallow (Fast)</MenuItem>
                </Select>
              </Grid>
            </Grid>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ cursor: 'pointer', color: 'text.secondary', mb: 2 }}>Advanced Options <Typography component="span" variant="caption">▼</Typography></Typography>

            <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
              <Button
                variant="contained"
                startIcon={<Play size={16} />}
                disabled={selectedSources.length === 0 || startIngestionMutation.isPending || activeJob?.status === 'running'}
                onClick={handleStartIngestion}
              >
                {activeJob?.status === 'running' ? 'Running...' : 'Start Ingestion'}
              </Button>
              <Button variant="outlined" startIcon={<RotateCcw size={16} />} color="inherit">Reset</Button>
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <IngestionProgress job={activeJob} onComplete={handleJobComplete} />
        </Grid>
      </Grid>

      <Box sx={{ mt: 3 }}>
        <RecentRunsTable jobs={recentJobs} />
      </Box>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity} sx={{ width: '100%' }}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default Ingestion;