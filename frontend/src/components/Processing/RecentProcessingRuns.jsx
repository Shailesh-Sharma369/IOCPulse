import React from 'react';
import { Paper, Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip, IconButton } from '@mui/material';
import { Eye } from 'lucide-react';

const RecentProcessingRuns = ({ jobs }) => {
  // Filter only processing jobs
  const processingJobs = jobs?.filter(job => job.type === 'processing') || [];

  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight="bold">Recent Processing Runs</Typography>
        <Typography variant="button" color="primary" sx={{ cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>View all runs →</Typography>
      </Box>

      <TableContainer>
        <Table sx={{ minWidth: 650 }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Run ID</TableCell>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Started At</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: 'text.secondary' }}>Articles Processed</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: 'text.secondary' }}>IOCs Extracted</TableCell>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Status</TableCell>
              <TableCell align="center" sx={{ fontWeight: 600, color: 'text.secondary' }}>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {processingJobs.length > 0 ? (
              processingJobs.map((job) => (
                <TableRow key={job.job_id} sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                  <TableCell component="th" scope="row">{job.job_id.slice(-6)}</TableCell>
                  <TableCell>{new Date(job.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">{job.result || 0}</TableCell>
                  <TableCell align="right">0</TableCell>
                  <TableCell>
                    <Chip 
                      label={job.status === 'completed' ? 'Completed' : job.status === 'failed' ? 'Failed' : 'Running'} 
                      size="small" 
                      color={job.status === 'completed' ? 'success' : job.status === 'failed' ? 'error' : 'default'} 
                      sx={{ fontWeight: 600 }}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <IconButton size="small"><Eye size={16} /></IconButton>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>No processing runs found.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default RecentProcessingRuns;