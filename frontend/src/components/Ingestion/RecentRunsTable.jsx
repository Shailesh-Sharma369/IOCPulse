import React from 'react';
import { Paper, Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip, IconButton } from '@mui/material';
import { Eye } from 'lucide-react';

const RecentRunsTable = ({ jobs }) => {
  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight="bold">Recent Ingestion Runs</Typography>
        <Typography variant="button" color="primary" sx={{ cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>View all runs →</Typography>
      </Box>

      <TableContainer>
        <Table sx={{ minWidth: 650 }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Run ID</TableCell>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Started At</TableCell>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Sources</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: 'text.secondary' }}>Articles Found</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: 'text.secondary' }}>Articles Extracted</TableCell>
              <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Status</TableCell>
              <TableCell align="center" sx={{ fontWeight: 600, color: 'text.secondary' }}>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs && jobs.length > 0 ? (
              jobs.map((job) => (
                <TableRow key={job.job_id} sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                  <TableCell component="th" scope="row">{job.job_id.slice(-6)}</TableCell>
                  <TableCell>{new Date(job.created_at).toLocaleString()}</TableCell>
                  <TableCell>18 / 28</TableCell>
                  <TableCell align="right">{job.status === 'completed' ? job.result || 0 : '-'}</TableCell>
                  <TableCell align="right">{job.status === 'completed' ? job.result || 0 : '-'}</TableCell>
                  <TableCell>
                    <Chip 
                      label={job.status === 'completed' ? 'Completed' : 'In Progress'} 
                      size="small" 
                      color={job.status === 'completed' ? 'success' : 'default'} 
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
                <TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>No ingestion runs found.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default RecentRunsTable;