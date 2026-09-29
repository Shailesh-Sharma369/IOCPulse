import React, { useState } from 'react';
import { Drawer, Box, Typography, IconButton, Divider, Chip, Button, Paper, CircularProgress } from '@mui/material';
import { X, ExternalLink } from 'lucide-react';
import { useRawArticle } from '../../hooks/useArticles';
import FullContentDialog from './FullContentDialog';

const ArticleDetailPanel = ({ open, onClose, articleId }) => {
  const { data: article, isLoading } = useRawArticle(articleId);
  const [fullContentOpen, setFullContentOpen] = useState(false);

  // Helper to strip HTML tags for a clean text preview
  const stripHtml = (html) => {
    if (!html) return '';
    const tmp = document.createElement('DIV');
    tmp.innerHTML = html;
    return tmp.textContent || tmp.innerText || '';
  };

  // Helper to calculate rough word count from HTML
  const calculateWordCount = (html) => {
    const text = stripHtml(html);
    return text.split(/\s+/).filter(word => word.length > 0).length;
  };

  if (!open) return null;

  return (
    <>
      <Drawer anchor="right" open={open} onClose={onClose} variant="temporary" PaperProps={{ sx: { width: { xs: '100%', sm: 450, md: 500 } } }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, borderBottom: '1px solid #E2E8F0' }}>
          <Typography variant="h6" fontWeight="bold">Article Details</Typography>
          <IconButton onClick={onClose}><X size={20} /></IconButton>
        </Box>

        <Box sx={{ p: 3, overflowY: 'auto', height: '100%' }}>
          {isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
          ) : article ? (
            <Box>
              <Typography variant="h6" fontWeight="bold" sx={{ mb: 2 }}>{article.title || 'Untitled Article'}</Typography>
              
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Source</Typography>
                  <Typography variant="body2" fontWeight={500}>{article.source_domain}</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Published At</Typography>
                  <Typography variant="body2">{article.published_utc ? new Date(article.published_utc).toLocaleString() : '-'}</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Collected At</Typography>
                  <Typography variant="body2">{article.retrieved_utc ? new Date(article.retrieved_utc).toLocaleString() : '-'}</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Status</Typography>
                  <Chip 
                    label={article.status || 'UNKNOWN'} 
                    size="small" 
                    sx={{ 
                      bgcolor: article.status === 'PROCESSED' ? '#22C55E15' : article.status === 'PENDING' ? '#F59E0B15' : '#EF444415',
                      color: article.status === 'PROCESSED' ? '#22C55E' : article.status === 'PENDING' ? '#F59E0B' : '#EF4444',
                      fontWeight: 600
                    }} 
                  />
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="body2" color="text.secondary">Original URL</Typography>
                  <Button 
                    variant="text" 
                    size="small" 
                    endIcon={<ExternalLink size={14} />}
                    href={article.source_url}
                    target="_blank"
                    rel="noreferrer"
                    sx={{ textTransform: 'none', color: '#2563EB' }}
                  >
                    {article.source_domain}
                  </Button>
                </Box>
              </Box>

              <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Content Preview</Typography>
              <Paper variant="outlined" sx={{ p: 2, mb: 3, bgcolor: '#F8FAFC', maxHeight: 200, overflowY: 'auto' }}>
                <Typography variant="body2" color="text.secondary">
                  {stripHtml(article.raw_html).substring(0, 1000) || 'No content preview available.'}
                  {stripHtml(article.raw_html).length > 1000 && '...'}
                </Typography>
              </Paper>

              <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Metadata</Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Content Type</Typography>
                  <Typography variant="body2">{article.source_domain ? 'Article' : '-'}</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Language</Typography>
                  <Typography variant="body2">English (Derived)</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Word Count</Typography>
                  <Typography variant="body2">{calculateWordCount(article.raw_html).toLocaleString()}</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">HTML Size</Typography>
                  <Typography variant="body2">{(article.raw_html?.length || 0).toLocaleString()} KB</Typography>
                </Box>
                <Divider />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">Extraction Method</Typography>
                  <Typography variant="body2">Not available in backend schema</Typography>
                </Box>
              </Box>

              <Box sx={{ display: 'flex', gap: 2, mt: 3 }}>
                <Button variant="outlined" fullWidth onClick={() => setFullContentOpen(true)}>View Full Content</Button>
                <Button variant="contained" fullWidth endIcon={<ExternalLink size={16} />} href={article.source_url} target="_blank" rel="noreferrer">Open Original</Button>
              </Box>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary" align="center">Failed to load article details.</Typography>
          )}
        </Box>
      </Drawer>

      <FullContentDialog 
        open={fullContentOpen} 
        onClose={() => setFullContentOpen(false)} 
        htmlContent={article?.raw_html} 
        title={article?.title} 
      />
    </>
  );
};

export default ArticleDetailPanel;