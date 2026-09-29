import React, { useState } from 'react';
import { 
  Box, Grid, Paper, Typography, TextField, InputAdornment, 
  Select, MenuItem, FormControl, Chip, IconButton, Table, 
  TableBody, TableCell, TableContainer, TableHead, TableRow,
  TablePagination, Button
} from '@mui/material';
import { Search, RefreshCw, FileText, FileCheck, Clock, AlertTriangle, Archive, Eye } from 'lucide-react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import dayjs from 'dayjs';
import { useDashboard } from '../hooks/useDashboard';
import { useRawArticles } from '../hooks/useArticles';
import ArticleDetailPanel from '../components/RawArticles/ArticleDetailPanel';

const RawArticles = () => {
  // Real data from backend
  const { data: dashboardData } = useDashboard();

  // UI State
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [searchQuery, setSearchQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [dateRange, setDateRange] = useState([null, null]); // Start and End
  const [selectedArticleId, setSelectedArticleId] = useState(null); // For side panel

  // Format API params from state
  const apiParams = {
    page: page + 1, // MUI TablePagination is 0-indexed, Backend is 1-indexed
    page_size: rowsPerPage,
    source_domain: sourceFilter !== 'All' ? sourceFilter : undefined,
    status: statusFilter !== 'All' ? statusFilter : undefined,
    date_from: dateRange[0] ? dateRange[0].toISOString() : undefined,
    date_to: dateRange[1] ? dateRange[1].toISOString() : undefined,
    search: searchQuery || undefined,
    sort_by: 'published_utc',
    sort_dir: 'DESC'
  };

  const { data: rawArticlesData, isLoading, refetch } = useRawArticles(apiParams);
  const articles = rawArticlesData?.data || [];
  const pagination = rawArticlesData?.pagination || { total: 0, page: 1, page_size: 10 };

  // KPI Cards (Strictly using real Dashboard data, excluding "Archived" which does not exist in API yet)
  const kpiData = [
    { title: 'Total Articles', value: dashboardData?.total_raw || 0, icon: FileText, color: '#3B82F6', sub: 'Total scrapped' },
    { title: 'Processed', value: dashboardData?.processed || 0, icon: FileCheck, color: '#22C55E', sub: `${Math.round(((dashboardData?.processed || 0) / (dashboardData?.total_raw || 1)) * 100)}%` },
    { title: 'Pending', value: dashboardData?.pending || 0, icon: Clock, color: '#F59E0B', sub: 'Waiting for AI' },
    { title: 'Failed', value: dashboardData?.failed || 0, icon: AlertTriangle, color: '#EF4444', sub: 'Processing errors' },
    { title: 'Archived', value: 0, icon: Archive, color: '#64748B', sub: 'Not in API yet' },
  ];

  // Helpers for status badge
  const getStatusChip = (status) => {
    const colors = {
      'PROCESSED': { bg: '#22C55E15', text: '#22C55E' },
      'PENDING': { bg: '#F59E0B15', text: '#F59E0B' },
      'FAILED': { bg: '#EF444415', text: '#EF4444' },
    };
    const style = colors[status] || { bg: '#64748B15', text: '#64748B' };
    return <Chip label={status} size="small" sx={{ bgcolor: style.bg, color: style.text, fontWeight: 600, borderRadius: 1 }} />;
  };

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight="bold">Raw Articles</Typography>
        <Typography variant="body2" color="text.secondary">Browse and inspect articles collected by Module 1 (Ingestion).</Typography>
      </Box>

      {/* KPI Cards */}
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
              <Typography variant="h5" fontWeight="bold">{kpi.value.toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary">{kpi.sub}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      {/* Filters Bar */}
      <Paper sx={{ p: 2, mb: 3, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
        <TextField 
          placeholder="Search title or content..." 
          size="small" 
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ flexGrow: 1, minWidth: 200 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search size={18} /></InputAdornment> }}
        />
        
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <Select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} displayEmpty>
            <MenuItem value="All">All Sources</MenuItem>
            {/* Note: Backend needs a sources endpoint to dynamically populate this */}
            <MenuItem value="CISA">CISA</MenuItem>
            <MenuItem value="BleepingComputer">BleepingComputer</MenuItem>
            <MenuItem value="The Hacker News">The Hacker News</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} displayEmpty>
            <MenuItem value="All">All Status</MenuItem>
            <MenuItem value="PENDING">Pending</MenuItem>
            <MenuItem value="PROCESSED">Processed</MenuItem>
            <MenuItem value="FAILED">Failed</MenuItem>
          </Select>
        </FormControl>

        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <DatePicker 
              label="From" 
              value={dateRange[0]} 
              onChange={(val) => setDateRange([val, dateRange[1]])} 
              slotProps={{ textField: { size: 'small', sx: { width: 130 } } }} 
            />
            <DatePicker 
              label="To" 
              value={dateRange[1]} 
              onChange={(val) => setDateRange([dateRange[0], val])} 
              slotProps={{ textField: { size: 'small', sx: { width: 130 } } }} 
            />
          </Box>
        </LocalizationProvider>

        <Button variant="outlined" startIcon={<RefreshCw size={16} />} onClick={() => refetch()} size="small" sx={{ borderColor: '#E2E8F0', color: '#475569' }}>
          Refresh
        </Button>
      </Paper>

      {/* Data Table */}
      <Paper>
        <TableContainer>
          <Table sx={{ minWidth: 750 }}>
            <TableHead sx={{ bgcolor: '#F1F5F9' }}>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Title</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Source</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Published At</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Collected At</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Status</TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: 'text.secondary' }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3 }}>Loading articles...</TableCell></TableRow>
              ) : articles.length === 0 ? (
                <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>No articles found.</TableCell></TableRow>
              ) : (
                articles.map((article) => (
                  <TableRow key={article.id} hover>
                    <TableCell padding="checkbox" />
                    <TableCell component="th" scope="row" sx={{ fontWeight: 500 }}>{article.title || 'Untitled'}</TableCell>
                    <TableCell>{article.source_domain}</TableCell>
                    <TableCell>{article.published_utc ? new Date(article.published_utc).toLocaleString() : '-'}</TableCell>
                    <TableCell>{article.retrieved_utc ? new Date(article.retrieved_utc).toLocaleString() : '-'}</TableCell>
                    <TableCell>{getStatusChip(article.status)}</TableCell>
                    <TableCell align="center">
                      <IconButton size="small" onClick={() => setSelectedArticleId(article.id)}>
                        <Eye size={16} />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
        
        {/* Pagination driven by real Backend pagination data */}
        <TablePagination
          rowsPerPageOptions={[10, 25, 50]}
          component="div"
          count={pagination.total || 0}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={(e, newPage) => setPage(newPage)}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
        />
      </Paper>

      {/* Selected Article Details Panel */}
      <ArticleDetailPanel 
        open={!!selectedArticleId} 
        onClose={() => setSelectedArticleId(null)} 
        articleId={selectedArticleId} 
      />
    </Box>
  );
};

export default RawArticles;