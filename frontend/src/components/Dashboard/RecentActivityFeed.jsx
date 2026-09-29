import React from 'react';
import { Box, Paper, Typography, List, ListItem, ListItemText, Chip } from '@mui/material';

const RecentActivityFeed = ({ activities = [] }) => {
  return (
    <Paper sx={{ p: 3, height: '100%', overflowY: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight="bold">Recent Pipeline Activity</Typography>
        <Typography variant="button" color="primary" sx={{ cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>View all</Typography>
      </Box>

      {activities.length === 0 ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: 150, alignItems: 'center' }}>
          <Typography variant="body2" color="text.secondary">No pipeline activities logged yet.</Typography>
          <Typography variant="caption" color="text.secondary">Run Ingestion or Processing to see real-time logs here.</Typography>
        </Box>
      ) : (
        <List>
          {activities.slice(0, 5).map((job) => (
            <ListItem key={job.job_id} divider sx={{ px: 0 }}>
              <ListItemText
                primary={<Typography variant="body2" fontWeight="bold">{job.type.toUpperCase()} JOB</Typography>}
                secondary={new Date(job.created_at).toLocaleString()}
              />
              <Chip
                label={job.status}
                size="small"
                color={job.status === 'completed' ? 'success' : job.status === 'failed' ? 'error' : 'primary'}
                sx={{ fontWeight: 600 }}
              />
            </ListItem>
          ))}
        </List>
      )}
    </Paper>
  );
};

export default RecentActivityFeed;