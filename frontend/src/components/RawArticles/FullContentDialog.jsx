import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography } from '@mui/material';

const FullContentDialog = ({ open, onClose, htmlContent, title }) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>{title || 'Full Article Content'}</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ bgcolor: '#F8FAFC', p: 2, borderRadius: 1, maxHeight: '60vh', overflowY: 'auto', border: '1px solid #E2E8F0' }}>
          {htmlContent ? (
            <div dangerouslySetInnerHTML={{ __html: htmlContent }} />
          ) : (
            <Typography variant="body2" color="text.secondary">No HTML content available.</Typography>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="contained">Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default FullContentDialog;