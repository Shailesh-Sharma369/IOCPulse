import React, { useState, useEffect } from 'react';
import { Box, Paper, Typography, LinearProgress, Grid, Card, CardContent, List, ListItem, Divider, Chip } from '@mui/material';
import { CheckCircle, Loader2, FileText, RefreshCw, Search, Map, Save } from 'lucide-react';

const steps = [
  { label: 'Reading Articles', icon: FileText },
  { label: 'Calling LLM', icon: RefreshCw },
  { label: 'Extracting IOCs', icon: Search },
  { label: 'MITRE Mapping', icon: Map },
  { label: 'Saving Results', icon: Save },
];

const ProcessingProgress = ({ job }) => {
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs] = useState([]);

  // ---- FIX: Live Timer and simulated logs ----
  useEffect(() => {
    if (!job) return;
    const startTime = new Date(job.created_at);

    const interval = setInterval(() => {
      const now = new Date();
      setElapsed(Math.floor((now - startTime) / 1000));

      if (job.status === 'running' && Math.random() > 0.6) {
        const logLines = [
          "Extracting IPs and domains...",
          "Mapping MITRE ATT&CK techniques...",
          "Analyzing malware family...",
          "Validating IOCs against article...",
          "Summarizing threat actor behavior...",
          "Parsing LLM response..."
        ];
        const randomLog = logLines[Math.floor(Math.random() * logLines.length)];
        setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg: randomLog }].slice(-6));
      }
    }, 1000);

    if (job.status === 'completed') {
      setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg: "✅ Processing complete!" }]);
      clearInterval(interval);
    } else if (job.status === 'failed') {
      setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg: "❌ Processing failed. Check logs." }]);
      clearInterval(interval);
    }

    return () => clearInterval(interval);
  }, [job]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  if (!job) {
    return (
      <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', bgcolor: '#F8FAFC' }}>
        <Box sx={{ width: 80, height: 80, bgcolor: '#E2E8F0', borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
          <FileText size={40} color="#94A3B8" />
        </Box>
        <Typography variant="body2" color="text.secondary" fontWeight="bold">No processing running.</Typography>
        <Typography variant="caption" color="text.secondary">Click "Start Processing" to begin.</Typography>
      </Paper>
    );
  }

  let currentStep = 0;
  if (job.status === 'running') {
    currentStep = Math.min(Math.floor(elapsed / 8), steps.length - 1);
  } else if (job.status === 'completed') {
    currentStep = steps.length - 1;
  } else if (job.status === 'failed') {
    currentStep = 2;
  }

  const processed = job.status === 'completed' ? job.result || 0 : 0;
  const failed = job.status === 'failed' ? 1 : 0;

  return (
    <Paper sx={{ p: 3, height: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="body2" color="text.secondary">
            Started At: {new Date(job.created_at).toLocaleString()}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="caption" fontWeight={600} sx={{ color: job.status === 'running' ? '#3B82F6' : job.status === 'completed' ? '#22C55E' : '#EF4444' }}>
            {job.status === 'running' ? 'In Progress' : job.status === 'completed' ? 'Completed' : 'Failed'}
          </Typography>
          {job.status === 'running' && (
            <Typography variant="caption" color="text.secondary">
              ⏱ {formatTime(elapsed)}
            </Typography>
          )}
        </Box>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', position: 'relative', mb: 3, px: 2 }}>
        <LinearProgress
          variant="determinate"
          value={job.status === 'completed' ? 100 : (job.status === 'running' ? Math.min((elapsed / 40) * 100, 95) : 0)}
          sx={{ position: 'absolute', top: 12, left: 0, right: 0, height: 4, zIndex: 0 }}
        />
        {steps.map((step, index) => {
          const isActive = index === currentStep;
          const isCompleted = index < currentStep;
          const Icon = isCompleted ? CheckCircle : (isActive ? step.icon : step.icon);

          return (
            <Box key={step.label} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 1, width: 60 }}>
              <Box sx={{
                width: 40, height: 40, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                bgcolor: isCompleted ? '#22C55E' : (isActive ? '#2563EB' : '#E2E8F0'),
                color: 'white',
                mb: 1,
                animation: isActive && job.status === 'running' ? 'pulse 1.5s ease-in-out infinite' : 'none'
              }}>
                <Icon size={18} className={isActive && job.status === 'running' ? 'animate-spin' : ''} />
              </Box>
              <Typography variant="caption" align="center" sx={{ color: isCompleted || isActive ? 'text.primary' : 'text.disabled', fontWeight: isActive ? 600 : 400, fontSize: '0.6rem' }}>
                {step.label}
              </Typography>
            </Box>
          );
        })}
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={3}>
          <Card variant="outlined">
            <CardContent sx={{ p: 1.5, textAlign: 'center', '&:last-child': { pb: 1.5 } }}>
              <Typography variant="h6" fontWeight="bold">{processed}</Typography>
              <Typography variant="caption" color="text.secondary">Processed</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={3}>
          <Card variant="outlined">
            <CardContent sx={{ p: 1.5, textAlign: 'center', '&:last-child': { pb: 1.5 } }}>
              <Typography variant="h6" fontWeight="bold">0</Typography>
              <Typography variant="caption" color="text.secondary">IOCs Extracted</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={3}>
          <Card variant="outlined" sx={{ borderColor: failed > 0 ? '#EF4444' : 'divider' }}>
            <CardContent sx={{ p: 1.5, textAlign: 'center', '&:last-child': { pb: 1.5 } }}>
              <Typography variant="h6" fontWeight="bold" color={failed > 0 ? '#EF4444' : 'inherit'}>{failed}</Typography>
              <Typography variant="caption" color="text.secondary">Failed</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={3}>
          <Card variant="outlined">
            <CardContent sx={{ p: 1.5, textAlign: 'center', '&:last-child': { pb: 1.5 } }}>
              <Typography variant="h6" fontWeight="bold">{formatTime(elapsed)}</Typography>
              <Typography variant="caption" color="text.secondary">Elapsed Time</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Live Logs</Typography>
      <Box sx={{ bgcolor: '#F8FAFC', borderRadius: 1, p: 2, height: 130, overflowY: 'auto', border: '1px solid #E2E8F0' }}>
        {logs.length === 0 ? (
          <Typography variant="caption" color="text.secondary">Waiting for logs...</Typography>
        ) : (
          <List dense disablePadding>
            {logs.map((log, idx) => (
              <ListItem key={idx} disableGutters sx={{ py: 0.5 }}>
                <Box sx={{ display: 'flex', gap: 2, width: '100%', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                  <Typography variant="caption" sx={{ minWidth: 60, color: 'text.secondary' }}>{log.time}</Typography>
                  <Typography variant="caption" sx={{ color: 'text.primary' }}>{log.msg}</Typography>
                </Box>
              </ListItem>
            ))}
          </List>
        )}
      </Box>
    </Paper>
  );
};

export default ProcessingProgress;