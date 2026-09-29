import React, { useState, useEffect } from 'react';
import { Box, Paper, Typography, LinearProgress, List, ListItem, Divider, Chip } from '@mui/material';
import { CheckCircle, Clock, Loader2, AlertCircle, Globe, Database, FileText, Save } from 'lucide-react';

const stages = [
  { label: 'Initializing', icon: Clock },
  { label: 'Connecting to Sources', icon: Globe },
  { label: 'Downloading Feed', icon: Loader2 },
  { label: 'Parsing Articles', icon: FileText },
  { label: 'Saving to Database', icon: Database },
  { label: 'Completed', icon: CheckCircle },
];

// Mock log messages for each stage
const stageLogs = {
  'Initializing': ['Preparing ingestion environment...', 'Loading source configurations...'],
  'Connecting to Sources': ['Connecting to CISA...', 'Connecting to BleepingComputer...', 'Connecting to The Hacker News...'],
  'Downloading Feed': ['Downloading RSS feed from CISA...', 'Downloading HTML from BleepingComputer...', 'Fetching article links...'],
  'Parsing Articles': ['Parsing 12 articles from CISA...', 'Extracting content from BleepingComputer...', 'Filtering by date range...'],
  'Saving to Database': ['Inserting articles into database...', 'Committing transactions...'],
  'Completed': ['Ingestion completed successfully!'],
};

const IngestionProgress = ({ job, onComplete }) => {
  const [currentStageIndex, setCurrentStageIndex] = useState(0);
  const [logs, setLogs] = useState([]);
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    if (!job) return;

    const startTime = new Date(job.created_at);
    const updateInterval = setInterval(() => {
      const now = new Date();
      const elapsedSeconds = Math.floor((now - startTime) / 1000);
      setElapsed(elapsedSeconds);
    }, 1000);

    if (job.status === 'running') {
      setIsRunning(true);
      // Simulate progress: 0-90% over 20 seconds, then 90-99% for rest
      const elapsedSeconds = (new Date() - new Date(job.created_at)) / 1000;
      let pct = Math.min((elapsedSeconds / 20) * 90, 90);
      if (elapsedSeconds > 20) {
        pct = 90 + Math.min((elapsedSeconds - 20) / 40 * 9, 9);
      }
      setProgress(Math.min(pct, 99));

      // Determine stage based on elapsed time
      const stageIndex = Math.min(Math.floor(elapsedSeconds / 5), stages.length - 2);
      setCurrentStageIndex(stageIndex);

      // Generate logs periodically
      if (logs.length < 20 && Math.random() < 0.3) {
        const stageLabel = stages[stageIndex].label;
        const possibleLogs = stageLogs[stageLabel] || ['Processing...'];
        const newLog = possibleLogs[Math.floor(Math.random() * possibleLogs.length)];
        setLogs(prev => {
          const updated = [...prev, { time: new Date().toLocaleTimeString(), level: 'INFO', message: newLog }];
          if (updated.length > 50) updated.shift();
          return updated;
        });
      }
    } else if (job.status === 'completed') {
      setIsRunning(false);
      setProgress(100);
      setCurrentStageIndex(stages.length - 1);
      // Add completion log
      setLogs(prev => {
        const updated = [...prev, { time: new Date().toLocaleTimeString(), level: 'SUCCESS', message: `✅ Ingestion completed. ${job.result || 0} articles collected.` }];
        if (updated.length > 50) updated.shift();
        return updated;
      });
      if (onComplete) onComplete(job);
      clearInterval(updateInterval);
    } else if (job.status === 'failed') {
      setIsRunning(false);
      setProgress(100);
      setCurrentStageIndex(stages.length - 1);
      setLogs(prev => {
        const updated = [...prev, { time: new Date().toLocaleTimeString(), level: 'ERROR', message: `❌ Ingestion failed: ${job.error || 'Unknown error'}` }];
        if (updated.length > 50) updated.shift();
        return updated;
      });
      clearInterval(updateInterval);
    }

    return () => clearInterval(updateInterval);
  }, [job, onComplete]);

  if (!job) {
    return (
      <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', bgcolor: '#F8FAFC' }}>
        <Box sx={{ width: 80, height: 80, bgcolor: '#E2E8F0', borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
          <Database size={40} color="#94A3B8" />
        </Box>
        <Typography variant="body2" color="text.secondary" fontWeight="bold">No active ingestion job.</Typography>
        <Typography variant="caption" color="text.secondary">Configure and start a job on the left.</Typography>
      </Paper>
    );
  }

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  const currentStage = stages[currentStageIndex] || stages[0];

  return (
    <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Started: {new Date(job.created_at).toLocaleString()}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="caption" fontWeight={600} sx={{ color: job.status === 'running' ? '#3B82F6' : job.status === 'completed' ? '#22C55E' : '#EF4444' }}>
            {job.status === 'running' ? 'Running' : job.status === 'completed' ? 'Completed' : 'Failed'}
          </Typography>
          {job.status === 'running' && (
            <Typography variant="caption" color="text.secondary">
              ⏱ {formatTime(elapsed)}
            </Typography>
          )}
        </Box>
      </Box>

      {/* Progress Bar */}
      <Box sx={{ mb: 2 }}>
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{ height: 8, borderRadius: 4, bgcolor: '#E2E8F0' }}
        />
      </Box>

      {/* Stage Timeline */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', position: 'relative', mb: 3, px: 2 }}>
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{ position: 'absolute', top: 12, left: 0, right: 0, height: 4, zIndex: 0 }}
        />
        {stages.map((stage, index) => {
          const isActive = index === currentStageIndex;
          const isCompleted = index < currentStageIndex;
          const Icon = isCompleted ? CheckCircle : (isActive ? stage.icon : stage.icon);

          return (
            <Box key={stage.label} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 1, width: 60 }}>
              <Box sx={{
                width: 40, height: 40, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                bgcolor: isCompleted ? '#22C55E' : (isActive ? '#2563EB' : '#E2E8F0'),
                color: 'white',
                mb: 1,
                animation: isActive && job.status === 'running' ? 'pulse 1.5s ease-in-out infinite' : 'none',
                transition: 'all 0.3s'
              }}>
                <Icon size={18} className={isActive && job.status === 'running' ? 'animate-spin' : ''} />
              </Box>
              <Typography variant="caption" align="center" sx={{ color: isCompleted || isActive ? 'text.primary' : 'text.disabled', fontWeight: isActive ? 600 : 400, fontSize: '0.6rem' }}>
                {stage.label}
              </Typography>
            </Box>
          );
        })}
      </Box>

      {/* Live Logs */}
      <Typography variant="subtitle2" fontWeight="bold" sx={{ mt: 2, mb: 1 }}>Live Logs</Typography>
      <Box sx={{ bgcolor: '#F8FAFC', borderRadius: 1, p: 1, flex: 1, overflowY: 'auto', border: '1px solid #E2E8F0', maxHeight: 300 }}>
        <List dense disablePadding>
          {logs.length === 0 && (
            <ListItem>
              <Typography variant="caption" color="text.secondary">Waiting for logs...</Typography>
            </ListItem>
          )}
          {logs.map((log, idx) => (
            <React.Fragment key={idx}>
              <ListItem disableGutters sx={{ py: 0.5 }}>
                <Box sx={{ display: 'flex', gap: 2, width: '100%', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                  <Typography variant="caption" sx={{ minWidth: 60, color: 'text.secondary' }}>{log.time}</Typography>
                  <Chip
                    label={log.level}
                    size="small"
                    sx={{
                      minWidth: 50,
                      height: 16,
                      fontSize: '0.6rem',
                      bgcolor: log.level === 'SUCCESS' ? '#22C55E15' : log.level === 'ERROR' ? '#EF444415' : '#3B82F615',
                      color: log.level === 'SUCCESS' ? '#22C55E' : log.level === 'ERROR' ? '#EF4444' : '#3B82F6'
                    }}
                  />
                  <Typography variant="caption" sx={{ color: 'text.primary', flex: 1 }}>{log.message}</Typography>
                </Box>
              </ListItem>
              {idx < logs.length - 1 && <Divider component="li" />}
            </React.Fragment>
          ))}
        </List>
      </Box>
    </Paper>
  );
};

export default IngestionProgress;